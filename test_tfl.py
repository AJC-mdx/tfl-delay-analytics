import requests
import pandas as pd

# 1. The URL for the live TfL API (Tube lines only for this test)
url = "https://api.tfl.gov.uk/Line/Mode/tube/Status"

print("Asking TfL for live train status...")
response = requests.get(url)
data = response.json()

# 2. Create a blank list to hold our clean data
tube_lines = []

# 3. Loop through the messy data and grab just the name and status
for line in data:
    name = line["name"]
    status = line["lineStatuses"][0]["statusSeverityDescription"]
    
    tube_lines.append({"Line": name, "Status": status})

# 4. Turn it into a Pandas DataFrame (which is just a Python spreadsheet)
df = pd.DataFrame(tube_lines)

print("\n--- LIVE TUBE STATUS ---")
print(df.to_string(index=False))