# TfL Delay Analysis — Project Plan

## Phase 1: The Engine (Connecting to the Data)
**Goal:** Prove you can pull live and historical data using Python.

- [x] **1.1 Workspace Setup:** Create the project folder and install Python tools (requests, pandas).
  - *Done:* `TFL_project` folder created; Anaconda Python has pandas 3.0.3 and requests 2.34.2. PowerShell execution policy fixed so the Anaconda environment loads in new terminals.
- [x] **1.2 "Hello World" API Call:** Write a 15-line Python script that successfully prints the live TfL status to your screen.
  - *Done:* `test_tfl.py` called the TfL API and printed the status of every Tube line. (Removed in 5.3; superseded by `collect_tfl_status.py`.)
- [x] **1.3 Save to a File (Live Collector):** Upgrade the script so it saves that live status into a local CSV file or database.
  - TfL does not publish historical line status, so this script is how we build our **real** history.
  - *Done:* `collect_tfl_status.py` appends a timestamped (UTC) snapshot of every Tube line's status, severity code and disruption reason to `data/tfl_live_status.csv`. Each run is logged to `logs/collector.log`.
  - *Done (moved to the cloud, 17 Oct 2026):* a **GitHub Actions** workflow (`.github/workflows/collect_tfl_status.yml`) runs the collector every 15 minutes, 24/7, and commits each snapshot to `data/tfl_live_status.csv` in the public repo **github.com/AJC-mdx/tfl-delay-analytics** ("git scraping"). `python refresh.py` now starts with `git pull` to fetch the latest data.
  - *Reliability fix (20 Oct 2026):* GitHub's own schedule only ran ~6 of ~96 times a day, so **cron-job.org** now triggers the workflow every 15 minutes through GitHub's `workflow_dispatch` API (a fine-grained token limited to this repo with Actions read/write, stored only in cron-job.org). The GitHub schedule stays on as a backup; the workflow's concurrency setting prevents overlapping runs. ⚠️ **The token has an expiry date. Renew it in GitHub and cron-job.org before it expires**, or collection stops.
  - *Why:* the original Windows Task Scheduler task (14–17 Oct) only ran while the laptop was awake, about 00:00–03:00, when the Tube is closed, so it captured no service hours. That task is now **disabled** (not deleted) so the two collectors don't conflict. Real service-hours data starts 17 Oct 2026.
- [x] **1.4 The Backfill (Mock Data for Now):** Historical TfL status data is not available, so we use mock data to build and test the rest of the pipeline while the live collector gathers real data.
  - *Done:*
    - `get_weather.py` downloaded hourly London weather from Open-Meteo for 1–7 Jan 2024. (Later extended to cover all mock and live dates; see 2.4 and Phase 4.)
    - `generate_tfl_history.py` creates **simulated** TfL status history based on the weather → `data/tfl_history_sample.csv`.
    - `data/StationFootfall_2024.csv` downloaded.
  - *Later:* once enough real data has been collected, swap the mock TfL history for the collected data (and download weather for the matching dates). Keep the mock and real data clearly labelled so the dashboard and model never mix them by accident.

## Phase 2: The Warehouse (SQL Transformations)
**Goal:** Show you can organize messy data and write analytical queries.

- [x] **2.1 Database Setup:** Load your downloaded historical data and your live API data into a local SQL database (like DuckDB or SQLite).
  - *Done:* Chose **DuckDB** (installed duckdb 1.5.6). `load_database.py` loads each CSV unchanged into a `raw_` table in `tfl.duckdb`: `raw_weather`, `raw_tfl_mock`, `raw_tfl_live`, `raw_footfall`. Re-run it any time to pick up new live rows.
