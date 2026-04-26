# F1 Championship Prediction Pipeline

A production-grade data engineering platform that ingests 75 years of Formula 1 race data, processes it through a full medallion architecture, predicts the **2026 F1 World Championship**, and generates a natural language analyst breakdown powered by an LLM.

**Built with:** Terraform · AWS S3 · Apache Kafka · Databricks · Delta Lake · dbt · scikit-learn · LLM Analyst · Power BI · Streamlit · GitHub Actions

> Detailed architecture decisions, data quality observations, and phase-by-phase notes are documented in [`docs/`](./docs/).

---

## The Question This Project Answers

*Based on driver performance, constructor momentum, and historical regulation-change patterns — who wins the 2026 F1 World Championship?*

2026 introduces the most significant engine formula and aerodynamic overhaul since 2022. Constructor performance reshuffles dramatically in these years, making historical analog modeling genuinely defensible — and the prediction genuinely interesting.

The 2026 season is already underway. As races complete, the pipeline ingests new data, reruns the model, and the dashboard shows predicted vs. actual standings in real time.

---

## Architecture Overview
```
Kaggle API ──────────────────────────────────► S3 (raw landing)
                                                    │
OpenF1 API ──► Kafka ──► Spark Streaming ──► Bronze Delta Tables
                                                    │
                                                Silver (cleaned)
                                                    │
                                                Gold (dbt models)
                                                    │
                    ┌───────────────────────────────┼───────────────────────────┐
                    │                               │                           │
                    Historical Dashboard            Live Race Dashboard         2026 Prediction
                    Power BI (1950–2026)          Streamlit (real-time)    Streamlit (ML + LLM)
```
---

## Phases

### Phase 0 — Infrastructure & Secrets

All AWS infrastructure is provisioned using Terraform from the local terminal — nothing is clicked manually in the AWS console. This creates the S3 bucket used as the raw landing zone, an IAM policy scoped specifically to that bucket, and attaches it to the project user. The goal is full reproducibility: anyone can clone the repo and have identical infrastructure running in under a minute.

All credentials — AWS keys and the Kaggle API token — are stored as Databricks secrets and never appear in any notebook or file. Every notebook pulls them at runtime. Nothing sensitive ever touches GitHub.

---

### Phase 1 — Raw Ingestion

A Databricks notebook calls the Kaggle API and streams both F1 datasets directly into memory as zip files, extracts each CSV, and uploads them to S3 without writing anything to disk. S3 is used here purely as a raw landing zone. Deduplication is handled downstream in Bronze via MERGE logic, so re-uploading the full dataset each run is safe and keeps the ingestion layer simple.

Two Kaggle datasets are used: the primary historical race data covering the full Ergast schema through 2026, and a race events dataset capturing safety car, virtual safety car, and red flag deployments per race.

---

### Phase 2 — Bronze Layer

The Bronze layer reads every CSV from S3 and writes it into Delta tables using a skip-if-exists pattern — tables that already exist are not reprocessed. New files are ingested using MERGE on composite keys so re-running after a new race appends only new rows without duplicating existing data. All files across both S3 paths are processed in parallel using a thread pool.

Column names are sanitized on ingestion — special characters and spaces are stripped and everything is lowercased so downstream queries are consistent regardless of what the source CSV headers look like.

Large tables like lap times and results are partitioned by year. F1 queries are almost always filtered to a specific season, so partitioning eliminates full table scans on the tables with millions of rows.

19 tables are ingested in total, covering race results, lap times, pit stops, qualifying, driver and constructor standings, circuits, safety car events, and historical fatality records.

---

### Phase 3 — Streaming Layer

During a live race weekend, a Kafka producer polls the OpenF1 API every 2-3 seconds and publishes car telemetry for all 20 drivers to a Kafka topic. A Spark Structured Streaming consumer processes each message as it arrives and writes to a continuously updating Delta table. End-to-end latency is roughly 3-5 seconds from the track event to the Delta table — faster than the TV broadcast.

The OpenF1 free tier allows 30 requests per minute. One API call returns all 20 drivers simultaneously, so polling every 2-3 seconds stays within that limit. The weather endpoint is polled every 15 seconds separately.

Kafka is kept in the architecture deliberately. The producer/consumer pattern is identical to what a production F1 data team actually runs, and swapping between a live API call and a historical session replay requires changing one line. Between race weekends the producer stops and the consumer idles at zero cost.

---

### Phase 4 — Silver Layer

Silver reads all 19 Bronze tables, applies a two-pass transform pipeline, and writes clean Delta tables to the Silver schema. Bad data never reaches Gold.

