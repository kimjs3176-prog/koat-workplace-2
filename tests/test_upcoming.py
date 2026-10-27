"""상위법 개정 선제 알림: 공포됐지만 시행 전인 판을 찾아 인용 내규와 함께 보여 준다."""
import xml.etree.ElementTree as ET

import reg_agent as ra


def _reg(slug, body, rev="2024년 1월 개정"):
    return {"slug": slug, "title": slug + "규정", "category": "규정", "revision": rev, "addenda": "", "appendix": "",
            "articles": [{"no": "1", "title": "", "body": body, "deleted": False}]}


def test_lookup_law_records_next_version(monkeypatch):
    import api_server as A
    root = ET.Element("LawSearch")
    for st, ef, anc, typ in (("현행", "20250101", "20241201", "일부개정"), ("시행예정", "20990301", "20990101", "일부개정"),
                             ("시행예정", "20990601", "20990105", "타법개정"), ("연혁", "20200101", "20191201", "제정")):
        it = ET.SubElement(root, "law")
        for k, v in (("법령일련번호", ef), ("법령ID", "1"), ("법령명한글", "근로기준법"), ("현행연혁코드", st),
                     ("시행일자", ef), ("공포일자", anc), ("제개정구분명", typ)):
            ET.SubElement(it, k).text = v
    monkeypatch.setattr(A, "_law_get_xml", lambda *a, **k: root)
    v = A._lookup_law("근로기준법", "law")
    assert v["ef"] == "20250101" and v["next"] == {"ef": "20990301", "anc": "20990101", "type": "일부개정", "status": "시행예정", "name": "근로기준법"}


def test_health_laws_passes_next(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "law_info", lambda nm: {"mst": "1", "rank": 0, "ef": "20250101",
                                                         "next": {"ef": "20990301", "anc": "20990101", "type": "일부개정"}})
    ra._LAW_FRESH.clear()
    d = client.post("/api/regagent/health/laws", json={"names": ["근로기준법"]}).get_json()
    assert d["laws"]["근로기준법"]["next"] == {"ef": "20990301", "anc": "20990101", "type": "일부개정"}
    ra._LAW_FRESH.clear()


def test_health_row_upcoming_and_aggregate():
    info = {"근로기준법": {"ef": "20230101", "found": True, "next": {"ef": "20261201", "anc": "20261001", "type": "일부개정"}},
            "고용보험법": {"ef": "20230101", "found": True, "next": {"ef": "20280101", "anc": "20261001", "type": "일부개정"}}}   # 180일 밖
    a = ra.health_row(_reg("가", "「근로기준법」과 「고용보험법」에 따른다."), info, "20261027")
    b = ra.health_row(_reg("나", "「근로기준법」에 따른다."), info, "20261027")
    assert a["upcoming"] == [{"law": "근로기준법", "ef": "20261201", "anc": "20261001", "type": "일부개정", "kind": "law"}]
    assert not a["stale_laws"]                                   # 시행 전이라 미반영으로 감점하지 않는다
    up = ra.upcoming_laws([a, b])
    assert [(u["law"], [r["slug"] for r in u["regs"]]) for u in up] == [("근로기준법", ["가", "나"])]


def test_health_endpoint_has_upcoming(client):
    d = client.post("/api/regagent/health", json={"law_info": {}}).get_json()
    assert d["upcoming"] == []
