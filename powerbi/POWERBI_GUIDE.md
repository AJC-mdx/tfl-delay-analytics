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

Measures are formulas that recalculate for whatever is selected (a line, a date range, a slicer). We build them in layers: simple **base measures** first, then **headline measures** built from them. If a base measure is right, everything built on it is right too.

### Step 1: Create a measures table

Keeping all measures in one place (instead of scattered across tables) is standard good practice.

1. **Home → Enter data**.
2. Name the table `_Measures` (the underscore sorts it to the top) → **Load**.
3. You'll add measures to this table. When you've added the first one, delete the empty `Column1`. The table's icon then changes to a calculator.

### Step 2: Add the measures

For each measure: select `_Measures` in the **Data** pane → **Table tools → New measure** → paste the formula → press Enter. Then set its format in **Measure tools** (shown under each formula).

> Paste one measure at a time. The text before `=` is the measure's name.

#### Base measures

```dax
Running Line-Hours =
CALCULATE ( COUNTROWS ( fct_line_hour ), fct_line_hour[is_running] = TRUE () )
```
*Hours when a line was actually running (overnight closures excluded).* Format: Whole number, thousands separator.

```dax
Delays Started =
CALCULATE ( SUM ( fct_line_hour[delays_started] ), fct_line_hour[is_running] = TRUE () )
```
*New delays, counted from the line-hour table, so they can be filtered by weather.* Format: Whole number.

```dax
Delays =
COUNTROWS ( fct_delay_episodes )
```
*Number of delay episodes, from the episodes table (use this with reasons/durations).* Format: Whole number.

```dax
Confirmed Delays =
CALCULATE ( [Delays], fct_delay_episodes[end_confirmed] = TRUE () )
```
*Delays where we actually saw the line recover.* Format: Whole number.

#### Headline measures

```dax
Delay Rate =
DIVIDE ( [Delays Started], [Running Line-Hours] )
```
*The chance a new delay starts on a line in any given hour.* Format: **Percentage**, 1 decimal place.

```dax
Disrupted Hours % =
DIVIDE (
    CALCULATE ( COUNTROWS ( fct_line_hour ),
        fct_line_hour[is_running] = TRUE (),
        fct_line_hour[any_disruption] = TRUE () ),
    [Running Line-Hours]
)
```
*Share of running line-hours with any disruption.* Format: Percentage, 1 decimal place.

```dax
Service Availability % =
1 - CALCULATE ( AVERAGE ( fct_line_hour[disrupted_share] ), fct_line_hour[is_running] = TRUE () )
```
*Share of running time with no disruption.* Format: Percentage, 1 decimal place.

```dax
MTTR (min) =
CALCULATE ( AVERAGE ( fct_delay_episodes[duration_minutes] ), fct_delay_episodes[end_confirmed] = TRUE () )
```
*Mean Time To Recovery: the average delay length. Only confirmed delays, since unconfirmed ones are minimums, not true lengths (rule from 2.3).* Format: Decimal, 0 decimal places.

```dax
Longest Delay (min) =
CALCULATE ( MAX ( fct_delay_episodes[duration_minutes] ), fct_delay_episodes[end_confirmed] = TRUE () )
```
Format: Whole number.

#### Weather measures

`is_wet` means **any** rain in the previous hour, which is known in advance, so this also matches what the Phase 4 model can use.

```dax
Delay Rate (Wet) =
CALCULATE ( [Delay Rate], fct_line_hour[is_wet] = TRUE () )
```

```dax
Delay Rate (Dry) =
CALCULATE ( [Delay Rate], fct_line_hour[is_wet] = FALSE () )
```
Format both: Percentage, 1 decimal place.

```dax
Weather Delay Risk =
DIVIDE ( [Delay Rate (Wet)], [Delay Rate (Dry)] )
```
*How many times more likely a delay is after rain. 1.5 = 50% more likely.* Format: in **Measure tools → Format**, type the custom format `0.0"×"` so it shows as e.g. **1.5×**.