**Transform Architecture**

Transforms are split across three utility notebooks in `scripts/utils/`:

- `helper_utils` — shared primitives: `send_to_schema`, `convert_time_to_ms` (native Spark, no UDF), `clean_wall_clock`
- `general_transforms_utils` — runs on every table: URL removal, string trimming, status/nationality mapping, date casting, integer casting
- `specific_transforms_utils` — per-table logic dispatched via a dictionary map

**General transforms** handle what is consistent across all 19 tables — dropping `url` columns, trimming whitespace, mapping abbreviated codes (`R` → `Retired`, `USA` → `United States`) and null sentinels (`\N` → NULL), casting date columns to `DateType`, and casting numeric columns with `try_cast` to safely handle Ergast's `\N` null sentinel.

**Specific transforms** handle what is unique to individual tables:

| Table | Transforms |
|---|---|
| `race_data_races` | Drop `year`, clean wall clock time columns to `HH:mm:ss` string |
| `race_data_results` | `try_cast` fastestlap/fastestlapspeed, convert fastestlaptime to ms, drop `time` |
| `race_data_pit_stops` | Convert duration to ms, clean wall clock `time`, cast milliseconds |
| `race_data_lap_times` | Drop redundant `time` string |
| `race_data_qualifying` | Convert q1/q2/q3 lap times to milliseconds |
| `race_data_sprint_results` | Convert fastestlaptime to ms, cast fastestlap/rank, drop `time` |
| `race_data_drivers` | Cast `dob` to `DateType` |
| `race_data_seasons` | Cast `year` integer to `DateType` |
| `race_events_safety_cars` | Normalize cause values: accident variants → `Accident(s)`, stranded car variants → `Stranded Car(s)`, debris variants → `Debris` |
| `race_events_fatal_accidents_drivers` | Parse historical 2-digit dates (`10/24/71` → `1971-10-24`) using LEGACY time parser |
| `race_events_fatal_accidents_marshalls` | Same date fix as above |

---

### Phase 5 — Gold Layer

The entire Gold layer is built in dbt SQL models running locally in VSCode and connecting to Databricks remotely. SQL is more readable for analytical transforms, dbt handles dependency ordering between models automatically, and the auto-generated lineage graph reflects how production data teams actually build Gold layers.

**13 models across 4 layers:**

| Layer | Models |
|---|---|
| Dimensions | `dim_circuits`, `dim_drivers`, `dim_teams`, `dim_races` |
| Facts | `fact_results`, `fact_sprint_results`, `fact_qualifying`, `fact_lap_times`, `fact_pit_stops` |
| Standings | `standings_drivers`, `standings_teams` |
| Events | `event_race_incidents`, `event_fatal_accidents` |

Key design decisions:
- `race_key` — a derived natural identifier (`2023_British_Grand_Prix`) built once in `dim_races` and propagated to all fact and event tables, giving the event tables a proper join key to the main schema
- `dnf_flag` — boolean derived from `positiontext`, critical ML feature for DNF rate analysis
- `positions_gained` — `grid - positionorder`, one of the most common F1 performance metrics
- `pit_stop_count` and `total_pit_time_ms` — aggregated from `fact_pit_stops` and joined into `fact_results`
- Safety cars and red flags combined into `event_race_incidents` with an `incident_type` column
- Driver and marshal fatal accidents combined into `event_fatal_accidents` with a `type` column

---

### Phase 6 — Dashboards

**Historical Analysis** built in Power BI connecting directly to Gold dbt tables. Four pages covering overview statistics, driver and team performance records, season-by-season championship story, and safety and incident history. Covers all 75 years of data from 1950 through 2026.

**Live Race** built in Streamlit, reading from the continuously updating streaming Delta table. Auto-refreshes with a few seconds of end-to-end latency from track event to screen.

**2026 Prediction** built in Streamlit, showing ranked driver standings with predicted points, feature importance breakdown, natural language LLM analyst commentary, and predicted vs. actual comparison updating as the 2026 season progresses.

---

### Phase 7 — ML Prediction + LLM Analyst

A Databricks notebook reads Gold fact tables, engineers features, and trains a Gradient Boosting Regressor to predict 2026 championship points per driver.

Features include average points per race over the last 3 seasons, DNF rate, qualifying versus race pace delta, constructor momentum over the last 4 races, consistency score based on finishing position variance, and weather conditions from OpenF1 for sessions from 2023 onwards.

