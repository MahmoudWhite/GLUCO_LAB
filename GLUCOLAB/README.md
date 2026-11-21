# GLUCOLAB — AGP-style profile, daily basal totals and device paths (v7)

A locally hosted Python/FastAPI web app (not Streamlit). It requires no cloud account or outside internet service. You choose the data files from the system file manager; uploads are processed by the **local** Python server. Files are spooled to disk as needed, without an application-specific size limit. Hardware and operating system limits still apply.

## Start GLUCOLAB on Windows using Anaconda Prompt

1. Extract the ZIP. To avoid loading stale files, rename your old `GLUCOLAB` folder as a backup, and extract this version so it creates a **new `GLUCOLAB` folder**.
2. Open **Anaconda Prompt** from the Windows Start menu.
3. Navigate to your extracted `GLUCOLAB` folder. For example, if your folder is under Desktop → LibreAnalysis:
   ```bat
   cd /d "%USERPROFILE%\Desktop\LibreAnalysis\GLUCOLAB"
   ```
4. Install dependencies (once for this Anaconda environment):
   ```bat
   python -m pip install -r requirements.txt
   ```
5. Start the app:
   ```bat
   python app.py
   ```
6. Keep the terminal open, visit **http://127.0.0.1:8000** and press **Ctrl + F5** if an old page is cached.

**Do not double-click `index.html`**. It needs the running Python backend. If port 8000 is taken, run `python app.py --port 8001` and use http://127.0.0.1:8001.

## Select your devices

The first page asks which combination you use:

- **Pump + Libre:** Upload a LibreView historical glucose CSV and a Medtronic MiniMed/CareLink CSV. Preserves the recent 14-day glucose dashboard, observed candidate basal time ranges, the illustrative rate comparison, daily statistics, episode review, quick questions, exports and formatted Python output. Click **Explain modifications** to open a modal with clear segment-by-segment reasoning and detailed hour/date evidence. The hourly pump-entry table, the oversized orange warning/source-text area and the inline raw source-record table were removed, as requested.
- **Libre only:** Upload one LibreView CSV. View the same recent glucose summaries, 24-hour AGP-style profile, hourly averages, hypo episodes and daily analyses, plus a 24-hour glucose-pattern timeline. The timeline highlights **three customary meal periods** (breakfast, lunch and dinner), with historically lower-alert candidates and alert periods to discuss with a diabetes clinician. It **does not** determine medically safe/unsafe eating times or tell you to skip meals.

Click **Change devices** below the server-status indicator (top-right) to return to the first page without restarting the server. Each upload card now has a bottom-right **Show Method** link that opens a dedicated GLUCOLAB step-by-step download guide in the same tab (you can use Back to return). This does not need separate backend routes or popup permissions. The guides also link to Abbott and Medtronic documentation. The shorter upload instructions still require the same CSV file contents as before.

## CSV formats and recent window

- LibreView: `Device Timestamp`, `Record Type`, `Historic Glucose (mg/dL)` or `Historic Glucose (mmol/L)`; **Record Type 0** only, day/month/year export timestamps. Metadata rows are detected.
- Medtronic: `Date`, `Time`, `Basal Rate (U/h)` with year/month/day export timestamps. Metadata rows and optional schedule-event fields are detected.
- Both paths use the **latest 14 × 24 hours** ending at the newest LibreView reading. The Pump + Libre path further narrows the period if an explicit and more recent profile edit event is found.
- **New AGP-style 24-hour glucose chart**: instead of plotting raw calendar-time glucose as a single line, GLUCOLAB groups *observed* historical glucose readings by 30-minute clock-time bins and calculates the 5th, 25th, 50th (median), 75th, and 95th percentiles. The dark band is the 25th–75th percentile interval; the light band is 5th–95th. The green horizontal lines indicate the target range; amber indicates above-range portions. Light dots are sampled observed readings. Each half-hour bin requires at least 5 readings on 2 distinct calendar days; otherwise it is omitted rather than fabricated. This is an **exploratory AGP-style visualization**, NOT a standardized clinical report or an inference about an individual's safe treatment. The chronological trend series is preserved in exported JSON and the Python response for compatibility. Its reading gaps are still explicitly marked.
- Hypoglycemia episodes are **consecutive below-range readings**, separated by normal readings or gaps greater than 20 minutes. They are not validated clinical event classifications.

