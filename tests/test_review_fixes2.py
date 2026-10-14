"""완성도 2차 점검에서 고친 부분의 회귀 테스트."""
import io
import xml.etree.ElementTree as ET

import pytest

import reg_agent as ra
import reg_import as ri


@pytest.mark.parametrize("text,want", [
    ("국가표준기본법 및 산업표준화법 제27조에 따라", []),
    ("「근로자참여 및 협력증진에 관한 법률」제6조제2항의 근로자위원 또는 제26조", []),
    ("「법」 제6조의 규정에도 불구하고 제26조에 따른다", ["26"]),
    ("위원회는 제6조에 따른다", ["6"]),
])
def test_internal_refs(text, want):
    assert [x[0] for x in ra.internal_refs(text)] == want


def test_law_aliases_and_removed_terms():
    assert "부정청탁 및 금품등 수수의 금지에 관한 법률" in ra._law_aliases("청탁금지법")
    assert ra._law_aliases("근로 기준법") == ["근기법", "근로기준법"]
    old = "① 공공기관의 장은 임원 중 사람을 임명한다. 기관의 장은 이를 공개한다."
    new = "① 공공기관장은 임원 중 사람을 임명한다. 기관장은 이를 공개한다."
    assert ra._removed_terms(old, new) == []
    assert "부원장" in ra._removed_terms("부원장이 결재한다.", "총괄이사가 결재한다.")


def test_upper_spacing_and_alias(client):
    a = client.post("/api/regagent/upper", json={"law": "개인정보 보호법"}).get_json()
    b = client.post("/api/regagent/upper", json={"law": "개인정보보호법"}).get_json()
    assert a["count"] == b["count"] > 0 and "truncated" in a
    c = client.post("/api/regagent/upper", json={"law": "청탁금지법"}).get_json()
    d = client.post("/api/regagent/upper", json={"law": "부정청탁 및 금품등 수수의 금지에 관한 법률"}).get_json()
    assert c["count"] == d["count"]


def test_bulk_join_locs():
    assert ra._join_locs(["제13조 제목", "제13조제1항", "제15조"]) == "제13조의 제목, 같은 조 제1항 및 제15조"


def test_bulk_routing_without_keyword():
    assert ra.heuristic_plan("경영지원팀을 경영관리팀으로 바꿔줘")["mode"] == "bulk"
    assert ra.heuristic_plan("여비규정에서 원장을 이사장으로 바꿔줘")["mode"] != "bulk"


def test_lint_own_articles_of_incorporation():
    r = ra.lint_articles([{"no": "1", "title": "목적", "body": "「농진원 정관」 제5조에 따라 정한다.", "deleted": False}])
    items = r.get("items") if isinstance(r, dict) else r
    assert not [x for x in items if "regname" in str(x)]


@pytest.mark.parametrize("ln", ["부 칙2023. 03. 15.", "<부칙>", "【부칙】", "부칙 <2022. 3. 29.>"])
def test_addenda_line(ln):
    assert ra._ADDENDA_LINE.match(ln)


def test_addenda_line_not_body():
    assert not ra._ADDENDA_LINE.match("부칙에 따라 처리한다.")
    assert ra._APPX_LINE.match("〔별표1〕 <제20조 관련>") and ra._APPX_LINE.match("【별표 2】")


def test_decode_rejects_binary_and_reads_utf16():
    assert ri._decode("제1조(목적) 가".encode("utf-16")) == "제1조(목적) 가"
    assert ri._decode("제1조 가".encode("cp949")) == "제1조 가"
    with pytest.raises(ValueError):
        ri._decode(bytes(range(256)) * 20)


def test_hwpx_text_after_nested_tab():
    ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = (f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{ns}">'
           f'<hp:p><hp:run><hp:t>제1조(목적)<hp:tab/>이 규정은<hp:lineBreak/>정한다.</hp:t></hp:run></hp:p></hs:sec>')
    blocks = ri._xml_blocks(ET.fromstring(xml), "p", "tbl", "tr", "tc", {"t"}, {"lineBreak"})
    text = "\n".join(b["text"] for b in blocks if b["type"] == "p")
    assert "이 규정은" in text and "정한다." in text


def test_body_cleans_surrogates_and_bad_types(client):
    for path, body in [("/api/regagent/review", '{"text":"제1조(목적) 가.","focus":5}'),
                       ("/api/regagent/review", '{"text":"제1조(목적) 가.","alio_refs":true}'),
                       ("/api/regagent/hwpx", '{"blocks":[{"t":"p","text":"\\ud800 x"}]}'),
                       ("/api/regagent/docx", '{"blocks":[{"t":"table","rows":[[{"t":"a","cs":Infinity}]]}]}')]:
        r = client.post(path, data=body, content_type="application/json")
        assert r.status_code == 200, (path, r.get_data(as_text=True)[:200])
