# 🏎️ F1 Championship Prediction Pipeline

> A production-grade Formula 1 data engineering platform that predicts the **2026 F1 World Championship** using the full modern data stack — Terraform, Kafka, Databricks, Delta Lake, dbt, Great Expectations, GitHub Actions, and scikit-learn.

---

## 📌 Project Overview

This project ingests 75 years of Formula 1 race data (1950–2026), processes it through a medallion architecture (Bronze → Silver → Gold), applies machine learning trained on historical regulation-change seasons, and produces a ranked prediction of the 2026 F1 World Championship standings.

**The central question this project answers:**
*Based on driver performance, constructor momentum, and historical regulation-change patterns — who wins the 2026 F1 World Championship?*

**Why 2026 specifically?**
The 2026 season introduces a major new engine formula and aerodynamic regulation overhaul — the most significant rule change since 2022. This reshuffles constructor performance dramatically, making the prediction genuinely interesting and the historical analog approach defensible.

**Live validation:**
The 2026 season is already underway. As races complete, the pipeline ingests new data, re-runs the model, and the dashboard shows predicted vs actual standings in real time.

---

## 🗂️ Order of Events — How the Pipeline Works

### Step 1 — Infrastructure Provisioning (Terraform)
Before a single line of data is touched, Terraform runs from the local terminal and creates all AWS infrastructure as code. Nothing is clicked manually in the AWS console.

```bash
cd terraform_code/
terraform init
terraform apply
```

**What gets created:**
- S3 bucket `f1-dp-vn` in `us-east-2` with versioning enabled and public access blocked
- IAM policy `f1-project-s3-policy-dev` scoped to the F1 bucket only
- Policy attached to existing IAM user

**Why Terraform over clicking the console?**
Anyone can clone this repo, run `terraform apply`, and have the exact same infrastructure in 30 seconds. That replaceability is the point.

---

### Step 2 — Secrets Management (Databricks CLI)
All credentials are stored as Databricks secrets — never hardcoded in any notebook or config file.

```bash
databricks secrets create-scope f1-secrets
databricks secrets put-secret f1-secrets AWS_ACCESS_KEY_ID --string-value ...
databricks secrets put-secret f1-secrets AWS_SECRET_ACCESS_KEY --string-value ...
databricks secrets put-secret f1-secrets KAGGLE_API_TOKEN --string-value ...
```

Every notebook pulls credentials at runtime via `dbutils.secrets.get("f1-secrets", "KEY")`. No credentials ever touch GitHub.

---

### Step 3 — Raw Data Landing (Kaggle → S3)
A Databricks notebook calls the Kaggle API and uploads all F1 CSVs to S3. Uses a **high watermark pattern** to handle incremental updates — only new rows are uploaded after each race weekend.

**First run (full load):**
```
Kaggle API → /tmp/ → S3: race_data/full_load/
                       race_events/full_load/
                       watermark/last_updated.json
```

**Subsequent runs (incremental):**
```
Kaggle API → /tmp/ → filter rows where date > last_updated
                   → S3: race_data/incremental/YYYYMMDD/
                          race_events/incremental/YYYYMMDD/
                          watermark/last_updated.json (updated)
```

**Why not re-upload everything every time?**
James Trotman's dataset is a full historical CSV — downloading 75 years of data to get 1 new race is wasteful. The watermark reads the `date` column from `races.csv` and filters all other CSVs by joining on `raceId`. Only genuinely new rows hit S3. Bronze MERGE handles deduplication downstream.

**S3 structure:**
```
f1-dp-vn/
├── race_data/
│   ├── full_load/        ← loaded once, 1950–2026 Race 1
│   └── incremental/      ← new rows only, after each race weekend
├── race_events/
│   ├── full_load/
│   └── incremental/
└── watermark/
    └── last_updated.json
```

---

### Step 4 — Bronze Layer (Batch Ingestion)
A Databricks notebook reads CSVs from S3 and writes Bronze Delta tables using incremental MERGE logic. Large tables are partitioned by `year` to eliminate full table scans.

**Tables created:**
`bronze_races`, `bronze_results`, `bronze_lap_times`, `bronze_pit_stops`, `bronze_qualifying`, `bronze_drivers`, `bronze_constructors`, `bronze_circuits`, `bronze_driver_standings`, `bronze_constructor_standings`, `bronze_constructor_results`, `bronze_status`, `bronze_seasons`, `bronze_sprint_results`, `bronze_safety_car`, `bronze_driver_fatalities`, `bronze_marshal_fatalities`

**MERGE logic:** Every run compares incoming S3 rows against existing Delta table rows on a composite key (e.g. `raceId + driverId` for results). Only inserts rows that don't already exist. Re-running Bronze after a new race adds only that race's rows — no duplicates, no full reloads.

