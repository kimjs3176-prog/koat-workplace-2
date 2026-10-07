"""완성도 점검에서 찾은 결함의 회귀 테스트 — 일괄 정비 조사, 삭제 조, 항 기호, 문서 서식, 인용 관계, 에이전트 계획, 표기 점검, 업로드."""
import io
import re
import zipfile
from xml.dom import minidom


# ── 일괄 정비 ───────────────────────────────────────────────────────────────
def test_replace_term_neutral_particles(ra):
    for t, want in [("이사장의 승인", "원장의 승인"), ("이사장에게 보고", "원장에게 보고"),
                    ("이사장도 참석", "원장도 참석"), ("이사장만 정한다", "원장만 정한다")]:
        assert ra.replace_term(t, "이사장", "원장")[0] == want
    # 다른 낱말(이사회·이사장)은 그대로
    assert ra.replace_term("이사회와 이사장", "이사", "임원")[0] == "이사회와 이사장"


def test_bulk_sentence_records_particle_change(ra):
    s = ra._bulk_sentence([("제3조", ("부원장", "총괄이사")), ("제4조", ("부원장은", "총괄이사는")),
                           ("제5조", ("부원장", "총괄이사"))], "부원장", "총괄이사")
    assert s == "제3조, 제5조 중 “부원장”을 각각 “총괄이사”로 하고, 제4조 중 “부원장은”을 “총괄이사는”으로 한다."


def test_bulk_named_term_cap(client, ra):
    # 기관장 명칭은 흔해도 직제 개편 때 모두 고쳐야 하므로 막지 않는다
    d = client.post("/api/regagent/bulk", json={"old": ra.ORG["head"], "new": "이사장"}).get_json()
    assert d["success"], d.get("error")


# ── 조문 구조 ───────────────────────────────────────────────────────────────
def test_deleted_article_with_title(ra):
    p = ra.parse_text("제1조(목적) 가.\n제2조(기구) 삭제 <2020. 1. 1.>\n제3조(기타) 다.")
    assert [a["deleted"] for a in p["articles"]] == [False, True, False]


def test_dingbat_hang_normalized(ra):
    p = ra.parse_text("제1조(목적) ⓛ 가.\n➁ 나.")
    assert p["articles"][0]["body"].startswith("①") and "②" in p["articles"][0]["body"]
    assert not [i for i in ra.lint_articles(p["articles"], "시행한다") if i["code"] == "hang"]


def test_lint_reference_to_deleted_article(ra):
    p = ra.parse_text("제1조(목적) 제3조에 따른다.\n제2조(기타) 나.\n제3조 삭제")
    iss = ra.lint_articles(p["articles"], "이 규정은 발령한 날부터 시행한다.")
    assert any(i["code"] == "ref" and "삭제된 제3조" in i["msg"] for i in iss)


def test_clean_addenda_strips_heading(ra):
    assert ra._clean_addenda(["부칙 이 규칙은 발령한 날부터 시행한다.", "", "부 칙 <2026. 1. 1.> 제2조(경과조치) 가."]) == \
        ["이 규칙은 발령한 날부터 시행한다.", "제2조(경과조치) 가."]


def test_template_has_no_term_noise(ra):
    t = ra.template_enact({"title": "드론 운영지침", "purpose": "드론 운영",
                           "delegations": [{"law": "항공안전법", "art": "제5조(기술지원)"}]})
    assert "제5조에 따라" in t["articles"][0]["body"]          # 위임 조항 제목은 빼고 인용
    assert not ra.term_check(t["articles"])
    assert "을(를)" not in t["reason"]["purpose"]


# ── 문서 파일 ───────────────────────────────────────────────────────────────
_BLOCKS = [{"t": "p", "text": "「여비규정」 개정 이유서\n본문\x0b", "titleBold": 1},
           {"t": "table", "colWidths": [1, 3], "rows": [[{"t": "현 행", "hd": 1}, {"t": "개 정 안", "hd": 1}],
            [{"t": "3만원", "r": [{"s": "숙박비 "}, {"s": "3만원", "u": "d"}]}, {"t": "5만원", "r": [{"s": "숙박비 "}, {"s": "5만원", "u": "i"}]}]]}]


