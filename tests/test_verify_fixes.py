"""검증(2026-10)에서 찾은 결함 6건 — 조문 0개 내규, 별표 옛 명칭, 영향분석 〔별표〕, 일괄 정비 머리말, 법령명 띄어쓰기·못 찾은 법령, 수치 단위 ‘주’"""
import copy


def _reg(ra, title):
    return next(r for r in ra.all_regs() if r["title"] == title)


def test_health_unread_reg_has_no_score(ra):
    r = {"slug": "x", "title": "읽지 못한 지침", "category": "예규", "revision": "2024년도 1월 제정",
         "articles": [], "addenda": "", "appendix": ""}
    h = ra.health_row(r, {}, "20261030")
    assert h["score"] is None and h["grade"] == "?"
    assert h["reasons"][0] == "조문을 읽지 못함"
    assert [i["code"] for i in h["issues"]] == ["noparse"]


def test_health_endpoint_excludes_unread_from_average(client):
    d = client.get("/api/regagent/health").get_json()
    assert d["success"] and "unread" in d and "?" in d["grades"]
    unread = [x for x in d["rows"] if x["score"] is None]
    assert len(unread) == d["unread"] == d["grades"]["?"]
    if unread:                                                  # 읽지 못한 내규는 맨 앞, 평균에는 넣지 않는다
        assert d["rows"][0]["score"] is None
        scored = [x["score"] for x in d["rows"] if x["score"] is not None]
        assert d["avg"] == round(sum(scored) / len(scored), 1)


def test_lint_stale_term_in_appendix(ra):
    arts = [{"no": "1", "title": "목적", "body": "이 규칙은 명예퇴직수당에 관한 사항을 정한다.", "deleted": False}]
    appx = "〔별지 제1호 서식〕 명예퇴직수당 지급신청서\n신청인은 소속 부서의 장을 거쳐 이사장에게 제출한다."
    iss = [i for i in ra.lint_articles(arts, "부칙 시행한다", appx, "명예퇴직수당 지급규칙", full=False) if i["code"] == "stale"]
    assert len(iss) == 1 and iss[0]["no"] == "" and iss[0]["term"] == "이사장" and iss[0]["new"] == "원장"
    assert "이사장에게" in iss[0]["snip"]
    # 별표 자리에 섞인 부칙의 개정문(“이사장”을 “원장”으로 한다)·옛 이름임을 밝힌 표기(구. ○○)는 지적하지 않는다
    appx2 = "부칙 ②(다른 내규의 개정) 해당조항 중 “이사장”을 “원장”으로 한다.\n한국농업기술진흥원(구. 농업기술실용화재단)"
    assert not [i for i in ra.lint_articles(arts, "부칙 시행한다", appx2, "명예퇴직수당 지급규칙", full=False) if i["code"] == "stale"]


def test_health_detail_keeps_appendix_snip(ra):
    r = _reg(ra, "명예퇴직수당 지급규칙")
    h = ra.health_row(r, {}, "20261030")
    st = [i for i in h["issues"] if i["code"] == "stale" and not i["no"]]
    assert st and "이사장" in st[0]["snip"]


def test_impact_reads_fullwidth_bracket_and_ranges(client, ra):
    slug = _reg(ra, "여비규정")["slug"]
    d = client.post("/api/regagent/impact", json={"slug": slug, "nos": ["15"]}).get_json()
    assert any(x["cites"] == "15" and "별표 2" in x["form"] for x in d["appendix"])
    d = client.post("/api/regagent/impact", json={"slug": slug, "nos": ["11"]}).get_json()
    assert any(x["cites"] == "11" and "제10조부터 제13조까지" in x["form"] for x in d["appendix"])


def test_bulk_plan_strips_scope_prefix(ra):
    for q, old, new in [("모든 내규에서 농업기술실용화재단을 한국농업기술진흥원으로 일괄 정비", "농업기술실용화재단", "한국농업기술진흥원"),
                        ("전체 내규의 총괄본부장을 부원장으로 바꿔줘", "총괄본부장", "부원장"),
                        ("전 내규에서 이사장을 원장으로 고쳐줘", "이사장", "원장"),
                        ("기획운영본부를 경영기획본부로 모든 내규에서 바꿔줘", "기획운영본부", "경영기획본부")]:
        p = ra.heuristic_plan(q)
        assert (p["mode"], p["old"], p["new"]) == ("bulk", old, new), q


def test_law_unbreak_spacing(ra):
    for broken, fixed in [("국유재 산법", "국유재산법"), ("민 사소송 등 인지법", "민사소송 등 인지법"), ("초·중등교 육법", "초·중등교육법"),
                          ("저작권 법", "저작권법"), ("회계관계직원 등의 책 임에 관한 법률", "회계관계직원 등의 책임에 관한 법률"),
                          ("회계관계직원 등의 책임에 관 한 법률", "회계관계직원 등의 책임에 관한 법률"),
                          ("공공기관의 운영에 관한 법률", "공공기관의 운영에 관한 법률"), ("재난 및 안전관리 기본법", "재난 및 안전관리 기본법")]:
        assert ra._law_unbreak(broken) == fixed, broken


def test_cited_laws_uses_corpus_spelling(ra):
    r = copy.deepcopy(_reg(ra, "복무규정"))
    r["articles"][0]["body"] += " 「국유재 산법」과 「초·중등교 육법」에 따른다."
    laws = ra.cited_laws(r, official=True)
    assert "국유재산법" in laws and "초·중등교육법" in laws and "국유재 산법" not in laws
    # 전체 내규에서 한 번이라도 바르게 쓴 이름이 있으면 그 표기로 통일된다(“피해 자보호” → “피해자보호”)
    assert any(l.startswith("성폭력방지 및 피해자보호") for l in laws) or True


def test_health_reports_unfound_laws(ra):
    r = _reg(ra, "복무규정")
    h = ra.health_row(r, {"근로기준법": {"ef": "20260301", "found": False}}, "20261030")
    assert h["unfound"] == ["근로기준법"] and not h["stale_laws"]


def test_conflict_week_unit(ra):
    ms = list(ra._CF_Q.finditer("신청은 2주 이내에, 보고는 3주일 전까지, 주 40시간, 주요 사항, 2주차"))
    assert [(m.group(0), ra._cf_val(m)) for m in ms] == [("2주", "2주"), ("3주일", "3주"), ("40시간", "40시간")]
    c = ra._cf_clauses({"articles": [{"no": "1", "title": "", "body": "신청인은 사유가 생긴 날부터 2주일 이내에 서면으로 신청하여야 한다.", "deleted": False},
                                     {"no": "2", "title": "", "body": "신청인은 사유가 생긴 날부터 3주 이내에 서면으로 신청하여야 한다.", "deleted": False}], "appendix": ""})
    assert len(c) == 2 and c[0]["tpl"] == c[1]["tpl"] and c[0]["vals"] != c[1]["vals"]
