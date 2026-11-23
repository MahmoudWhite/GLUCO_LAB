#chatgpt

import pandas as pd

# STEP 1: Load LibreView CSV file
from tkinter import Tk, filedialog

root = Tk()
root.withdraw()

file_path = filedialog.askopenfilename(
    title="Select LibreView CSV File",
    filetypes=[("CSV files", "*.csv")]
)

root.destroy()

if not file_path:
    raise SystemExit("No CSV file selected.")

df = pd.read_csv(
    file_path,
    skiprows=1,
    low_memory=False
)

# STEP 2: Clean column names
df.columns = df.columns.str.strip()

# STEP 3: Select historical glucose readings
df = df[
    pd.to_numeric(df["Record Type"], errors="coerce") == 0
].copy()

# STEP 4: Identify glucose column and unit
if "Historic Glucose mg/dL" in df.columns:
    glucose_col = "Historic Glucose mg/dL"
    unit = "mg/dL"
    hypo_threshold = 70

elif "Historic Glucose mmol/L" in df.columns:
    glucose_col = "Historic Glucose mmol/L"
    unit = "mmol/L"
    hypo_threshold = 3.9

else:
    raise ValueError("Glucose column not found")

# STEP 5: Convert timestamps
df["timestamp"] = pd.to_datetime(
    df["Device Timestamp"],
    format="mixed",
    dayfirst=True,
    errors="coerce"
)

# STEP 6: Convert glucose readings
df["bg"] = pd.to_numeric(
    df[glucose_col],
    errors="coerce"
)

# STEP 7: Remove invalid readings
df = df.dropna(subset=["timestamp", "bg"])
df = df[df["bg"] > 0].copy()

# Remove duplicate timestamps
df = df.sort_values("timestamp")
df = df.drop_duplicates(subset=["timestamp"])


# STEP 8: Function to detect hypoglycemia episodes
def detect_hypos(data, threshold):
    episodes = []

    active = False
    start = None
    last_low = None
    recovery_start = None
    previous_time = None

    minimum_duration = pd.Timedelta(minutes=15)
    maximum_gap = pd.Timedelta(minutes=20)

    def save_episode():
        if (active and start is not None
                and last_low is not None
                and last_low - start >= minimum_duration):
            episodes.append(start)

    for time, bg in zip(data["timestamp"], data["bg"]):

        # Large gaps break an episode
        if (previous_time is not None and
                time - previous_time > maximum_gap):
            save_episode()
            active = False
            start = None
            last_low = None
            recovery_start = None

        previous_time = time

        if bg < threshold:
            if not active:
                active = True
                start = time

            last_low = time
            recovery_start = None

        elif active:
            if recovery_start is None:
                recovery_start = time

            elif time - recovery_start >= minimum_duration:
                save_episode()
                active = False
                start = None
                last_low = None
                recovery_start = None

    # Check the final episode
    save_episode()

    return episodes


# STEP 9: Ask user for number of days
try:
    days = int(input("Enter time range in days: "))

except ValueError:
    days = 0

# STEP 10: Check requested range
if days <= 0 or df.empty:
    print("Range not found")

else:
    # Use latest recorded date in CSV
    end_date = df["timestamp"].max().normalize()

    # Calculate starting date
    start_date = end_date - pd.Timedelta(days=days - 1)

    range_end = end_date + pd.Timedelta(days=1)

    # STEP 11: Filter selected range
    range_df = df[
        (df["timestamp"] >= start_date) &
        (df["timestamp"] < range_end)
    ].copy()

    # Count days containing readings
    available_days = (
        range_df["timestamp"].dt.normalize().nunique()
    )

    # STEP 12: Check if all requested days exist
    if available_days < days:
        print("Range not found")

    else:
        # STEP 13: Extract hour (0 to 23)
        range_df["hour"] = range_df["timestamp"].dt.hour

        # STEP 14: Calculate average BG for each hour
        hourly_means = (
            range_df.groupby("hour")["bg"].mean()
        )

        # STEP 15: Create dictionary with 24 entries
        hourly_bg = {
            hour: (
                round(float(hourly_means[hour]), 2)
                if hour in hourly_means.index
                else None
            )
            for hour in range(24)
        }

        # STEP 16: Detect hypoglycemia episodes
        # Use full history to identify episode start times
        all_hypos = detect_hypos(df, hypo_threshold)

        # STEP 17: Keep episodes starting in selected range
        selected_hypos = [
            time for time in all_hypos
            if start_date <= time < range_end
        ]

        # STEP 18: Count episodes for each hour
        hypo_episodes = {
            hour: sum(
                1 for time in selected_hypos
                if time.hour == hour
            )
            for hour in range(24)
        }

        # STEP 19: Print results
        print("\nAverage BG for each hour (" + unit + ")")
        print("Last", days, "days")
        print("From:", start_date.date())
        print("To:", end_date.date())

        print("\nHourly BG:")
        for hour, bg in hourly_bg.items():
            print(f"Hour {hour}: {bg}")

        print("\nHypoglycemia episodes per hour:")
        for hour, episodes in hypo_episodes.items():
            if episodes > 0:
                print(f"Hour {hour}: {episodes}")

        print("\nTotal hypoglycemia episodes:", len(selected_hypos))
#chatgpt ends
basal={}
n=float(input("\n24 hrs total active basal:"))
aold=0
bold=0
i=1
total=0
print("24hr Format:\n")
while total < n:
    #or while total<23:
    a = int(input(f"Timeframe {i} (start): "))
    if aold>a:
        print("Time conflict (please restart)")
        break
    b = int(input(f"Timeframe {i} (end): "))
    if bold>b:
        print("Time conflict (please restart)")
        break
    if a>b:
        print("Invalid timeframe (please restart)")
        break
    aold=a
    bold=b
    basal[f"hr: {a}",f"hr: {b}"]=float(input(f"Rate of unit(s)/hr taken from {a} --> {b} :"))
    print()
    total+=basal[f"hr: {a}",f"hr: {b}"]+(b-a)
    for bt in range(a,b+1):
        # or total+=1
        if hourly_bg[bt] >=180 and hypo_episodes[bt]==0:
            basal[f"hr: {a}",f"hr: {b}"]+=0.05
            break
        if hourly_bg[bt] <180 and hypo_episodes[bt]>0:
            basal[f"hr: {a}",f"hr: {b}"]-=0.05
            break
    i+=1
if total > n:
    print("invalid total (please check your ranges again)")
else:
    for i in basal:
        print(i,basal[i])
        print()