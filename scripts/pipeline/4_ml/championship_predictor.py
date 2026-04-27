# scripts/pipeline/4_ml/championship_predictor.py

import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import cross_val_score
from databricks.sdk import WorkspaceClient

WAREHOUSE_ID = "528397b2a432db12"
client = WorkspaceClient()

def query(sql):
    response = client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        wait_timeout="50s"
    )
    cols = [c.name for c in response.manifest.schema.columns]
    rows = response.result.data_array or []
    return pd.DataFrame(rows, columns=cols)

print("Pulling features from Gold...")

# ── 1. Final season standings per driver per year ──────────────────────────────
standings = query("""
    SELECT
        driver_id,
        driver_full_name,
        year,
        MAX(points)   AS final_points,
        MIN(position) AS final_position,
        MAX(wins)     AS season_wins
    FROM formone.gold.standings_drivers
    GROUP BY driver_id, driver_full_name, year
""")

# ── 2. Race performance per driver per year ────────────────────────────────────
race_perf = query("""
    SELECT
        driver_id,
        year,
        AVG(CAST(finish_position AS DOUBLE))   AS avg_finish_pos,
        AVG(CAST(grid_position AS DOUBLE))     AS avg_grid_pos,
        SUM(CASE WHEN dnf_flag = true THEN 1 ELSE 0 END) / COUNT(*) AS dnf_rate,
        AVG(CAST(positions_gained AS DOUBLE))  AS avg_positions_gained,
        AVG(CAST(fastest_lap_speed AS DOUBLE)) AS avg_fastest_lap_speed,
        COUNT(*)                               AS races_entered
    FROM formone.gold.fact_results
    WHERE finish_position IS NOT NULL
    GROUP BY driver_id, year
""")

# ── 3. Qualifying performance per driver per year ──────────────────────────────
quali = query("""
    SELECT
        driver_id,
        year,
        AVG(CAST(qualifying_position AS DOUBLE)) AS avg_quali_pos
    FROM formone.gold.fact_qualifying
    WHERE qualifying_position IS NOT NULL
    GROUP BY driver_id, year
""")

# ── 4. Lap time consistency ────────────────────────────────────────────────────
consistency = query("""
    SELECT
        driver_id,
        year,
        STDDEV(CAST(lap_time_ms AS DOUBLE)) AS lap_time_stddev,
        AVG(CAST(lap_time_ms AS DOUBLE))    AS avg_lap_time_ms
    FROM formone.gold.fact_lap_times
    WHERE lap_time_ms IS NOT NULL
      AND lap_time_ms > 60000
      AND lap_time_ms < 300000
    GROUP BY driver_id, year
""")

# ── 5. Constructor strength per driver per year ────────────────────────────────
constructor = query("""
    SELECT
        fr.driver_id,
        fr.year,
        AVG(CAST(st.position AS DOUBLE)) AS constructor_standing
    FROM formone.gold.fact_results fr
    JOIN formone.gold.standings_teams st
        ON fr.team_id = st.team_id AND fr.year = st.year
    GROUP BY fr.driver_id, fr.year
""")

# ── 6. Sprint points per driver per year ──────────────────────────────────────
sprint = query("""
    SELECT
        driver_id,
        year,
        SUM(CAST(points AS DOUBLE)) AS sprint_points,
        COUNT(*)                    AS sprint_races
    FROM formone.gold.fact_sprint_results
    WHERE dnf_flag = false
    GROUP BY driver_id, year
""")

# ── 7. IMPROVEMENT 1: Races remaining in 2026 ──────────────────────────────────
races_info = query("""
    SELECT
        COUNT(*) AS total_races,
        SUM(CASE WHEN date <= CURRENT_DATE THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN date >  CURRENT_DATE THEN 1 ELSE 0 END) AS remaining
    FROM formone.silver.race_data_races
    WHERE YEAR(date) = 2026
""")

