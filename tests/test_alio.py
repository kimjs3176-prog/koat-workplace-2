"""다른 기관 사규(알리오) — 저장한 실제 알리오 응답(tests/fixtures/alio, alio-mcp 가 수집한 공개 공시 자료)으로
네트워크 없이 검색·첨부 목록·본문 조문 추출을 확인한다."""
import io
import json
import os
import struct
import zlib

import pytest

FX = os.path.join(os.path.dirname(__file__), "fixtures", "alio")


def _fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


class _Resp:
    def __init__(self, ct="application/json"):
        self.headers = {"content-type": ct}


@pytest.fixture()
def fake_alio(monkeypatch, ra):
    import alio
    alio._cache.update({"orgs": None, "orgs_at": 0.0, "search": {}, "files": {}, "text": {}})
    orgs = json.loads(_fx("orgs.json"))
    pages = json.loads(_fx("search_C0105_all.json"))
    hwpx = ra.build_hwpx([{"t": "p", "text": "인사규정\n제1조(목적) 이 규정은 인사에 관한 사항을 정한다.\n"
                                             "제2조(여비) ① 출장 여비는 실비로 지급한다.\n② 숙박비는 별표에 따른다.\n"
                                             "제3조(채용) 직원은 공개경쟁으로 채용한다."}])
    calls = []

    def fake(method, path, *, json_body=None, binary=False, retries=2):
        calls.append(path)
        if path.startswith("/item/itemOrganListSusi.json"):
            return _Resp(), json.dumps(orgs)
        if path.startswith("/item/itemReportListSusi.json"):
            if json_body["apbaId"] != "C0105":
                return _Resp(), json.dumps({"data": {"result": [], "page": {"totalPage": 1, "totalCount": 0}}})
            return _Resp(), json.dumps(pages[str(json_body["pageNo"])])
        if path.startswith("/item/itemBoard21110.do"):
            return _Resp("text/html"), _fx("detail_C0105_21892.html")
        if path.startswith("/download/rulefiledown.json"):
            return _Resp("application/octet-stream"), hwpx
        raise AssertionError(path)

    monkeypatch.setattr(alio, "_request", fake)
    return calls


def test_alio_orgs_and_peers(client, fake_alio):
    d = client.get("/api/regagent/alio/orgs").get_json()
    assert d["success"] and len(d["orgs"]) == 355
    assert d["self"] == "C0422"                                  # 한국농업기술진흥원
    names = {o["id"]: o["name"] for o in d["orgs"]}
    assert "농림식품기술기획평가원" in {names[i] for i in d["peers"]} and "C0422" not in d["peers"]


def test_alio_search_paginates_and_marks(client, fake_alio):
    d = client.post("/api/regagent/alio/search", json={"q": "", "category": "K1400", "orgs": ["C0105", "C0422"]}).get_json()
    assert d["success"], d
    assert len(d["hits"]) == 91 and d["searched"] == 2 and not d["failed"]
    h = d["hits"][0]
    assert {"org", "orgId", "title", "idx", "enf", "superseded"} <= set(h)


def test_alio_search_validation(client, fake_alio):
    assert client.post("/api/regagent/alio/search", json={"q": "여비", "orgs": []}).status_code == 400
    assert client.post("/api/regagent/alio/search", json={"q": "", "orgs": ["C0105"]}).status_code == 400
    assert client.post("/api/regagent/alio/rule", json={"orgId": "C0105", "idx": "1;rm"}).status_code == 400


def test_alio_rule_latest_file_to_articles(client, fake_alio):
    d = client.post("/api/regagent/alio/rule", json={"orgId": "C0105", "idx": "21892", "category": "K1100", "q": "여비 숙박비"}).get_json()
    assert d["success"], d
    assert d["file"]["fileNo"] == "218027" and d["versions"] == 7    # 가장 나중에 올린 파일
    assert d["count"] == 3 and d["articles"][0]["no"] == "2"         # 검색어와 가장 맞는 조문이 먼저
    assert d["url"].startswith("https://www.alio.go.kr/item/itemBoard21110.do?")


