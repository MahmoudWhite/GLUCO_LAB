"""Regressions for guided sensor/pump setup and clock-format choices."""
import re
from pathlib import Path
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from app import app

HTML = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')

class Radios(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            props = dict(attrs)
            self.entries.append(props)


def test_device_catalog_selection_is_radio_single_choice():
    parser = Radios()
    parser.feed(HTML)
    sensors = [x for x in parser.entries if x.get('name') == 'sensorChoice']
    pumps = [x for x in parser.entries if x.get('name') == 'pumpChoice']
    assert len(sensors) == 9
    assert len(pumps) == 8
    assert all('disabled' not in x for x in sensors)
    assert all('disabled' not in x for x in pumps)
    assert any(x['value'] == 'no-pump' for x in pumps)
    assert not any('checked' in x for x in pumps)
    assert not any('checked' in x for x in sensors)
    assert [x['value'] for x in pumps if x['value'].startswith('minimed')] == ['minimed600', 'minimed700']
    assert 'minimed670' not in HTML and 'minimed770' not in HTML and 'minimed780' not in HTML


def test_pump_section_initially_locked_and_time_format_required():
    assert re.search(r'<fieldset[^>]*id="pumpSection"[^>]*disabled>', HTML)
    assert '$("pumpSection").disabled=!selectedSensor;' in HTML
    assert '$("continueSetup").addEventListener("click"' in HTML
    assert 'selectedPump==="no-pump"?"libre":"both"' in HTML
    assert 'name="clockChoice" value="12"' in HTML
    assert 'name="clockChoice" value="24"' in HTML
    assert 'id="clockSection" disabled' in HTML
    assert 'id="sensorStep"' in HTML and 'id="pumpStep"' in HTML and 'id="timeStep"' in HTML
    assert "markStep('sensorStep'" in HTML
    assert "markStep('pumpStep'" in HTML
    assert "markStep('timeStep'" in HTML


def test_time_format_only_changes_display_and_not_export():
    assert 'function clockTime(value)' in HTML
    assert 'function clockText(value)' in HTML
    assert 'clockFormat==="12"?`${(hr%12)||12}' in HTML
    assert 'JSON.stringify(latest,null,2)' in HTML
    assert 'csvString(latest.libre.hourly)' in HTML
    assert 'meals.hourly_display.map(' in HTML


def test_mode_apis_still_work_with_current_csv_exports():
    root=Path(__file__).resolve().parents[1]
    client=TestClient(app)
    libre=(root/'samples/example_libreview.csv').read_bytes()
    pump=(root/'samples/example_medtronic.csv').read_bytes()
    a=client.post('/api/analyze', data={'mode':'libre'}, files={'libre_file':('libre.csv',libre,'text/csv')})
    assert a.status_code == 200
    assert len(a.json()['meal_timeline']['hourly_display']) == 24
    b=client.post('/api/analyze',data={'mode':'both'},files={'libre_file':('libre.csv',libre,'text/csv'),'pump_file':('pump.csv',pump,'text/csv')})
    assert b.status_code == 200
    assert b.json()['pattern'] is not None


def test_all_device_choices_can_submit_a_structured_file():
    for choice in ['dexcomg6','dexcomg7','guardian4','simplera','eversense']:
        assert f'name="sensorChoice" value="{choice}"' in HTML
    for choice in ['omnipod5','tslim','mobi','ilet','ypsopump']:
        assert f'name="pumpChoice" value="{choice}"' in HTML
    assert 'function selectedExportsSupported()' in HTML
    assert 'Boolean(selectedSensor&&selectedPump&&clockFormat)' in HTML
    assert 'form.append("sensor_device",selectedSensor)' in HTML
    assert 'form.append("pump_device",selectedPump)' in HTML
    assert 'not every manufacturer' in HTML.lower()
