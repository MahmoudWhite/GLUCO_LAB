"""Keep every device connected to its upload card's logo color."""
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / 'index.html').read_text('utf-8')


def test_all_device_choices_define_color():
    for kind in ('sensor', 'pump'):
        selected = re.findall(rf'<label class="hardware-choice[^>]*for="{kind}-[^"]+"[^>]*>', HTML)
        assert selected, f'No {kind} choices found'
        assert all('--accent-rgb:' in choice for choice in selected), kind


def test_upload_card_theme_tracks_the_selected_device():
    assert 'function syncUploadCardColors()' in HTML
    assert "syncUploadCardColors();" in HTML
    assert "device?.style.getPropertyValue('--accent-rgb')" in HTML
    assert "upload.style.setProperty('--upload-brand',rgb)" in HTML
    assert 'rgba(var(--upload-brand),.11)' in HTML
    assert '#uploadSidebar .upload-card .file-button' in HTML
    assert '#uploadSidebar .upload-card .method-link' in HTML


def test_all_choice_values_have_legible_dark_link_and_button_colors():
    values = set(re.findall(r'<input type="radio" id="(?:sensor|pump)-[^"]+" name="(?:sensorChoice|pumpChoice)" value="([^"]+)"', HTML))
    palette = HTML.split('function syncUploadCardColors(){', 1)[1].split('for(const [name,uploadId', 1)[0]
    for value in values:
        assert re.search(rf"(?:^|[\s,])(?:'{re.escape(value)}'|{re.escape(value)}):'#[0-9A-Fa-f]{{6}}'", palette), value
