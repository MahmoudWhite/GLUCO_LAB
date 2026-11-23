# GLUCOLAB — AGP-style profile, daily basal totals and device paths (v7)

A locally hosted Python/FastAPI web app (not Streamlit). It requires no cloud account or outside internet service for local analysis. You choose the data files from the system file manager; uploads are processed by the **local** Python server. Files are temporarily spooled as needed, with a 30 MB per-file limit in this import-enabled version.

## Fix for sensor-only error: "Cannot read properties of undefined (reading 'map')"

The expanded Libre-only timeline uses 48 half-hour bins and six meal/snack period objects. Older versions of `app.py` send the previous 24-hour/three-window format instead. If the webpage and running Python server use different versions, the timeline cannot render. This version checks the API schema and shows a clear restart message rather than a JavaScript error.

**After updating, you must restart the actual Python server**, not just refresh Chrome:

1. In **every Anaconda Prompt window running GLUCOLAB**, press `Ctrl + C` to stop the old Python process. Close those windows if necessary.
2. Rename the old `GLUCOLAB` folder as a backup, extract the ZIP, and ensure the `GLUCOLAB` folder contains this new `app.py` and `index.html` together.
3. In Anaconda Prompt, run:
   ```bat
   cd /d "C:\Users\SA-MA\Desktop\LibreAnalysis\GLUCOLAB"
   python app.py
   ```
4. Open `http://127.0.0.1:8000` and press `Ctrl + F5` in Chrome. The server status should read **Python server connected**, not **server update required**.

If you see `Address already in use` or `Only one usage of each socket address`, the old Python server is still running on port 8000. Stop it first.

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

## Select sensor, pump and clock format (new first page)

The home page has three sequential steps, with a green **check mark** after each completed selection:

1. **Sensor:** Select exactly one of the displayed sensor models. This unlocks the pump section. The file parser validates the *content*, not the model name; tested formats and unverified formats are documented below.
2. **Pump:** Select a MiniMed **600 Series** or **700 Series**, one of the other listed pumps, or explicitly choose **No insulin pump**. This unlocks the time-format section. A device being selectable does *not* mean its native export has been fully integrated.
3. **Time format:** Explicitly select **12-hour (AM/PM)** or **24-hour**. This changes display labels, not the underlying timestamps, backend calculations, or data exports.

The Continue button remains disabled until all three steps are finished.

Click the orange **Continue** button:

- **Sensor + pump:** Upload timestamped sensor glucose and basal-rate data. MiniMed CareLink-style exports retain the original exploratory candidate-basal path. Other pumps get descriptive recorded-rate analysis only when their units/columns can be verified; no simulated rate adjustments are generated for them.
- **Sensor only / no pump:** Upload a structured glucose file that passes validation and open glucose charts and illustrative meal/snack timing insights. The visual timeline contains **24 hourly blocks**, built from **48 half-hour backend analysis bins**. The highlight boxes are the original crisp floating blue glass style.

The 230 mg/dL reference in the historical timeline is **not** a safe-to-eat threshold; do not postpone meals based on it. Meal/snack periods are illustrative and cannot identify actual meal behavior.

**Change devices** below the server status returns to selection. The two upload cards retain **Show Method** links to the dedicated data-export instructions.

