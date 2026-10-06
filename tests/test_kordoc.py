"""kordoc 연동(/api/kordoc/*) — Node·kordoc 이 설치된 환경(npm install)에서만 실행한다."""
import io
import os
import shutil
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(not shutil.which("node") or not os.path.isdir(os.path.join(ROOT, "node_modules", "kordoc")),
                                reason="Node.js·kordoc 미설치(npm install 필요)")

MD = "# 「여비규정」 개정(안) 사전예고\n\n다음과 같이 예고합니다.\n\n1. 개정 이유\n  - 일비를 현실화하려는 것임.\n\n붙임  신구조문대비표 1부.  끝.\n"


def test_status(client):
    assert client.get("/api/kordoc/status").get_json()["success"]


def test_bundle_single_is_hwpx(client):
    r = client.post("/api/kordoc/bundle", json={"files": [{"name": "사전예고", "preset": "통지", "markdown": MD}]})
    assert r.status_code == 200 and r.mimetype == "application/hwp+zip"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert "Contents/section0.xml" in z.namelist()
    assert "일비를 현실화" in z.read("Contents/section0.xml").decode("utf-8")


def test_bundle_many_is_zip_with_passthrough(client, ra):
    law = ra.build_hwpx([{"t": "p", "text": "제1조(목적) 가."}])
    import base64
    r = client.post("/api/kordoc/bundle", json={"filename": "세트", "files": [
        {"name": "사전예고", "preset": "통지", "markdown": MD},
        {"name": "규정안", "data_b64": base64.b64encode(law).decode()}]})
    assert r.status_code == 200 and r.mimetype == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert sorted(names) == ["규정안.hwpx", "사전예고.hwpx"]


def test_bundle_rejects_empty_and_bad(client):
    assert client.post("/api/kordoc/bundle", json={"files": []}).status_code == 400
    assert client.post("/api/kordoc/bundle", json=[1]).status_code == 400
    assert client.post("/api/kordoc/nope", json={}).status_code == 404


def test_lint_flags_notation(client):
    d = client.post("/api/kordoc/lint", json={"texts": {"n": "기간: 2026.10.06 ~ 2026.10.26\n5. 붙임: 대비표 1부. 끝."}}).get_json()
    rules = {f["rule"] for f in d["results"]["n"]}
    assert {"DATE_NO_SPACE", "BUNIM_COLON"} <= rules
