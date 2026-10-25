"""공공데이터(법제처) 활용: 내규 자문의 법령해석례 참고, 건강검진의 행정규칙 최신성."""
import xml.etree.ElementTree as ET

import pytest

import reg_agent as ra


def _reg(body, title="시험규칙", revision="2020년 3월 1일 개정"):
    return {"slug": "t", "title": title, "category": "", "revision": revision, "addenda": "", "appendix": "",
            "articles": [{"no": "1", "title": "준용", "body": body, "deleted": False}]}


def test_cited_rules_picks_government_rules_only():
    r = _reg("「기타공공기관 계약사무 운영규정(기획재정부훈령)」, 「종자관리요강」, 「인사규정」, 「국가공무원법」, "
             "「농진원 정관」, 「공공기 관의 안전관리에 관한 지침」, 「종자관리요강」, 「인사 규정」, 「한국농업기술진흥원 회계기준」에 따른다.")
    assert ra.cited_rules(r) == ["기타공공기관 계약사무 운영규정", "종자관리요강", "공공기 관의 안전관리에 관한 지침"]


def test_health_row_flags_rule_enforced_after_revision():
    r = _reg("「종자관리요강」과 「공공기 관의 안전관리에 관한 지침」에 따른다.")
    info = {"종자관리요강": {"ef": "20221020", "found": True},
            "공공기관의 안전관리에 관한 지침": {"ef": "20240101", "found": True}}   # 띄어쓰기가 다른 표기로 확인해도 같은 규범
    row = ra.health_row(r, info, "20261025")
    assert [(x["law"], x["kind"]) for x in row["stale_laws"]] == [("종자관리요강", "rule"), ("공공기 관의 안전관리에 관한 지침", "rule")]
    assert "내규 개정 뒤 시행된 상위법·행정규칙 2건" in row["reasons"]
    assert row["rules"] and row["laws"] == []
    r = _reg("「국가공무원 복무규정」에 따른다.")
    row = ra.health_row(r, {"국가공무원 복무규정": {"ef": "20261002", "found": True, "kind": "law"}}, "20261025")
    assert row["stale_laws"][0]["kind"] == "law" and "내규 개정 뒤 시행된 상위법 1건" in row["reasons"]   # 대통령령은 상위법
    row = ra.health_row(r, {"국가공무원 복무규정": {"ef": "20221020", "found": False}}, "20261025")
    assert not row["stale_laws"]                                     # 법제처에 없는 이름은 미반영으로 보지 않는다


def test_health_lists_rules_once(client):
    d = client.post("/api/regagent/health", json={"law_info": {}}).get_json()
    assert d["rules"] and not set(d["rules"]) & set(d["laws"])
    keys = [ra._nk(x) for x in d["rules"]]
    assert len(keys) == len(set(keys))                               # 표기만 다른 같은 규범은 한 번만 조회
    assert "공공기관의 안전관리에 관한 지침" in d["rules"]                # 가장 많이 쓴(띄어쓰기가 바른) 표기


def test_health_laws_routes_rules_to_admrul_lookup(client, monkeypatch):
    seen = []
    monkeypatch.setitem(ra._CTX, "law_info", lambda nm: seen.append(("law", nm)) or {"mst": "1", "rank": 0, "ef": "20250101"})
    monkeypatch.setitem(ra._CTX, "rule_info", lambda nm: seen.append(("rule", nm)) or
                        {"mst": "2", "rank": 0, "ef": "20260101", "kind": "admrul"})
    ra._LAW_FRESH.clear()
    d = client.post("/api/regagent/health/laws", json={"names": ["국가공무원법", "종자관리요강"]}).get_json()
    assert sorted(seen) == [("law", "국가공무원법"), ("rule", "종자관리요강")]
    assert d["laws"]["종자관리요강"] == {"ef": "20260101", "status": "", "name": "", "kind": "admrul", "found": True}
    assert d["laws"]["국가공무원법"]["kind"] == "law"
    ra._LAW_FRESH.clear()


def test_lookup_rule_tries_law_then_admrul(monkeypatch):
    import api_server as A
    calls = []

    def fake(name, target="law"):
        calls.append((target, name))
        if target == "law":
            return {"mst": "9", "rank": 3, "name": "다른 법령"}
        return {"mst": "5", "rank": 0, "name": name, "ef": "20261016"}
    monkeypatch.setattr(A, "_lookup_law", fake)
    v = A._lookup_rule("기타공공기관 계약사무 운영규정(기획재정부훈령)")
    assert v["kind"] == "admrul" and v["ef"] == "20261016"
    assert calls == [("law", "기타공공기관 계약사무 운영규정"), ("admrul", "기타공공기관 계약사무 운영규정")]
    calls.clear()
    A._lookup_rule("개인정보보호 업무처 리 지침")                       # PDF 에서 깨진 띄어쓰기는 붙여서 찾는다
    assert calls[0] == ("law", "개인정보보호업무처리지침")
    monkeypatch.setattr(A, "_lookup_law", lambda name, target="law": {"mst": "", "rank": 99, "error": "timeout"})
    assert A._lookup_rule("종자관리요강").get("error")                 # 조회 실패는 '없음'과 구분(캐시하지 않음)


