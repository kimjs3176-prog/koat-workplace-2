"""AI 호출 실패(과부하 503·한도 429) 때 다른 Gemini 모델로 자동 전환하는지."""
import json
import time

import pytest

import api_server as A


@pytest.fixture(autouse=True)
def _no_live_model_list(monkeypatch):
    """대체 모델을 고를 때 부르는 ListModels(실제 네트워크)를 막는다 — 시험마다 필요하면 다시 바꾼다."""
    monkeypatch.setattr(A, "_gemini_latest_model", lambda k: "gemini-flash-latest")
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})
    yield
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})


class _R:
    def __init__(self, code, body):
        self.status_code = code
        self.text = json.dumps(body, ensure_ascii=False)
        self._b = body

    def json(self):
        return self._b


def _ok(text):
    return _R(200, {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def test_alternates_prefer_same_generation_then_other_flash():
    A._GEMINI_MODEL_CACHE["ranked"] = []
    assert A._gemini_alternates("gemini-2.5-flash") == ["gemini-flash-latest", "gemini-flash-lite-latest"]   # 은퇴하는 버전 이름은 쓰지 않는다
    A._GEMINI_MODEL_CACHE["ranked"] = ["gemini-3.0-pro", "gemini-3.0-flash", "gemini-3.0-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    alts = A._gemini_alternates("gemini-3.0-flash")
    assert alts[0] == "gemini-3.0-flash-lite" and "gemini-3.0-flash" not in alts and "gemini-3.0-pro" not in alts
    A._GEMINI_MODEL_CACHE["ranked"] = []


def test_generate_switches_model_on_overload(monkeypatch):
    calls = []
    def post(url, **kw):
        calls.append(url)
        if "gemini-2.5-flash:" in url:
            return _R(503, {"error": {"message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"}})
        return _ok('{"mode":"amend"}')
    monkeypatch.setattr(A.req_lib, "post", post)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE["ranked"] = []
    text, err = A._ai_generate("gemini", "k", "gemini-2.5-flash", "sys", "user", json_mode=True)
    assert err == "" and text == '{"mode":"amend"}'
    # 원래 모델 3회(재시도) 뒤 대체 모델 1회로 성공
    assert sum("gemini-2.5-flash:" in u for u in calls) == 3
    assert any("gemini-flash-latest:" in u for u in calls)


def test_generate_reports_alternates_when_all_fail(monkeypatch):
    monkeypatch.setattr(A.req_lib, "post", lambda url, **kw: _R(429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "status": "RESOURCE_EXHAUSTED"}}))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE["ranked"] = []
    text, err = A._ai_generate("gemini", "k", "gemini-2.5-flash", "sys", "user")
    assert text == "" and "사용량 한도" in err and "대체 모델" in err and "gemini-flash-latest" in err


def test_error_kinds():
    assert A._ai_error(_R(429, {"error": {"message": "quota exceeded"}}))[1] == "quota"
    assert A._ai_error(_R(503, {"error": {"message": "The model is overloaded"}}))[1] == "overload"
    assert A._ai_error(_R(403, {"error": {"message": "API key not valid"}}))[1] == "auth"


def test_generate_switches_model_on_timeout(monkeypatch):
    calls = []
    def post(url, **kw):
        calls.append((url, kw.get("timeout")))
        if "gemini-2.5-flash:" in url:
            raise A.req_lib.exceptions.Timeout()
        return _ok("ok")
    monkeypatch.setattr(A.req_lib, "post", post)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE["ranked"] = []
    text, err = A._ai_generate("gemini", "k", "gemini-2.5-flash", "sys", "user")
    assert (text, err) == ("ok", "")
    assert calls[0][1] <= 40 and any("flash-latest" in u for u, _ in calls)


def test_generate_timeout_message_when_all_slow(monkeypatch):
    def post(url, **kw):
        raise A.req_lib.exceptions.Timeout()
    monkeypatch.setattr(A.req_lib, "post", post)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    text, err = A._ai_generate("gemini", "k", "gemini-2.5-flash", "sys", "user")
    assert text == "" and "응답이 늦습니다" in err


def test_retired_model_uses_suggested_then_remembers(monkeypatch):
    """“models/gemini-2.0-flash is no longer available … use models/gemini-3.8-flash” → 안내된 모델로 바꾸고 기본으로 기억."""
    calls = []
    def post(url, **kw):
        calls.append(url)
        if "gemini-3.8-flash:" in url:
            return _ok("ok")
        return _R(404, {"error": {"message": "This model models/gemini-2.0-flash is no longer available. Please update your code to use models/gemini-3.8-flash for the latest features and improvements."}})
    monkeypatch.setattr(A.req_lib, "post", post)
    monkeypatch.setattr(A, "_gemini_latest_model", lambda k: "gemini-flash-latest")   # 목록 조회는 이 시험에서 막는다
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})
    text, err = A._ai_generate("gemini", "k", "gemini-2.0-flash", "sys", "user")
    assert (text, err) == ("ok", "")
    assert "gemini-3.8-flash:" in calls[1]                       # 원 모델 1회(재시도 안 함) 뒤 바로 안내된 모델
    assert A._GEMINI_MODEL_CACHE["model"] == "gemini-3.8-flash"
    assert A._default_model_for("gemini") == "gemini-3.8-flash"
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})


def test_retired_model_message_and_default():
    assert A.GEMINI_DEFAULT_MODEL in ("gemini-flash-latest",) or A.os.environ.get("GEMINI_MODEL")
    msg, kind = A._ai_error(_R(404, {"error": {"message": "This model models/gemini-2.5-flash is no longer available."}}))
    assert kind == "gone" and "최신 Flash" in msg


def test_overload_fills_live_model_list(monkeypatch):
    """과부하로 대체할 때 모델 목록이 비어 있으면 ListModels로 현행 모델을 채워 그중에서 고른다."""
    calls = []
    def post(url, **kw):
        calls.append(url)
        if "gemini-flash-latest:" in url:
            return _R(503, {"error": {"message": "The model is overloaded."}})
        return _ok("ok")
    def latest(k):
        A._GEMINI_MODEL_CACHE["ranked"] = ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-pro"]
        return "gemini-3.8-flash"
    monkeypatch.setattr(A.req_lib, "post", post)
    monkeypatch.setattr(A, "_gemini_latest_model", latest)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})
    text, err = A._ai_generate("gemini", "k", "gemini-flash-latest", "sys", "user")
    assert (text, err) == ("ok", "") and "gemini-3.8-flash:" in calls[-1]
    A._GEMINI_MODEL_CACHE.update({"model": None, "ranked": []})
