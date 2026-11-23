from pathlib import Path
import re,base64,io
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'index.html').read_text(encoding='utf-8')
def test_eversense_uploaded_artwork_is_real_local_png():
    match=re.search(r'<img class="local-device-logo wide eversense-vector" src="data:image/png;base64,([^"]+)" alt="Eversense 365 logo"',HTML)
    assert match is not None
    im=Image.open(io.BytesIO(base64.b64decode(match.group(1))))
    assert im.mode=='RGBA' and im.width>200 and im.height>50
    assert (ROOT/'logos'/'eversense_reference_clean.png').read_bytes()==base64.b64decode(match.group(1))
def test_tandem_white_t_matches_wide_reference():
    assert HTML.count('class="local-device-logo wide tandem-mark"')==2
    assert 'M28 20H80V30H59V60H49V30H28Z' in HTML
    assert 'aria-label="Tandem Diabetes Care T logo"' in HTML
def test_omnipod_and_ypsopump_unchanged():
    assert 'aria-label="Omnipod wordmark"' in HTML
    assert 'aria-label="mylife YpsoPump logo"' in HTML
