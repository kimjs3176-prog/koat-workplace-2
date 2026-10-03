"""reg_agent 순수 함수 — 조문 파싱·점검·인용 정정·용어 치환·계획."""
SAMPLE = ("제1조(목적) 이 규정은 목적을 정한다.\n"
          "제2조(정의) ① 용어는 다음과 같다.\n1. \"가\"란 가이다.\n② 제1조에 따른다.\n"
          "제3조(위임) 제2조제1항 및 제5조에 따른다.\n"
          "부칙\n이 규정은 발령한 날부터 시행한다.")


def test_parse_text_articles_and_addenda(ra):
    p = ra.parse_text(SAMPLE)
    assert [(a["no"], a["title"]) for a in p["articles"]] == [("1", "목적"), ("2", "정의"), ("3", "위임")]
    assert p["addenda"].startswith("부칙")


def test_parse_text_branch_and_deleted(ra):
    p = ra.parse_text("제1조(목적) 가.\n제1조의2(특례) 나.\n제2조 삭제 <2024. 1. 1.>\n제3조(기타) 다.")
    nos = [a["no"] for a in p["articles"]]
    assert nos[:2] == ["1", "1의2"]
    assert "2" in nos and "3" in nos


def test_parse_text_empty(ra):
    p = ra.parse_text("")
    assert p["articles"] == []


def test_art_key_order(ra):
    assert sorted(["3", "1의2", "1", "10"], key=ra.art_key) == ["1", "1의2", "3", "10"]


def test_lint_missing_article_reference(ra):
    p = ra.parse_text(SAMPLE)
    iss = ra.lint_articles(p["articles"], p["addenda"], title="시험규정")
    refs = [i for i in iss if i["code"] == "ref"]
    assert len(refs) == 1 and "제5조" in refs[0]["msg"]


def test_lint_duplicate_number(ra):
    p = ra.parse_text("제1조(목적) 가.\n제2조(정의) 나.\n제2조(적용) 다.")
    iss = ra.lint_articles(p["articles"], "", title="시험규정")
    assert any(i["level"] == "error" for i in iss)


def test_lint_ignores_external_law_refs(ra):
    p = ra.parse_text("제1조(목적) 「공공기관의 운영에 관한 법률」 제31조에 따른다.\n제2조(기타) 나.")
    iss = ra.lint_articles(p["articles"], "", title="시험규정")
    assert not [i for i in iss if i["code"] == "ref"]


def test_retarget_refs(ra):
    out, n = ra.retarget_refs("제2조제1항 및 제3조에 따라", {"2": "3", "3": "4"})
    assert out == "제3조제1항 및 제4조에 따라" and n == 2


def test_retarget_refs_keeps_external(ra):
    out, n = ra.retarget_refs("「여비규정」 제2조에 따르고, 이 규정 제2조", {"2": "3"})
    assert out == "「여비규정」 제2조에 따르고, 이 규정 제3조" and n == 1
    # 외부 인용에 이어진 나열(「…」 제15조, 제17조)도 외부로 본다
    assert ra.retarget_refs("「개인정보 보호법」 제2조, 제3조", {"3": "4"})[1] == 0


def test_replace_term_fixes_josa(ra):
    out, hits = ra.replace_term("기획운영본부는 기획운영본부를 둔다", "기획운영본부", "경영지원실")
    assert out == "경영지원실은 경영지원실을 둔다" and len(hits) == 2


def test_replace_term_whole_word(ra):
    out, hits = ra.replace_term("부원장과 원장", "원장", "기관장", whole=True)
    assert "부원장" in out and hits


def test_heuristic_plan_modes(ra):
    assert ra.heuristic_plan("기획운영본부를 경영기획본부로 모든 내규에서 바꿔줘")["mode"] == "bulk"
    assert ra.heuristic_plan("여비규정 제15조의 일비를 3만원으로 올려줘")["mode"] == "amend"
    assert ra.heuristic_plan("업무용 드론 운영지침을 새로 만들어줘")["mode"] == "enact"
    assert ra.heuristic_plan("「공공기관의 운영에 관한 법률」 제31조가 개정됐어")["mode"] == "upper"


