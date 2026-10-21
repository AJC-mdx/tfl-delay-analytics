"""
Live TfL status collector.

Each run takes one snapshot of the current status of every Tube line and
APPENDS it to data/tfl_live_status.csv. Run it on a schedule (e.g. every
15 minutes) to build up our own real history of line statuses.
"""
import csv
import logging
import time
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


def fetch_status(attempts=3, wait_seconds=10):
    """Get the status of every line. TfL's API occasionally returns an empty or
    broken response (seen 21 Oct 2026: HTTP 200 with an empty body), so check
    the response really contains line data and retry a few times, waiting a
    little longer each time, before giving up."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(URL, timeout=30)
            response.raise_for_status()
            lines = response.json()
            if not isinstance(lines, list) or not lines or "lineStatuses" not in lines[0]:
                raise ValueError(f"unexpected response: {response.text[:200]!r}")
            return lines
        except (requests.RequestException, ValueError) as error:
            # (requests' JSON decode error is a ValueError too)
            logging.warning("Attempt %d/%d failed: %s", attempt, attempts, error)
            print(f"Attempt {attempt}/{attempts} failed: {error}")
            if attempt == attempts:
                raise
            time.sleep(wait_seconds * attempt)  # 10s, then 20s


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
    try:
        lines = fetch_status()
        # timestamp the moment the data actually arrived (after any retries)
        collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = to_rows(lines, collected_at)
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
