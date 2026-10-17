"""
One command to bring everything up to date:

    python refresh.py

1. get_weather.py        - download weather for all mock + live dates
2. get_bank_holidays.py  - download UK bank holidays (for the calendar)
3. load_database.py      - rebuild tfl.duckdb (raw tables, views, quality
                           checks) and export the Power BI files

If a download fails (e.g. no internet), the database is still rebuilt using
the files we already have.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def run(script):
    print(f"\n=== {script} ===", flush=True)  # flush so it appears before the script's output
    # sys.executable = the same Python that is running this script
    return subprocess.run([sys.executable, str(PROJECT_DIR / script)], cwd=PROJECT_DIR).returncode


downloads = {script: run(script) == 0 for script in ["get_weather.py", "get_bank_holidays.py"]}
for script, ok in downloads.items():
    if not ok:
        print(f"\nWARNING: {script} failed - continuing with the existing file.")

db_result = run("load_database.py")

print("\n=== Summary ===")
for script, ok in downloads.items():
    print(f"{script:<22} {'updated' if ok else 'FAILED (used existing file)'}")
print(f"{'load_database.py':<22} {'rebuilt, all checks passed, Power BI files exported' if db_result == 0 else 'FAILED - see output above'}")

sys.exit(db_result or (0 if all(downloads.values()) else 1))
