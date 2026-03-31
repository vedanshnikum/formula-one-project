# 🏎️ F1 Championship Prediction Pipeline

> A production-grade Formula 1 data engineering platform that predicts the **2026 F1 World Championship** using the full modern data stack — Terraform, Kafka, Databricks, Delta Lake, dbt, Great Expectations, GitHub Actions, and scikit-learn.

---

## 📌 Project Overview

This project ingests 75 years of Formula 1 race data (1950–2025), processes it through a medallion architecture (Bronze → Silver → Gold), applies machine learning trained on historical regulation-change seasons, and produces a ranked prediction of the 2026 F1 World Championship standings.

**The central question this project answers:**  
*Based on driver performance, constructor momentum, and historical regulation-change patterns — who wins the 2026 F1 World Championship?*

**Why 2026 specifically?**  
The 2026 season introduces a major new engine formula and aerodynamic regulation overhaul — the most significant rule change since 2022. This reshuffles constructor performance dramatically, making the prediction genuinely interesting and the historical analog approach defensible.

---

## 🗂️ Order of Events — How the Pipeline Works

This section explains exactly what happens from start to finish, in order.

### Step 1 — Infrastructure Provisioning (Terraform)
Before a single line of data is touched, Terraform runs from the local terminal and creates all AWS infrastructure as code — S3 buckets for raw landing, processed data, and logs, plus IAM roles and policies that allow Databricks to access S3. Nothing is clicked manually in the AWS console.

```bash
terraform init
terraform apply
```

**Output:** Three S3 buckets created, IAM policy attached, Databricks access configured.

---

### Step 2 — Raw Data Landing (Kaggle → S3)
A Python ingestion script calls the Kaggle API and uploads all 14 F1 CSVs directly to the S3 raw landing bucket. This is the Bronze source of truth — raw files exactly as downloaded, never modified.

```
kaggle_to_s3.py → s3://f1-raw-landing/
```

**Files landed:**
`circuits.csv`, `constructors.csv`, `constructor_results.csv`, `constructor_standings.csv`, `drivers.csv`, `driver_standings.csv`, `lap_times.csv`, `pit_stops.csv`, `qualifying.csv`, `races.csv`, `results.csv`, `seasons.csv`, `sprint_results.csv`, `status.csv`

---

### Step 3 — Bronze Layer (Batch Ingestion)
A Databricks notebook reads all 14 CSVs from S3 and writes them into Bronze Delta tables using incremental MERGE logic. Large tables (`lap_times`, `results`) are partitioned by `year` to eliminate full table scans on common query patterns.

```
S3 raw CSVs → bronze_circuits, bronze_drivers, bronze_constructors,
               bronze_races, bronze_results, bronze_lap_times,
               bronze_pit_stops, bronze_qualifying, bronze_status,
               bronze_sprint_results
```

**Partition strategy:** `year` column on all large tables. Query patterns are almost always season-filtered — partitioning by year eliminates full scans on `lap_times` which has millions of rows.

---

### Step 4 — Streaming Layer (Kafka)
Simultaneously with batch ingestion, a Kafka producer script reads `lap_times.csv` row by row with a small delay between each message, simulating live race telemetry arriving in real time. A Spark Structured Streaming consumer reads from the Kafka topic and writes micro-batches into a separate Bronze streaming Delta table.

```
kafka_producer.py → Kafka topic: f1-lap-telemetry
                 → kafka_consumer_streaming.py
                 → bronze_lap_telemetry_stream (Delta, streaming)
```

This simulates what a real F1 data pipeline looks like during a live race weekend — telemetry arriving continuously per driver per lap.

---

### Step 5 — Silver Layer (Cleaning + Validation)
A Silver transformation notebook reads all Bronze tables, performs joins and cleaning, and runs **Great Expectations** data quality checks before writing any data downstream. If validation fails, the pipeline stops completely and writes a failure record to `pipeline_logs` — bad data never reaches Gold.

