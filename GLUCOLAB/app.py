"""GLUCOLAB: exploratory LibreView + Medtronic CSV dashboard.

Local use: python app.py then http://127.0.0.1:8000
Public beta: deploy with `render.yaml` and GLUCOLAB_PUBLIC=1.
Public hosting requires independent security/privacy review before clinical data use.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from device_imports import normalize_glucose, normalize_pump, ImportProblem, ALLOWED_EXTENSIONS

ROOT = Path(__file__).resolve().parent
MAX_CHART_POINTS = 12000
EPISODE_GAP_MINUTES = 20
RECENT_DAYS = 14  # automatic fallback relative to the latest LibreView reading
PUBLIC_MODE = os.getenv("GLUCOLAB_PUBLIC", "0") == "1"
# File-size caps protect both public beta and local import routines.
MAX_PUBLIC_FILE_BYTES = 30 * 1024 * 1024
MAX_PUBLIC_REQUEST_BYTES = 64 * 1024 * 1024


class InputError(ValueError):
    """A readable, non-sensitive validation error to show in the browser."""


def uploaded_csv(data: bytes | BinaryIO, required: set[str], description: str) -> pd.DataFrame:
    """Read from a seekable upload stream. The request body is never read into one bytes object.

    FastAPI UploadFile uses a spooled file, moving large uploads to temporary disk.
    There is deliberately no application-level file-size cutoff; RAM/disk remain finite.
    """
    source = io.BytesIO(data) if isinstance(data, bytes) else data
    source.seek(0)
    prefix = source.read(4096)
    if not prefix:
        raise InputError(f"The {description} file is empty.")
    if b"\x00" in prefix and not prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise InputError(f"The {description} file doesn't appear to be a text CSV.")

    encodings = ["utf-16"] if prefix.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "cp1252"]
    for encoding in encodings:
        source.seek(0)
        reader = io.TextIOWrapper(source, encoding=encoding, newline="")
        header_index = None
        try:
            for i in range(65):
                line = reader.readline()
                if not line:
                    break
                try:
                    cells = next(csv.reader([line]))
                except csv.Error:
                    continue
                names = {str(c).strip().lstrip("\ufeff").casefold() for c in cells}
                if required.issubset(names):
                    header_index = i
                    break
        except UnicodeDecodeError:
            pass
        finally:
            reader.detach()  # do not close the underlying UploadFile
        if header_index is None:
            continue
        source.seek(0)
        try:
            df = pd.read_csv(source, skiprows=header_index, encoding=encoding,
                             dtype=str, low_memory=False)
        except UnicodeDecodeError:
            continue
        except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
            raise InputError(f"The {description} CSV couldn't be read: {str(exc)[:160]}") from exc
        df.columns = df.columns.map(lambda name: str(name).strip().lstrip("\ufeff"))
        return df
    raise InputError(
        f"The {description} CSV has no recognizable header or encoding. "
        f"Expected columns including: {', '.join(sorted(required))}."
    )


def parse_timestamps(series: pd.Series, *, day_first: bool) -> pd.Series:
    """Parse known date layouts explicitly to avoid silent day/month mistakes."""
    values = series.fillna("").astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    # Year-first is unambiguous. The day/month choice is user-controllable.
    formats = [
        "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %I:%M:%S %p", "%Y-%m-%d %I:%M:%S %p",
    ]
    order = ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y") if day_first else (
        "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y"
    )
    for date_fmt in order:
        for time_fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
            formats.append(f"{date_fmt} {time_fmt}")
    for fmt in formats:
        candidate = pd.to_datetime(values, format=fmt, errors="coerce")
        parsed = parsed.fillna(candidate)
    return parsed


def minute_of_day(value: str) -> int:
    try:
        hour, minute = (int(x) for x in value.split(":"))
    except (ValueError, AttributeError):
        raise InputError("Time must be in HH:MM format.") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise InputError("Enter a time from 00:00 to 23:59.")
    return hour * 60 + minute


class TimeWindow:
    """Clock-time window plus optional calendar dates, shared by both files."""

    def __init__(self, start_time: str, end_time: str, start_date: str, end_date: str):
        self.start = minute_of_day(start_time)
        self.end = minute_of_day(end_time)
        self.start_time = start_time
        self.end_time = end_time
        try:
            self.start_date = date.fromisoformat(start_date) if start_date else None
            self.end_date = date.fromisoformat(end_date) if end_date else None
        except ValueError:
            raise InputError("Dates must be valid dates in YYYY-MM-DD format.") from None
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise InputError("Start date must not be after end date.")

    def mask(self, timestamps: pd.Series) -> pd.Series:
        minutes = timestamps.dt.hour * 60 + timestamps.dt.minute
        if self.start == self.end:
            mask = pd.Series(True, index=timestamps.index)
        elif self.start < self.end:
            mask = (minutes >= self.start) & (minutes < self.end)
        else:
            mask = (minutes >= self.start) | (minutes < self.end)
        if self.start_date:
            mask &= timestamps.dt.date >= self.start_date
        if self.end_date:
            mask &= timestamps.dt.date <= self.end_date
        return mask & timestamps.notna()

    def as_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_date": str(self.start_date) if self.start_date else None,
            "end_date": str(self.end_date) if self.end_date else None,
            "all_hours": self.start == self.end,
        }


def numeric_or_none(value) -> float | None:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return None
    return round(float(value), 2)


def date_string(ts) -> str | None:
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d %H:%M")


class LibreAnalyzer:
    """Historical CGM analysis based on the previous LibreView Record Type 0 code."""

    def __init__(self, contents: bytes | BinaryIO, day_first: bool = True):
        original = uploaded_csv(contents, {"record type", "device timestamp"}, "LibreView")
        lower_to_actual = {name.casefold(): name for name in original.columns}
        glucose_cols = [
            name for name in original.columns
            if name.casefold().startswith("historic glucose")
            and ("mg/dl" in name.casefold() or "mmol/l" in name.casefold())
        ]
        if not glucose_cols:
            raise InputError(
                "LibreView needs a 'Historic Glucose (mg/dL)' or "
                "'Historic Glucose (mmol/L)' column."
            )
        glucose_col = glucose_cols[0]
        self.unit = "mmol/L" if "mmol/l" in glucose_col.casefold() else "mg/dL"
        self.low, self.high = (3.9, 10.0) if self.unit == "mmol/L" else (70.0, 180.0)
        keep = original.loc[
            pd.to_numeric(original[lower_to_actual["record type"]], errors="coerce").eq(0)
        ].copy()
        keep["timestamp"] = parse_timestamps(
            keep[lower_to_actual["device timestamp"]], day_first=day_first
        )
        keep["glucose"] = pd.to_numeric(keep[glucose_col], errors="coerce")
        self.data = (keep[["timestamp", "glucose"]]
                     .dropna()
                     .drop_duplicates(subset="timestamp")
                     .sort_values("timestamp")
                     .reset_index(drop=True))
        if self.data.empty:
            raise InputError("The LibreView file contains no usable historic glucose readings.")

    def _episodes(self) -> list[dict]:
        """Count distinct low runs; a gap >20 min starts a new episode."""
        events: list[dict] = []
        current = None
        last_timestamp = None
        for item in self.data.itertuples(index=False):
            stamp = item.timestamp
            glucose = float(item.glucose)
            too_far = (
                last_timestamp is not None
                and (stamp - last_timestamp).total_seconds() > EPISODE_GAP_MINUTES * 60
            )
            if glucose < self.low:
                if current is None or too_far:
                    if current is not None:
                        events.append(current)
                    current = {"start": stamp, "end": stamp,
                               "lowest": glucose, "readings": 1}
                else:
                    current["end"] = stamp
                    current["lowest"] = min(current["lowest"], glucose)
                    current["readings"] += 1
            else:
                if current is not None:
                    events.append(current)
                    current = None
            last_timestamp = stamp
        if current is not None:
            events.append(current)
        return events

    def analyze(self, window: TimeWindow) -> dict:
        selected = self.data.loc[window.mask(self.data["timestamp"])].copy()
        if selected.empty:
            raise InputError("No LibreView readings match the selected dates and hours.")
        values = selected["glucose"]
        min_row = selected.loc[values.idxmin()]
        max_row = selected.loc[values.idxmax()]
        hourlybg: dict[int, float | None] = {}
        hourly_readings: dict[int, int] = {}
        hourly_low: dict[int, int] = {}
        for hour in range(24):
            hour_values = selected.loc[selected["timestamp"].dt.hour == hour, "glucose"]
            hourlybg[hour] = numeric_or_none(hour_values.mean()) if not hour_values.empty else None
            hourly_readings[hour] = int(len(hour_values))
            hourly_low[hour] = int((hour_values < self.low).sum())

        selected_episodes = [
            event for event in self._episodes()
            if bool(window.mask(pd.Series([event["start"]])).iloc[0])
        ]
        hypo_events_per_hour = {hour: 0 for hour in range(24)}
        for event in selected_episodes:
            hypo_events_per_hour[event["start"].hour] += 1

        grouped = selected.groupby(selected["timestamp"].dt.date)["glucose"]
        daily = [{
            "date": str(day), "mean": numeric_or_none(vals.mean()),
            "min": numeric_or_none(vals.min()), "max": numeric_or_none(vals.max()),
            "readings": int(len(vals)),
        } for day, vals in grouped]

        # Preserve contiguous traces. The old global stride discarded 5-minute
        # samples and made points >20 minutes apart; the browser then drew no line.
        # Identify real gaps BEFORE downsampling. Sample within each continuous run
        # and tell the browser which runs start a new trace.
        chronological = selected.reset_index(drop=True)
        runs = chronological["timestamp"].diff().gt(pd.Timedelta(minutes=EPISODE_GAP_MINUTES)).cumsum()
        stride = max(1, math.ceil(len(chronological) / MAX_CHART_POINTS))
        keep_indices = set()
        for _, group in chronological.groupby(runs):
            indices = list(group.index)
            keep_indices.update(indices[::stride])
            keep_indices.add(indices[-1])
        sampled = chronological.loc[sorted(keep_indices)]
        trend = []
        previous_run = None
        for idx, row in sampled.iterrows():
            run_number = int(runs.loc[idx])
            trend.append({
                "time": date_string(row["timestamp"]),
                "epoch": int(row["timestamp"].value // 1_000_000),
                "value": round(float(row["glucose"]), 2),
                "break_before": previous_run is None or run_number != previous_run,
            })
            previous_run = run_number

        # AGP-style 24-hour glucose distribution. Use each observed LibreView
        # reading's local clock time, grouped into 30-minute bins; do not invent
        # readings between gaps. Sparse bins remain empty rather than implying
        # percentile estimates from a single day or a few observations.
        profile_data = selected.copy()
        profile_data["half_hour"] = (
            profile_data["timestamp"].dt.hour * 2
            + profile_data["timestamp"].dt.minute // 30
        )
        profile_data["calendar_day"] = profile_data["timestamp"].dt.date
        profile_groups = profile_data.groupby("half_hour")
        agp_bins = []
        for slot in range(48):
            if slot not in profile_groups.groups:
                agp_bins.append({"minute": slot * 30, "readings": 0, "days": 0,
                                 "p05": None, "p25": None, "p50": None,
                                 "p75": None, "p95": None})
                continue
            group = profile_groups.get_group(slot)
            sample_count = int(len(group))
            days_count = int(group["calendar_day"].nunique())
            result = {"minute": slot * 30, "readings": sample_count,
                      "days": days_count, "p05": None, "p25": None,
                      "p50": None, "p75": None, "p95": None}
            if sample_count >= 5 and days_count >= 2:
                q = group["glucose"].quantile([.05, .25, .50, .75, .95])
                for key, at in (("p05", .05), ("p25", .25), ("p50", .50),
                                ("p75", .75), ("p95", .95)):
                    result[key] = round(float(q.loc[at]), 2)
            agp_bins.append(result)

        mean = float(values.mean())
        std = float(values.std()) if len(values) > 1 else None
        summary = {
            "readings": int(len(selected)),
            "total_readings": int(len(self.data)),
            "from": date_string(selected["timestamp"].min()),
            "to": date_string(selected["timestamp"].max()),
            "mean": numeric_or_none(mean),
            "median": numeric_or_none(values.median()),
            "std_dev": numeric_or_none(std),
            "coefficient_of_variation_pct": numeric_or_none(100 * std / mean) if std is not None and mean else None,
            "lowest": numeric_or_none(min_row["glucose"]),
            "lowest_at": date_string(min_row["timestamp"]),
            "highest": numeric_or_none(max_row["glucose"]),
            "highest_at": date_string(max_row["timestamp"]),
            "below_pct": round(100 * float((values < self.low).mean()), 1),
            "in_range_pct": round(100 * float(((values >= self.low) & (values <= self.high)).mean()), 1),
            "above_pct": round(100 * float((values > self.high).mean()), 1),
            "low_readings": int((values < self.low).sum()),
            "hypo_episodes": len(selected_episodes),
        }
        return {
            "unit": self.unit, "low": self.low, "high": self.high,
            "summary": summary, "hourlybg": hourlybg,
            "hypo_events_per_hour": hypo_events_per_hour,
            "hourly": [{"hour": f"{hour:02d}:00", "average": hourlybg[hour],
                        "readings": hourly_readings[hour],
                        "low_readings": hourly_low[hour],
                        "episodes": hypo_events_per_hour[hour]}
                       for hour in range(24)],
            "daily": daily,
            "episodes": [{"started": date_string(ev["start"]),
                          "ended": date_string(ev["end"]),
                          "lowest": numeric_or_none(ev["lowest"]),
                          "readings": ev["readings"]}
                         for ev in selected_episodes],
            "trend": trend,
            "agp": {"bin_minutes": 30, "bins": agp_bins,
                    "minimum_readings_per_bin": 5,
                    "minimum_days_per_bin": 2,
                    "method": "Observed historical glucose values aggregated by local clock time; 5th/25th/50th/75th/95th percentiles"},
        }


class PumpAnalyzer:
    """Medtronic CSV recorded basal-rate entries (not delivered insulin)."""

    def __init__(self, contents: bytes | BinaryIO, day_first: bool = False):
        original = uploaded_csv(contents, {"date", "time", "basal rate (u/h)"}, "Medtronic")
        columns = {name.casefold(): name for name in original.columns}
        combined = (original[columns["date"]].fillna("").str.strip() + " "
                    + original[columns["time"]].fillna("").str.strip())
        original["timestamp"] = parse_timestamps(combined, day_first=day_first)
        original["basal"] = pd.to_numeric(original[columns["basal rate (u/h)"]], errors="coerce")
        # A recorded basal-rate change is NOT proof a *programmed basal profile* was edited.
        # Only an explicit labeled schedule/profile programming event is used as an auto anchor.
        event_columns = [name for name in original.columns
                         if name.casefold() in {"event marker", "device update event", "event", "activity", "description"}]
        explicit = pd.Series(False, index=original.index)
        for name in event_columns:
            desc = original[name].fillna("").str.lower()
            explicit |= (desc.str.contains(r"basal.*(?:profile|pattern|schedule)|(?:profile|pattern|schedule).*basal", regex=True)
                         & desc.str.contains(r"edit|chang|updat|program|modif|set", regex=True))
        edits = original.loc[explicit, "timestamp"].dropna()
        self.last_schedule_edit = edits.max() if not edits.empty else None
        suspend_column = columns.get("suspend")
        if suspend_column is not None:
            self.suspend_events = (original[["timestamp", suspend_column]]
                                   .dropna().rename(columns={suspend_column: "suspend"})
                                   .sort_values("timestamp").reset_index(drop=True))
        else:
            self.suspend_events = pd.DataFrame(columns=["timestamp", "suspend"])
        self.data = (original[["timestamp", "basal"]].dropna()
                     .loc[lambda df: (df["basal"] >= 0) & (df["basal"] <= 100)]
                     .sort_values("timestamp").reset_index(drop=True))
        if self.data.empty:
            raise InputError("The Medtronic CSV contains no usable dated basal-rate entries.")

    def observed_profile(self, earliest: pd.Timestamp, latest: pd.Timestamp) -> tuple[list[dict], dict]:
        """Build candidate RECORDED rate ranges, explicitly excluding interruptions.

        Medtronic's 'Basal Rate (U/h)' is an *active* basal delivery rate,
        NOT a programmer-readable basal-profile snapshot.  Suspension/resumption
        records may interrupt delivery with transient zero and restoration rates.

        For the selected day we use positive rates at whole-second clock times.
        If the export contains a recurrent set of candidate time boundaries
        (seen on >=2 different calendar days), only that recurrent set is used.
        This reduces one-off delivery-event artifacts. Consecutive equal rates
        are merged for readability; source/profile boundaries are unverified.

        Select the most RECENT completed candidate day at/before the CGM cutoff.
        Do not prefer whichever day has the most (possibly spurious) events.
        Never extend morning-only observations to 24:00.
        """
        recent = self.data.loc[(self.data["timestamp"] >= earliest)
                               & (self.data["timestamp"] <= latest)].copy()
        events = [{"timestamp": date_string(r.timestamp), "rate": round(float(r.basal), 3)}
                  for r in recent.tail(30).itertuples(index=False)]
        info = {"recent_rate_entries": len(recent), "observed_events": events,
                "profile_day": None, "profile_complete": False,
                "range_note": "", "partial_ranges": [],
                "source": "Recorded pump rates (NOT confirmed programmed settings)",
                "profile_discrepancies": [], "candidate_days_checked": 0,
                "excluded_rate_entries": 0, "suspension_events_on_day": 0}
        if recent.empty:
            info["range_note"] = "No dated Medtronic basal-rate entries overlap the recent LibreView analysis window."
            return [], info

        # Count distinct dates, not duplicate rows: a routine scheduled time
        # repeats each day, whereas many suspend/resume events are one-off.
        positive = self.data.loc[(self.data["basal"] > 0)
                                 & (self.data["timestamp"].dt.second == 0)].copy()
        positive["clock"] = positive["timestamp"].dt.strftime("%H:%M:%S")
        positive["day"] = positive["timestamp"].dt.date
        counts = positive.groupby("clock")["day"].nunique()
        common_times = set(counts.index[counts >= 2])
        # Small uploads with just one example day cannot establish recurrence.
        # Still allow strictly whole-second positive rate observations, but
        # make it clear the result is an unverified example.
        use_recurrent = (len(common_times) >= 3 and
                         any(int(t[:2]) >= 18 for t in common_times))

        day_records = []
        for day, grp in recent.groupby(recent["timestamp"].dt.date):
            eligible = grp.loc[(grp["basal"] > 0) & (grp["timestamp"].dt.second == 0)].copy()
            if use_recurrent:
                eligible = eligible.loc[eligible["timestamp"].dt.strftime("%H:%M:%S")
                                        .isin(common_times)]
            by_minute: dict[int, float] = {}
            for row in eligible.itertuples(index=False):
                minute = int(row.timestamp.hour * 60 + row.timestamp.minute)
                by_minute[minute] = round(float(row.basal), 3)
            points = sorted(by_minute.items())
            collapsed = [(minute, rate) for i, (minute, rate) in enumerate(points)
                         if i == 0 or rate != points[i - 1][1]]
            if not collapsed or len(collapsed) > 96:
                continue
            past_day = day < latest.date()
            near_end_of_day = day == latest.date() and latest.hour >= 23
            # Demand an evening boundary. A day that has only morning rows is
            # not evidence for a full 24-hour candidate pattern.
            potentially_complete = (points[0][0] == 0
                                    and points[-1][0] >= 18 * 60
                                    and (past_day or near_end_of_day))
            excluded = len(grp) - len(eligible)
            day_records.append({"day": day, "points": collapsed,
                                "complete": potentially_complete,
                                "excluded": excluded})

        info["candidate_days_checked"] = len(day_records)
        complete_days = [d for d in day_records if d["complete"] and len(d["points"]) >= 2]
        if complete_days:
            # RECENCY, not maximum number of changes, is the primary selector.
            selected = max(complete_days, key=lambda d: (d["day"], len(d["points"])))
            day, points = selected["day"], selected["points"]
            ranges = [
                {"start_minute": start,
                 "end_minute": points[i + 1][0] if i + 1 < len(points) else 1440,
                 "original_rate": rate, "source_day": str(day)}
                for i, (start, rate) in enumerate(points)
            ]
            info["profile_day"] = str(day)
            info["profile_complete"] = True
            info["excluded_rate_entries"] = int(selected["excluded"])
            if not self.suspend_events.empty:
                info["suspension_events_on_day"] = int(
                    (self.suspend_events["timestamp"].dt.date == day).sum())
            info["source"] = ("Most recent completed candidate day with recurring clock-time basal observations "
                              "(NOT programmed settings)" if use_recurrent else
                              "Most recent completed candidate day with positive whole-second basal observations "
                              "(recurrence not established; NOT programmed settings)")
            discrepancies = []
            for minute, chosen_rate in points:
                other_rates = sorted({rate for d in day_records if d["day"] != day
                                      for t, rate in d["points"] if t == minute and rate != chosen_rate})
                if other_rates:
                    discrepancies.append({"time": clock(minute), "selected_rate": chosen_rate,
                                          "other_rates": other_rates})
            info["profile_discrepancies"] = discrepancies
            latest_eligible_day = max(d["day"] for d in day_records)
            late_note = (f" The later day {latest_eligible_day} is incomplete or has too few transitions "
                         "and has not been projected to midnight." if latest_eligible_day > day else "")
            matching_note = (" Recurrence of candidate start times was observed on at least two dates."
                             if use_recurrent else
                             " There is insufficient data to confirm repeating clock-time boundaries.")
            info["range_note"] = (
                f"Candidate {len(ranges)} merged rate intervals from {day}, the most recent "
                f"completed eligible pump day before the LibreView cutoff. "
                "Excluded zero-rate delivery interruptions and nonrecurring second-level "
                "rate events; adjacent equal rates were merged. "
                f"Excluded {selected['excluded']} transient/zero-rate entries on the selected date; "
                f"identified {info['suspension_events_on_day']} explicit suspend/resume events. "
                "These are UNVERIFIED recorded intervals, not a programmed basal profile."
                + matching_note + late_note)
            if discrepancies:
                info["range_note"] += (
                    " Other dates contain DIFFERENT rates at matching clock times; "
                    "confirm actual pump settings with the device settings report.")
            return ranges, info

        partial_candidates = [d for d in day_records if len(d["points"]) >= 2]
        if partial_candidates:
            selected = max(partial_candidates, key=lambda d: (d["day"], len(d["points"])))
            day, points = selected["day"], selected["points"]
            info["partial_ranges"] = [
                {"date": str(day), "start": clock(start), "end": clock(points[i + 1][0]),
                 "rate": rate}
                for i, (start, rate) in enumerate(points[:-1])
            ]
            info["range_note"] = (
                f"Only partial observed rate intervals on {day} were found. "
                "A reliable full-day candidate cannot be inferred: a recent day has "
                "no adequate midnight-to-evening evidence. Delivery interruptions "
                "are excluded. Confirm the programmed pattern in the pump settings report.")
            return [], info

        info["range_note"] = (
            "One recorded rate cannot establish a full-day pattern. No suitable "
            "repeated positive-rate start times were found. "
            "For confirmed ranges use the Medtronic Device Settings / Basal Pattern report.")
        return [], info

    def analyze(self, window: TimeWindow) -> dict:
        selected = self.data.loc[window.mask(self.data["timestamp"])].copy()
        # The pump data may legitimately contain no basal observations in this window.
        if selected.empty:
            return {"summary": {"entries": 0, "total_entries": len(self.data),
                                "mean": None, "min": None, "max": None,
                                "from": None, "to": None},
                    "hourly": [{"hour": f"{hour:02d}:00", "average": None, "entries": 0}
                               for hour in range(24)]}
        values = selected["basal"]
        hourly = []
        for hour in range(24):
            hour_values = selected.loc[selected["timestamp"].dt.hour == hour, "basal"]
            hourly.append({"hour": f"{hour:02d}:00",
                           "average": numeric_or_none(hour_values.mean()) if len(hour_values) else None,
                           "entries": int(len(hour_values))})
        return {"summary": {"entries": int(len(selected)),
                            "total_entries": int(len(self.data)),
                            "mean": numeric_or_none(values.mean()),
                            "min": numeric_or_none(values.min()),
                            "max": numeric_or_none(values.max()),
                            "from": date_string(selected["timestamp"].min()),
                            "to": date_string(selected["timestamp"].max())},
                "hourly": hourly}


def clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def segment_hours(start: int, end: int) -> list[int]:
    """Hours touching a segment, including intervals wrapping over midnight."""
    if start == end:
        return list(range(24))
    intervals = [(start, end)] if start < end else [(start, 1440), (0, end)]
    return [h for h in range(24)
            if any(h * 60 < b and (h + 1) * 60 > a for a, b in intervals)]


def integrated_daily_basal(segments: list[dict], rate_key: str) -> float | None:
    """Hypothetical 24h quantity (U), not actual delivered insulin.

    A complete, non-overlapping midnight-to-midnight schedule is necessary.
    Do NOT sum rates in U/h, and do NOT estimate totals for partial days.
    """
    if not segments:
        return None
    total, next_start = 0.0, 0
    for seg in sorted(segments, key=lambda x: minute_of_day(x["start"])):
        start = minute_of_day(seg["start"])
        end = 1440 if seg["end"] == "24:00" else minute_of_day(seg["end"])
        rate = seg.get(rate_key)
        if start != next_start or end <= start or end > 1440 or rate is None:
            return None
        rate = float(rate)
        if not math.isfinite(rate) or rate < 0:
            return None
        total += rate * ((end - start) / 60.0)
        next_start = end
    return round(total, 4) if next_start == 1440 else None


class BasalPatternReview:
    """Demonstrate the user's proposed threshold rules, *not* a dosing algorithm.

    The generated rate table is a hypothetical comparison to an unverified
    reconstruction of recorded rates. It MUST NOT be used to program a pump.
    """

    def __init__(self, libre: LibreAnalyzer, pump: PumpAnalyzer, anchor: pd.Timestamp | None,
                 anchor_source: str, window_start: pd.Timestamp):
        self.window_start = window_start
        self.libre = libre
        self.pump = pump
        self.anchor = anchor
        self.anchor_source = anchor_source

    def analyze(self) -> dict:
        info = {
            "status": "review_only_unknown_edit" if self.anchor is None else "review_only",
            "last_edit": date_string(self.anchor) if self.anchor is not None else None,
            "anchor_source": self.anchor_source,
            "last_glucose": date_string(self.libre.data["timestamp"].max()),
            "glucose_start": None, "glucose_end": None,
            "glucose_readings": 0,
            "recent_days": RECENT_DAYS,
            "window_start": date_string(self.window_start),
            "profile_day": None, "profile_complete": False,
            "range_note": "", "observed_events": [], "partial_ranges": [], "recent_rate_entries": 0,
            "profile_source": "Unverified, recorded pump rate transitions (NOT a programmed profile)",
            "hourly_evidence": [], "segments": [],
            "observed_daily_basal_u": None,
            "illustrative_daily_basal_u": None,
            "illustrative_daily_difference_u": None,
            "warnings": [
                "Illustrative calculation only. Never enter the displayed rates into a pump without professional review.",
                "CareLink basal-rate entries are not proof of the current programmed basal schedule; temporary or automated delivery may differ.",
                "A glucose pattern alone cannot establish which insulin change is appropriate.",
            ],
            "rules": {
                "high_day_cutoff_mg_dl": 200,
                "average_cutoff_mg_dl": 200,
                "two_days_above": "Daily mean for the hour >200 mg/dL on at least two distinct dates",
                "overall_average": "Mean for the hour >=200 mg/dL in the available analysis window",
                "repeat_low": "Distinct low-episode starts in the same clock hour on adjacent dates",
                "same_segment": "Apply at most one illustrative 0.05 U/h step per rate segment",
                "conflicts": "A simultaneous high and repeated-low signal is flagged for review, without changing the illustrative rate",
            },
        }
        if self.anchor is None:
            info["warnings"].append(
                "No explicit basal-profile edit event was found in the Medtronic CSV. "
                "Only the latest 14 days of LibreView readings are analyzed; this period is NOT verified "
                "as starting when the programmed basal-profile was changed."
            )
        data = self.libre.data.loc[self.libre.data["timestamp"] >= self.window_start].copy()
        if self.anchor is not None:
            data = data.loc[data["timestamp"] > self.anchor].copy()
        if data.empty:
            info["status"] = "no_data"
            info["warnings"].append("No LibreView readings occurred after the stated last basal schedule edit.")
            return info
        info["glucose_start"] = date_string(data["timestamp"].min())
        info["glucose_end"] = date_string(data["timestamp"].max())
        info["glucose_readings"] = int(len(data))
        info["days_observed"] = int(data["timestamp"].dt.date.nunique())
        # Convert 200 mg/dL to mmol/L when applicable, without rounding before comparisons.
        cutoff = 200.0 if self.libre.unit == "mg/dL" else 200.0 / 18.0182
        data["day"] = data["timestamp"].dt.date
        data["hour"] = data["timestamp"].dt.hour
        per_day_hour = data.groupby(["day", "hour"])["glucose"].mean()
        starts = [e["start"] for e in self.libre._episodes()
                  if self.anchor is None or e["start"] > self.anchor]
        low_dates = {h: set() for h in range(24)}
        for started in starts:
            low_dates[started.hour].add(started.date())
        hour_details = []
        for hour in range(24):
            values = data.loc[data["hour"] == hour, "glucose"]
            daily_means = [(day, float(mean)) for (day, h), mean in per_day_hour.items() if h == hour]
            dates_above = [str(day) for day, avg in daily_means if avg > cutoff]
            avg = float(values.mean()) if len(values) else None
            average_high = avg is not None and avg >= cutoff
            repeat_high = len(dates_above) >= 2
            dates_low = sorted(low_dates[hour])
            consecutive_pairs = [(str(a), str(b)) for a, b in zip(dates_low, dates_low[1:])
                                 if b - a == timedelta(days=1)]
            repeat_low = bool(consecutive_pairs)
            high = repeat_high or average_high
            hour_details.append({
                "hour": clock(hour * 60), "hour_index": hour, "average": numeric_or_none(avg),
                "days_with_readings": len(daily_means), "high_dates": dates_above,
                "two_high_days": repeat_high, "overall_average_high": average_high,
                "low_dates": [str(d) for d in dates_low], "low_consecutive_pairs": consecutive_pairs,
                "repeated_low": repeat_low,
                "signal": "conflict" if high and repeat_low else "low" if repeat_low else "high" if high else "none",
            })
        info["hourly_evidence"] = hour_details
        libre_latest = self.libre.data["timestamp"].max()
        profile, source = self.pump.observed_profile(self.window_start, libre_latest)
        info.update(source)
        info["profile_source"] = source["source"]
        latest_pump_record = self.pump.data["timestamp"].max()
        if latest_pump_record.date() > libre_latest.date():
            mismatch = (
                "DATE MISMATCH: The Medtronic export contains later pump records "
                f"(through {latest_pump_record.strftime('%Y-%m-%d')}) than the "
                f"latest LibreView reading ({libre_latest.strftime('%Y-%m-%d')}). "
                "The candidate rate pattern is from an older overlapping day, "
                "NOT the current programmed profile; later settings cannot be "
                "evaluated using these earlier glucose readings."
            )
            info["range_note"] += " " + mismatch
            info["warnings"].append(mismatch)
        if not profile:
            info["status"] = "partial_profile" if source["partial_ranges"] else "no_profile"
            info["warnings"].append(source["range_note"])
            return info
        info["warnings"].append(source["range_note"])
        for seg in profile:
            relevant = [hour_details[h] for h in segment_hours(seg["start_minute"], seg["end_minute"])]
            highs = [h["hour"] for h in relevant if h["signal"] in {"high", "conflict"}]
            lows = [h["hour"] for h in relevant if h["signal"] in {"low", "conflict"}]
            # Do not resolve mixed high/low signals automatically; require manual review.
            action = "conflict" if highs and lows else "low" if lows else "high" if highs else "unchanged"
            delta = 0.0 if action in {"conflict", "unchanged"} else (-0.05 if action == "low" else 0.05)
            baseline = float(seg["original_rate"])
            if baseline + delta < 0:
                action, delta = "conflict", 0.0
            info["segments"].append({
                "start": clock(seg["start_minute"]), "end": clock(seg["end_minute"]),
                "original_rate": round(baseline, 3), "change": round(delta, 2),
                "illustrative_rate": round(baseline + delta, 3),
                "action": action, "high_hours": highs, "low_hours": lows,
                "reason": ("Conflicting glucose patterns — requires clinical review" if action == "conflict" else
                           "Repeated low episodes on adjacent dates" if action == "low" else
                           "High daily/overall hourly glucose pattern" if action == "high" else
                           "No threshold pattern detected"),
            })
        info["observed_daily_basal_u"] = integrated_daily_basal(info["segments"], "original_rate")
        info["illustrative_daily_basal_u"] = integrated_daily_basal(info["segments"], "illustrative_rate")
        if info["observed_daily_basal_u"] is not None and info["illustrative_daily_basal_u"] is not None:
            info["illustrative_daily_difference_u"] = round(
                info["illustrative_daily_basal_u"] - info["observed_daily_basal_u"], 4
            )
        info["segments_changed"] = sum(s["change"] != 0 for s in info["segments"])
        info["segments_conflict"] = sum(s["action"] == "conflict" for s in info["segments"])
        if info["days_observed"] < 2:
            info["warnings"].append("Fewer than two calendar days are available in the analysis period; average-based signals may reflect only one day.")
        info["warnings"].append("No pump setting has been changed. This is a simulated output with an UNVERIFIED baseline.")
        return info


def format_report(libre: dict, pump: dict, pattern: dict) -> str:
    g, p = libre["summary"], pump["summary"]
    lines = [
        "GLUCOLAB / GLUCOSE + PUMP REVIEW", "=" * 66,
        f"Libre data analyzed : {g['from']} to {g['to']}",
        f"Last profile edit   : {pattern['last_edit'] or 'NOT KNOWN'} ({pattern['anchor_source']})",
        f"Pattern window      : {pattern['glucose_start'] or '--'} to {pattern['glucose_end'] or '--'}",
        f"Period verified?    : {'Explicit profile-edit event (recent subset)' if pattern['last_edit'] else 'NO — latest 14 days, edit date unknown'}",
        "", "LIBREVIEW / HISTORICAL GLUCOSE", "-" * 66,
        f"Readings            : {g['readings']:,}",
        f"Average glucose     : {g['mean']} {libre['unit']}",
        f"Lowest glucose      : {g['lowest']} {libre['unit']} at {g['lowest_at']}",
        f"Highest glucose     : {g['highest']} {libre['unit']} at {g['highest_at']}",
        f"Within target       : {g['in_range_pct']}% of readings",
        f"Hypo events         : {g['hypo_episodes']}",
        "", "HOURLY GLUCOSE / HYPOGLYCEMIA", "-" * 66,
        f"{'Hour':<8} {'Avg BG':>10} {'Readings':>10} {'Low':>7} {'Episodes':>10}",
    ]
    for row in libre["hourly"]:
        avg = "--" if row["average"] is None else str(row["average"])
        lines.append(f"{row['hour']:<8} {avg:>10} {row['readings']:>10} {row['low_readings']:>7} {row['episodes']:>10}")
    lines.extend(["", "MEDTRONIC / OBSERVED RATE ENTRIES", "-" * 66,
                  f"Observed entries   : {p['entries']:,}",
                  f"Average recorded    : {p['mean'] if p['mean'] is not None else '--'} U/h",
                  "", "SIMULATED BASAL PATTERN (NOT FOR PUMP PROGRAMMING)", "-" * 66,
                  f"Recent pump records  : {pattern['recent_rate_entries']}",
                  f"Rate-range source    : {pattern['range_note']}",
                  "It is NOT proof of actual active/programmed basal pattern."])
    if not pattern["segments"]:
        lines.append("Not computed: " + pattern["status"] + ". A usable observed rate profile and glucose records are needed.")
    else:
        lines.extend(["", "CANDIDATE RECORDED TIME RANGES (UNVERIFIED)", "-" * 66,
                      f"Reference date: {pattern['profile_day']} — NOT confirmed pump settings",
                      f"{'Time range':<22}{'Recorded rate (U/h)':>23}"])
        for seg in pattern["segments"]:
            lines.append(f"{seg['start']+' - '+seg['end']:<22}{seg['original_rate']:>23.2f}")
        observed_total = pattern.get("observed_daily_basal_u")
        lines.append(f"Estimated 24-hour candidate total : {observed_total:.3f} U/day (NOT delivered insulin)" if observed_total is not None else "Estimated 24-hour candidate total : unavailable (incomplete clock-day)")
        lines.extend(["", "ILLUSTRATIVE CHANGES (NOT FOR PUMP PROGRAMMING)", "-" * 66])
        lines.append(f"{'Time':<18} {'Observed':>10} {'Delta':>9} {'Simulated':>11}    Signal")
        for seg in pattern["segments"]:
            lines.append(f"{seg['start']+'-'+seg['end']:<18} {seg['original_rate']:>10.3f} {seg['change']:>+9.2f} "
                         f"{seg['illustrative_rate']:>11.3f}    {seg['action']}")
        simulated_total = pattern.get("illustrative_daily_basal_u")
        lines.append(f"Illustrative 24-hour total        : {simulated_total:.3f} U/day (NOT for pump programming)" if simulated_total is not None else "Illustrative 24-hour total        : unavailable (incomplete clock-day)")
    if pattern["partial_ranges"]:
        lines.extend(["", "PARTIAL RECORDED RANGES — NOT A COMPLETE BASAL PATTERN", "-" * 66])
        for seg in pattern["partial_ranges"]:
            lines.append(f"{seg['date']}  {seg['start']}–{seg['end']}  {seg['rate']:.3f} U/h")
    if pattern["observed_events"]:
        lines.extend(["", "MOST RECENT PUMP RATE RECORDS (UP TO 30)", "-" * 66])
        for event in reversed(pattern["observed_events"]):
            lines.append(f"{event['timestamp']}  {event['rate']:.3f} U/h")
    lines.extend(["", "CAUTIONS", "-" * 66, *["* " + x for x in pattern["warnings"]]])
    return "\n".join(lines)


def analyze_files(libre_file: bytes | BinaryIO, pump_file: bytes | BinaryIO, options: dict | None = None) -> dict:
    options = options or {}
    libre_obj = LibreAnalyzer(libre_file, day_first=True)
    pump_obj = PumpAnalyzer(pump_file, day_first=False)
    latest = libre_obj.data["timestamp"].max()
    earliest_recent = latest - pd.Timedelta(days=RECENT_DAYS)
    anchor = pump_obj.last_schedule_edit
    # Only explicit profile events may establish an actual edit time. All other
    # uploads automatically use a recent 14-day observation period, never 4 years.
    source = ("explicit pump event"
              if anchor is not None else "automatic last 14 days — profile edit date unknown")
    cutoff = max(earliest_recent, anchor) if anchor is not None else earliest_recent
    time_mask = (libre_obj.data["timestamp"] >= cutoff) & (libre_obj.data["timestamp"] <= latest)
    if anchor is not None:
        time_mask &= libre_obj.data["timestamp"] > anchor
    selected = libre_obj.data.loc[time_mask].copy()
    if selected.empty:
        raise InputError("There are no historical LibreView readings in the recent post-profile-edit window.")

    # Make sure every display card, chart, hourly average, and low-event result
    # uses the SAME recent dates as the basal-pattern evidence.
    scoped_libre = LibreAnalyzer.__new__(LibreAnalyzer)
    scoped_libre.unit, scoped_libre.low, scoped_libre.high = libre_obj.unit, libre_obj.low, libre_obj.high
    scoped_libre.data = selected.reset_index(drop=True)
    window = TimeWindow("00:00", "00:00", "", "")
    libre = scoped_libre.analyze(window)
    # Pump summary is limited to the same period, but schedule/event extraction
    # still examines the source data inside that period in PumpAnalyzer.
    scoped_pump = PumpAnalyzer.__new__(PumpAnalyzer)
    scoped_pump.data = pump_obj.data.loc[
        (pump_obj.data["timestamp"] >= cutoff) & (pump_obj.data["timestamp"] <= latest)
    ].copy().reset_index(drop=True)
    pump = scoped_pump.analyze(window)
    pattern = BasalPatternReview(scoped_libre, pump_obj, anchor, source, cutoff).analyze()
    return {
        "mode": "both",
        "meal_timeline": None,
        "filters": {"mode": "automatic_recent", "days": RECENT_DAYS,
                    "source": source, "from": date_string(selected["timestamp"].min()),
                    "to": date_string(latest)},
        "libre": libre, "pump": pump, "pattern": pattern,
        "report": format_report(libre, pump, pattern)
    }



def build_meal_timeline(libre: LibreAnalyzer) -> dict:
    """Describe recurring clock-time CGM patterns in 30-minute bins.

    Meal and snack labels are broad *illustrative* time-of-day categories, not
    detected meal events and not advice about when eating is allowed. Without
    a meal log and clinical context, CGM data alone cannot determine that.
    """
    data = libre.data.copy()
    # Historic values may be in mmol/L: use a unit-equivalent marker.
    threshold = 230.0 if libre.unit == "mg/dL" else 230.0 / 18.0182
    data["half_hour_bin"] = data["timestamp"].dt.hour * 2 + (data["timestamp"].dt.minute // 30)
    data["day"] = data["timestamp"].dt.date

    # Broader illustrative periods, including snacks. These are not actual
    # observed meal times or medically prescribed meal schedules.
    period_definitions = [
        ("Breakfast", "Breakfast", 5, 11),
        ("Morning snack", "S1", 11, 12),
        ("Lunch", "Lunch", 12, 17),
        ("Afternoon snack", "S2", 17, 18),
        ("Dinner", "Dinner", 18, 23),
        ("Evening snack", "S3", 23, 24),
    ]
    half_hourly = []
    for index in range(48):
        group = data.loc[data["half_hour_bin"] == index]
        values = group["glucose"]
        count, days = len(values), int(group["day"].nunique())
        median = numeric_or_none(values.median()) if count else None
        lows = int((values < libre.low).sum())
        above = int((values >= threshold).sum())
        # Avoid labeling unobserved/sparse periods. The median reflects a
        # historical clock-time pattern, NOT the user's current BG.
        if days < 3 or count < 6:
            status = "insufficient"
        elif median is not None and median >= threshold:
            status = "above-230"
        elif median is not None and median < libre.low:
            status = "low-observed"
        else:
            status = "below-230"
        half_hourly.append({
            "index": index,
            "start": clock(index * 30),
            "end": clock((index + 1) * 30),
            "start_hour": index / 2,
            "end_hour": (index + 1) / 2,
            "readings": count,
            "days": days,
            "median": median,
            "average": numeric_or_none(values.mean()) if count else None,
            "low_readings": lows,
            "at_or_above_230_readings": above,
            "status": status,
        })

    # Keep the detailed 48-bin analysis above, but expose a 24-block display.
    # A visible hour reflects BOTH of its 30-minute results. If the two
    # half-hours differ, prioritize a detected low, then a high, then missing
    # data; otherwise mark the hour below the illustrative reference marker.
    hourly_display = []
    for hour in range(24):
        half_hours = half_hourly[hour * 2:hour * 2 + 2]
        statuses = [bin_info["status"] for bin_info in half_hours]
        if "low-observed" in statuses:
            status = "low-observed"
        elif "above-230" in statuses:
            status = "above-230"
        elif "insufficient" in statuses:
            status = "insufficient"
        else:
            status = "below-230"
        hourly_display.append({
            "hour": hour,
            "start": clock(hour * 60),
            "end": clock((hour + 1) * 60),
            "status": status,
            "half_hour_statuses": statuses,
            "readings": sum(bin_info["readings"] for bin_info in half_hours),
            "days": max(bin_info["days"] for bin_info in half_hours),
        })

    def join_ranges(slots: list[dict]) -> list[dict]:
        """Merge adjacent bins of the same evidence type, preserving gaps."""
        ranges = []
        for slot in slots:
            if ranges and ranges[-1]["status"] == slot["status"]:
                ranges[-1]["end"] = slot["end"]
                ranges[-1]["end_hour"] = slot["end_hour"]
                ranges[-1]["readings"] += slot["readings"]
            else:
                ranges.append({
                    "status": slot["status"],
                    "start": slot["start"],
                    "end": slot["end"],
                    "start_hour": slot["start_hour"],
                    "end_hour": slot["end_hour"],
                    "readings": slot["readings"],
                })
        return ranges

    periods = []
    for name, short_name, start_hour, end_hour in period_definitions:
        slots = half_hourly[start_hour * 2:end_hour * 2]
        ranges = join_ranges(slots)
        periods.append({
            "meal": name,
            "short_label": short_name,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "start": clock(start_hour * 60),
            "end": clock(end_hour * 60),
            "ranges": ranges,
            "below_230_ranges": [r for r in ranges if r["status"] == "below-230"],
            "above_230_ranges": [r for r in ranges if r["status"] == "above-230"],
            "low_ranges": [r for r in ranges if r["status"] == "low-observed"],
            "missing_ranges": [r for r in ranges if r["status"] == "insufficient"],
        })

    return {
        "threshold_mgdl": 230,
        "threshold": round(threshold, 2),
        "unit": libre.unit,
        "half_hourly": half_hourly,
        "hourly_display": hourly_display,
        "periods": periods,
        "notice": (
            "Historical clock-time medians from the latest 14 days are split into 30-minute "
            "bins. Shaded periods and snack labels are illustrative, NOT actual logged meals "
            "or a list of times when eating is safe or forbidden. A median below 230 mg/dL "
            "does not establish that eating is safe; a reading at or above 230 mg/dL "
            "does not mean that meals should be skipped. Do not delay meals based on "
            "this graphic; follow your individual diabetes care plan, including for lows."
        ),
    }


def analyze_libre_only(libre_file: bytes | BinaryIO) -> dict:
    libre_obj = LibreAnalyzer(libre_file, day_first=True)
    latest = libre_obj.data["timestamp"].max()
    cutoff = latest - pd.Timedelta(days=RECENT_DAYS)
    scoped = LibreAnalyzer.__new__(LibreAnalyzer)
    scoped.unit, scoped.low, scoped.high = libre_obj.unit, libre_obj.low, libre_obj.high
    scoped.data = libre_obj.data.loc[libre_obj.data["timestamp"] >= cutoff].reset_index(drop=True)
    libre = scoped.analyze(TimeWindow("00:00", "00:00", "", ""))
    meals = build_meal_timeline(scoped)
    s = libre["summary"]
    report = "\n".join([
        "GLUCOLAB / LIBREVIEW PATTERN EXPLORER", "=" * 60,
        f"Window: {s['from']} to {s['to']}",
        f"Readings: {s['readings']:,}",
        f"Average BG: {s['mean']} {libre['unit']}",
        f"Lowest BG: {s['lowest']} {libre['unit']} at {s['lowest_at']}",
        f"Highest BG: {s['highest']} {libre['unit']} at {s['highest_at']}",
        f"In range (reading based): {s['in_range_pct']}%",
        f"Detected low episodes: {s['hypo_episodes']}",
        "", "EXPLORATORY MEAL-PERIOD TIMELINE (NOT MEAL-TIMING ADVICE)",
        *[f"{p['meal']} ({p['start']}–{p['end']}): " +
          "; ".join(f"{r['start']}–{r['end']} {r['status']}" for r in p['ranges'])
          for p in meals['periods']],
        "", meals['notice'],
    ])
    return {
        "mode": "libre",
        "filters": {"mode": "automatic_recent", "days": RECENT_DAYS,
                    "source": "LibreView only — latest 14 days",
                    "from": s["from"], "to": s["to"]},
        "libre": libre, "pump": None, "pattern": None,
        "meal_timeline": meals, "report": report,
    }


app = FastAPI(title="GLUCOLAB", docs_url=None, redoc_url=None, openapi_url=None)

@app.middleware("http")
async def public_web_headers(request: Request, call_next):
    """Basic HTTP hardening; does not replace an independent security audit."""
    if PUBLIC_MODE and request.method == "POST" and request.url.path == "/api/analyze":
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                too_large = int(raw_length) > MAX_PUBLIC_REQUEST_BYTES
            except ValueError:
                return JSONResponse({"error": "Invalid request size."}, status_code=400,
                                    headers={"Cache-Control": "no-store"})
            if too_large:
                return JSONResponse(
                    {"error": "Upload is too large for the public demo (64 MB total, 30 MB per file)."},
                    status_code=413, headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response



@app.get("/")
async def index():
    return FileResponse(ROOT / "index.html", media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/how-to/libre")
async def libre_guide():
    return FileResponse(ROOT / "guides" / "libre.html", media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/how-to/pump")
async def pump_guide():
    return FileResponse(ROOT / "guides" / "pump.html", media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "product": "GLUCOLAB", "api_schema": 3}


@app.post("/api/analyze")
def analyze_upload(libre_file: UploadFile = File(...), pump_file: UploadFile | None = File(None),
                   mode: str = Form("both"), sensor_device: str = Form(""),
                   pump_device: str = Form("minimed700")):
    """Analyze the *data* after its columns/units pass checks, not merely its filename."""
    try:
        if mode not in {"both", "libre"}:
            raise InputError("Choose sensor + pump or sensor only.")
        if mode == "both" and pump_file is None:
            raise InputError("Sensor + pump mode requires both sensor and pump data files.")
        for upload in (libre_file,pump_file if mode=="both" else None):
            if upload is None:continue
            if not upload.filename or Path(upload.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
                raise InputError("Please upload a structured CSV, TSV, XLSX, JSON, PDF, or DOCX export.")
            if upload.size is not None and upload.size > MAX_PUBLIC_FILE_BYTES:
                return JSONResponse({"error":"Each file must be 30 MB or smaller."},
                                    status_code=413,headers={"Cache-Control":"no-store"})
        glucose_bytes,glucose_source=normalize_glucose(libre_file.file,libre_file.filename,sensor_device)
        if mode=="libre":
            output=analyze_libre_only(glucose_bytes)
            if sensor_device and not sensor_device.startswith('libre'):
                output['report']=output['report'].replace('LIBREVIEW','CGM').replace('LibreView','sensor export')
                output['filters']['source']=f'Structured sensor export · last {RECENT_DAYS} days'
            output['import_info']={'sensor':sensor_device,'sensor_format':glucose_source,
                                   'pump':None,'pump_format':None,
                                   'message':'Analysis uses validated timestamped glucose readings.'}
        else:
            pump_bytes,pump_source,verified_vendor=normalize_pump(pump_file.file,pump_file.filename,pump_device)
            output=analyze_files(glucose_bytes,pump_bytes,{})
            if not verified_vendor:
                # Existing simulation is for the original MiniMed example only;
                # other manufacturers do not share verified programmable basal semantics.
                pat=output['pattern']
                pat.update(status='generic_basal_only',segments=[],segments_changed=0,
                           segments_conflict=0,observed_daily_basal_u=None,
                           illustrative_daily_basal_u=None,illustrative_daily_difference_u=None)
                pat['warnings'].append(
                    'Other pump format: GLUCOLAB identified dated basal-rate observations, '
                    'but cannot verify whether these are delivered, temporary, or programmed '
                    'rates. No hypothetical pump setting changes are generated.')
                ls=output['libre']['summary']
                output['report']=(
                    'GLUCOLAB — STRUCTURED DEVICE DATA REVIEW\n'
                    'Glucose and pump export columns were validated; this is not a clinical report.\n'
                    f"Selected CGM readings: {ls['readings']}\n"
                    f"Glucose mean: {ls['mean']} {output['libre']['unit']}\n"
                    f"Recorded basal observations: {pat.get('recent_rate_entries', 0)}\n"
                    'No basal schedule or dose-change simulation is supported for this pump format.\n'
                    'Do not program pump settings using this exploratory analysis.\n')
            output['import_info']={'sensor':sensor_device,'sensor_format':glucose_source,
                                   'pump':pump_device,'pump_format':pump_source,
                                   'message':('Recorded basal observations; no programming recommendation.'
                                              if not verified_vendor else
                                              'MiniMed candidate recorded basal review; not verified pump settings.')}
        return JSONResponse(output,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    except (InputError,ImportProblem) as exc:
        return JSONResponse({'error':str(exc)},status_code=422)
    except (ValueError,TypeError,KeyError,pd.errors.ParserError) as exc:
        # May contain parser details; do not expose user data in a public error.
        return JSONResponse({'error':'Cannot validate the uploaded data. Check for timestamp, glucose unit, and U/h basal-rate columns.'},status_code=422)
    except Exception:
        return JSONResponse({'error':'Unexpected analysis error. Use a raw, structured device export with timestamped values.'},status_code=500)


def main() -> None:
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="GLUCOLAB local Python web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"GLUCOLAB ready at http://127.0.0.1:{args.port} (30 MB per uploaded file)")
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