**Partition strategy:** `year` on all large tables. F1 queries are almost always season-filtered. Partitioning by year means Spark scans only the relevant partition on `lap_times` which has millions of rows.

---

### Step 5 — Streaming Layer (Kafka + OpenF1 API)
During a live race weekend, a Kafka producer calls the OpenF1 API every 2-3 seconds and publishes real car telemetry for all 20 drivers to a Kafka topic. A Spark Structured Streaming consumer processes each message the moment it arrives.

```
OpenF1 API (one call = all 20 drivers)
  → kafka_producer.py
  → Kafka topic: f1-telemetry
  → Spark Structured Streaming consumer
  → bronze_lap_telemetry_stream (Delta, continuous)
```

**Rate limit strategy:** Free tier = 30 req/min. One session-level API call returns all 20 drivers simultaneously. At one call per 2-3 seconds that is ~20-30 calls/min — right at the limit. Weather endpoint polled every 15 seconds — barely touches quota.

**End-to-end latency:** ~3-5 seconds from track event to Delta table. Faster than the TV broadcast.

**Between races:** Producer stops, consumer idles. Zero cost, zero processing. Restarts when the next session begins — OpenF1 goes live ~30 minutes before each session.

**Why a real API instead of replaying a CSV?**
The producer is architecturally identical to what a production F1 data team actually runs. Swapping between live API and historical session replay requires changing one line. That replaceability is a sign of good architecture.

---

### Step 6 — Silver Layer (Cleaning + Great Expectations)
Silver reads all Bronze tables, joins and cleans them, and runs Great Expectations data quality checks before writing anything downstream. Bad data never reaches Gold.

**Great Expectations checks:**
- No nulls on `driverId`, `raceId`, `constructorId`
- Finishing positions between 1 and 20
- Row counts above expected threshold per table
- Referential integrity between `results` and `races`

**If any check fails:** Pipeline stops. Failure record written to `pipeline_logs` Delta table. Gold never runs.

**Structured logging:** Every notebook writes to `pipeline_logs` — start time, end time, rows read, rows written, rows failed, validation status. Full pipeline history queryable with SQL.

---

### Step 7 — Gold Layer (dbt)
The entire Gold layer is built in dbt SQL models — not PySpark. dbt handles dependency ordering automatically, runs built-in tests, and generates a browsable data dictionary and lineage graph.

**Models:**
- `fact_race_results` — one row per driver per race, all metrics joined
- `fact_lap_times` — lap-level performance data
- `dim_drivers` — driver biographical and career info
- `dim_constructors` — team information and history
- `dim_circuits` — circuit geography and characteristics

**dbt tests run automatically on every build:**
- Uniqueness on all primary keys
- Not-null on all required fields
- Referential integrity between facts and dims

```bash
dbt build        # runs all models + all tests
dbt docs serve   # generates lineage graph + data dictionary
```

**Why dbt over PySpark notebooks for Gold?**
SQL is more readable than PySpark for analytical transforms. dbt's dependency resolver means no manually sequenced notebook runs. Built-in tests catch data contract violations immediately. The lineage graph and auto-generated docs look and behave like a real data team built this.

---

### Step 8 — ML / AI Layer (scikit-learn)
A Databricks ML notebook reads Gold fact tables, engineers features, and trains a Gradient Boosting Regressor to predict 2026 championship points per driver.

**Features:**
- Average points per race (last 3 seasons)
- DNF rate
- Qualifying vs race pace delta
- Constructor momentum (team performance trend, last 4 races)
- Consistency score (std dev of finishing positions)
- Weather conditions (from OpenF1, 2023+)

**Why train on regulation-change seasons only?**
Training on 2014, 2017, and 2022 — seasons where major regulation changes reshuffled the constructor order — provides the most relevant signal for 2026. Training on all 75 years would dilute this with stable-regulation data that is less predictive of a regulation-change year.

**Output:** `gold_championship_prediction_2026` — predicted points and ranking per driver, plus feature importance scores.

---

### Step 9 — Orchestration (Databricks Workflows)
Databricks Workflows runs all batch jobs in dependency order with retry logic and a quality gate.

```
Bronze Batch → Silver Transform → [GE Quality Gate] → dbt Gold Build → ML Prediction
```

- Silver fails → retry twice → email alert on third failure
- GE validation fails → Gold never runs
- Kafka consumer runs as a separate continuous streaming job

---

### Step 10 — CI/CD (GitHub Actions)
Every push to GitHub automatically triggers checks — no manual runs needed.

**On every push:**
- `flake8` Python linting
- `dbt compile` — catches SQL syntax errors before they hit the cluster
- `dbt test` — runs schema tests against dev schema

**On merge to main:**
- Full Great Expectations validation suite

