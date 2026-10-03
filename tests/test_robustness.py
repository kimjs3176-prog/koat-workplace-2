"""잘못된 입력에도 HTML 500 이 아니라 JSON(400/404/200)으로 답해야 한다 — 서버 검토에서 찾은 결함의 회귀 테스트."""
import pytest

POST_ENDPOINTS = ["similar", "impact", "upper", "lint", "parse", "draft", "hwpx", "docx", "bulk",
                  "review", "health", "plan"]
BAD_BODIES = [[1], "abc", 5, None]
BAD_FIELDS = {
    "lint": [{"text": 123}],
    "impact": [{"moves": ["a"]}, {"nos": 5}, {"reg": 5}, {"text": "제1조(목적) 제5조.\n제5조(정의) 가.", "moves": {"5": "abc"}}],
    "upper": [{"arts": 5, "law": "민법"}, {"law": "민법", "old": 5}],
    "bulk": [{"slugs": [{"a": 1}], "old": "기획운영본부", "new": "경영기획본부"}, {"old": 5, "new": "x"}],
    "similar": [{"query": 5}, {"query": "여비", "exclude": 5}],
    "plan": [{"request": 5}],
    "draft": [{"mode": 5}, {"title": "가", "contents": ["a"]}, {"title": "가", "delegations": ["a"]}, {"title": "가", "provider": 5}],
    "review": [{"text": "제1조(목적) 가.", "ans": [1]}, {"text": "제1조(목적) 가.", "delegations": ["x"]}, {"text": "제1조(목적) 가.", "purpose": 5}],
    "hwpx": [{"filename": 5, "blocks": [{"t": "p", "text": "a"}]}, {"blocks": [1]}, {"blocks": "abc"}],
    "docx": [{"filename": 5, "blocks": [{"t": "p", "text": "a"}]}, {"blocks": [1]}, {"blocks": "abc"}],
}


def _ok(r):
    assert r.status_code in (200, 400, 404), (r.status_code, r.data[:200])
    assert r.is_json or r.status_code == 200, r.data[:200]   # 200 은 문서 파일일 수 있다


@pytest.mark.parametrize("ep", POST_ENDPOINTS)
@pytest.mark.parametrize("body", BAD_BODIES)
def test_non_object_body(client, ep, body):
    _ok(client.post(f"/api/regagent/{ep}", json=body))


@pytest.mark.parametrize("ep,body", [(e, b) for e, bs in BAD_FIELDS.items() for b in bs])
def test_wrong_field_types(client, ep, body):
    _ok(client.post(f"/api/regagent/{ep}", json=body))


def test_health_laws_bad_names(client):
    _ok(client.post("/api/regagent/health/laws", json={"names": 5}))


def test_impact_ignores_invalid_moves(client):
    d = client.post("/api/regagent/impact", json={"text": "제1조(목적) 이 규정은 제5조에 따른다.\n제5조(정의) 정의한다.",
                                                  "nos": ["5"], "moves": {"5": "abc"}}).get_json()
    assert "제0조" not in str(d)


@pytest.mark.parametrize("fmt", ["hwpx", "docx"])
@pytest.mark.parametrize("cells", [[{"cs": 12000000}], [{"cs": 1}, {"cs": -1}], [{"cs": "x"}]])
def test_table_colspan_is_bounded(client, fmt, cells):
    r = client.post(f"/api/regagent/{fmt}", json={"blocks": [{"t": "table", "rows": [cells]}]})
    assert r.status_code in (200, 400)
    assert len(r.data) < 2_000_000
