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