- [x] **2.2 Data Cleaning SQL:** Write a query to clean up missing values and standardize the timestamps.
  - *Done:* Layered approach, `raw_` tables → cleaned `stg_` views, all built by running `load_database.py`:
    - **Reference tables** (`data/reference/`): `ref_status_severity` maps every TfL severity code to a category (`good`, `delay`, `suspended`, `planned_works`, `service_closed`, `other`), an `is_disruption` flag and a priority rank. `ref_tube_lines` lists the 11 Tube line IDs and names.
    - **`stg_tfl_status`** (`sql/01_stg_tfl_status.sql`): mock and live data in one shape with a `data_source` column ('mock' / 'live'). Mock line names converted to TfL IDs, severity codes added to mock data, "None"/empty reasons → NULL, UTC timestamps plus `hour_utc` (for the weather join) and `observed_at_london` (handles GMT/BST, for rush-hour analysis). Keeps only the worst status per line per snapshot.
    - **`stg_weather`** (`sql/02_stg_weather.sql`): clear names and units, UTC and London hour, negative values → NULL.
    - **`stg_footfall`** (`sql/03_stg_footfall.sql`): `20240101` → real date, `total_taps` added. Note: includes non-Tube stations (DLR, Overground, etc.).
    - **Quality checks** (`sql/checks.sql`): 9 checks (duplicates, missing timestamps, unknown lines/severity codes, Service Closed counted as disruption, bad weather/footfall values). All pass; the script reports any failures.
  - **Rules to carry into 2.3:**
    - Use `is_disruption` (not "anything that isn't Good Service") to define a delay.
    - Don't fill gaps in live data. If two consecutive snapshots for a line are more than ~30 minutes apart (laptop off/asleep), treat it as a gap, not one long delay.
    - Always filter or split by `data_source` so mock and live data are never mixed in results.
  - ⚠️ **Do not count overnight closures as delays.** *(Handled: "Service Closed" is category `service_closed` with `is_disruption = false`, and a quality check enforces it.)* The collector records "Service Closed" (severity 20) when the Tube shuts each night. Exclude it (or flag it as "closed", not "delayed") so it doesn't inflate delay counts or durations in 2.3, the dashboard, or the ML model. Note: the Night Tube runs on some lines on Friday/Saturday nights, so don't just drop fixed hours — filter on the status itself.
- [x] **2.3 The "Interview Query":** Write an advanced SQL query using Window Functions (like LAG or LEAD) to calculate the exact duration of train delays.
  - *Done:* `sql/04_fct_delay_episodes.sql` builds the `fct_delay_episodes` view: one row per delay episode (an unbroken run of disrupted snapshots on one line) with start/end time, `duration_minutes`, worst status and first reason. Solved as a "gaps and islands" problem: `LAG`/`LEAD` → flag new runs → running `SUM() OVER` to number runs → `GROUP BY` run.
  - Handles: delays that get worse (one episode, worst status kept), data gaps (episode stops, `end_confirmed = false`), delays running into the overnight closure (ends at "Service Closed"), and delays still going (`is_ongoing = true`).
  - Durations are accurate to the snapshot interval (15 min live, 1 hour mock). For averages like Mean Time To Recovery, use only `end_confirmed = true` episodes.
  - Two new quality checks: no negative durations, no overlapping episodes on the same line.
- [x] **2.4 Weather Join:** Write a query that joins the weather data to the TfL data to see how rain impacts delays.
  - *Done:* `get_weather.py` now downloads weather for every date we have TfL data for (mock week + live collection) into `data/london_weather.csv`, using Open-Meteo's archive plus its forecast service for the last 7 days (the archive runs ~5 days behind). **To update everything, run `python refresh.py`**: it runs `get_weather.py` then `load_database.py` and prints a summary (if the weather download fails, it still rebuilds the database with the existing weather).  - *Done:* `sql/05_fct_line_hour.sql` → `fct_line_hour`: one row per line per hour with `is_running` (closed hours excluded from rates), `new_delay_started`, `disrupted_share` and weather. Three rain columns because of timing (Open-Meteo rain at 10:00 = rain from 09:00–10:00): `rain_this_hour_mm` (same time as the delays), `rain_prev_hour_mm` and `rain_last_3h_mm` (known in advance, so the only ones usable for prediction in Phase 4).
  - *Done:* `sql/06_rpt_weather_impact.sql` → `rpt_weather_impact`: delay rate and relative risk by rain band (Dry / Light / Moderate / Heavy) and wind band, with sample sizes.
  - *Validated on mock data:* the generator's built-in rule (5% → 15% delay chance when rain > 0.5 mm or wind > 25 km/h) was recovered as 5.6% → 14.7%, with the jumps at exactly the right thresholds. This proves the query works; it is **not** a real finding. Real conclusions come from live data.
  - Three new quality checks: running hours all have weather, no delays start in closed hours, no delays lost when grouping by hour.
  - *Optional later:* a statistical test (e.g. chi-square in Python) to show whether a rain effect is real or chance. Small bands (e.g. 36 "very windy" line-hours) are unreliable on their own.

## Phase 3: The Analyst Deliverable (Power BI)
**Goal:** Build a commercial-grade dashboard you can immediately put on your CV.

