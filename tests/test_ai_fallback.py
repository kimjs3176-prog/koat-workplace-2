"""AI 호출 실패(과부하 503·한도 429) 때 다른 Gemini 모델로 자동 전환하는지."""
import json
import time

import api_server as A


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
    assert A._gemini_alternates("gemini-2.5-flash") == ["gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-flash-latest"]
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
    assert any("gemini-2.5-flash-lite:" in u for u in calls)


def test_generate_reports_alternates_when_all_fail(monkeypatch):
    monkeypatch.setattr(A.req_lib, "post", lambda url, **kw: _R(429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "status": "RESOURCE_EXHAUSTED"}}))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    A._GEMINI_MODEL_CACHE["ranked"] = []
    text, err = A._ai_generate("gemini", "k", "gemini-2.5-flash", "sys", "user")
    assert text == "" and "사용량 한도" in err and "대체 모델" in err and "gemini-2.5-flash-lite" in err


def test_error_kinds():
    assert A._ai_error(_R(429, {"error": {"message": "quota exceeded"}}))[1] == "quota"
    assert A._ai_error(_R(503, {"error": {"message": "The model is overloaded"}}))[1] == "overload"
    assert A._ai_error(_R(403, {"error": {"message": "API key not valid"}}))[1] == "auth"
