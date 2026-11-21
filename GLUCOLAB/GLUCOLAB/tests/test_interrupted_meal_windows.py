"""Test interrupted 30-minute historical glucose patterns and UI positioning."""
from pathlib import Path
import sys
from datetime import datetime, timedelta
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import LibreAnalyzer, build_meal_timeline

ROOT=Path(__file__).resolve().parents[1]


def make_analyzer(unit="mg/dL"):
    """Synthetic repeated clock-time sample for a split lunch period."""
    analyzer=LibreAnalyzer.__new__(LibreAnalyzer)
    analyzer.unit=unit
    analyzer.low=70.0 if unit=="mg/dL" else 3.9
    analyzer.high=180.0 if unit=="mg/dL" else 10.0
    readings=[]
    for day in range(5):
        start=datetime(2026,11,1)+timedelta(days=day)
        for half in range(48):
            value=140.0
            if half==29: # 14:30–15:00, within lunch
                value=250.0
            if half==34: # 17:00–17:30, within afternoon snack
                value=50.0
            if unit=="mmol/L":
                value=value/18.0182
            # 2 readings per half-hour on 5 days
            readings.extend([
                {"timestamp":start+timedelta(minutes=half*30+k*10),"glucose":value}
                for k in range(2)
            ])
    analyzer.data=pd.DataFrame(readings)
    return analyzer


def test_lunch_is_split_and_resumed_when_230_marker_is_exceeded():
    result=build_meal_timeline(make_analyzer())
    lunch=next(x for x in result['periods'] if x['meal']=='Lunch')
    assert lunch['start']=='12:00' and lunch['end']=='17:00'
    assert [(x['start'],x['end']) for x in lunch['below_230_ranges']]==[
        ('12:00','14:30'),('15:00','17:00')
    ]
    assert [(x['start'],x['end']) for x in lunch['above_230_ranges']]==[
        ('14:30','15:00')
    ]
    assert result['half_hourly'][29]['median']==250.0
    assert result['half_hourly'][29]['status']=='above-230'


def test_unit_conversion_and_low_detection():
    result=build_meal_timeline(make_analyzer("mmol/L"))
    assert 12.7<result['threshold']<12.8
    assert result['half_hourly'][29]['status']=='above-230'
    assert result['half_hourly'][34]['status']=='low-observed'


def test_sparse_data_does_not_create_below_threshold_ranges():
    analyzer=make_analyzer()
    analyzer.data=analyzer.data.iloc[:12].copy()
    result=build_meal_timeline(analyzer)
    assert all(x['status']=='insufficient' for x in result['half_hourly'])
    assert all(not p['below_230_ranges'] for p in result['periods'])


def test_buttons_are_aligned_right_in_both_results_panels():
    html=(ROOT/'index.html').read_text(encoding='utf8')
    assert '.result-title>.results-tools,.pattern-panel>.blocktitle>.results-tools{' in html
    assert 'margin-left:auto;flex-shrink:0' in html
    for name in ('exportJson','printReport','explainMods','exportSchedule'):
        assert f'id="{name}"' in html
