"""
Download UK (England & Wales) bank holidays from GOV.UK and save them to
data/reference/uk_bank_holidays.csv, for the calendar table (dim_date).
Run by refresh.py; GOV.UK covers roughly the previous few years to next year.
"""
from pathlib import Path

import pandas as pd
import requests

OUTPUT_FILE = Path(__file__).resolve().parent / "data" / "reference" / "uk_bank_holidays.csv"

response = requests.get("https://www.gov.uk/bank-holidays.json", timeout=30)
response.raise_for_status()
events = response.json()["england-and-wales"]["events"]

holidays = pd.DataFrame(events)[["date", "title"]].rename(columns={"title": "holiday_name"})
holidays.to_csv(OUTPUT_FILE, index=False)
print(f"Saved {len(holidays)} bank holidays ({holidays['date'].min()} to {holidays['date'].max()}) to {OUTPUT_FILE}")
