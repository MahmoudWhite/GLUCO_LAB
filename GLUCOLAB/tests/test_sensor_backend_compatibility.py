"""Guard against an older Python server behind the new sensor-only timeline UI."""
from pathlib import Path
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app

ROOT = Path(__file__).resolve().parents[1]


def test_server_exposes_required_schema_version():
    response = TestClient(app).get('/api/health')
    assert response.status_code == 200
    assert response.json()['api_schema'] == 3


def test_libre_response_contains_new_half_hour_schema():
    payload = (ROOT / 'samples' / 'example_libreview.csv').read_bytes()
    response = TestClient(app).post('/api/analyze',
        data={'mode': 'libre'},
        files={'libre_file': ('libre.csv', payload, 'text/csv')})
    assert response.status_code == 200
    meals = response.json()['meal_timeline']
    assert len(meals['half_hourly']) == 48
    assert len(meals['periods']) == 6
    assert all(all(key in meal for key in
                   ('ranges', 'below_230_ranges', 'above_230_ranges', 'low_ranges', 'missing_ranges'))
               for meal in meals['periods'])


def test_webpage_checks_for_old_python_server_before_mapping():
    html = (ROOT/'index.html').read_text(encoding='utf-8')
    assert 'data.api_schema!==REQUIRED_API_SCHEMA' in html
    assert 'validExpandedMealTimeline(data.meal_timeline)' in html
    assert 'OUTDATED_SERVER_MESSAGE' in html
    assert 'Stop the old Anaconda Prompt server with Ctrl+C' in html
