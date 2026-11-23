from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')


def test_offline_vector_images_for_all_device_cards():
    assert HTML.count('class="local-device-logo') == 12
    assert HTML.count('class="libre-symbol"') >= 4
    assert 'class="official-device-logo"' not in HTML
    assert 'class="brand-logo-fallback"' not in HTML
    assert len(list((ROOT / 'logos').glob('*.svg'))) >= 9
    assert (ROOT / 'logos' / 'eversense-reference-trace.svg').exists()


def test_offline_brand_vectors_are_graphics_not_text_only_placeholders():
    assert 'class="local-device-logo square dexcom-g6"' in HTML
    assert 'class="local-device-logo square dexcom-g7"' in HTML
    assert 'class="local-device-logo wide eversense-vector"' in HTML
    assert HTML.count('class="local-device-logo emblem medtronic-emblem"') == 4
    assert HTML.count('class="local-device-logo wide tandem-mark"') == 2
    assert 'fill="#0E1F5B"' in HTML  # Beta Bionics emblem
    assert 'fill="#B0CE3B"' in HTML  # refined mylife symbol
    assert 'src="https://dexcom.' not in HTML
    assert 'src="https://upload.wikimedia.' not in HTML


def test_logo_frames_removed_brand_card_border_remains():
    assert 'background:transparent!important;border:0!important;box-shadow:none!important;' in HTML
    assert 'border-color:var(--accent)' in HTML
    assert 'background:linear-gradient(145deg,#fff,var(--accent-soft))' in HTML


def test_selected_sensor_and_pump_icons_used_in_upload_forms():
    assert 'id="sensorUploadIcon"' in HTML
    assert 'id="pumpUploadIcon"' in HTML
    assert 'function syncUploadIcons()' in HTML
    assert 'sensorWrap.innerHTML=sensorIcon' in HTML
    assert 'pumpWrap.innerHTML=pumpIcon' in HTML


def test_selection_functionality_unchanged():
    assert len(re.findall(r'<input[^>]*name="sensorChoice"', HTML)) == 9
    assert len(re.findall(r'<input[^>]*name="pumpChoice"', HTML)) == 8
    assert 'id="continueSetup"' in HTML