**Great Expectations checks include:**
- No nulls on `driverId`, `raceId`, `constructorId`
- Finishing positions between 1 and 20
- Row counts above threshold per table
- Referential integrity between `results` and `races`

**Structured logging:** Every notebook writes a record to `pipeline_logs` capturing start time, end time, rows read, rows written, rows failed, and validation status. The entire pipeline history is queryable with SQL.

```
Bronze tables → [Great Expectations validation] → Silver tables
                                               → pipeline_logs (Delta)
```

---

### Step 6 — Gold Layer (dbt)
The entire Gold layer is built in **dbt SQL models** — not PySpark notebooks. dbt reads from Silver tables, builds fact and dimension tables in dependency order automatically, and tests them.

**dbt models:**
- `fact_race_results` — one row per driver per race, all metrics joined
- `fact_lap_times` — lap-level performance data
- `dim_drivers` — driver biographical and career info
- `dim_constructors` — team information and history
- `dim_circuits` — circuit geography and characteristics

**dbt tests run automatically:**
- Uniqueness on all primary keys
- Not-null on all required fields
- Referential integrity between facts and dims

```bash
dbt build      # runs all models + tests
dbt docs serve # generates browsable data dictionary + lineage graph
```

---

### Step 7 — ML / AI Layer (scikit-learn)
A Databricks ML notebook reads from Gold fact tables, engineers features, and trains a **Gradient Boosting Regressor** to predict 2026 championship points per driver.

**Features used:**
- Average points per race (last 3 seasons)
- DNF (did not finish) rate
- Qualifying vs race pace delta (how much a driver gains/loses from grid to finish)
- Constructor momentum (team performance trend over last 4 races)
- Consistency score (standard deviation of finishing positions)

**Why train on regulation-change seasons?**  
The model is trained specifically on 2014, 2017, and 2022 — seasons where major regulation changes reshuffled the constructor order dramatically, the same dynamic expected in 2026.

**Output:** `gold_championship_prediction_2026` Delta table with predicted points and ranking per driver, plus feature importance showing which factors most influenced each prediction.

---

### Step 8 — Orchestration (Databricks Workflows)
A Databricks Workflow ties all batch jobs together with proper dependency ordering, retry logic, and a data quality gate.

**Workflow order:**
```
Bronze Batch → Silver Transform → [GE Quality Gate] → dbt Gold Build → ML Prediction
```

- If Silver fails → retry twice → email alert on third failure
- If Great Expectations validation fails → Gold never runs
- Kafka consumer runs as a separate continuous streaming job

---

### Step 9 — CI/CD (GitHub Actions)
Every push to GitHub automatically triggers:

**On push (`.github/workflows/on_push.yml`):**
- `flake8` Python linting
- `dbt compile` — catches SQL syntax errors
- `dbt test` — runs schema tests against dev schema

**On merge to main (`.github/workflows/on_merge.yml`):**
- Full Great Expectations validation suite

Green checkmarks on every commit signal that the codebase meets quality standards before anything runs in production.

---

### Step 10 — Dashboard (Databricks)
A Databricks Dashboard consumes Gold dbt models and the ML prediction table, producing five visualizations:

1. **Historical Championship Trends** — points per driver/constructor across seasons
2. **Circuit Performance Analysis** — average finishing position by driver by track type
3. **Live Lap Telemetry Feed** — real-time streaming visualization from `bronze_lap_telemetry_stream`
4. **2026 Championship Prediction** — ranked drivers with predicted points and confidence ranges
5. **Pit Stop Strategy Impact** — correlation between pit stop timing, strategy, and race outcome

---

### Step 11 — 2025 Data Enrichment (Post-Build)
After the initial project is complete, 2025 season data is loaded through the existing Bronze pipeline with zero architectural changes. The ML model re-runs with 2025 data included, and the 2026 prediction updates. The delta between the 2024-based and 2025-based predictions is documented in the dashboard — showing which drivers gained or lost predicted standing based on their 2025 performance.

---

## 📂 Data Sources

