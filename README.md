# F1 Championship Prediction Pipeline

A production-grade data engineering platform that ingests 75 years of Formula 1 race data, processes it through a full medallion architecture, predicts the **2026 F1 World Championship**, and generates a natural language analyst breakdown powered by an LLM.

**Built with:** Terraform · AWS S3 · Apache Kafka · Databricks · Delta Lake · Great Expectations · dbt · scikit-learn · LLM Analyst · GitHub Actions

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
OpenF1 API ──► Kafka ──► Spark Streaming ──► Bronze Delta Tables (GE + custom checks)
                                                       │
                                      Silver (cleaned) (GE + custom checks)
                                                        │
                                                Gold (dbt models)
                                                        │
                            ┌───────────────────────────┼───────────────────────────┐
                            │                           │                           │
                    Historical Dashboard         Live Race Dashboard         2026 Prediction
                    (1950 – 2026 data)          (real-time telemetry)    (ML model + LLM analyst)
```
---

## Phases

### Phase 0 — Infrastructure & Secrets

Before any data is touched, all AWS infrastructure is provisioned using Terraform from the local terminal — nothing is clicked manually in the AWS console. This creates the S3 bucket used as the raw landing zone, an IAM policy scoped specifically to that bucket, and attaches it to the project user. The goal is full reproducibility: anyone can clone the repo and have identical infrastructure running in under a minute.

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

19 tables are ingested in total, covering race results, lap times, pit stops, qualifying, driver and constructor standings, circuits, safety car events, and historical fatality records. The schema is passed in as a Databricks widget so the same notebook runs against dev or prod without any code changes.

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

Time columns are stored as millisecond integers (lap times, pit stop durations) or `HH:mm:ss` strings (wall clock session times). Date and session time columns in `races` are kept as strings in Silver so Gold can freely concat them into proper `TimestampType` columns.

---

### Phase 5 — Gold Layer

The entire Gold layer is built in dbt SQL models rather than PySpark notebooks. SQL is more readable for analytical transforms, dbt handles dependency ordering between models automatically, built-in tests run on every build, and the auto-generated lineage graph and data dictionary reflect how production data teams actually build Gold layers.

Session timestamps are constructed in Gold by concatenating Silver's separate date and time string columns — `fp1_date` + `fp1_time` → `fp1_timestamp` as a proper `TimestampType`.

dbt models and tests are documented in [`docs/gold.md`](./docs/gold.md) as they are finalized.

---

### Phase 6 — ML Prediction + LLM Analyst

A Databricks notebook reads Gold fact tables, engineers features, and trains a Gradient Boosting Regressor to predict 2026 championship points per driver.

Features include average points per race over the last 3 seasons, DNF rate, qualifying versus race pace delta, constructor momentum over the last 4 races, consistency score based on finishing position variance, and weather conditions from OpenF1 for sessions from 2023 onwards.

The model is trained on regulation-change seasons only — 2014, 2017, and 2022. These are the three most structurally comparable seasons to 2026, where major rule changes caused significant constructor performance reshuffles. Training on all 75 years would dilute this signal with stable-regulation data that is not predictive of a reshuffle year.

The ML output — ranked predicted standings with feature importance scores — is then passed to an LLM which generates a natural language race analyst style breakdown of each prediction. Rather than a table of numbers, the prediction dashboard surfaces a written explanation of why each driver is ranked where they are, grounded entirely in the model's actual output and historical data.

---

### Phase 7 — Orchestration

All batch jobs run in dependency order via Databricks Workflows. Bronze must succeed before Silver runs. Silver must pass the data quality gate before Gold builds. Gold must complete before the ML prediction runs. Silver failures retry twice before triggering an email alert. The Kafka consumer runs as a separate continuous streaming job independent of the batch pipeline.

---

### Phase 8 — CI/CD

Every push to GitHub triggers Python linting, dbt SQL compilation to catch syntax errors before they reach the cluster, and dbt schema tests against the dev schema. Every merge to main runs the full Great Expectations validation suite. Green checks on every commit; red means fix before merging.

---

### Phase 9 — Dashboards

Three dashboards built on Gold dbt tables and the ML prediction output.

**Historical Analysis** covers championship trends, circuit performance breakdowns, pit stop strategy impact, and driver and constructor comparisons across all 75 years of data from 1950 through 2026.

**Live Race** shows real-time lap telemetry from the continuously updating streaming Delta table. The dashboard auto-refreshes on a short interval with a few seconds of end-to-end latency from track event to screen.

**2026 Prediction** shows the ranked driver standings with predicted points, the feature importance breakdown explaining each prediction, a natural language analyst commentary generated by the LLM, and a predicted vs. actual comparison that updates as the 2026 season progresses.

---

## Architecture Decisions

Detailed decisions documented in [`docs/decisions.md`](./docs/decisions.md).

---

## Tech Stack

| Tool | Layer | Role |
|---|---|---|
| Terraform | Infrastructure | AWS resources as code |
| AWS S3 | Raw Storage | Raw landing zone for Kaggle CSVs |
| Databricks CLI | Secrets | Runtime credential management |
| Apache Kafka | Streaming | Decoupled telemetry ingestion from OpenF1 |
| Databricks + Delta Lake | Compute + Storage | Medallion architecture, MERGE upserts, ACID tables |
| Great Expectations + custom checks | Data Quality | Validation gate at Silver and Gold |
| dbt | Gold Layer | SQL models, dependency resolution, built-in testing, lineage |
| scikit-learn | ML | Gradient Boosting trained on regulation-change seasons |
| LLM API | Prediction Analyst | Natural language breakdown of ML prediction output |
| Databricks Workflows | Orchestration | Dependency ordering, retries, quality gate |
| GitHub Actions | CI/CD | Lint and test on every push |
| Databricks Dashboards | Serving | Historical, live, and prediction views |

---

## Repository Structure

```
formula-one-project/
├── configs/
│   └── credentials
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
│       └── 2_silver/
│           └── silver_transforms
├── terraform/
│   ├── iam.tf
│   ├── main.tf
│   ├── outputs.tf
│   ├── s3.tf
│   └── variables.tf
└── utils/
    ├── general_transforms_utils
    ├── great_expectations_utils
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

**Prerequisites:** AWS account with IAM credentials · Terraform installed · Databricks workspace with CLI configured · Kaggle account and API token · Python 3.9+

Provision infrastructure by running Terraform from the `terraform/` directory. Store AWS and Kaggle credentials as Databricks secrets under the `f1-secrets` scope. Run the ingestion, Bronze, Silver, Gold, and ML notebooks in order from the Databricks workspace. Start the Kafka producer and consumer as continuous jobs during race weekends. Use `dbt build` and `dbt docs serve` from the Gold dbt directory to build the Gold layer and view the lineage graph. Detailed setup notes are in [`docs/`](./docs/).

---

## Resources

- [Kaggle — James Trotman F1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)
- [Kaggle — James Trotman F1 Race Events](https://www.kaggle.com/datasets/jtrotman/formula-1-race-events)

---

**Vedansh Nikum** — MIS @ Penn State Smeal College of Business · [GitHub](https://github.com/vedanshnikum)
