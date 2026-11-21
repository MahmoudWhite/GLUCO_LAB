"""Protect the restored 24-block, floating-glass Libre timeline."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import LibreAnalyzer, build_meal_timeline


def analyzer():
    a=LibreAnalyzer.__new__(LibreAnalyzer)
    a.unit='mg/dL';a.low=70.0;a.high=180.0
    readings=[]
    for day in range(5):
        start=datetime(2026,11,1)+timedelta(days=day)
        for halfhour in range(48):
            value=255.0 if halfhour==29 else 140.0  # 14:30–15:00
            readings.extend({
                'timestamp': start+timedelta(minutes=halfhour*30+offset),
                'glucose': value,
            } for offset in (0, 10))
    a.data=pd.DataFrame(readings)
    return a


def test_backend_keeps_48_detailed_bins_but_adds_24_visual_hours():
    result=build_meal_timeline(analyzer())
    assert len(result['half_hourly']) == 48
    assert len(result['hourly_display']) == 24
    assert result['hourly_display'][14]['status'] == 'above-230'
    assert result['hourly_display'][14]['half_hour_statuses'] == ['below-230', 'above-230']
    assert result['hourly_display'][15]['status'] == 'below-230'
    lunch=next(p for p in result['periods'] if p['meal']=='Lunch')
    # Preserve the detailed data for the cards, even though the bar is hourly.
    assert [(r['start'],r['end']) for r in lunch['above_230_ranges']] == [('14:30','15:00')]


def test_original_glass_boxes_overlay_hourly_bar_and_labels_above():
    html=(ROOT/'index.html').read_text(encoding='utf8')
    assert 'meals.hourly_display.map(' in html
    assert 'meals.half_hourly.map(' not in html
    assert 'class="hourcell ${esc(h.status)}"' in html
    assert 'class="meal-highlight"' in html
    assert 'class="period-label"' in html
    assert 'outlines.join(' in html
    assert 'labels.join(' in html
    assert 'outline:2px solid rgba(255,255,255,.97)' in html
    assert 'backdrop-filter:none;-webkit-backdrop-filter:none' in html
    # A backdrop blur would wash out or soften the colored hourly data blocks.
    assert 'backdrop-filter:blur(3px)' not in html
    assert 'Array.isArray(meals.hourly_display) && meals.hourly_display.length===24' in html