```dax
Risk vs Dry =
VAR DryRate =
    CALCULATE (
        [Delay Rate],
        REMOVEFILTERS ( fct_line_hour[rain_band], fct_line_hour[rain_band_order] ),
        fct_line_hour[rain_band] = "Dry (0 mm)"
    )
RETURN
    DIVIDE ( [Delay Rate], DryRate )
```
*For the rain-band chart: each band's delay rate compared with dry hours.* Format: custom `0.0"×"`.

> **Why `REMOVEFILTERS` on two columns?** When a chart shows `rain_band`, Power BI also filters its sort column `rain_band_order` behind the scenes (from 3.2 Step 3). Removing only `rain_band` would leave the hidden sort filter in place and the "dry" rate would come out blank. This is a classic Power BI trap and a good interview talking point.

#### Labels for the report

```dax
Data Banner =
IF (
    HASONEVALUE ( dim_data_source[data_source] ),
    IF (
        SELECTEDVALUE ( dim_data_source[is_simulated] ),
        "⚠ SIMULATED DATA: mock values for testing the pipeline, not real TfL performance",
        "Live TfL data, collected every 15 minutes"
    ),
    "Select one data source (Simulated or Live)"
)
```

```dax
Data Coverage =
VAR FirstHour = MIN ( fct_line_hour[hour_london] )
VAR LastHour  = MAX ( fct_line_hour[hour_london] )
RETURN
    IF ( ISBLANK ( FirstHour ), "No data for this selection",
        "Data: " & FORMAT ( FirstHour, "d mmm yyyy" ) & " to " & FORMAT ( LastHour, "d mmm yyyy" )
            & " · " & FORMAT ( [Running Line-Hours], "#,0" ) & " line-hours" )
```

### Step 3: Check the numbers against SQL

Put a **Slicer** with `dim_data_source[data_source_label]` on the page and select **Simulated (mock data)**. Add a **Card** (or a **Table** with all measures) and compare with these values, calculated directly in SQL:

| Measure | Expected (mock data) |
|---|---|
| Running Line-Hours | 19,656 |
| Delays Started | 1,325 |
| Delays | 1,325 |
| Confirmed Delays | 1,324 |
| Delay Rate | 6.7% |
| Disrupted Hours % | 7.4% |
| Service Availability % | 92.6% |
| MTTR (min) | 66 |
| Longest Delay (min) | 180 |
| Delay Rate (Wet) | 9.6% |
| Delay Rate (Dry) | 6.0% |
| Weather Delay Risk | 1.6× |

*(Updated 20 Oct 2026 when the mock data was extended from 1 week to 3 months, Jan–Mar 2024. The first version used 1 week: 1,512 line-hours, 113 delays, 7.5%, 1.5×.)*

Then add a **Table** with `fct_line_hour[rain_band]`, `Delay Rate` and `Risk vs Dry`. **Dry** should show **1.0×**, and no row should be blank.

If any number differs, check (in this order): the slicer is on Simulated, the relationships from 3.2 (all *:1, Single), and that the formula was pasted completely.

> **Why "Weather Delay Risk" is 1.6× rather than the ~2.4× from 2.4:** here *wet* includes **light** rain (≤ 0.5 mm), which in the mock data has no effect, so it dilutes the result. The 2.4× figure was for moderate rain only. The rain-band table shows both views. The measure uses "any rain" on purpose, because it's a neutral definition we didn't pick to match the mock rule.

Delete the test visuals when done and **Save**.

---

## 3.4 Design the dashboard

A single page that answers four questions at a glance: **How often are there delays? How quickly does service recover? When and where are delays worst? Does rain make it worse?**

### Design rules (and why)

- **One accent colour.** Every bar uses the same blue. Lines are identified by **name**, not colour. TfL has 11 line colours, which is too many to tell apart (especially for colour-blind viewers), and several (Circle yellow, Hammersmith & City pink) are unreadable on white.
- **Heatmap = one colour, light → dark.** Light blue = rare delays, dark blue = frequent. Never a rainbow.
- **Never two y-axes.** Power BI's "Line and clustered column" chart tempts you to put Delay Rate and Risk on two scales. Don't: two scales invent correlations that aren't in the data. Show extra numbers in labels or tooltips instead.
- **Titles say what the chart shows**, and the main ones update with the data (Step 3).
- **Recessive chrome.** Light hairline gridlines, no heavy borders, plenty of white space.