The model is trained on regulation-change seasons only — 2014, 2017, and 2022 — the three most structurally comparable seasons to 2026.

The ML output is passed to an LLM which generates a natural language race analyst style breakdown of each prediction, grounded entirely in the model's actual output and historical data.

---

### Phase 8 — Orchestration

All batch jobs run in dependency order via Databricks Workflows. Bronze must succeed before Silver runs. Silver must pass before Gold builds. Gold must complete before the ML prediction runs. The Kafka consumer runs as a separate continuous streaming job independent of the batch pipeline.

---

### Phase 9 — CI/CD

Every push to GitHub triggers Python linting and dbt SQL compilation to catch syntax errors before they reach the cluster. Every merge to main runs the full validation suite. Green checks on every commit; red means fix before merging.

---

## Tech Stack

| Tool | Layer | Role |
|---|---|---|
| Terraform | Infrastructure | AWS resources as code |
| AWS S3 | Raw Storage | Raw landing zone for Kaggle CSVs |
| Databricks CLI | Secrets | Runtime credential management |
| Apache Kafka | Streaming | Decoupled telemetry ingestion from OpenF1 |
| Databricks + Delta Lake | Compute + Storage | Medallion architecture, MERGE upserts, ACID tables |
| dbt (local) | Gold Layer | SQL models, dependency resolution, lineage |
| scikit-learn | ML | Gradient Boosting trained on regulation-change seasons |
| LLM API | Prediction Analyst | Natural language breakdown of ML prediction output |
| Databricks Workflows | Orchestration | Dependency ordering, retries |
| GitHub Actions | CI/CD | Lint and compile on every push |
| Power BI | Historical Dashboard | Business intelligence on 75 years of F1 data |
| Streamlit | Live + Prediction Dashboard | Real-time telemetry and ML prediction display |

---

## Repository Structure
```
formula-one-project/
├── configs/
│   └── credentials
├── docs/
├── scripts/
│   ├── exploration/
│   │   ├── main_explore
│   │   └── quality_checks
│   └── pipeline/
│       ├── 0_setup/
│       │   ├── catalog_setup
│       │   └── kaggle_to_s3
│       ├── 1_bronze/
│       │   └── full_load_ingest
│       ├── 2_silver/
│       │   └── silver_transforms
│       └── 3_gold/
│           └── dbt_f1/
│               ├── models/
│               │   ├── dimensions/
│               │   ├── facts/
│               │   ├── standings/
│               │   └── events/
│               ├── dbt_project.yml
│               └── sources.yml
├── terraform/
│   ├── iam.tf
│   ├── main.tf
│   ├── outputs.tf
│   ├── s3.tf
│   └── variables.tf
└── utils/
├── general_transforms_utils
├── helper_utils
└── specific_transforms_utils
```
---

## Data Sources

| Dataset | Source | Used For | Updates |
|---|---|---|---|
| Formula 1 Race Data | James Trotman (Kaggle) | Primary historical batch — full Ergast schema through 2026 | After each race |
| Formula 1 Race Events | James Trotman (Kaggle) | Safety car, VSC, red flag deployments per race | After each race |
| OpenF1 API — Telemetry | OpenF1 | 3.7Hz car telemetry, all 20 drivers, Kafka streaming source | Live during sessions |
| OpenF1 API — Weather | OpenF1 | Track/air temp, humidity, rainfall, wind — ML features | Live during sessions |

---

## 2026 Predictions

| Rank | Driver | Constructor | Predicted Points |
|---|---|---|---|
| — | — | — | — |

*Populated after ML model runs on complete 2025 data.*

---

## How to Run

**Prerequisites:** AWS account with IAM credentials · Terraform installed · Databricks workspace with CLI configured · Kaggle account and API token · Python 3.11+

Provision infrastructure by running Terraform from the `terraform/` directory. Store AWS and Kaggle credentials as Databricks secrets under the `f1-secrets` scope. Run the ingestion, Bronze, and Silver notebooks in order from the Databricks workspace. From the `scripts/pipeline/3_gold/dbt_f1/` directory, run `dbt run` to build the Gold layer. Start the Kafka producer and consumer as continuous jobs during race weekends. Run `dbt docs serve` to view the lineage graph.

---

## Resources

- [Kaggle — James Trotman F1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)
- [Kaggle — James Trotman F1 Race Events](https://www.kaggle.com/datasets/jtrotman/formula-1-race-events)
- [OpenF1 API](https://openf1.org/)

---

**Vedansh Nikum** — MIS @ Penn State Smeal College of Business · [GitHub](https://github.com/vedanshnikum)