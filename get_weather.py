"""
Download hourly London weather from Open-Meteo for every date we have TfL
data for (the mock history AND the live collection), and save it to
data/london_weather.csv. Re-run it before load_database.py to cover new
live days.

Open-Meteo has two services:
  * archive  - quality-checked historical data, but runs ~5 days behind
  * forecast - also returns the recent past, so we use it for the last week
All times are UTC. Precipitation at e.g. 10:00 is the rain that fell
between 09:00 and 10:00.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = DATA_DIR / "london_weather.csv"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_LAG_DAYS = 7  # dates newer than this come from the forecast service


def date_range_of(csv_file, time_column):
    """First and last date found in one of our TfL CSV files."""
    times = pd.to_datetime(pd.read_csv(DATA_DIR / csv_file, usecols=[time_column])[time_column], utc=True)
    return times.min().date(), times.max().date()


def fetch(url, start, end):
    params = {
        "latitude": 51.5074,   # central London
        "longitude": -0.1278,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "timezone": "GMT",
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    return pd.DataFrame({
        "time": hourly["time"],
        "temp_c": hourly["temperature_2m"],
        "rain_mm": hourly["precipitation"],
        "wind_kph": hourly["wind_speed_10m"],
    })


def download(start, end):
    """Use the archive where possible, the forecast service for recent days."""
    archive_cutoff = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    parts = []
    if start <= archive_cutoff:
        part = fetch(ARCHIVE_URL, start, min(end, archive_cutoff))
        parts.append(part.assign(weather_source="archive"))
    if end > archive_cutoff:
        part = fetch(FORECAST_URL, max(start, archive_cutoff + timedelta(days=1)), end)
        parts.append(part.assign(weather_source="forecast"))
    return pd.concat(parts)


ranges = {
    "mock TfL history": date_range_of("tfl_history_sample.csv", "time"),
    "live TfL data":    date_range_of("tfl_live_status.csv", "collected_at_utc"),
}

frames = []
for label, (start, end) in ranges.items():
    print(f"Fetching weather for {label}: {start} to {end}")
    frames.append(download(start, end))

weather = pd.concat(frames).drop_duplicates(subset="time").sort_values("time")

# The forecast service also returns future hours - keep only the past
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
weather = weather[weather["time"] <= now_utc]

# Open-Meteo returns empty values for hours it doesn't have yet
weather = weather.dropna(subset=["temp_c", "rain_mm", "wind_kph"])

weather.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved {len(weather):,} hours of weather to {OUTPUT_FILE}")
print(weather["weather_source"].value_counts().to_string())