### Step 1: Apply the theme

1. **View → Themes → Browse for themes** → choose `powerbi/tfl_theme.json`.
2. **View → Page view → Fit to page**. Leave the page size at the default **16:9 (1280 × 720)**.

The theme sets the colours, fonts (Segoe UI), soft card backgrounds and light gridlines for every visual, so you don't format each one by hand.

### Step 2: Layout

Build this on a 1280 × 720 page. Sizes are a guide (set them in **Format → General → Properties → Size and position**):

```
 x=16                                                               x=1264
 ┌────────────────────────────────┬──────────────┬───────────┬───────────┐ y=16
 │ London Underground Delays      │ Data source  │ Date range│ Line      │ h=56
 │ (text box)                     │ (slicer)     │ (slicer)  │ (slicer)  │
 ├────────────────────────────────┴──────────────┴───────────┴───────────┤ y=80
 │ ⚠ Data Banner (card)                                                   │ h=32
 ├─────────────────┬─────────────────┬─────────────────┬─────────────────┤ y=124
 │ Delay Rate      │ MTTR (min)      │ Delays          │ Weather Delay   │ h=96
 │                 │                 │                 │ Risk            │ w=302 each
 ├─────────────────┴─────────────────┴───┬─────────────┴─────────────────┤ y=236
 │ HEATMAP: line × hour of day           │ Delay rate by rain            │ h=260
 │ (matrix)  w=760                       │ (bar chart)  w=472            │
 ├───────────────────────────────────────┼───────────────────────────────┤ y=508
 │ Lines ranked (table)  w=760           │ Top delay reasons (bar chart) │ h=180
 ├───────────────────────────────────────┴───────────────────────────────┤ y=696
 │ footer text                                                            │ h=20
 └────────────────────────────────────────────────────────────────────────┘
```

Keep **16px gaps** between everything (the numbers above already include them).

### Step 3: Add the dynamic-title measures

Add these to `_Measures` (same as in 3.3). They make chart titles state the current finding, and they update when you change the slicers or when live data arrives.

```dax
Title Heatmap =
VAR TopHour = TOPN ( 1, VALUES ( dim_hour[hour_label] ), [Delay Rate], DESC )
RETURN
    IF ( ISBLANK ( [Delays Started] ), "No delays in this selection",
        "Delays are most likely around " & CONCATENATEX ( TopHour, dim_hour[hour_label], ", " ) )
```

```dax
Title Rain =
IF ( ISBLANK ( [Weather Delay Risk] ), "Delay rate by rain in the previous hour",
    "Delays are " & FORMAT ( [Weather Delay Risk], "0.0" ) & "× as likely after rain" )
```

```dax
Title Lines =
VAR TopLine = TOPN ( 1, VALUES ( dim_line[line_name] ), [Delay Rate], DESC )
RETURN
    IF ( ISBLANK ( [Delays Started] ), "Lines ranked by delay rate",
        CONCATENATEX ( TopLine, dim_line[line_name], " & " ) & " has the highest delay rate" )
```

To use one as a title: select the visual → **Format → General → Title → Text → fx** (conditional formatting) → **Format style: Field value** → choose the measure.

### Step 4: Build each visual

**Title text box** (Insert → Text box): "London Underground Delays", 20pt Segoe UI Semibold. Under it, add **+ Value** → `Data Coverage` (the dynamic text from 3.3), 10pt grey.

**Slicers** (top right, one row, so all filters sit together above everything they control):

| Slicer | Field | Settings |
|---|---|---|
| Data source | `dim_data_source[data_source_label]` | **Format → Slicer settings → Style: Tile**, **Single select: On**. Select **Simulated (mock data)** before saving. |
| Date range | `dim_date[date]` | Style: **Between** |
| Line | `dim_line[line_name]` | Style: **Dropdown**, multi-select, **Select all** option on |

