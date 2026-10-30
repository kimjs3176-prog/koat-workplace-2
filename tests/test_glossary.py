# 용어 사전(규정 온톨로지 1단계): 정의 수집·정의 불일치·동의어·자문 연계·내보내기
import pytest
import reg_agent as ra


@pytest.fixture(scope="module")
def client():
    import api_server
    return api_server.app.test_client()


def test_glossary_collects_and_flags_conflicts():
    g = ra.glossary()["terms"]
    assert len(g) > 500
    e = g["임직원"]
    assert e["conflict"] and e["variants"] == 4 and len(e["regs"]) == 4       # 계약직 포함 범위가 내규마다 다르다
    assert g["보수"]["conflict"]
    assert not g.get("위원회", {"conflict": False})["conflict"]                # 일반 약칭은 내규마다 달라도 불일치로 보지 않는다


def test_def_conflict_in_lint_for_draft():
    p = ra.parse_text("제2조(정의) 1. “임직원”이란 원장과 정규직 직원을 말한다.")
    iss = [i for i in ra.lint_articles(p["articles"], "", "", "새 규칙") if i["code"] == "defconf"]
    assert iss and "임직원" in iss[0]["msg"] and iss[0]["level"] == "info"


def test_synonyms_include_user_and_abbr():
    assert "여비" in ra.synonyms("출장비")
    assert "일비" in ra.synonyms("출장수당", {"출장수당": ["일비"]})
    assert ra._user_syn({"a" * 40: ["x"], "y": 3}) == {"a" * 30: ["x"], "y": ["3"]}


def test_terms_api_and_advise_definitions(client):
    d = client.post("/api/regagent/terms", json={"filter": "conflict"}).get_json()
    assert d["success"] and d["stats"]["conflict"] == d["count"] and any(x["term"] == "임직원" for x in d["items"])
    one = client.post("/api/regagent/terms", json={"term": "임직원"}).get_json()["item"]
    assert len(one["defs"]) == 4
    assert client.post("/api/regagent/terms", json={"term": "없는용어"}).status_code == 404
    a = client.post("/api/regagent/advise", json={"question": "임직원에 계약직도 포함되나요?"}).get_json()
    assert a["term_conflicts"] == ["임직원"] and sum(s["role"] == "def" for s in a["sources"]) == 4
    assert any("임직원" in c for c in a["caveats"])
    b = client.post("/api/regagent/advise", json={"question": "출장수당은 하루 얼마인가요?", "synonyms": {"출장수당": ["일비"]}}).get_json()
    assert "일비" in b["tokens"]


def test_ontology_export(client):
    r = client.get("/api/regagent/ontology")
    d = r.get_json()
    assert r.status_code == 200 and d["@type"] == "skos:ConceptScheme"
    c = next(x for x in d["skos:hasTopConcept"] if x["skos:prefLabel"]["@value"] == "임직원")
    assert len(c["skos:definition"]) == 4 and "skos:note" in c
