# Power BI Guide

How to build the dashboard from the files in `powerbi/data/`.
Those files are created by `python refresh.py`. Run it first.

---

## 3.1 Connect Power BI to the data

### Step 1: Turn off two automatic features (before loading anything)

1. Open **Power BI Desktop** and start a **Blank report**.
2. Go to **File → Options and settings → Options**.
3. Under **CURRENT FILE → Data Load**, untick:
   - **Auto date/time**. We have our own calendar table (`dim_date`); the automatic one bloats the file and causes confusing date hierarchies.
   - **Autodetect new relationships after data is loaded**. We'll create the relationships ourselves in 3.2, so Power BI doesn't guess wrong ones.
4. Click **OK**.
5. **File → Save as** → save as `TfL_Delays.pbix` inside the `powerbi` folder.

### Step 2: Create a folder parameter

This stores the data folder location in one place, so anyone who downloads the project only has to change this one setting.

1. **Home → Transform data** (opens Power Query Editor).
2. **Home → Manage Parameters → New Parameter**:
   - **Name:** `DataFolder`
   - **Type:** Text
   - **Current Value:** `C:\Users\ahmed\OneDrive\Desktop\TFL_project\powerbi\data\`
     (keep the `\` at the end)
3. Click **OK**.

### Step 3: Load the six tables

Do this once for each table in the list below:

1. In Power Query Editor: **Home → New Source → Blank Query**.
2. **Home → Advanced Editor**, delete what's there and paste the code below, changing the file name each time:

   ```
   let
       Source = Parquet.Document(File.Contents(DataFolder & "fct_line_hour.parquet"))
   in
       Source
   ```

3. Click **Done**.
4. In the **Query Settings** panel on the right, set **Name** to the table name (e.g. `fct_line_hour`).

| Query name | File name |
|---|---|
| `fct_line_hour` | `fct_line_hour.parquet` |
| `fct_delay_episodes` | `fct_delay_episodes.parquet` |
| `dim_line` | `dim_line.parquet` |
| `dim_date` | `dim_date.parquet` |
| `dim_hour` | `dim_hour.parquet` |
| `dim_data_source` | `dim_data_source.parquet` |

> Tip: after the first one, right-click it → **Duplicate**, then just change the file name in the Advanced Editor and rename it.

### Step 4: Check the column types

Parquet files carry their types, so these should already be right. Click each table and check the icon next to the column name:

- `fct_line_hour`: `hour_utc`, `hour_london` = date/time · `date_london` = date · `is_...` columns = True/False
- `fct_delay_episodes`: `delay_start_utc`, `delay_end_utc`, `delay_start_london` = date/time · `start_date_london` = date
- `dim_date`: `date` = date

If any show as text (**ABC**) or whole number instead, click the icon and change the type.

### Step 5: Load and check

1. **Home → Close & Apply**.
2. Open **Table view** (the grid icon on the left) and check the row count shown at the bottom for each table. They should match the "rows" numbers printed by `refresh.py` (e.g. `fct_line_hour` 1,534+, `dim_hour` 24, `dim_line` 11). The live data grows, so live-related counts will be higher.
3. **Save.**

### Updating the data later

1. Run `python refresh.py`.
2. In Power BI: **Home → Refresh**.

### If something goes wrong

| Problem | Fix |
|---|---|
| "Could not find file" | Check `DataFolder` ends with `\` and the path is right (Transform data → Manage Parameters). Run `python refresh.py` to create the files. |
| Refresh fails with "file in use" | Close anything else that has the Parquet file open and try again. |
| Numbers look out of date | You refreshed Power BI without running `python refresh.py` first. |

---

## 3.2 Build the data model

The goal is a **star schema**: two fact tables in the middle (things that happened), with dimension tables around them (ways to slice them). Every filter flows **from a dimension into the facts**.

```
                 dim_date        dim_hour
                     \             /
   dim_data_source — fct_line_hour — dim_line
                     \             /
                    fct_delay_episodes
         (the same four dimensions also connect here)
