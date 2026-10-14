"""완성도 4차 점검(AI 응답 처리 등)에서 고친 부분의 회귀 테스트."""
import pytest

import reg_agent as ra


def test_json_from_trailing_text_and_type():
    assert ra._json_from('{"a": 1}\n참고: 위 {초안}은 예시입니다.') == {"a": 1}
    assert ra._json_from('```json\n{"a": 2}\n```') == {"a": 2}
    with pytest.raises(ValueError):
        ra._json_from('[1, 2]')


@pytest.mark.parametrize("v,want", [("15-2", "15의2"), ("제5조 제1항", "5"), ("제7조의3", "7의3"), ("부칙", ""), (3, "3")])
def test_art_no(v, want):
    assert ra._art_no(v) == want


def _fake(out):
    ra._CTX["ai_generate"] = lambda *a, **k: out


@pytest.fixture
def ai(monkeypatch):
    old = ra._CTX.get("ai_generate")
    yield _fake
    ra._CTX["ai_generate"] = old


AI = {"provider": "claude", "api_key": "k", "model": "claude-x"}


def test_enact_falls_back_to_template(client, ai):
    for out in [("", "과부하"), ("not json", ""), ('{"articles": "x"}', ""), ("[1]", "")]:
        ai(out)
        j = client.post("/api/regagent/draft", json=dict(AI, mode="enact", title="드론 운영지침")).get_json()
        assert j["success"] and j["draft"]["articles"] and "표준 조문 골격" in j["notice"]


def test_enact_normalizes_types(client, ai):
    ai(('{"articles":[{"no":"1","title":"목적","body":"x"},{"no":"1","title":"b","body":"y"}],"reason":{"main":"한 줄"},"notes":"n"}', ""))
    j = client.post("/api/regagent/draft", json=dict(AI, mode="enact", title="x 지침")).get_json()
    assert j["draft"]["reason"]["main"] == ["한 줄"] and j["draft"]["notes"] == ["n"] and "겹칩니다" in j["notice"]


def test_amend_dedup_and_drop_notice(client, ai):
    ai(('{"changes":[{"no":"부칙","body":"x"},{"no":"5","body":"a"},{"no":"제5조","body":"b"},"s"]}', ""))
    j = client.post("/api/regagent/draft", json=dict(AI, mode="amend", intent="수정", reg="여비규정")).get_json()
    assert [c["body"] for c in j["draft"]["changes"]] == ["b"] and "2건" in j["notice"]


def test_plan_coerces_types(client, ai):
    ai(('{"mode":"upper","law":"근로기준법","arts":"제31조"}', ""))
    j = client.post("/api/regagent/plan", json=dict(AI, request="근로기준법이 바뀌었어")).get_json()
    assert j["plan"]["arts"] == ["31"]
    ai(('{"mode":"amend","intent":["여비규정 출장비 인상"]}', ""))
    r = client.post("/api/regagent/plan", json=dict(AI, request="여비규정 출장비를 올려줘"))
    assert r.status_code == 200
