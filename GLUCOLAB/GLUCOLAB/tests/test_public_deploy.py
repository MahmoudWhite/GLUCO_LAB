"""Basic public-deployment configuration regressions; not a security audit."""
import subprocess
import sys
import os
from pathlib import Path

from fastapi.testclient import TestClient
from app import app

ROOT = Path(__file__).resolve().parents[1]


def test_local_mode_remains_unrestricted():
    from app import PUBLIC_MODE
    if not PUBLIC_MODE:
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"


def test_public_deployment_includes_render_blueprint_and_privacy_note():
    config = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "uvicorn app:app --host 0.0.0.0 --port $PORT" in config
    assert "GLUCOLAB_PUBLIC" in config
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "publicBetaNotice" in page
    assert "Your CSVs are transmitted to this website" in page
    assert (ROOT / ".gitignore").exists()


def test_public_mode_upload_validation_in_subprocess():
    script = '''
from fastapi.testclient import TestClient
from app import app, MAX_PUBLIC_REQUEST_BYTES
from pathlib import Path
with TestClient(app) as c:
    files={"libre_file":("example.csv",Path("samples/example_libreview.csv").open("rb"),"text/csv")}
    assert c.post("/api/analyze",data={"mode":"libre"},files=files).status_code==200
    files={"libre_file":("invalid.txt",Path("samples/example_libreview.csv").open("rb"),"text/plain")}
    assert c.post("/api/analyze",data={"mode":"libre"},files=files).status_code==422
    r=c.post("/api/analyze",data={"mode":"libre"},headers={"content-length":str(MAX_PUBLIC_REQUEST_BYTES+1)})
    assert r.status_code==413
'''
    env = dict(os.environ, GLUCOLAB_PUBLIC="1")
    output = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    assert output.returncode == 0, (output.stdout + output.stderr)[-1000:]
