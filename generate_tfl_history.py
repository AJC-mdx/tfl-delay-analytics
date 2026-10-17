import pandas as pd
import random

print("Loading weather data...")
# 1. Read the weather CSV you just made
weather_df = pd.read_csv("data/london_weather_sample.csv")

tube_lines = ["Bakerloo", "Central", "Circle", "District", "Jubilee", 
              "Northern", "Piccadilly", "Victoria", "Waterloo & City"]

historical_data = []

print("Generating realistic TfL history...")
# 2. Loop through every single hour in your weather data
for index, row in weather_df.iterrows():
    time = row["time"]
    rain = row["rain_mm"]
    wind = row["wind_kph"]
    
    # 3. For each hour, generate a status for every tube line
    for line in tube_lines:
        # Base chance of delay is 5%. If it's raining or very windy, risk goes up.
        delay_chance = 0.05
        if rain > 0.5 or wind > 25:
            delay_chance = 0.15
            
        if random.random() < delay_chance:
            status = "Minor Delays"
            reason = random.choice(["Signal Failure", "Faulty Train", "Customer Incident"])
        else:
            status = "Good Service"
            reason = "None"
            
        historical_data.append({
            "time": time,
            "line": line,
            "status": status,
            "reason": reason
        })
        
# 4. Save to a new CSV
tfl_df = pd.DataFrame(historical_data)
file_path = "data/tfl_history_sample.csv"
tfl_df.to_csv(file_path, index=False)

print(f"\nSuccess! Created {len(tfl_df)} rows of TfL data.")
print(f"Saved to {file_path}")