Device catalog examples: [American Diabetes Association CGM guide](https://consumerguide.diabetes.org/products/cgms) and [ADA insulin-pump guide](https://consumerguide.diabetes.org/products/insulin-pumps). Device availability and export format vary by country.

## CSV formats and recent window

- LibreView: `Device Timestamp`, `Record Type`, `Historic Glucose (mg/dL)` or `Historic Glucose (mmol/L)`; **Record Type 0** only, day/month/year export timestamps. Metadata rows are detected.
- Medtronic: `Date`, `Time`, `Basal Rate (U/h)` with year/month/day export timestamps. Metadata rows and optional schedule-event fields are detected.
- Both paths use the **latest 14 × 24 hours** ending at the newest LibreView reading. The Pump + Libre path further narrows the period if an explicit and more recent profile edit event is found.
- **New AGP-style 24-hour glucose chart**: instead of plotting raw calendar-time glucose as a single line, GLUCOLAB groups *observed* historical glucose readings by 30-minute clock-time bins and calculates the 5th, 25th, 50th (median), 75th, and 95th percentiles. The dark band is the 25th–75th percentile interval; the light band is 5th–95th. The green horizontal lines indicate the target range; amber indicates above-range portions. Light dots are sampled observed readings. Each half-hour bin requires at least 5 readings on 2 distinct calendar days; otherwise it is omitted rather than fabricated. This is an **exploratory AGP-style visualization**, NOT a standardized clinical report or an inference about an individual's safe treatment. The chronological trend series is preserved in exported JSON and the Python response for compatibility. Its reading gaps are still explicitly marked.
- Hypoglycemia episodes are **consecutive below-range readings**, separated by normal readings or gaps greater than 20 minutes. They are not validated clinical event classifications.

## How the meal/snack timeline is calculated

The 24-hour timeline displays 24 hourly blocks derived from 48 backend clock-time bins (30 minutes each), with broad **illustrative** breakfast, lunch, dinner and snack-period labels. For every bin, GLUCOLAB calculates the median of the corresponding recent LibreView readings. Bins with fewer than 6 readings or data from fewer than 3 separate dates are shaded grey. The bins are classified by historical median as below 230 mg/dL (green), at or above 230 mg/dL (amber), or below the dataset's low-glucose threshold (pink). The 230 mg/dL threshold is converted automatically if the CSV uses mmol/L. Adjacent bins with matching status are merged within each labelled period; a high interval can split a period, which can then resume at the next below-threshold bin.

**This is not a meal recommendation, actual-meal detection, or permission to eat only at green times.** GLUCOLAB has no log of meals, carbohydrate amounts, insulin, exercise, or individual medical instructions. The medians represent several historical days, not a live sensor reading. Do not skip/delay food based on this graphic or rely on it to manage high/low glucose. Follow your own diabetes care plan.

References: [CDC — Managing Blood Sugar](https://www.cdc.gov/diabetes/treatment/) and [CDC — Diabetes Meal Planning](https://www.cdc.gov/diabetes/healthy-eating/diabetes-meal-planning.html).

## Pump range limitations and simulated comparison

The ordinary CareLink `Basal Rate (U/h)` column records the active basal delivery rate; it does **not** confirm the programmed basal schedule. A brief suspension must not become a newly programmed basal interval. GLUCOLAB excludes zero-rate interruptions and one-off second-level transitions, looks for recurring clock-time observations on multiple recent dates, selects the most recent **complete eligible observed day** up to the LibreView end, and merges adjacent equal-rate intervals. These are **candidate reconstructed observations** only.

The **first basal table** now shows a hypothetical 24-hour basal total in `U/day`, calculated by integrating each candidate recorded rate across the hours of its corresponding segment (`rate U/h × duration hours`). The **second comparison table** shows the equivalent total after hypothetical changes. These totals appear only when the reconstructed intervals form one uninterrupted 00:00–24:00 day; a partial or missing interval produces an *unavailable* total. They are **not measured delivery, not a pump prescription, and not actual daily insulin use**. The comparison table shows the columns in order: Time range, Observed U/h, **Illustrative U/h**, **Simulated step**, Pattern / impacted hours. The simulated-step value retains its colored bold styling, and the illustrated rate retains its bold styling.

The prior ±0.05 U/h threshold-rule calculation is preserved **solely as an illustration**. Its generated final-rate table is not a clinical dosing recommendation or a safe pump-programming plan. The program does not control or change an insulin pump. Differences between dates or mismatches between pump and LibreView cutoffs can prevent a valid current-profile comparison. Use a Medtronic Device Settings / Basal Pattern report to confirm actual programmed settings with a qualified clinician.

## Tests

Run:

```bat
python -m pytest -q
```

Automated regression tests cover this version; coverage includes both modes, Libre-only upload, 24-hour percentile profile, duration-weighted daily totals and incomplete-day rejection, 24-hour meal timeline, and earlier Medtronic suspension/range regressions. HTML and JavaScript interactions were checked in headless Chromium with both a correct sensor-only response and a simulated older-server response. Direct navigation to localhost is blocked in this test environment, so actual upload-response handling was independently verified using FastAPI's test client. No actual patient data is bundled in the ZIP.

## Privacy and deployment

By default the server listens only on `127.0.0.1`, intended for personal local use. It has no authentication, so do not expose it to an untrusted LAN or the public internet. No uploaded files are persisted by the application or sent to an external service. Files may temporarily reside in operating-system-managed disk spool locations during processing. Supported inputs are capped at 30 MiB per file.

## Glucose profile references

The median, 25th–75th percentile, and 5th–95th percentile display follows the general concept described in [Abbott's AGP guide](https://pro.freestyle.abbott/uk-en/scientific-resources-education/scientific-evidences/agp-in-practice.html) and in the [clinical AGP interpretation review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9354515/). GLUCOLAB has a custom 30-minute implementation and must **not** be represented as a certified or official manufacturer-generated AGP report.

## New interface features — six glucose colors and expandable uploads

- After successful analysis, the left file-upload panel collapses automatically. Use the little arrow tab on the left of the results to reopen or hide it; the results use the freed space. Works in both Libre-only and Pump + Libre modes.
- The hourly average glucose bars use six visual categories: under 54 mg/dL, 54–69, 70–99, 100–180, 181–250, above 250. For mmol/L exports, the same categories use equivalent units. The legend is immediately under the bars.
- These are display categories based on the observed hourly **average**, not medical advice or predictions. The original hypoglycemia-event colors and all analysis calculations remain unchanged.

## Optional public beta hosting

To prepare a public URL for testing, see **DEPLOY_PUBLIC.md** and the included `render.yaml` blueprint. The public configuration introduces an upload limit, warnings about hosted processing, and basic HTTP security headers. It is **not** a privacy/security certification; the default local version remains preferable for identifiable medical data.

## 30-minute meal/snack period display (historical data, not eating advice)

The six *illustrative* labels are Breakfast 05:00–11:00, Morning snack 11:00–12:00, Lunch 12:00–17:00, Afternoon snack 17:00–18:00, Dinner 18:00–23:00, and Evening snack 23:00–24:00. Time categories do not represent actual meal events; no meal log is provided. Each 30-minute clock-time bin uses the latest 14 days of historic readings. A bin with fewer than 6 readings or fewer than 3 distinct observation dates displays insufficient data. Other bins are colored by historical median relative to 230 mg/dL (unit-converted for mmol/L); a median below the patient's low threshold is shown separately. Adjacent evidence categories are merged into continuous ranges; gaps and interruptions are preserved. A green segment is **not** a recommendation or authorization to eat, and orange is **not** a recommendation to postpone or skip food. Insulin users in particular should follow an individualized medical plan and respond promptly to low glucose.

The buttons "Download JSON", "Print report", "Explain modifications", and "Export simulated CSV" are aligned to the far right of their panels.


### Device chooser: MiniMed series and other devices (November 2026)

The first page allows selecting any listed sensor and, after a sensor is selected, any listed pump or No insulin pump.
The MiniMed pump choices are **600 Series** and **700 Series** (replacing individual model cards).
**Selection does not mean guaranteed format compatibility.** LibreView and MiniMed CareLink remain the original validated paths. Dexcom EGV CSV and several generic structured data formats have synthetic parser tests; other device exports are attempted with strict field validation and a clear rejection if not safely interpreted. A successful parser test does not clinically validate the result.
A generic strict import layer now supports structured tables; **native proprietary exports still need verified brand-specific parsers and example files**.

## Version 2026-11: guided setup and structured-device import

**Three completed steps:** Select one sensor (unlocks pump choices), select a pump or
**No insulin pump** (unlocks the clock settings), and explicitly choose 12h/24h.
Each completed step turns green and receives a check mark. Continue is only enabled
when all three choices are complete.

**Accepted input file containers:** `.csv`, `.tsv`, `.xlsx`, `.json`, `.pdf`, `.docx`
(maximum 30 MiB per file). **Accepted content** is narrower: GLUCOLAB requires
individual timestamped sensor glucose readings with unambiguous units (mg/dL or
mmol/L) and, for pump analysis, individual timestamped basal-rate values explicitly
labelled U/h. It validates the data fields and may reject files with supported
extensions if their layouts cannot be safely interpreted.

* LibreView historical exports (Record Type 0): tested with provided examples.
* Dexcom Clarity EGV `.csv`: tested against a representative synthetic export
  with labelled glucose readings and ISO timestamps. Dexcom publishes CSV exports.
* Tidepool-style `cbg` JSON: tested against representative synthetic records.
* Sensor glucose tables in CSV/TSV/Excel, text-extractable PDF tables, or Word
  tables: **best effort**, not guaranteed for any manufacturer or layout.
* MiniMed 600/700 CareLink dated basal-rate CSV: original exploratory candidate
  schedule/simulation path, still **NOT** verified programmed pump settings.
* Other pumps: only if the actual file contains clear timestamped basal-rate U/h
  data. GLUCOLAB reports descriptive pump observations and **suppresses simulated
  dose/schedule changes** because those vendors' event semantics aren't verified.

A selected device does **not** mean its proprietary export is supported. Scanned
PDFs, text-only PDF reports, Word narratives, graph images, binary device downloads,
bolus-only records, ambiguous units and incompatible/UTC-only timestamps are not
converted into readings. Do not upload patient-identifiable clinical records to a
publicly deployed beta. Independent security, vendor-format and clinical validation
are required before medical use.

**Preferred format:** raw manufacturer CSV or structured JSON. If GLUCOLAB rejects
an export, do not rename its file extension; obtain the original data export and
validate the actual column layout before adding a device-specific reader.

External documentation:

* Dexcom official CSV FAQ: https://www.dexcom.com/en-us/m/faqs/can-i-export-raw-data
* LibreView source: https://www.freestyle.abbott/en-us/support/faq/apps/downloading-glucose-data-from-the-freestyle-libre-3-app.html
* Tidepool supported device guide: https://www.tidepool.org/devices
* Tidepool data model: https://tidepool.redocly.app/docs/device-data/common-fields