- [x] **3.1 Connect Power BI:** Hook Power BI Desktop up to your local database.
  - *Approach:* the warehouse exports a ready-made "serving layer" of Parquet files to `powerbi/data/`, which Power BI loads natively (no driver needed, no file locks with `refresh.py`, works for anyone who downloads the repo). The export only runs if every quality check passes.
  - *Done (data side):*
    - Star schema tables: `fct_line_hour`, `fct_delay_episodes`, `dim_line` (with TfL line colours), `dim_date` (calendar with weekends and UK bank holidays from GOV.UK), `dim_hour` (time bands: AM peak / PM peak / off-peak…), `dim_data_source` (one slicer to switch mock ↔ live).
    - Added Power BI columns to the facts: London date and hour (join keys), `is_rush_hour` (weekday peaks, excluding bank holidays), rain/wind bands with sort order, `is_wet`.
    - Weather bands and time bands defined once as SQL macros (`sql/00_macros.sql`) and reused everywhere.
    - New quality check: every fact row matches a date, hour, line and data source in the dimension tables.
    - `refresh.py` now also runs `get_bank_holidays.py`.
  - *Done (Power BI):* six tables loaded into `powerbi/TfL_Delays.pbix` from Parquet via a `DataFolder` parameter, following `powerbi/POWERBI_GUIDE.md` → 3.1.
- [x] **3.2 Build the Data Model:** Connect your tables (TfL status, Weather, Calendar) in the Power BI relationship view.
  - *Done:* star schema with 8 many-to-one, single-direction relationships (both facts → `dim_date`, `dim_hour`, `dim_line`, `dim_data_source`); `dim_date` marked as date table; sort-by columns, summarization and hidden keys set (`powerbi/POWERBI_GUIDE.md` → 3.2).
- [x] **3.3 Write DAX Measures:** Create formulas for "Mean Time To Recovery" and "Weather Delay Risk".
  - *Done:* `_Measures` table with base measures (Running Line-Hours, Delays Started, Delays, Confirmed Delays), headline measures (Delay Rate, Disrupted Hours %, Service Availability %, **MTTR** on confirmed delays only, Longest Delay), weather measures (Delay Rate Wet/Dry, **Weather Delay Risk**, Risk vs Dry using `REMOVEFILTERS` on the band and its sort column) and report labels (Data Banner, Data Coverage). All values match the SQL results (mock: Delay Rate 7.5%, MTTR 65 min, Weather Delay Risk 1.5×).
- [x] **3.4 Design the Dashboard:** Build a clean, 1-page visual report with heatmaps and KPIs.
  - *Done:* one-page report in `powerbi/TfL_Delays.pbix` using `powerbi/tfl_theme.json`: filter row (data source / date / line), SIMULATED DATA banner, 4 KPI cards (Delay Rate, MTTR, Delays, Weather Delay Risk), line × hour heatmap (single-hue blue), delay rate by rain band, lines ranked table with data bars, top delay reasons, dynamic titles, alt text and data attributions (`powerbi/POWERBI_GUIDE.md` → 3.4).
  - *Done:* screenshot saved as `powerbi/dashboard_mock.png`. Final layout: KPI row, then rain chart / delay reasons / lines ranked table, with a full-width line × hour heatmap along the bottom.
- [x] **3.5 Milestone Reached:** At this point, you have a complete Data Analyst project ready for job applications.
  - *Reached 20 Oct 2026* with the full pipeline working end to end on mock data. Note: the headline numbers are simulated. Once a few weeks of live data are collected, switch the slicer to Live and refresh the screenshot; the real numbers are what make it compelling to recruiters.

## Phase 4: The Data Science Upgrade (Machine Learning)
**Goal:** Train an AI model to predict delays before they happen.

> **Built and validated on mock data (20 Oct 2026).** To run on real data once enough is collected (~3–4 weeks, more is better): `python refresh.py` then `python train_model.py --source live`. The script refuses to train until there are 30+ delays in both the train and test periods.
>
> To test the model properly, the mock data was extended from 1 week to **3 months (Jan–Mar 2024)**: `generate_tfl_history.py` now downloads its own weather and uses a fixed random seed, so it is reproducible. Same rule as before (5% → 15% when rain > 0.5 mm or wind > 25 km/h). Dashboard numbers changed as a result; the expected values in `powerbi/POWERBI_GUIDE.md` 3.3 are updated. **Refresh Power BI and retake `dashboard_mock.png`.**