total_2026   = int(races_info["total_races"].iloc[0])
completed_2026 = int(races_info["completed"].iloc[0])
remaining_2026 = int(races_info["remaining"].iloc[0])
season_completion = completed_2026 / total_2026 if total_2026 > 0 else 1.0

print(f"\n2026 season: {completed_2026}/{total_2026} races complete, {remaining_2026} remaining")
print(f"Season completion: {season_completion:.1%}")

# ── Merge all features ─────────────────────────────────────────────────────────
print("\nMerging features...")

df = standings.merge(race_perf,    on=["driver_id", "year"], how="left")
df = df.merge(quali,               on=["driver_id", "year"], how="left")
df = df.merge(consistency,         on=["driver_id", "year"], how="left")
df = df.merge(constructor,         on=["driver_id", "year"], how="left")
df = df.merge(sprint,              on=["driver_id", "year"], how="left")


# ── Type conversions ───────────────────────────────────────────────────────────
num_cols = [
    "final_points", "final_position", "season_wins",
    "avg_finish_pos", "avg_grid_pos", "dnf_rate",
    "avg_positions_gained", "avg_fastest_lap_speed", "races_entered",
    "avg_quali_pos", "lap_time_stddev", "avg_lap_time_ms",
    "constructor_standing", "sprint_points", "sprint_races"
]
for col in num_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["year"] = pd.to_numeric(df["year"], errors="coerce")

# ── Feature engineering ────────────────────────────────────────────────────────
# Cap + log-scale wins to suppress single-season dominance
df["season_wins"] = df["season_wins"].clip(upper=10)
df["season_wins"] = np.log1p(df["season_wins"])

# Points per race (comparable across seasons with different race counts)
df["points_per_race"] = df["final_points"] / df["races_entered"].replace(0, np.nan)

# Fill sprint NaN with 0
df["sprint_points"] = df["sprint_points"].fillna(0)
df["sprint_races"]  = df["sprint_races"].fillna(0)

# Label: 1 if this driver won the championship that year
df["champion"] = (df["final_position"] == 1).astype(int)

# ── IMPROVEMENT 3: Train separate models per regulation era ───────────────────
# Era 0: 2000-2013 (V10/V8 naturally aspirated)
# Era 1: 2014-2021 (V6 hybrid)
# Era 2: 2022-2025 (ground effect)
# Era 3: 2026+     (new regs) — we use era 2 model to predict since it's closest
def assign_era(year):
    if year <= 2013:
        return 0
    elif year <= 2021:
        return 1
    elif year <= 2025:
        return 2
    else:
        return 3

df["era"] = df["year"].apply(assign_era)

features = [
    "points_per_race",
    "season_wins",
    "avg_quali_pos",
    "avg_finish_pos",
    "avg_grid_pos",
    "dnf_rate",
    "avg_positions_gained",
    "avg_fastest_lap_speed",
    "races_entered",
    "lap_time_stddev",
    "constructor_standing",
    "sprint_points"
]

df = df[df["year"] >= 2000].dropna(subset=[
    "final_points", "season_wins", "avg_quali_pos",
    "avg_finish_pos", "dnf_rate", "constructor_standing"
])

print(f"Total training data: {len(df)} rows across {df['year'].nunique()} seasons")
print(f"Championships labeled: {df['champion'].sum()}")

# ── Train one model per era ────────────────────────────────────────────────────
era_models = {}
for era_id in [0, 1, 2]:
    era_df = df[df["era"] == era_id]
    if len(era_df) < 20:
        continue
    X = era_df[features].fillna(era_df[features].median())
    y = era_df["champion"]
    m = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=15,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss"
    )
    m.fit(X, y)
    scores = cross_val_score(m, X, y, cv=5, scoring="roc_auc")
    print(f"Era {era_id} model AUC: {scores.mean():.3f} (+/- {scores.std():.3f})  [{len(era_df)} rows]")
    era_models[era_id] = {"model": m, "median": era_df[features].median()}