| Dataset | Source | Author | Files | Coverage |
|---|---|---|---|---|
| Formula 1 World Championship | Kaggle | Vopani | 14 CSVs | 1950–2024 |
| Formula 1 Race Data | Kaggle | James Trotman | 14 CSVs | 2025 season |
| Live lap telemetry | Kafka simulation | — | lap_times.csv replayed | Real-time sim |
| 2026 early results | Manual pull | — | — | Post-build validation |

---

## 🛠️ Tech Stack

| Tool | Layer | Why This Tool |
|---|---|---|
| **Terraform** | Infrastructure | Provisions all AWS resources as code — nothing clicked manually |
| **AWS S3** | Storage | Raw landing zone and Delta Lake storage |
| **Apache Kafka** | Streaming | Simulates live F1 lap telemetry — architecturally identical to real telemetry ingestion |
| **Databricks** | Compute | Unified platform for batch transforms, streaming, and ML |
| **Delta Lake** | Storage Format | ACID tables, time travel, and efficient upserts via MERGE |
| **dbt** | Gold Layer | SQL models with auto-dependency ordering, built-in testing, and lineage graphs |
| **Great Expectations** | Data Quality | Validates data at Silver — pipeline stops on bad data before it reaches Gold |
| **GitHub Actions** | CI/CD | Auto-lints and tests code on every push — green checkmarks on every commit |
| **scikit-learn** | ML / AI | Gradient Boosting model predicts 2026 championship — trained on regulation-change seasons |
| **Databricks Dashboard** | Serving | Visualizes analytics and prediction outputs |

---

## 📁 Repository Structure

```
f1-championship-pipeline/
├── terraform/
│   ├── main.tf              # Provider config
│   ├── s3.tf                # S3 bucket definitions
│   ├── iam.tf               # IAM roles and policies
│   └── variables.tf         # Input variables
├── ingestion/
│   ├── kaggle_to_s3.py      # Pulls Kaggle CSVs → S3
│   ├── bronze_batch.py      # S3 → Bronze Delta tables with MERGE
│   ├── kafka_producer.py    # Reads lap_times.csv → Kafka topic
│   └── kafka_consumer_streaming.py  # Kafka → bronze_lap_telemetry_stream
├── silver/
│   ├── silver_transform.py  # Bronze → Silver with joins and cleaning
│   └── great_expectations/  # GE expectation suites and checkpoints
├── dbt_f1/
│   ├── models/
│   │   ├── facts/
│   │   │   ├── fact_race_results.sql
│   │   │   └── fact_lap_times.sql
│   │   └── dims/
│   │       ├── dim_drivers.sql
│   │       ├── dim_constructors.sql
│   │       └── dim_circuits.sql
│   ├── tests/
│   └── schema.yml           # dbt tests — uniqueness, not-null, referential integrity
├── ml/
│   └── championship_prediction.py   # Feature engineering + GBR model + prediction output
├── workflows/
│   └── pipeline_workflow.json       # Databricks Workflow definition
├── dashboard/
│   └── screenshots/         # Dashboard screenshots for portfolio
├── .github/
│   └── workflows/
│       ├── on_push.yml      # flake8 + dbt compile + dbt test
│       └── on_merge.yml     # Full GE validation suite
└── README.md
```

---

## 🧠 Design Decisions

**Why dbt for Gold instead of PySpark notebooks?**  
SQL is more readable than PySpark for analytical transformations. dbt handles dependency ordering automatically — no need to manually sequence notebook runs. Built-in testing catches data contract violations immediately. dbt docs generates a browsable data dictionary and lineage graph automatically. A Gold layer in dbt looks and behaves like it was built by a real data team.

**Why Great Expectations over custom checks?**  
Writing `if df.null_count() > 0: raise Exception` works but signals tutorial-level thinking. Great Expectations is an industry-recognized tool used in production data teams. It produces shareable HTML validation reports, integrates naturally with pipeline orchestration, and signals professional ecosystem awareness to any interviewer. At the junior/internship level, tool recognition matters.