def test_rev_date(ra):
    assert ra.rev_date("2023년도 5월 일부개정") == "20230501"
    assert ra.rev_date("") == ""


def test_xml_escape_in_documents(ra):
    import zipfile, io
    blocks = [{"t": "p", "text": "<b>&\"'</b>"}, {"t": "table", "rows": [[{"t": "<x>", "hd": 1}, {"t": "a&b"}]]}]
    for build in (ra.build_hwpx, ra.build_docx):
        z = zipfile.ZipFile(io.BytesIO(build(blocks)))
        body = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml"))
        assert "<b>&" not in body and "&lt;b&gt;" in body


def test_org_format(ra):
    assert "{" not in ra.ofmt("{org}·{head}")


# ── 서버 검토에서 찾은 결함의 회귀 테스트 ────────────────────────────────────
def test_replace_term_short_word_boundary(ra):
    out, hits = ra.replace_term("이사장은 이사회를 소집하고 이사는 출석한다.", "이사", "임원")
    assert out == "이사장은 이사회를 소집하고 임원은 출석한다." and len(hits) == 1


def test_replace_term_long_name_derivative(ra):
    out, _ = ra.replace_term("기획운영본부장은 기획운영본부를", "기획운영본부", "경영기획본부")
    assert out == "경영기획본부장은 경영기획본부를"


def test_replace_term_compound_particles(ra):
    got = [ra.replace_term(t, "부서", "팀")[0] for t in ["부서와의", "부서로부터", "부서로서", "부서와는"]]
    assert got == ["팀과의", "팀으로부터", "팀으로서", "팀과는"]


def test_internal_refs_after_common_words(ra):
    assert ra.internal_refs("방법 제3조에 따른다") and ra.internal_refs("운영 제3조")
    assert not ra.internal_refs("근로기준법 제3조") and not ra.internal_refs("같은 법 시행령 제3조")


def test_style_hints_need_word_boundary(ra):
    p = ra.parse_text("제1조(목적) 공동조사와 노동조합 및 비상기구를 둔다.")
    assert not [i for i in ra.lint_articles(p["articles"], "", title="x") if i["code"] == "style"]


def test_lint_counts_paragraphs_on_one_line(ra):
    p = ra.parse_text("제2조(정의) ① 가를 말한다. ② 나를 말한다.")
    assert not [i for i in ra.lint_articles(p["articles"], "", title="x") if i["code"] == "hang1"]


def test_org_profile_validation(ra):
    org = ra._check_org({**ra._ORG_DEFAULT, "stale_terms": [["구", "신", "2020"], "x", ["옛", "새"]],
                         "review_criteria": [{"id": "a"}, {"id": "b", "t": "기준"}], "notice_days": "abc"})
    assert org["stale_terms"] == [["옛", "새"]]
    assert [c["id"] for c in org["review_criteria"]] == ["b"]
    assert org["notice_days"] == ra._ORG_DEFAULT["notice_days"]


def test_sanitize_html_blocks_script_vectors():
    import reg_import as ri
    for h in ["<svg/onload=alert(1)>", "<a href=javascript:alert(1)>x</a>", '<a href="jav&#x61;script:alert(1)">x</a>']:
        out = ri._sanitize_html(h).lower()
        assert "onload" not in out and "javascript" not in out and "&#x61;" not in out
    assert ri._sanitize_html('<a href="https://law.go.kr">ok</a>') == '<a href="https://law.go.kr">ok</a>'


def test_reg_slug_limits():
    import reg_import as ri
    assert len(ri.reg_slug("가" * 120).encode("utf-8")) <= 200
    assert ri.reg_slug("a\x00b#c%d/e") == "abcde"