**Data banner** (Card): field `Data Banner`. Turn the category label off. Callout font 12pt. This keeps "SIMULATED DATA" visible on every screenshot.

**KPI cards** (four Cards, or the newer **Card** visual with multiple values):

| Card | Measure | Label under the number |
|---|---|---|
| 1 | `Delay Rate` | "chance of a new delay per line, per hour" |
| 2 | `MTTR (min)` | "average minutes to recover" |
| 3 | `Delays` | "delays recorded" |
| 4 | `Weather Delay Risk` | "delay risk after rain vs dry" |

Use the theme's callout size (28pt). No icons or extra colour; the number is the point.

**Heatmap** (Matrix):
- **Rows:** `dim_line[line_name]` · **Columns:** `dim_hour[hour_label]` · **Values:** `Delay Rate`
- **Format → Cell elements → Background color → On → fx**: Format style **Gradient**, based on `Delay Rate`. Lowest value `#cde2fb`, highest value `#2a78d6`. (Stopping at this mid-blue keeps any black text readable.)
- **Hide the numbers in the cells.** 264 numbers is noise. Turn **Font color → fx** on with the **same gradient** as the background, so the text disappears into the cell. Values still show on hover (tooltip) and in **Show as a table**.
- Turn off row/column **subtotals**. Shrink column width so all 24 hours fit (about 26px each).
- **Title:** `Title Heatmap` (Step 3).

**Delay rate by rain** (Clustered bar chart):
- **Y-axis:** `fct_line_hour[rain_band]` (sorts Dry → Heavy thanks to the sort column from 3.2) · **X-axis:** `Delay Rate`
- **Tooltips:** add `Risk vs Dry` and `Running Line-Hours`, so hovering shows "2.4×" and how much data the bar is based on.
- **Data labels: On** (shows the rate at the end of each bar).
- One colour: leave the default blue. Do **not** add `Risk vs Dry` as a second axis.
- **Title:** `Title Rain`

**Lines ranked** (Table):
- Columns: `dim_line[line_name]`, `Delay Rate`, `Delays`, `MTTR (min)`, `Longest Delay (min)`
- Sort by `Delay Rate`, descending.
- **Cell elements → Data bars** on `Delay Rate` (positive bar colour `#2a78d6`). This makes the ranking visible at a glance without a separate chart.
- **Title:** `Title Lines`

**Top delay reasons** (Clustered bar chart):
- **Y-axis:** `fct_delay_episodes[first_reason]` · **X-axis:** `Delays` · sort by `Delays` descending
- Data labels on · Title: "What causes delays"
- *(With live data, TfL's reason text is long and varied. We may group it into categories later.)*

**Footer** (Text box, 8pt grey):
> Powered by TfL Open Data · Weather data by Open-Meteo.com (CC BY 4.0) · Bank holidays: GOV.UK · Not affiliated with Transport for London

The attributions are **required** by TfL's and Open-Meteo's terms. Don't use TfL's logo or roundel (they're trademarks).

### Step 5: Accessibility and finishing touches

- **Alt text:** for each visual, **Format → General → Alt text**: one sentence on what it shows (e.g. "Heatmap of delay rate by Tube line and hour of day"). Screen readers use this; recruiters notice it.
- **Show as a table:** every visual has it built in (right-click → Show as a table), which gives a text version of every chart.
- **Tab order:** **View → Selection → Tab order**, arranged top-left to bottom-right.
- **Check the numbers again** with the slicer on **Simulated**: the KPI cards should match the 3.3 table (Delay Rate 6.7%, MTTR 66, Delays 1,325, Weather Delay Risk 1.6×).
- Make sure **Simulated** is selected in the data-source slicer, then **Save**.

### Step 6: Screenshot it

**File → Export → Export to PDF**, or take a screenshot of the page (`Win + Shift + S`). Save as `powerbi/dashboard_mock.png`. We'll use it in the README (5.2). Because the banner says SIMULATED DATA, the screenshot can't be mistaken for real results.
