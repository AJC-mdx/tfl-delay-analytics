"""
Live TfL status collector.

Each run takes one snapshot of the current status of every Tube line and
APPENDS it to data/tfl_live_status.csv. Run it on a schedule (e.g. every
15 minutes) to build up our own real history of line statuses.
"""
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

# Use paths relative to this script, so it works no matter which folder
# Task Scheduler starts it from
PROJECT_DIR = Path(__file__).resolve().parent
DATA_FILE = PROJECT_DIR / "data" / "tfl_live_status.csv"
LOG_FILE = PROJECT_DIR / "logs" / "collector.log"

URL = "https://api.tfl.gov.uk/Line/Mode/tube/Status"

COLUMNS = [
    "collected_at_utc",    # when we took the snapshot
    "line_id",
    "line_name",
    "status_severity",     # TfL's code, e.g. 10 = Good Service, 9 = Minor Delays, 20 = Service Closed
    "status_description",  # e.g. "Good Service", "Minor Delays"
    "reason",              # TfL's explanation text (blank when Good Service)
    "disruption_category", # e.g. "RealTime", "PlannedWork"
]

LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def fetch_status():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    return response.json()


def to_rows(lines, collected_at):
    rows = []
    for line in lines:
        # A line can have more than one status at once (e.g. part closure
        # plus minor delays elsewhere), so keep every one of them
        for status in line.get("lineStatuses", []):
            disruption = status.get("disruption") or {}
            rows.append({
                "collected_at_utc": collected_at,
                "line_id": line["id"],
                "line_name": line["name"],
                "status_severity": status.get("statusSeverity"),
                "status_description": status.get("statusSeverityDescription"),
                "reason": (status.get("reason") or "").strip(),
                "disruption_category": disruption.get("category", ""),
            })
    return rows


def append_to_csv(rows):
    DATA_FILE.parent.mkdir(exist_ok=True)
    write_header = not DATA_FILE.exists()
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = to_rows(fetch_status(), collected_at)
        append_to_csv(rows)
        logging.info("Saved %d rows", len(rows))
        print(f"Saved {len(rows)} rows to {DATA_FILE}")
    except Exception:
        # Log and exit quietly, so one failed run (e.g. no internet)
        # doesn't stop the next scheduled run
        logging.exception("Collection failed")
        raise


if __name__ == "__main__":
    main()
