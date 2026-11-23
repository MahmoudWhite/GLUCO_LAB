from pathlib import Path
import re
from urllib.parse import unquote

HTML = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')


def test_logo_is_yellow_square_with_face_not_old_svg():
    assert '<div class="logo" aria-hidden="true">-_-</div>' in HTML
    assert '.brand .logo{width:43px;height:43px;' in HTML
    assert 'background:linear-gradient(145deg,#f4a600,#f9ca2f)' in HTML
    assert '-_-' in unquote(re.search(r'<link rel="icon"[^>]+href="([^"]+)', HTML).group(1))


def test_progress_step_styles_are_yellow_and_yellow_completed_line():
    assert '.picker-steps .picker-step.completed{color:#8d5d00;background:#fff1ad' in HTML
    assert '.picker-steps .picker-step.current{color:#895400;background:#fff2bc}' in HTML
    assert '.picker-steps .step-line.completed{background:#eab11b;' in HTML


def test_left_aligned_compact_omnipod_tandem_without_altering_device_icons():
    assert '.hardware-choice:has(.omnipod-mark) .hardware-top,' in HTML
    assert '.hardware-choice:has(.tandem-mark) .hardware-top{flex-direction:row;align-items:flex-start;justify-content:space-between}' in HTML
    assert '.hardware-choice .local-device-logo.omnipod-mark{width:64px;height:36px;' in HTML
    assert '.hardware-choice .local-device-logo.tandem-mark{width:56px;height:34px;' in HTML
    assert HTML.count('aria-label="Tandem Diabetes Care T logo"') == 2