# 2026 uses the era 2 model (ground effect / most recent regulation era)
active_model  = era_models[2]["model"]
active_median = era_models[2]["median"]

# ── IMPROVEMENT 4: Decayed weighted average across seasons ────────────────────
season_weights = {
    2026: 0.35,
    2025: 0.25,
    2024: 0.18,
    2023: 0.12,
    2022: 0.07,
    2021: 0.03
}

dfs = []
for yr, w in season_weights.items():
    d = df[df["year"] == yr].copy()
    if len(d) == 0:
        continue
    for f in features:
        d[f] = pd.to_numeric(d[f], errors="coerce") * w
    dfs.append(d)

recent = pd.concat(dfs)
df_pred = recent.groupby(["driver_id", "driver_full_name"])[features].sum().reset_index()

# 2026 grid — exact names matching gold table
grid_2026 = [
    "Max Verstappen", "Lando Norris", "Charles Leclerc", "Lewis Hamilton",
    "George Russell", "Oscar Piastri", "Carlos Sainz", "Fernando Alonso",
    "Lance Stroll", "Pierre Gasly", "Esteban Ocon", "Oliver Bearman",
    "Alexander Albon", "Yuki Tsunoda", "Nico Hülkenberg", "Andrea Kimi Antonelli",
    "Isack Hadjar", "Liam Lawson", "Franco Colapinto", "Arvid Lindblad",
    "Gabriel Bortoleto", "Sergio Pérez", "Valtteri Bottas"
]

df_pred = df_pred[df_pred["driver_full_name"].isin(grid_2026)].copy()

matched = df_pred["driver_full_name"].tolist()
missing = [d for d in grid_2026 if d not in matched]
print(f"\nMatched {len(matched)} drivers, missing {len(missing)}: {missing}")

midfield_avg = df_pred[features].median()
if missing:
    new_rows = pd.DataFrame({
        "driver_full_name": missing,
        **{f: midfield_avg[f] for f in features}
    })
    df_pred = pd.concat([df_pred, new_rows], ignore_index=True)

X_pred = df_pred[features].fillna(active_median)
probs   = active_model.predict_proba(X_pred)[:, 1]

# ── IMPROVEMENT 2: Confidence interval scaling by season completion ────────────
# The closer to end of season, the tighter the confidence intervals
# If only 3 races remain, leader is very likely to win — scale up their probability
# If 10+ races remain, compress toward mean — more uncertainty
uncertainty_factor = 1 - season_completion  # 0 = season over, 1 = season just started

# Blend raw probs toward uniform distribution based on remaining uncertainty
n_drivers = len(probs)
uniform = np.ones(n_drivers) / n_drivers
adjusted_probs = (1 - uncertainty_factor) * probs + uncertainty_factor * uniform * probs.sum()

df_pred["raw_prob"]      = probs
df_pred["adjusted_prob"] = adjusted_probs
df_pred["confidence_pct"] = (adjusted_probs / adjusted_probs.sum() * 100).round(1)
df_pred = df_pred.sort_values("confidence_pct", ascending=False)

print(f"\n🏆 2026 F1 WORLD CHAMPIONSHIP PREDICTIONS")
print(f"   (Based on {completed_2026}/{total_2026} races — {remaining_2026} races remaining)")
print("=" * 65)
for _, row in df_pred.iterrows():
    bar = "█" * int(row["confidence_pct"] / 1.5)
    print(f"{row['driver_full_name']:<25} {row['confidence_pct']:>5.1f}%  {bar}")

print("\n📊 Feature Importance (Era 2 / Ground Effect model):")
for feat, imp in sorted(zip(features, active_model.feature_importances_),
                        key=lambda x: x[1], reverse=True):
    print(f"  {feat:<28} {imp:.3f}")

print(f"\n📅 Season context: {season_completion:.1%} complete, uncertainty factor: {uncertainty_factor:.2f}")