**Why Kafka simulation instead of a live API?**  
The architecture is identical to real telemetry ingestion — a producer publishes messages, a consumer processes them via Spark Structured Streaming. There are no API rate limits, no costs, and no dependency on an external service being available. The producer script is swappable for a real Ergast API poller in under 30 minutes — and that replaceability is itself a sign of good architecture.

**Why partition by year on large tables?**  
Query patterns in F1 analytics are almost always season-filtered — "show me Verstappen's lap times in 2023" not "show me all lap times ever." Partitioning `lap_times` and `results` by year means Spark only scans the relevant partition, eliminating full table scans on tables with millions of rows.

**Why train on regulation-change seasons (2014, 2017, 2022)?**  
The 2026 season introduces a fundamental engine and aerodynamic regulation change — the most significant reshuffling event in the sport. Training on 2014 (V6 hybrid introduction), 2017 (aero overhaul), and 2022 (ground effect return) provides the most relevant historical signal for how constructor performance shifts in regulation-change years. Training on all seasons would dilute this signal with stable-regulation data that is less predictive of 2026 outcomes.

**Why Gradient Boosting over a simpler model?**  
Linear regression would underfit — the relationship between features and championship outcome is non-linear (a driver's DNF rate matters much more at the front of the grid than mid-field). Gradient boosting handles mixed feature types, is robust to outliers (one anomalous season), and produces interpretable feature importance scores. It requires no deep mathematical understanding to implement correctly with sklearn.

---

## ⚙️ How to Run This Project

### Prerequisites
- AWS account with IAM user credentials
- Terraform installed (`terraform -version`)
- Databricks workspace
- Kaggle account and API token (`~/.kaggle/kaggle.json`)
- Python 3.9+
- dbt-databricks (`pip install dbt-databricks`)

### Step 1 — Provision Infrastructure
```bash
cd terraform/
terraform init
terraform apply
```

### Step 2 — Configure Databricks ↔ S3 Connection
Add your AWS access key and secret to Databricks cluster config or secrets:
```
fs.s3a.access.key = <your-iam-access-key>
fs.s3a.secret.key = <your-iam-secret-key>
```

### Step 3 — Run Ingestion
```bash
python ingestion/kaggle_to_s3.py
```
Then run `ingestion/bronze_batch.py` as a Databricks notebook.

### Step 4 — Start Kafka Streaming
```bash
python ingestion/kafka_producer.py
```
Run `ingestion/kafka_consumer_streaming.py` as a continuous Databricks streaming job.

### Step 5 — Run Silver Transformation
Run `silver/silver_transform.py` as a Databricks notebook. Great Expectations checks run automatically.

### Step 6 — Run dbt Gold Models
```bash
cd dbt_f1/
dbt build
dbt docs generate
dbt docs serve
```

### Step 7 — Run ML Prediction
Run `ml/championship_prediction.py` as a Databricks notebook.

### Step 8 — View Dashboard
Open the Databricks Dashboard in your workspace. All visualizations populate from Gold Delta tables automatically.

---

## 📊 Key Results

| Predicted Rank | Driver | Constructor | Predicted Points (2026) |
|---|---|---|---|
| 1 | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD |

*Results populated after model runs on complete 2024 + 2025 data.*

---

## 🔗 Resources

- [Kaggle — Vopani F1 1950–2024](https://www.kaggle.com/datasets/rohanrao/formula-1-world-championship-1950-2020)
- [Kaggle — James Trotman 2025](https://www.kaggle.com/datasets/jamestrotman/formula-1-race-data)
- [dbt-databricks Docs](https://docs.getdbt.com/docs/core/connect-data-platform/databricks-setup)
- [Great Expectations Docs](https://docs.greatexpectations.io)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Spark Structured Streaming + Kafka](https://spark.apache.org/docs/latest/structured-streaming-kafka-integration.html)

---

## 👤 Author

**Vedansh Nikum**  
MIS @ Penn State Smeal College of Business  
[LinkedIn](#) · [GitHub](#)