def test_alio_network_error_is_json(client, monkeypatch, ra):
    import alio
    alio._cache.update({"orgs": None, "orgs_at": 0.0})

    def boom(*a, **k):
        raise alio.AlioError("NETWORK", "알리오 연결 실패: ConnectTimeout")
    monkeypatch.setattr(alio, "_request", boom)
    r = client.get("/api/regagent/alio/orgs")
    assert r.status_code == 502 and "다시 시도" in r.get_json()["error"]


def test_alio_base_title():
    import alio
    assert alio.base_title("인사규정(2023년 1월 개정)") == "인사규정"
    assert alio.base_title("2024년도 업무편람") == "업무편람"


# ── HWP 5.0 레코드·문단 글자 ─────────────────────────────────────────────────
def _rec(tag, payload):
    size = len(payload)
    return struct.pack("<I", tag | (min(size, 0xFFF) << 20)) + (struct.pack("<I", size) if size >= 0xFFF else b"") + payload


def test_hwp_para_text_controls():
    import hwp5
    txt = "제1조(목적) 가".encode("utf-16-le")
    table_ctrl = struct.pack("<H", 11) + b"\0" * 14                # 확장 컨트롤(표 자리) 8 WCHAR
    payload = txt + table_ctrl + struct.pack("<H", 10) + "나".encode("utf-16-le") + struct.pack("<H", 13)
    assert hwp5._para_text(payload) == "제1조(목적) 가\n나"
    big = ("가" * 3000).encode("utf-16-le")                         # 0xFFF 넘는 레코드 크기
    recs = list(hwp5._records(_rec(66, b"xx") + _rec(hwp5.HWPTAG_PARA_TEXT, big)))
    assert [t for t, _ in recs] == [66, hwp5.HWPTAG_PARA_TEXT] and len(recs[1][1]) == 6000


def test_hwp_rejects_non_hwp():
    import hwp5
    with pytest.raises(ValueError):
        hwp5.hwp_paragraphs(b"not a hwp")
    with pytest.raises(ValueError, match="3.x"):
        hwp5.hwp_paragraphs(b"HWP Document File V3.00 \x1a\x01\x02\x03\x04\x05")


# ── 에이전트·심의 사전검토·규정 체계 비교 ─────────────────────────────────────
def test_plan_compare_mode(ra):
    for q, kw in [("다른 기관은 재택근무를 어떻게 규정했어?", "재택근무"), ("다른 기관은 여비를 어떻게 규정했어?", "여비"),
                  ("타 기관 「여비규정」 사례 찾아줘", "여비"), ("공공기관들의 드론 운영 사례 알려줘", "드론")]:
        p = ra.heuristic_plan(q)
        assert p["mode"] == "compare" and p["keyword"] == kw, (q, p)
    # 제정·개정 요청은 사례라는 말이 있어도 제정·개정으로
    assert ra.heuristic_plan("다른 기관 사례 참고해서 드론 운영지침 만들어줘")["mode"] == "enact"
    assert ra.heuristic_plan("여비규정 제15조 일비를 올려줘")["mode"] == "amend"


def test_review_cites_other_agency_cases(ra):
    r = ra.review_draft({"mode": "enact", "title": "드론 운영지침", "text": "제1조(목적) 이 지침은 드론 운영을 정한다.",
                         "purpose": "업무용 드론의 안전한 운영을 위하여 필요한 사항을 정하려는 것임",
                         "alio_refs": [{"org": "한국농어촌공사", "reg": "드론 운영규정", "no": "5", "title": "비행 승인"}]})
    need = next(x for x in r["rows"] if x["id"] == "need")
    assert any("다른 공공기관 운영 사례 1곳" in i["msg"] and "한국농어촌공사 「드론 운영규정」 제5조(비행 승인)" in i["msg"] for i in need["items"])


def test_alio_search_all_without_keyword(client, fake_alio):
    d = client.post("/api/regagent/alio/search", json={"q": "", "all": True, "orgs": ["C0105"]}).get_json()
    assert d["success"] and len(d["hits"]) == 91