def test_hwpx_keeps_underline_and_header(ra):
    z = zipfile.ZipFile(io.BytesIO(ra.build_hwpx(_BLOCKS)))
    for n in z.namelist():
        if n.endswith(".xml"):
            minidom.parseString(z.read(n))                       # 제어 문자가 있어도 올바른 XML
    sec, head = z.read("Contents/section0.xml").decode(), z.read("Contents/header.xml").decode()
    ul = re.findall(r'<hh:charPr id="(\d+)"[^>]*>(?:(?!</hh:charPr>).)*<hh:underline', head, re.S)
    assert len(ul) >= 2
    assert re.search(r'charPrIDRef="(%s)"><hp:t>3만원' % "|".join(ul), sec)
    assert 'header="1"' in sec
    assert z.read("Preview/PrvText.txt").decode().startswith("「여비규정」")


def test_docx_underline_and_widths(ra):
    doc = zipfile.ZipFile(io.BytesIO(ra.build_docx(_BLOCKS))).read("word/document.xml").decode()
    minidom.parseString(doc)
    assert doc.count("<w:u ") == 2
    assert '<w:gridCol w:w="2250"/><w:gridCol w:w="6750"/>' in doc
    assert '<w:jc w:val="center"/>' in doc


# ── 인용 관계·에이전트 ──────────────────────────────────────────────────────
def test_graph_ignores_national_decree(ra):
    g = ra.citation_graph()
    assert not [b for b in g["broken"] if b["name"] == "보안업무규정"]


def test_plan_short_law_and_missing_article(client):
    d = client.post("/api/regagent/plan", json={"request": "청탁금지법이 바뀌었어"}).get_json()["plan"]
    assert d["mode"] == "upper" and d["law"] == "청탁금지법"
    d = client.post("/api/regagent/plan", json={"request": "여비규정 제99조 일비 인상"}).get_json()["plan"]
    assert d.get("missing") == ["99"] and any("제99조" in r for r in d["reasoning"])


def test_health_skips_unmatched_law(ra):
    r = next(x for x in ra.all_regs() if ra.cited_laws(x))
    nm = ra.cited_laws(r)[0]
    row = ra.health_row(r, {nm: {"ef": "20990101", "found": False}}, "20991231")
    assert not row["stale_laws"]


# ── 표기 점검 ───────────────────────────────────────────────────────────────
def _rules(t):
    import notation
    return {(f["rule"], f["suggest"]) for f in notation.check(t, "law")}


def test_notation_false_positives(ra):
    import notation
    assert not [f for f in notation.check("붙임 자료를 참고하시기 바랍니다.  끝.") if f["rule"].startswith("BUNIM")]
    assert ("TIME", "14:00") in _rules("회의는 오후 2:00에 연다.")
    assert not _rules("www.koat.or.kr:8080 에 접속한다.")
    assert ("TILDE", "제1조∼제5조") in _rules("제1조~제5조")
    assert ("MONEY", "금30,000원(금삼만원)") in _rules("금 30,000원 (금삼만원)")


# ── 업로드 ──────────────────────────────────────────────────────────────────
def test_html_upload_text(ra):
    import reg_import
    r = reg_import._convert_upload("a.html", "<html><head><title>T</title></head><body><p>제1조(목적) A&nbsp;&amp; B</p><p>제2조(x) y</p></body></html>".encode(), "T", {})
    assert r["text"] == "제1조(목적) A & B\n제2조(x) y" and not r["warning"]
    assert [a["no"] for a in ra.parse_text(r["text"])["articles"]] == ["1", "2"]


def test_write_reg_drops_stale_text(tmp_path, monkeypatch):
    import reg_import
    monkeypatch.setattr(reg_import, "REG_DIR", str(tmp_path))
    reg_import.write_reg("r", "<p>v1</p>", "제1조(목적) 옛 본문", "a.hwpx", b"x")
    reg_import.write_reg("r", "<p>v2</p>", "", "a.pdf", b"%PDF")
    files = sorted(p.name for p in (tmp_path / "r").iterdir())
    assert files == ["index.html", "original.pdf"]
