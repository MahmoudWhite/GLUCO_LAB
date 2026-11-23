from pathlib import Path
from xml.etree import ElementTree as ET
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')

def vector_by_label(label):
    matches=re.findall(r'<svg\b[^>]*aria-label="'+re.escape(label)+r'"[^>]*>.*?</svg>',HTML,re.S)
    for value in matches:
        ET.fromstring(value)
    return matches

def test_reference_based_logo_symbols_render_locally():
    assert len(vector_by_label('Omnipod wordmark')) == 1
    assert HTML.count('alt="Eversense 365 logo"') == 1
    assert len(vector_by_label('mylife YpsoPump logo')) == 1
    assert len(vector_by_label('Tandem Diabetes Care T logo')) == 2
    assert HTML.count('aria-label="Omnipod wordmark"') == 1
    assert 'class="local-device-logo wide omnipod-mark"' in HTML
    assert 'fill="#FFA700"' in HTML  # traced from user-supplied original
    assert 'src="data:image/png;base64,' in HTML and 'eversense<tspan' not in HTML
    assert 'YpsoPump</text>' in HTML
    for name in ['omnipod-wordmark-refined.svg','eversense-clean.svg','ypsopump-refined.svg','tandem-mark-refined.svg']:
        assert (ROOT/'logos'/name).exists()

def test_logos_display_without_network_dependency():
    assert 'function syncUploadIcons()' in HTML
    assert 'src="https://dexcom.' not in HTML
    assert 'src="https://upload.wikimedia.' not in HTML