Green checkmarks on every commit. Red X means fix before merging.

---

### Step 11 — Dashboard (Databricks)
Five visualizations built on Gold dbt tables and the ML prediction table:

1. **Historical Championship Trends** — points per driver/constructor across seasons
2. **Circuit Performance Analysis** — average finishing position by driver by track type
3. **Live Lap Telemetry** — real-time streaming from `bronze_lap_telemetry_stream`
4. **2026 Championship Prediction** — ranked drivers with predicted points
5. **Pit Stop Strategy Impact** — correlation between pit stop timing and race outcome

---

### Step 12 — 2025 Data Enrichment (Post-Build)
After the initial build, 2025 data is loaded through the existing Bronze pipeline with zero architectural changes. The model re-runs, the prediction updates, and the dashboard shows the delta between 2024-based and 2025-based predictions — documenting which drivers gained or lost predicted standing based on their 2025 performance.

---

## 📂 Data Sources

| Name | Author | Why | Layer | Updates |
|---|---|---|---|---|
| Formula 1 Race Data | James Trotman | Primary historical batch — 14 CSVs, full Ergast schema, through 2026 Race 1 | Bronze batch | Monthly after each race |
| Formula 1 Race Events | James Trotman | SC, VSC, red flag deployments per race. Adds incident context affecting points and strategy | Bronze batch | Monthly after each race |
| OpenF1 API — Telemetry | OpenF1 | 3.7Hz car telemetry for all 20 drivers. Kafka streaming source, one call = all drivers | Kafka streaming | Live during sessions (2023+) |
| OpenF1 API — Weather | OpenF1 | Track/air temp, humidity, rainfall, wind per session. ML features for lap time and strategy modeling | Bronze batch + ML | Live during sessions (2023+) |

> **OpenF1 rate limit (free tier):** 30 req/min. Handled by session-level batching — one call returns all 20 drivers. At one call per 2-3 seconds during a live race, this stays well within limits.

---

## 🛠️ Tech Stack

| Tool | Layer | Why |
|---|---|---|
| **Terraform** | Infrastructure | All AWS resources as code — nothing clicked manually |
| **AWS S3** | Raw Storage | Raw landing zone with watermark-based incremental loading |
| **Databricks CLI** | Secrets | Credentials stored as secrets, never hardcoded |
| **Apache Kafka** | Streaming | Live F1 telemetry via OpenF1 API — real API call pattern, not CSV replay |
| **Databricks + Delta Lake** | Compute + Storage | Medallion architecture, ACID tables, MERGE upserts, time travel |
| **Great Expectations** | Data Quality | Validation gate at Silver — bad data never reaches Gold |
| **dbt** | Gold Layer | SQL models with auto-dependency ordering, built-in testing, lineage graphs |
| **scikit-learn** | ML | Gradient Boosting model trained on regulation-change seasons |
| **Databricks Workflows** | Orchestration | Dependency ordering, retry logic, quality gate |
| **GitHub Actions** | CI/CD | Auto-lints and tests on every push |
| **Databricks Dashboard** | Serving | Five visualizations on Gold tables and ML predictions |

---

## 📁 Repository Structure

```
formula-one-project/
├── terraform_code/
│   ├── main.tf              # Provider config
│   ├── s3.tf                # S3 bucket — f1-dp-vn
│   ├── iam.tf               # IAM policy scoped to F1 bucket
│   ├── variables.tf         # aws_region, project_name, environment
│   └── outputs.tf           # Bucket name and ARN
├── configs/
│   └── credentials          # Pulls all secrets from Databricks secrets (gitignored)
├── scripts/
│   ├── 0_setup/
│   │   └── kaggle_to_s3     # Kaggle → S3 with watermark incremental logic
│   ├── 1_bronze/
│   │   ├── bronze_batch     # S3 → Bronze Delta tables (MERGE, partitioned by year)
│   │   └── kafka_producer   # OpenF1 API → Kafka topic
│   ├── 2_silver/
│   │   └── silver_transform # Bronze → Silver with Great Expectations validation
│   ├── 3_gold/
│   │   └── dbt_f1/          # dbt SQL models — facts and dims
│   ├── 4_ml/
│   │   └── championship_prediction  # Feature engineering + GBR + prediction output
│   └── 5_streaming/
│       └── kafka_consumer   # Kafka → bronze_lap_telemetry_stream (Spark Streaming)
├── .github/
│   └── workflows/
│       ├── on_push.yml      # flake8 + dbt compile + dbt test
│       └── on_merge.yml     # Full GE validation suite
└── README.md
```

---

## 🧠 Design Decisions

