"""
Generate SIMULATED (mock) TfL status history, used to build and test the
pipeline while real data is collected (see collect_tfl_status.py).

The built-in rule (what the analysis and model should rediscover):
    base chance of a delay in any hour = 5%
    if rain > 0.5 mm in the hour before, or wind > 25 km/h -> 15%
Nothing else (line, time of day, history) affects the chance.

Covers MOCK_START to MOCK_END. The random seed is fixed, so re-running
produces exactly the same data.
"""
import random
from pathlib import Path

import pandas as pd
import requests

MOCK_START = "2024-01-01"
MOCK_END = "2024-03-31"
SEED = 42

DATA_DIR = Path(__file__).resolve().parent / "data"
WEATHER_FILE = DATA_DIR / "london_weather_sample.csv"
OUTPUT_FILE = DATA_DIR / "tfl_history_sample.csv"

TUBE_LINES = ["Bakerloo", "Central", "Circle", "District", "Jubilee",
              "Northern", "Piccadilly", "Victoria", "Waterloo & City"]

# 1. Hourly London weather for the mock period (Open-Meteo archive, UTC)
print(f"Downloading weather for {MOCK_START} to {MOCK_END}...")
response = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
    "latitude": 51.5074, "longitude": -0.1278,
    "start_date": MOCK_START, "end_date": MOCK_END,
    "hourly": "temperature_2m,precipitation,wind_speed_10m",
    "timezone": "GMT",
}, timeout=60)
response.raise_for_status()
hourly = response.json()["hourly"]
weather_df = pd.DataFrame({
    "time": hourly["time"],
    "temp_c": hourly["temperature_2m"],
    "rain_mm": hourly["precipitation"],
    "wind_kph": hourly["wind_speed_10m"],
})
weather_df.to_csv(WEATHER_FILE, index=False)

# 2. For every hour and line, roll the dice using the rule above
print("Generating simulated TfL history...")
random.seed(SEED)
historical_data = []
for row in weather_df.itertuples():
    delay_chance = 0.15 if (row.rain_mm > 0.5 or row.wind_kph > 25) else 0.05
    for line in TUBE_LINES:
        if random.random() < delay_chance:
            status = "Minor Delays"
            reason = random.choice(["Signal Failure", "Faulty Train", "Customer Incident"])
        else:
            status = "Good Service"
            reason = "None"
        historical_data.append({"time": row.time, "line": line, "status": status, "reason": reason})

tfl_df = pd.DataFrame(historical_data)
tfl_df.to_csv(OUTPUT_FILE, index=False)
print(f"Saved {len(tfl_df):,} rows ({len(weather_df):,} hours x {len(TUBE_LINES)} lines) to {OUTPUT_FILE}")
print(f"Delay rate: {(tfl_df['status'] != 'Good Service').mean():.1%}")