## How the meal timeline is calculated

Three traditional meal periods are inspected: morning, midday and evening. Within each period, a two-hour candidate is highlighted using the observed relative frequency of glucose alerts and minimum recording coverage. All 24 hours are also marked as lower-alert, frequent high readings, low readings, or insufficient data. This is a **descriptive retrospective visualization**, not a prediction, nutritional prescription or meal-time safety score. It cannot know when meals occurred, carbohydrate quantity, medication/insulin timing, exercise, sleep or the patient's individual care plan. **Never use a chart to justify skipping food, delaying treatment for a low, or changing insulin doses.**

References: [CDC — Managing Blood Sugar](https://www.cdc.gov/diabetes/treatment/) and [American Diabetes Association — Hypoglycemia Causes and Prevention](https://diabetes.org/living-with-diabetes/hypoglycemia-low-blood-glucose/causes-prevention).

## Pump range limitations and simulated comparison

The ordinary CareLink `Basal Rate (U/h)` column records the active basal delivery rate; it does **not** confirm the programmed basal schedule. A brief suspension must not become a newly programmed basal interval. GLUCOLAB excludes zero-rate interruptions and one-off second-level transitions, looks for recurring clock-time observations on multiple recent dates, selects the most recent **complete eligible observed day** up to the LibreView end, and merges adjacent equal-rate intervals. These are **candidate reconstructed observations** only.

The **first basal table** now shows a hypothetical 24-hour basal total in `U/day`, calculated by integrating each candidate recorded rate across the hours of its corresponding segment (`rate U/h × duration hours`). The **second comparison table** shows the equivalent total after hypothetical changes. These totals appear only when the reconstructed intervals form one uninterrupted 00:00–24:00 day; a partial or missing interval produces an *unavailable* total. They are **not measured delivery, not a pump prescription, and not actual daily insulin use**. The comparison table shows the columns in order: Time range, Observed U/h, **Illustrative U/h**, **Simulated step**, Pattern / impacted hours. The simulated-step value retains its colored bold styling, and the illustrated rate retains its bold styling.

The prior ±0.05 U/h threshold-rule calculation is preserved **solely as an illustration**. Its generated final-rate table is not a clinical dosing recommendation or a safe pump-programming plan. The program does not control or change an insulin pump. Differences between dates or mismatches between pump and LibreView cutoffs can prevent a valid current-profile comparison. Use a Medtronic Device Settings / Basal Pattern report to confirm actual programmed settings with a qualified clinician.

## Tests

Run:

```bat
python -m unittest discover -s tests -v
```

All **42 automated tests** passed on the update; coverage includes both modes, Libre-only upload, 24-hour percentile profile, duration-weighted daily totals and incomplete-day rejection, 24-hour meal timeline, and earlier Medtronic suspension/range regressions. HTML and JavaScript interactions were checked in a headless browser using synthetic analysis responses. The environment blocks direct browser navigation to localhost, so actual upload-response handling was separately verified using FastAPI's local test client. No actual patient data is bundled in the ZIP.

## Privacy and deployment

By default the server listens only on `127.0.0.1`, intended for personal local use. It has no authentication, so do not expose it to an untrusted LAN or the public internet. No uploaded files are persisted by the application or sent to an external service. Files may temporarily reside in operating-system-managed disk spool locations during processing.

## Glucose profile references

The median, 25th–75th percentile, and 5th–95th percentile display follows the general concept described in [Abbott's AGP guide](https://pro.freestyle.abbott/uk-en/scientific-resources-education/scientific-evidences/agp-in-practice.html) and in the [clinical AGP interpretation review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9354515/). GLUCOLAB has a custom 30-minute implementation and must **not** be represented as a certified or official manufacturer-generated AGP report.

## New interface features — six glucose colors and expandable uploads

- After successful analysis, the left file-upload panel collapses automatically. Use the little arrow tab on the left of the results to reopen or hide it; the results use the freed space. Works in both Libre-only and Pump + Libre modes.
- The hourly average glucose bars use six visual categories: under 54 mg/dL, 54–69, 70–99, 100–180, 181–250, above 250. For mmol/L exports, the same categories use equivalent units. The legend is immediately under the bars.
- These are display categories based on the observed hourly **average**, not medical advice or predictions. The original hypoglycemia-event colors and all analysis calculations remain unchanged.