# ── 법령해석례 ────────────────────────────────────────────────────────────
def _search_xml(items):
    root = ET.Element("Expc")
    for sid, title, date in items:
        e = ET.SubElement(root, "expc")
        for k, v in (("법령해석례일련번호", sid), ("안건명", title), ("안건번호", "21-0001"), ("질의기관명", "민원인"),
                     ("회신기관명", "법제처"), ("회신일자", date)):
            ET.SubElement(e, k).text = v
    return root


def _fake_xml(calls, by_query, fail=False):
    def xml(endpoint, params, timeout=None):
        calls.append((endpoint, params.get("query") or params.get("ID"), params.get("search")))
        if fail:
            raise TimeoutError("slow")
        if endpoint == "lawService.do":
            r = ET.Element("ExpcService")
            for k, v in (("질의요지", "질의 " * 200), ("회답", "회답입니다."), ("해석일자", "20210224")):
                ET.SubElement(r, k).text = v
            return r
        return _search_xml(by_query.get((params["query"], params["search"]), []))
    return xml


def test_expc_search_filters_and_summarizes(monkeypatch):
    calls = []
    by_query = {
        ("계약직원 명예퇴직수당", "1"): [("1", "고용노동부 - 계약직원에게 명예퇴직수당을 지급할 수 있는지 여부", "20200101")],
        ("명예퇴직수당", "1"): [("2", "행정안전부 - 임직원으로 임명된 경우 명예퇴직수당 지급 여부", "20110623"),   # “직원” 조각만 겹침 → 뺀다
                             ("3", "민원인 - 계약직원에게 명예퇴직수당을 지급할 수 있는지 여부", "20190101")],     # 같은 안건 → 하나만
        ("계약직원 명예퇴직수당 공공기관의 운영에 관한 법률", "2"): [("4", "「지방공무원법」 제46조 관련", "20051104")],                     # 본문에 모두 나옴 → 남긴다
    }
    monkeypatch.setitem(ra._CTX, "law_xml", _fake_xml(calls, by_query))
    ra._EXPC_CACHE.clear()
    v = ra.expc_search("계약직원도 명예퇴직수당을 받을 수 있나요?", ["공공기관의 운영에 관한 법률", "인사규정"])
    assert [x["id"] for x in v["items"]] == ["1", "4"]
    a = v["items"][0]
    assert a["title"] == "계약직원에게 명예퇴직수당을 지급할 수 있는지 여부" and a["org"] == "민원인"
    assert a["match"] == ["계약직원", "명예퇴직수당"] and a["date"] == "2021.02.24"
    assert a["answer"] == "회답입니다." and len(a["question"]) <= 301 and a["question"].endswith("…")
    assert a["url"] == "https://www.law.go.kr/LSW/expcInfoP.do?expcSeq=1"
    assert v["items"][1]["body"] and v["items"][1]["match"] == []
    assert ("lawSearch.do", "계약직원 명예퇴직수당 공공기관의 운영에 관한 법률", "2") in calls   # 법령명(내규명 제외)으로 본문 검색
    n = len(calls)
    assert ra.expc_search("계약직원도 명예퇴직수당을 받을 수 있나요?", ["공공기관의 운영에 관한 법률"])["items"]
    assert len(calls) == n                                             # 캐시
    ra._EXPC_CACHE.clear()


def test_expc_endpoint_failure_is_soft(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "law_xml", _fake_xml([], {}, fail=True))
    ra._EXPC_CACHE.clear()
    d = client.post("/api/regagent/expc", json={"question": "청원경찰 징계 절차는?"}).get_json()
    assert d["success"] and d["items"] == [] and "법제처" in d["error"]
    assert not ra._EXPC_CACHE                                          # 실패는 캐시하지 않는다
    assert client.post("/api/regagent/expc", json={"question": "a"}).status_code == 400
    monkeypatch.setitem(ra._CTX, "law_xml", None)
    assert client.post("/api/regagent/expc", json={"question": "청원경찰 징계 절차는?"}).get_json()["items"] == []
