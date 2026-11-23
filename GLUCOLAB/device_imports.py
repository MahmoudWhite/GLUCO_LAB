"""Conservative, format-aware import of *structured* diabetes exports.

No OCR, PDF chart inference, pump setting inference or extrapolation.  Vendor names
are not parsers; column semantics and units must be verified from the file.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS = frozenset({'.csv', '.tsv', '.xlsx', '.json', '.pdf', '.docx'})
MAX_EXTRACTED_ROWS = 250_000


class ImportProblem(ValueError):
    """User-facing error; must not include raw data or identifiable filenames."""


def _key(value) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value).lower().replace('µ','u'))


def _tidy_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how='all').dropna(axis=1, how='all').copy()
    if df.empty:
        return df
    df.columns = [str(x).strip().lstrip('\ufeff') for x in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()].copy()
    return df.astype(str).replace({'None':'','nan':'','NaN':'','NaT':''})


def _header_score(row: list[str]) -> int:
    """Detect actual measurement headers, never administrative metadata dates.

    In real LibreView and CareLink exports the first lines can contain a patient
    header with Start Date / End Date, which are *not* data timestamps.  Older
    versions specifically located the full device-data header before reading.
    """
    keys = {_key(cell) for cell in row if str(cell).strip()}
    timestamp = bool(keys.intersection({
        'devicetimestamp', 'timestamp', 'timestampyyyymmddthhmmss',
        'datetime', 'dateandtime', 'devicetime', 'displaytime',
        'systemtime', 'eventdatetime', 'eventdateandtime',
    })) or {'date','time'}.issubset(keys) or {'eventdate','eventtime'}.issubset(keys)
    glucose = any(k.startswith(('historicglucose','sensorglucose','cgmglucose',
                                'glucosevalue')) or k in {'glucose','glucosemgdl',
                                'glucosemmoll','value'} for k in keys)
    basal = any(k.startswith(('basalrate','deliveredbasalrate')) for k in keys)
    if not timestamp or not (glucose or basal):
        return 0
    # Give priority to exact LibreView and CareLink headers over an unrelated
    # summary table at the front of a multi-table export.
    score = 10 + (5 if basal else 0) + (5 if 'historicglucosemgdl' in keys or
        'historicglucosemmoll' in keys else 0)
    if 'recordtype' in keys and 'devicetimestamp' in keys:
        score += 10
    if {'date','time'}.issubset(keys) and basal:
        score += 10
    return score


def _from_rows(rows) -> pd.DataFrame:
    clean = []
    for row in rows:
        if isinstance(row, (list,tuple)):
            clean.append([str(v).strip() if v is not None else '' for v in row])
    if len(clean) < 2:
        return pd.DataFrame()
    maxlen = max(len(r) for r in clean)
    if maxlen > 120 or len(clean) > MAX_EXTRACTED_ROWS:
        raise ImportProblem('The export is too large or has too many columns to interpret safely.')
    clean = [r + [''] * (maxlen-len(r)) for r in clean]
    # Search administrative preambles, but demand a timestamp AND a value field.
    # Don't treat Start Date/End Date in the patient metadata as a data header.
    candidates = [(i, _header_score(row)) for i,row in
                  enumerate(clean[:min(100,len(clean)-1)])]
    winners = [(i,score) for i,score in candidates if score]
    if winners:
        # Highest score wins; stable leftmost choice on ties.
        i = max(winners,key=lambda item:item[1])[0]
        return _tidy_frame(pd.DataFrame(clean[i+1:], columns=clean[i]))
    return _tidy_frame(pd.DataFrame(clean[1:], columns=clean[0]))


def _read_csv(data:bytes, suffix:str) -> list[pd.DataFrame]:
    candidates=[]
    encodings = ['utf-16'] if data.startswith((b'\xff\xfe',b'\xfe\xff')) else ['utf-8-sig','cp1252']
    for encoding in encodings:
        try:
            text=data.decode(encoding)
        except UnicodeError:
            continue
        # Choose the delimiter by requiring both meaningful headers and columns.
        for delimiter in ('\t',',',';') if suffix=='.tsv' else (',',';','\t'):
            try:
                rows=list(csv.reader(io.StringIO(text),delimiter=delimiter))
                if any(len(row)>1 for row in rows[:80]):
                    candidates.append(_from_rows(rows))
            except (csv.Error,ValueError):
                continue
        break
    return candidates


def _read_xlsx(data:bytes) -> list[pd.DataFrame]:
    # Only read actual worksheet values; formulas are not calculated by GLUCOLAB.
    try:
        workbook = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None,
                                 engine='openpyxl', nrows=MAX_EXTRACTED_ROWS)
    except Exception as exc:
        raise ImportProblem('Cannot read the Excel file. Export the device readings as CSV instead.') from exc
    if len(workbook)>30:
        raise ImportProblem('Excel workbook has too many sheets. Export the glucose or basal table separately.')
    return [_from_rows(sheet.fillna('').values.tolist()) for sheet in workbook.values()]


def _read_json(data:bytes) -> list[pd.DataFrame]:
    try:
        obj=json.loads(data.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise ImportProblem('Invalid JSON: export a structured readings or basal-rate table.') from exc
    if isinstance(obj,list):
        return [_tidy_frame(pd.json_normalize(obj))]
    if isinstance(obj,dict):
        frames=[]
        for name in ('readings','glucose','data','events','records','basal','entries'):
            payload=obj.get(name)
            if isinstance(payload,list) and payload and isinstance(payload[0],dict):
                frames.append(_tidy_frame(pd.json_normalize(payload)))
        return frames or [_tidy_frame(pd.json_normalize([obj]))]
    return []


def _read_docx(data:bytes) -> list[pd.DataFrame]:
    try:
        from docx import Document
        doc=Document(io.BytesIO(data))
        return [_from_rows([[cell.text for cell in row.cells] for row in table.rows])
                for table in doc.tables[:30]]
    except Exception as exc:
        raise ImportProblem('The Word document could not be read. GLUCOLAB requires a table of timestamped values.') from exc


def _read_pdf(data:bytes) -> list[pd.DataFrame]:
    try:
        import pdfplumber
        frames=[]
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages)>40:
                raise ImportProblem('PDF has too many pages. Export its raw data table as CSV instead.')
            for page in pdf.pages:
                for table in page.extract_tables()[:20]:
                    frames.append(_from_rows(table))
        return frames
    except ImportProblem:
        raise
    except Exception as exc:
        raise ImportProblem('Could not extract a data table from this PDF. Scanned charts and report summaries cannot be converted reliably into raw readings.') from exc


def load_tables(file, filename:str) -> tuple[list[pd.DataFrame],str]:
    ext=Path(filename or '').suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ImportProblem('Supported structured file types: CSV, TSV, Excel (.xlsx), JSON, text-table PDF, and Word (.docx).')
    file.seek(0)
    data=file.read()
    if not data:
        raise ImportProblem('The selected file is empty.')
    if len(data)>30*1024*1024:
        raise ImportProblem('Files must be under 30 MB. Export a smaller date range.')
    if ext in {'.csv','.tsv'}:
        frames=_read_csv(data,ext)
    elif ext=='.xlsx':
        frames=_read_xlsx(data)
    elif ext=='.json':
        frames=_read_json(data)
    elif ext=='.docx':
        frames=_read_docx(data)
    else:
        frames=_read_pdf(data)
    return [frame for frame in frames if not frame.empty],ext


def _name(frame:pd.DataFrame, *alternatives: str) -> str | None:
    lookup={_key(col):col for col in frame.columns}
    for alias in alternatives:
        if _key(alias) in lookup:
            return lookup[_key(alias)]
    return None


def _timestamp(frame:pd.DataFrame, *, day_first:bool=False) -> pd.Series:
    stamp=_name(frame,'Device Timestamp','Timestamp (YYYY-MM-DDThh:mm:ss)',
                'Timestamp','Date and Time','Date/Time','Datetime','Date Time',
                'deviceTime','displayTime','System Time')
    if stamp:
        raw=frame[stamp].astype(str).str.strip()
    else:
        datecol=_name(frame,'Date','Event Date','EventDate')
        timecol=_name(frame,'Time','Event Time','EventTime')
        if datecol and timecol:
            raw=frame[datecol].astype(str).str.strip()+' '+frame[timecol].astype(str).str.strip()
        elif timecol:  # JSON export, e.g. Tidepool uses an ISO-8601 `time` key
            raw=frame[timecol].astype(str).str.strip()
        else:
            raise ImportProblem('A dated glucose or basal table needs a timestamp, or separate Date and Time columns.')
    if raw.str.contains(r'(?:Z|[+\-]\d{2}:?\d{2})$',regex=True,case=False).any():
        raise ImportProblem('Export timestamps contain UTC offsets. GLUCOLAB needs local device timestamps (e.g. deviceTime) to display clock-time patterns reliably.')
    raw=raw.str.replace('T',' ',regex=False)
    # US month-first for numeric date exports; ISO year-first remains unambiguous.
    # Numeric 01/02 dates are ambiguous outside explicitly identified vendor formats.
    # LibreView exports have historically used day-first; CareLink/generic US
    # pump exports are month-first. Generic ambiguous dates must not be guessed.
    if not day_first and not _name(frame,'Basal Rate (U/h)'):
        ambiguous=raw.str.match(r'^\s*(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|1[0-2])[/\-]\d{4}')
        if ambiguous.any():
            raise ImportProblem('Ambiguous dates (e.g. 02/03/2026). Export ISO dates (YYYY-MM-DD) instead.')
    parsed=pd.to_datetime(raw,format='mixed',errors='coerce',dayfirst=day_first,utc=False)
    try:
        if getattr(parsed.dt,'tz',None) is not None:
            parsed=parsed.dt.tz_localize(None)
    except (TypeError,AttributeError):
        pass
    if not pd.api.types.is_datetime64_any_dtype(parsed):
        raise ImportProblem('Timestamps contain incompatible time zones. Export local timestamps as CSV.')
    return parsed


def _unit_column(frame:pd.DataFrame, value_col:str, kind:str) -> str:
    label=_key(value_col)
    if 'mmoll' in label or 'mmol' in label:return 'mmol/L'
    if 'mgdl' in label:return 'mg/dL'
    explicit=_name(frame,'unit','units','glucose units','Glucose Units')
    if explicit:
        values={_key(x) for x in frame[explicit].dropna().unique() if str(x).strip()}
        if values=={'mmoll'}:return 'mmol/L'
        if values=={'mgdl'}:return 'mg/dL'
        if values:
            raise ImportProblem('Unknown or mixed glucose units. Expected mg/dL or mmol/L.')
    if kind=='tidepool' and _key(value_col)=='value':
        raise ImportProblem('Tidepool JSON glucose records must declare units.')
    raise ImportProblem('Glucose units are missing. Use a column labelled mg/dL or mmol/L, or add a units column.')


def _glucose_frame(frame:pd.DataFrame) -> tuple[pd.DataFrame,str]:
    native = _name(frame,'Record Type') and _name(frame,'Device Timestamp')
    if native:
        rectype=_name(frame,'Record Type')
        frame=frame.loc[pd.to_numeric(frame[rectype],errors='coerce').eq(0)]
    event_col=_name(frame,'Event Type','type','record type','Reading Type')
    event_kind=''
    if event_col and not native:
        values=frame[event_col].astype(str).str.lower().str.strip()
        if values.isin(['egv','cbg','cgm','sensor glucose','glucose','sensor reading']).any():
            frame=frame.loc[values.isin(['egv','cbg','cgm','sensor glucose','glucose','sensor reading'])]
            event_kind='tidepool'
        elif values.isin(['smbg','bolus','basal','calibration','insulin','fingerstick']).all():
            raise ImportProblem('This table has no sensor glucose readings (only other event types).')
    valuecol=_name(frame,'Historic Glucose (mg/dL)','Historic Glucose (mmol/L)',
                   'Glucose Value (mg/dL)','Glucose Value (mmol/L)',
                   'Sensor Glucose (mg/dL)','Sensor Glucose (mmol/L)',
                   'CGM Glucose (mg/dL)','CGM Glucose (mmol/L)',
                   'Glucose (mg/dL)','Glucose (mmol/L)',
                   'Sensor Glucose','CGM Glucose','Glucose Value','glucose','value')
    if not valuecol:raise ImportProblem('No glucose reading column was found.')
    unit=_unit_column(frame,valuecol,event_kind)
    times=_timestamp(frame,day_first=bool(native))
    values=pd.to_numeric(frame[valuecol].astype(str).str.replace(',','.',regex=False),errors='coerce')
    # A physiologically broad guard, NOT a medical diagnostic threshold.
    plausible=(values.between(20,600) if unit=='mg/dL' else values.between(1.1,33.3))
    keep=times.notna() & plausible
    if keep.sum()<2 or keep.mean()<0.5:
        raise ImportProblem('Too few valid timestamped CGM readings. Check the columns, units, and whether this is a raw export.')
    selected=pd.DataFrame({'timestamp':times.loc[keep],'value':values.loc[keep]})
    selected=selected.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    return selected,unit


def normalize_glucose(file, filename:str, sensor_id:str='') -> tuple[bytes,str]:
    frames,ext=load_tables(file,filename)
    problems=[]
    matches=[]
    for frame in frames:
        try:
            values,unit=_glucose_frame(frame)
            matches.append((values,unit))
        except (ImportProblem,ValueError,TypeError) as exc:
            problems.append(str(exc))
    if not matches:
        msg=problems[0] if problems else 'No tables were extracted.'
        raise ImportProblem('No recognizable raw sensor-glucose table was found. '+msg+
                            ' PDF/Word summaries and graphs are not substitutes for individual readings.')
    units={u for _,u in matches}
    if len(units)>1:
        raise ImportProblem('Multiple glucose tables use different units. Export a single unambiguous sensor table.')
    unit=units.pop()
    combined=pd.concat([x for x,_ in matches],ignore_index=True).drop_duplicates(subset='timestamp').sort_values('timestamp')
    if len(combined)>MAX_EXTRACTED_ROWS:
        raise ImportProblem('Too many readings to process. Export a shorter date interval.')
    col='Historic Glucose (mmol/L)' if unit=='mmol/L' else 'Historic Glucose (mg/dL)'
    out=pd.DataFrame({'Record Type':['0']*len(combined),
                      'Device Timestamp':combined.timestamp.dt.strftime('%Y/%m/%d %H:%M:%S'),
                      col:combined.value})
    return out.to_csv(index=False).encode('utf-8'),f'{ext} · validated timestamped readings · {unit}'


def _basal_frame(frame:pd.DataFrame) -> pd.DataFrame:
    ratecol=_name(frame,'Basal Rate (U/h)','Basal Rate (U/hr)','Basal Rate (Units/hr)',
                  'Basal Rate (Units/Hour)','Delivered Basal Rate (U/h)','BasalRate (U/h)',
                  'Basal Rate U/h', 'BasalRate', 'basal_rate')
    if not ratecol:raise ImportProblem('No rate column explicitly identified as basal was found. Bolus doses are not basal rates.')
    label=_key(ratecol)
    if not any(w in label for w in ('uh','uhr','unitshr','unitshour')):
        unitscol=_name(frame,'Basal Units','Rate Units','Units','unit')
        if not unitscol or set(_key(v) for v in frame[unitscol].dropna().unique() if v.strip()) not in ({'uh'},{'uhr'},{'unitshour'},{'unitshr'}):
            raise ImportProblem('Basal values must be explicitly labelled U/h or Units/hour. Doses in U cannot be interpreted as rates.')
    timestamp=_timestamp(frame)
    values=pd.to_numeric(frame[ratecol].astype(str).str.replace(',','.',regex=False),errors='coerce')
    valid=timestamp.notna() & values.between(0,100)
    # MiniMed CareLink CSV is an event log. Most rows contain bolus, alerts,
    # suspend/resume or other events and correctly have an EMPTY basal-rate
    # column. Its rate-bearing records may be far below half of all rows.
    # Keep only rows with explicit dated U/h readings, without interpreting
    # absent event fields as zeros or interpolating missing rates.
    if valid.sum()<2:
        raise ImportProblem('Too few valid timestamped basal-rate observations. Export raw basal data, not a report summary.')
    return pd.DataFrame({'timestamp':timestamp.loc[valid], 'rate':values.loc[valid]})


def normalize_pump(file, filename:str, pump_id:str='') -> tuple[bytes,str,bool]:
    frames,ext=load_tables(file,filename)
    problems=[]
    matches=[]
    for frame in frames:
        try: matches.append(_basal_frame(frame))
        except (ImportProblem,ValueError,TypeError) as exc:problems.append(str(exc))
    if not matches:
        msg=problems[0] if problems else 'No tables were extracted.'
        raise ImportProblem('No usable timestamped basal-rate table was found. '+msg+
                            ' GLUCOLAB cannot infer basal data from PDF charts, bolus totals or narrative reports.')
    combined=pd.concat(matches,ignore_index=True).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    if len(combined)>MAX_EXTRACTED_ROWS:
        raise ImportProblem('Too many pump records. Export a shorter date interval.')
    out=pd.DataFrame({'Date':combined.timestamp.dt.strftime('%Y/%m/%d'),
                      'Time':combined.timestamp.dt.strftime('%H:%M:%S'),
                      'Basal Rate (U/h)':combined.rate})
    # This remains a *recorded-rate* source. It is not a verified programmed profile.
    verified_vendor = pump_id in ('minimed600','minimed700')
    return out.to_csv(index=False).encode('utf-8'), f'{ext} · dated U/h basal observations',verified_vendor