```

### Step 1: Create the 8 relationships

1. Click **Model view** (the third icon on the left).
2. For each row below: **Home → Manage relationships → New...**, pick the two tables and click the matching columns, then check the settings and click **OK**.

| # | From (many side) | Column | To (one side) | Column |
|---|---|---|---|---|
| 1 | `fct_line_hour` | `date_london` | `dim_date` | `date` |
| 2 | `fct_line_hour` | `hour_of_day` | `dim_hour` | `hour_of_day` |
| 3 | `fct_line_hour` | `line_id` | `dim_line` | `line_id` |
| 4 | `fct_line_hour` | `data_source` | `dim_data_source` | `data_source` |
| 5 | `fct_delay_episodes` | `start_date_london` | `dim_date` | `date` |
| 6 | `fct_delay_episodes` | `start_hour_of_day` | `dim_hour` | `hour_of_day` |
| 7 | `fct_delay_episodes` | `line_id` | `dim_line` | `line_id` |
| 8 | `fct_delay_episodes` | `data_source` | `dim_data_source` | `data_source` |

For **every** relationship, the settings should be:
- **Cardinality:** Many to one (*:1)
- **Cross filter direction:** Single
- **Make this relationship active:** ticked

> If Power BI says the relationship would be "one to one" or "many to many", the wrong column is selected. Every `dim_` column above is unique, so it must be the "one" side.

**Do not** connect the two fact tables to each other. They connect only through the shared dimensions, which is what lets one slicer filter both.

### Step 2: Mark the calendar as a date table

1. Click `dim_date` in the **Data** pane.
2. **Table tools → Mark as date table** → choose the `date` column → **OK**.

This tells Power BI to use our calendar for date calculations.

### Step 3: Set sort orders

Without this, text sorts alphabetically: "Apr, Aug, Dec…" and "Friday, Monday…". In **Table view**, click the column, then **Column tools → Sort by column**:

| Table | Column | Sort by |
|---|---|---|
| `dim_date` | `month_label` | `month_sort` |
| `dim_date` | `day_of_week` | `day_of_week_number` |
| `dim_date` | `day_of_week_short` | `day_of_week_number` |
| `dim_hour` | `hour_label` | `hour_of_day` |
| `dim_data_source` | `data_source_label` | `sort_order` |
| `fct_line_hour` | `rain_band` | `rain_band_order` |
| `fct_line_hour` | `wind_band` | `wind_band_order` |

### Step 4: Stop Power BI adding up ID numbers

Power BI wants to **sum** every number column, which is meaningless for IDs and labels. For each column below: click it → **Column tools → Summarization → Don't summarize**.

- `dim_date`: `year`, `month_number`, `month_sort`, `day_of_week_number`
- `dim_hour`: `hour_of_day`
- `fct_delay_episodes`: `episode_id`

### Step 5: Hide the columns report users shouldn't pick

Keep the field list clean, so you always slice by the **dimension** columns. In **Model view**, right-click each column → **Hide in report view**:

- **In both fact tables:** the join keys (`date_london` / `start_date_london`, `hour_of_day` / `start_hour_of_day`, `line_id`, `data_source`) and `line_name` (use `dim_line[line_name]` instead).
- **Sort-helper columns:** `dim_date[month_sort]`, `dim_date[day_of_week_number]`, `dim_data_source[sort_order]`, `fct_line_hour[rain_band_order]`, `fct_line_hour[wind_band_order]`.

> Hidden columns still work in relationships, sorting and DAX. They just don't clutter the field list.

### Step 6: Quick test

1. **Report view** → add a **Slicer** with `dim_data_source[data_source_label]`.
2. Add a **Table** visual with `dim_line[line_name]` and `fct_delay_episodes[episode_id]` (set to **Count**).
3. Select **Simulated (mock data)** in the slicer. You should see 9 lines and **113** delays in total (the same as `fct_delay_episodes` for mock in SQL).
4. Select **Live (real TfL data)**. It should be empty or nearly empty for now (the live data so far is mostly overnight closures).
5. Delete the test visuals and **Save**.

---

## 3.3 DAX measures

*Coming next.*
