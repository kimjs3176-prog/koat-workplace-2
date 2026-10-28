"""조직·위원회(규정 온톨로지 2단계): 직제 조직도, 위원회 설치·구성, 직위·기능 부서, 직제에 없는 조직명."""
import pytest

import reg_agent as R


@pytest.fixture()
def client():
    import api_server
    api_server.app.config["TESTING"] = True
    return api_server.app.test_client()


def test_org_tree_from_jikje():
    E = R.entities()
    U = E["units"]
    assert U["기획운영본부"]["parent"] == E["deputy"] and U["홍보실"]["parent"] == E["head"]
    assert U["윤리감사실"]["parent"] == E["head"]                      # “…을 두고 … 윤리감사실을 둔다”
    assert "인사혁신실" in U["기획운영본부"]["children"] and U["기획운영본부"]["head"] == "기획운영본부장"
    assert U["종자산업진흥센터"]["parent"] == "종자사업본부"           # “종자사업본부에 두는 종자산업진흥센터”
    assert "업무를 수행" in U["기획운영본부"]["duty"]


def test_committees_setup_and_composition():
    C = R.entities()["committees"]
    c = C["인사위원회"]
    assert c["reg"] == "인사규정" and c["size"] == "8명 이상 12명 이하" and c["chair"] == "부원장"
    assert c["verb"] == "심의·의결" and any("신규채용" in f for f in c["functions"])
    assert C["민간기술이전심의회"]["size"] == "5명 이내"                # 원문에 끊긴 띄어쓰기(“민 간기술이전심의회”)
    s = C["산업안전보건위원회"]                                         # 「○○위원회 운영규칙」에서 구성을 채운다
    assert s["rules"]["slug"] == "산업안전보건위원회_운영규칙" and s["chair"] == "원장"
    assert C["이사회"]["size"] == "이사 전원" and C["이사회"]["chair"] == "원장"
    assert C["감사자문위원회"]["chair"] == "감사"
    generic = [k for k in C if k.startswith("심의위원회@")]
    assert len(generic) >= 3                                          # 내규마다 따로 둔 “심의위원회”는 구별한다
    assert not any(k.startswith(("따라", "경우", "반드시")) for k in C)


def test_roles_depts_unknown():
    E = R.entities()
    roles = {r["name"]: r for r in E["roles"]}
    assert roles[E["head"]]["n"] > 100 and "기획운영본부장" in roles
    d = next(x for x in E["depts"] if x["name"] == "내규관리부서")
    assert d["defs"]                                                  # 용어 사전의 정의와 이어진다
    odd = {x["name"] for x in R.unknown_units()}
    assert "총괄관리본부" in odd and "기획운영본부" not in odd


def test_org_api(client):
    d = client.get("/api/regagent/org").get_json()
    assert d["success"] and d["stats"]["units"] >= 40 and d["stats"]["committees"] >= 50
    x = client.post("/api/regagent/org/item", json={"kind": "committee", "id": "인사위원회"}).get_json()
    assert x["item"]["chair"] == "부원장" and x["item"]["articles"]
    x = client.post("/api/regagent/org/item", json={"kind": "unit", "id": "기획운영본부"}).get_json()
    assert x["item"]["articles"] and x["item"]["parent"]
    assert client.post("/api/regagent/org/item", json={"kind": "unit", "id": "없는조직"}).status_code == 404


def test_ontology_includes_org(client):
    d = client.get("/api/regagent/ontology").get_json()
    inc = d["@included"]
    u = next(x for x in inc if x.get("rdfs:label") == "인사혁신실")
    assert u["org:subOrganizationOf"]["@id"].endswith("unit/기획운영본부")
    c = next(x for x in inc if x.get("rdfs:label") == "인사위원회")
    assert c["org:classification"] == "회의체" and "부원장" in c["rdfs:comment"]
