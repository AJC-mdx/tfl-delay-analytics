"""
Build the local DuckDB database (tfl.duckdb) from scratch.

1. Raw layer (Phase 2.1): each CSV goes into its own "raw_" table exactly
   as it is, with no cleaning, so we always keep an untouched copy.
2. Reference tables: small hand-maintained lookups in data/reference/.
3. Views: runs every numbered SQL file in sql/ in order (00_..., 01_...)
   to create the macros and the stg_ / fct_ / rpt_ / dim_ views.
4. Data quality checks: runs sql/checks.sql and reports any failures.
5. Power BI export (Phase 3.1): if every check passed, saves the dashboard
   tables as Parquet files in powerbi/data/ for Power BI to load.

Safe to re-run any time; this also picks up new rows from the live collector.
"""
import sys
from pathlib import Path

import duckdb

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
SQL_DIR = PROJECT_DIR / "sql"
DB_FILE = PROJECT_DIR / "tfl.duckdb"
POWERBI_DIR = PROJECT_DIR / "powerbi" / "data"

# table name -> (CSV file, short description)
RAW_TABLES = {
    "raw_weather":     ("london_weather.csv",        "Hourly London weather (Open-Meteo, UTC) - run get_weather.py to update"),
    "raw_tfl_mock":    ("tfl_history_sample.csv",    "SIMULATED Tube status history (mock data)"),
    "raw_tfl_live":    ("tfl_live_status.csv",       "REAL Tube status collected every 15 min"),
    "raw_footfall":    ("StationFootfall_2024.csv",  "Daily station entry/exit taps, 2024"),
    "ref_status_severity": ("reference/status_severity.csv", "TfL severity codes -> category, disruption flag, priority"),
    "ref_tube_lines":      ("reference/tube_lines.csv",      "Tube line IDs, display names and colours"),
    "ref_bank_holidays":   ("reference/uk_bank_holidays.csv", "England & Wales bank holidays (GOV.UK) - run get_bank_holidays.py to update"),
}

# Tables the Power BI dashboard uses (a star schema: 2 fact tables + dimensions)
POWERBI_TABLES = [
    "fct_line_hour",
    "fct_delay_episodes",
    "dim_line",
    "dim_date",
    "dim_hour",
    "dim_data_source",
]

con = duckdb.connect(str(DB_FILE))

print("Loading tables:")
for table, (csv_name, description) in RAW_TABLES.items():
    csv_path = (DATA_DIR / csv_name).as_posix()
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto('{csv_path}')")
    con.execute(f"COMMENT ON TABLE {table} IS '{description}'")
    rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<20} {rows:>8,} rows  <- {csv_name}")

print("\nBuilding views:")
for sql_file in sorted(SQL_DIR.glob("[0-9]*.sql")):
    con.execute(sql_file.read_text(encoding="utf-8"))
    name = sql_file.stem.split("_", 1)[1]  # "01_stg_tfl_status" -> "stg_tfl_status"
    if name.startswith(("stg_", "fct_", "rpt_", "dim_")):
        rows = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name:<20} {rows:>8,} rows  <- sql/{sql_file.name}")
    else:
        print(f"  {name:<20} {'(ran)':>8}       <- sql/{sql_file.name}")

print("\nData quality checks:")
checks = con.execute((SQL_DIR / "checks.sql").read_text(encoding="utf-8")).fetchall()
failed = 0
for check_name, failures in checks:
    print(f"  {'FAIL' if failures else 'ok  '}  {check_name}" + (f" ({failures})" if failures else ""))
    failed += bool(failures)

if failed:
    # Don't publish bad data to the dashboard - keep the last good export
    print("\nPower BI export SKIPPED because checks failed (previous files kept).")
else:
    print("\nPower BI export:")
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    for table in POWERBI_TABLES:
        out_file = POWERBI_DIR / f"{table}.parquet"
        con.execute(f"COPY (SELECT * FROM {table}) TO '{out_file.as_posix()}' (FORMAT parquet)")
        print(f"  {table:<20} -> powerbi/data/{out_file.name}")

con.close()
print(f"\nDatabase saved to {DB_FILE}")

if failed:
    print(f"{failed} check(s) failed - see above.")
    sys.exit(1)