**Why a high watermark pattern for S3 instead of full re-upload?**
Kaggle only provides full dataset downloads — no incremental API. Re-uploading 75 years of data to get one new race is wasteful. The watermark reads the latest `date` from `races.csv`, stores it in `watermark/last_updated.json` in S3, and on subsequent runs only uploads rows where `date > last_updated`. In production this would be replaced with a CDC feed from the source system — noted as a known limitation in the architecture.

**Why Databricks secrets over a credentials file?**
A `credentials.py` with hardcoded keys is the simplest approach but creates risk — one accidental `git add` and credentials are public. Databricks secrets are write-only, never readable after storage, and referenced at runtime via `dbutils.secrets.get()`. No credentials ever touch the codebase or GitHub.

**Why dbt for Gold instead of PySpark notebooks?**
SQL is more readable than PySpark for analytical transformations. dbt handles dependency ordering automatically. Built-in testing catches data contract violations on every build. The auto-generated lineage graph and data dictionary look and behave like a real data team built this — because that's exactly how real data teams build Gold layers.

**Why Great Expectations over custom checks?**
`if df.null_count() > 0: raise Exception` works but signals tutorial-level thinking. Great Expectations is an industry-recognized tool used in production data teams. It produces shareable HTML validation reports and signals professional ecosystem awareness. At the internship level, tool recognition matters.

**Why OpenF1 API for streaming instead of replaying a CSV?**
A real API call pattern is architecturally identical to what a production F1 data pipeline actually does. The producer is swappable between live API and historical replay by changing one line. That replaceability is a sign of good architecture. OpenF1 is free, requires no authentication, and delivers data at ~3 second latency — faster than the TV broadcast.

**Why train on regulation-change seasons only?**
2026 is a major regulation-change year. Training on 2014, 2017, and 2022 — the three most comparable regulation-change seasons — provides the most relevant historical signal. Training on all 75 years dilutes this with stable-regulation data that is less predictive of a year where constructor performance shuffles dramatically.

**Why partition by year on large tables?**
F1 analytics queries are almost always season-filtered. Partitioning `lap_times` and `results` by year means Spark scans only the relevant partition. On `lap_times` which has millions of rows, this eliminates full table scans on the most common query pattern.

---

## ⚙️ How to Run

### Prerequisites
- AWS account with IAM credentials
- Terraform installed
- Databricks workspace with CLI configured
- Kaggle account and API token
- Python 3.9+

### Step 1 — Provision Infrastructure
```bash
cd terraform_code/
terraform init
terraform apply
```

### Step 2 — Store Secrets
```bash
databricks secrets create-scope f1-secrets
databricks secrets put-secret f1-secrets AWS_ACCESS_KEY_ID --string-value ...
databricks secrets put-secret f1-secrets AWS_SECRET_ACCESS_KEY --string-value ...
databricks secrets put-secret f1-secrets KAGGLE_API_TOKEN --string-value ...
```

### Step 3 — Run Kaggle → S3 Ingestion
Run `scripts/0_setup/kaggle_to_s3` notebook in Databricks.
First run does a full load. Every subsequent run is incremental.

### Step 4 — Run Bronze
Run `scripts/1_bronze/bronze_batch` notebook in Databricks.

### Step 5 — Start Kafka Streaming (during race weekends)
Run `scripts/1_bronze/kafka_producer` and `scripts/5_streaming/kafka_consumer` as continuous Databricks jobs.

### Step 6 — Run Silver
Run `scripts/2_silver/silver_transform` notebook. Great Expectations runs automatically.

### Step 7 — Run dbt Gold
```bash
cd scripts/3_gold/dbt_f1/
dbt build
dbt docs serve
```

### Step 8 — Run ML Prediction
Run `scripts/4_ml/championship_prediction` notebook in Databricks.

### Step 9 — View Dashboard
Open Databricks Dashboard. All visualizations populate from Gold Delta tables automatically.

---

## 📊 Key Results

| Predicted Rank | Driver | Constructor | Predicted Points (2026) |
|---|---|---|---|
| 1 | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD |

*Populated after ML model runs on complete 2024 + 2025 data.*

---

## 🔗 Resources

- [Kaggle — James Trotman F1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)
- [Kaggle — James Trotman F1 Race Events](https://www.kaggle.com/datasets/jtrotman/formula-1-race-events)
- [OpenF1 API Docs](https://openf1.org)
- [dbt-databricks Docs](https://docs.getdbt.com/docs/core/connect-data-platform/databricks-setup)
- [Great Expectations Docs](https://docs.greatexpectations.io)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Spark Structured Streaming + Kafka](https://spark.apache.org/docs/latest/structured-streaming-kafka-integration.html)

---

## 👤 Author

**Vedansh Nikum**
MIS @ Penn State Smeal College of Business
[LinkedIn](#) · [GitHub](https://github.com/vedanshnikum)