"""Every device has a dedicated help page and the correct platform source."""
import re
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

HTML = (Path(__file__).resolve().parents[1] / 'index.html').read_text('utf-8')


def test_16_devices_have_specific_guide_configs():
    inputs = re.findall(r'<input type="radio" id="((?:sensor|pump)-[^\"]+)"', HTML)
    device_ids = {value for value in inputs if value != 'pump-no-pump'}
    config = HTML.split('const DEVICE_DOWNLOAD_GUIDES={', 1)[1].split('};\nconst GLUCOLAB_BASE_TITLE', 1)[0]
    referenced = set(re.findall(r"'((?:sensor|pump)-[^']+)':", config))
    assert len(device_ids) == 16, device_ids
    assert referenced == device_ids, (referenced - device_ids, device_ids - referenced)


def test_selection_updates_links_in_both_upload_sections():
    assert "sensorMethodLink.href='/?guide=sensor-'+encodeURIComponent(selectedSensor)" in HTML
    assert "pumpMethodLink.href='/?guide=pump-'+encodeURIComponent(selectedPump)" in HTML
    assert 'function renderDeviceGuideForUrl(guideOverride)' in HTML
    assert "history.pushState({guide:true}" in HTML
    assert "history.pushState({guide:false}" in HTML
    assert "window.addEventListener('popstate',renderDeviceGuideForUrl)" in HTML


def test_device_guides_have_explicit_safety_and_source_disclosures():
    assert "Eversense 365" in HTML
    assert 'Raw event CSV export not verified' in HTML
    assert 'raw timestamped CSV not verified' in HTML
    assert 'CareLink Personal' in HTML
    assert 'Dexcom Clarity' in HTML
    assert 'Glooko raw CSV data export documented' in HTML
    assert 'Daily Timeline CSV export documented' in HTML
    assert 'the ZIP as a single file' in HTML
    assert 'mylife Software export help' in HTML
    assert 'a file type alone does not ensure compatibility' in HTML


def test_all_guides_use_root_html_route_not_missing_backend_routes():
    client = TestClient(app)
    for guide in ('sensor-libre3','sensor-dexcomg7','sensor-eversense',
                  'pump-omnipod5','pump-mobi','pump-ilet','pump-ypsopump'):
        response = client.get('/?guide='+guide)
        assert response.status_code == 200,guide
        assert 'id="deviceSpecificGuide"' in response.text
        assert 'function renderDeviceGuideForUrl' in response.text
