"""/api/regagent/* — 실제 등록 내규(regulations/)로 주요 흐름을 확인한다. 외부(법제처·AI) 호출은 하지 않는다."""
import io
import zipfile

import pytest


def post(client, url, body):
    r = client.post(url, json=body)
    return r.status_code, r.get_json(silent=True)


def test_ping_and_config(client):
    assert client.get("/api/ping").status_code == 200
    d = client.get("/api/regagent/config").get_json()
    assert d["success"] and d["reg_count"] > 0
    proc = d["org"]["procedure"]
    assert proc["steps"] and proc["phases"] and proc["actors"]
    import json, re
    assert not re.search(r"\{[a-z_]+\}", json.dumps(proc, ensure_ascii=False))   # 자리표시자가 모두 치환됨


def test_catalog_and_articles(client):
    regs = client.get("/api/regagent/catalog").get_json()["regs"]
    assert len(regs) > 50
    slug = next(r["slug"] for r in regs if "여비" in r["title"])
    d = client.get(f"/api/regagent/articles?slug={slug}").get_json()
    assert d["success"] and len(d["articles"]) > 10


def test_articles_unknown_slug(client):
    r = client.get("/api/regagent/articles?slug=__nope__")
    assert r.status_code in (400, 404) and r.get_json()["success"] is False


def test_lint_text_and_all(client):
    s, d = post(client, "/api/regagent/lint", {"text": "제1조(목적) 제9조에 따른다.", "title": "시험규칙"})
    assert s == 200 and any(i["code"] == "ref" for i in d["issues"])
    s, d = post(client, "/api/regagent/lint", {"all": True})
    assert s == 200 and d["checked"] > 50


def test_parse(client):
    s, d = post(client, "/api/regagent/parse", {"text": "제1조(목적) 가.\n제2조(정의) 나."})
    assert s == 200 and len(d["articles"]) == 2


def test_similar_keyword(client):
    s, d = post(client, "/api/regagent/similar", {"query": "출장 여비 숙박비 지급", "limit": 5})
    assert s == 200 and d["regs"]


def test_impact(client):
    regs = client.get("/api/regagent/catalog").get_json()["regs"]
    slug = next(r["slug"] for r in regs if "여비" in r["title"])
    s, d = post(client, "/api/regagent/impact", {"slug": slug, "nos": ["15"], "moves": {"15": "16"}})
    assert s == 200 and "summary" in d


def test_bulk(client):
    s, d = post(client, "/api/regagent/bulk", {"old": "기획운영본부", "new": "경영기획본부", "whole": True})
    assert s == 200 and d["reg_count"] > 0 and d["total"] >= d["reg_count"]


def test_upper(client):
    s, d = post(client, "/api/regagent/upper", {"law": "공공기관의 운영에 관한 법률", "arts": []})
    assert s == 200 and d["count"] > 0


def test_draft_template_without_ai(client):
    s, d = post(client, "/api/regagent/draft", {"mode": "enact", "title": "업무용 드론 운영지침", "purpose": "드론 안전 운영",
                                               "contents": "운영책임자: 지정\n비행승인: 사전 승인"})
    assert s == 200 and d["draft"]["template"] and len(d["draft"]["articles"]) >= 4


def test_review_without_ai(client):
    s, d = post(client, "/api/regagent/review", {"mode": "enact", "title": "시험지침", "text": "제1조(목적) 이 지침은 목적을 정한다.",
                                                "addenda": "이 지침은 발령한 날부터 시행한다.", "purpose": "시험", "main": [], "ai": False})
    assert s == 200 and d["rows"]


def test_plan_heuristic(client):
    s, d = post(client, "/api/regagent/plan", {"request": "기획운영본부를 경영기획본부로 모든 내규에서 바꿔줘"})
    assert s == 200 and d["plan"]["mode"] == "bulk"


def test_health(client):
    s, d = post(client, "/api/regagent/health", {"law_info": {}})
    assert s == 200 and d["count"] > 50 and 0 <= d["avg"] <= 100


@pytest.mark.parametrize("fmt", ["hwpx", "docx"])
def test_document_export(client, fmt):
    blocks = [{"t": "p", "text": "제목"}, {"t": "table", "rows": [[{"t": "현 행", "hd": 1}, {"t": "개 정 안", "hd": 1}], [{"t": "가"}, {"t": "나"}]]}]
    r = client.post(f"/api/regagent/{fmt}", json={"filename": "시험", "blocks": blocks})
    assert r.status_code == 200
    zipfile.ZipFile(io.BytesIO(r.data)).testzip()


def test_citation_graph(client):
    d = client.get("/api/regagent/graph").get_json()
    assert d["success"] and d["stats"]["regs"] == len(d["nodes"]) > 50
    n = len(d["nodes"])
    assert all(0 <= e["s"] < n and 0 <= e["t"] < n and e["s"] != e["t"] for e in d["edges"])
    assert sum(x["in"] for x in d["nodes"]) == len(d["edges"])
    assert all(b["kind"] in ("stale", "missing") for b in d["broken"])


def test_quoted_name_does_not_span_brackets(ra):
    names = [m.group(1) for m in ra._QUOTED_NAME.finditer("「정관 및「직제규정」")]
    assert names == ["직제규정"]


def test_bulk_rejects_overly_common_terms(client):
    r = client.post("/api/regagent/bulk", json={"old": "한다", "new": "하여야 한다", "whole": False})
    assert r.status_code == 400 and len(r.data) < 10_000


def test_korean_json_not_escaped(client):
    r = client.get("/api/regagent/config")
    assert "\\u" not in r.get_data(as_text=True)[:2000]