- [x] **4.1 Feature Engineering:** Use Python to create predictive columns (e.g., "Is it Rush Hour?", "Did it rain in the last 3 hours?").
  - *Done:* `sql/11_fct_ml_features.sql` → `fct_ml_features`. Question: *"the line is running normally at the start of the hour, will a new delay start during it?"* (hours already disrupted at the start are excluded, otherwise the model just learns "already delayed → no new delay").
  - Features (all known at the start of the hour, so no **data leakage**): hour of day, day of week, weekend, bank holiday, rush hour, line, rain in previous hour / 3 hours, wind, temperature, delays on the line in the last 24h, other lines disrupted last hour. Start-of-hour status uses an **ASOF join** to the last snapshot strictly before the hour.
  - Two new quality checks: no feature uses data from inside the hour (leakage guard), no duplicate line-hours.
- [x] **4.2 Train the Model:** Train a classification model (like XGBoost) using scikit-learn to predict if a line will be delayed.
  - *Done:* `train_model.py`. **Time-based split** (train on the first 75% of hours, test on the last 25%; never random). XGBoost with **early stopping** on a time-based validation slice (kept 72 trees) vs two baselines. Scored with ROC-AUC and PR-AUC (accuracy is useless at ~7% positives).
  - Mock results (test set): baseline ROC-AUC 0.500 / PR-AUC 0.073 · logistic regression 0.581 / 0.106 · **XGBoost 0.608 / 0.121**. The best possible on this data (a model that knows the exact mock rule) is **0.620**, so XGBoost captures nearly all of the available signal. It beats logistic regression because the rule is a threshold, which trees handle naturally.
  - Risk bands on unseen test hours: **High → 16.2%** actual delays vs **Normal → 5.5%**.
- [x] **4.3 Explain the Model:** Use a tool called SHAP to visualize why the model made its prediction (e.g., "The model predicted a delay because wind speeds were high").
  - *Done:* `ml/mock/shap_importance.png` (overall drivers), `shap_beeswarm.png` (how each feature's value moves risk), `shap_example_prediction.png` (why one hour was rated high-risk). SHAP values come from XGBoost's exact TreeSHAP. **Wind and rain in the previous hour are the top two drivers, matching the mock rule**; rush hour, weekend and bank holiday ≈ 0. Early stopping cut the noise the first version picked up from hour of day and temperature.
- [x] **4.4 Export Predictions:** Save the model's predictions back into your SQL database.
  - *Done:* table `ml_predictions` in `tfl.duckdb` and `powerbi/data/fct_ml_predictions.parquet`: predicted risk, risk vs average, risk band (Normal / Elevated / High), top risk factor (from SHAP), actual outcome, and `dataset_split` (train/test; only **test** rows show honest performance). Metrics and the model are saved in `ml/<source>/`.

## Phase 5: The Portfolio Showcase (Packaging)
**Goal:** Make the project irresistible to a recruiter who only has 30 seconds to look at it.

- [x] **5.1 Update Power BI:** Add a second page to your dashboard showing the Machine Learning predictions.
  - *Done (21 Oct 2026):* "Predicting Delays Before They Happen" page, filtered to the test period, screenshot in `powerbi/dashboard_model_mock.png` and added to the README. Values match SQL (ROC-AUC 0.61, 16.2% vs 5.5%, lift 3.0×).
  - *Done (data side):* `train_model.py` adds `risk_band_order` and a `ml_model_metrics` table (test scores for XGBoost and both baselines), both exported to `powerbi/data/`.
  - *To do (you):* follow **`powerbi/POWERBI_GUIDE.md` → 5.1**: load 2 tables, 5 relationships, 7 measures, a "Delay Risk Model" page filtered to the **test** period (KPI cards, predicted vs actual by risk band, top risk factors, predicted-risk heatmap). Screenshot as `powerbi/dashboard_model_mock.png`.
- [x] **5.2 Write the README:** Write a professional summary for your GitHub page explaining the business value of your project.
  - *Done:* `README.md`: one-line summary, live collector status badge, project-status note (simulated vs real), dashboard screenshot, business value, pipeline diagram (Mermaid), skills table, key decisions (gaps and islands, overnight closures, leakage, honest evaluation, validation against a known rule), results table with SHAP charts, run instructions, project structure, data sources and attributions, limitations and next steps.
  - *To do:* replace the simulated results with real ones once enough live data is collected.
- [x] **5.3 Clean the Code:** Remove leftover test code and add clear comments.
  - *Done:* removed `test_tfl.py` (superseded by the collector) and `data/london_weather_sample.csv` (the mock generator now keeps its weather in memory). Added `requirements.txt` with pinned versions. Every script has a header docstring explaining what it does and how to run it, and every SQL file explains its rules. Confirmed the mock data regenerates byte-for-byte identically (fixed seed).
  - *Optional:* delete the disabled Windows task "TfL Status Collector" (Task Scheduler → right-click → Delete); it's no longer needed.
