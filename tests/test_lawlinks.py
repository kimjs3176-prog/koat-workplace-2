"""법령 조문 연결(규정 온톨로지 4단계): 「법」 제N조, 약칭 “법 제N조”, “같은 법”, 범위·나열, 상위법 영향 연계."""
import pytest

import reg_agent as R


@pytest.fixture()
def client():
    import api_server
    api_server.app.config["TESTING"] = True
    return api_server.app.test_client()


def test_arts_in():
    assert R._arts_in("제3조제1항 및 제5조의2") == ["3", "5의2"]
    assert R._arts_in("제129조부터 제132조까지") == ["129", "130", "131", "132"]
    assert R._arts_in("제8조제1항·제2항, 제9조") == ["8", "9"]


def test_law_links_index():
    L = R.law_links()
    laws = L["laws"]
    assert "공공기관의 운영에 관한 법률" in laws and "공운법" not in laws          # 약칭은 정식 명칭으로
    a = laws["공직자의 이해충돌 방지법"]["arts"]
    assert "21" in a and "5" in a                                               # 지침 안의 “법 제21조”(약칭 정의)
    assert {"129", "130", "131", "132"} <= set(laws["형법"]["arts"])             # “제129조부터 제132조까지”
    assert "초·중등교육법" in laws and "초·중등교 육법" not in laws               # 끊긴 띄어쓰기 표기는 묶는다
    assert "대·중소기업 상생협력 촉진에 관한 법률 시행령" in laws               # “같은법 시행령 제14조의3”


def test_lawlinks_api_and_upper(client):
    d = client.get("/api/regagent/lawlinks").get_json()
    assert d["success"] and d["stats"]["laws"] > 100 and d["laws"][0]["regs"] >= d["laws"][-1]["regs"]
    d = client.post("/api/regagent/lawlinks", json={"law": "공운법"}).get_json()
    assert d["law"] == "공공기관의 운영에 관한 법률" and any(a["label"] == "제11조" for a in d["arts"])
    assert client.post("/api/regagent/lawlinks", json={"law": "없는법"}).status_code == 404
    # 상위법 영향: 약칭(“법 제21조”)으로만 인용한 조문도 개정 조문 후보로
    u = client.post("/api/regagent/upper", json={"law": "공직자의 이해충돌 방지법", "arts": ["21"]}).get_json()
    assert any(c["reg"] == "이해충돌방지제도 운영지침" and c["specific"] for c in u["candidates"])


def test_ontology_references(client):
    inc = client.get("/api/regagent/ontology").get_json()["@included"]
    assert any("dcterms:references" in x and any("형법" in r["@id"] for r in x["dcterms:references"]) for x in inc)
