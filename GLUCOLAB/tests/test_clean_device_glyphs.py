from pathlib import Path
from xml.etree import ElementTree as ET
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')


def _svg(label):
    matches = re.findall(r'<svg\b[^>]*aria-label="'+re.escape(label)+r'"[^>]*>.*?</svg>', HTML, re.S)
    for xml in matches: ET.fromstring(xml)
    return matches


def test_clean_logos_keep_device_counts_and_valid_vector_markup():
    assert len(_svg('Dexcom G6 symbol')) == 1
    assert len(_svg('Dexcom G7 symbol')) == 1
    assert len(re.findall(r'<img class="local-device-logo emblem medtronic-emblem"', HTML)) == 4
    assert len(_svg('Tandem Diabetes Care T logo')) == 2
    assert len(re.findall(r'<input[^>]*name="sensorChoice"', HTML)) == 9
    assert len(re.findall(r'<input[^>]*name="pumpChoice"', HTML)) == 8


def test_dexcom_and_tandem_have_no_duplicate_unwanted_shapes():
    assert _svg('Dexcom G6 symbol')[0].count('<circle') == 1
    assert _svg('Dexcom G7 symbol')[0].count('<circle') == 2
    assert _svg('Tandem Diabetes Care T logo')[0].count('<path') == 2
    assert _svg('Tandem Diabetes Care T logo')[0].count('<rect') == 0


def test_header_yellow_square_face_mark_and_local_upload_icons():
    header = re.search(r'<div class="brand"><div class="logo".*?</div>', HTML, re.S).group(0)
    assert '> -_-<' in header or '>-_-<' in header
    assert '<svg' not in header and '<img' not in header
    assert 'background:linear-gradient(145deg,#f4a600,#f9ca2f)' in HTML
    assert 'image/svg+xml' in HTML
    assert 'id="sensorUploadIcon"' in HTML and 'id="pumpUploadIcon"' in HTML
