"""완성도 4차 점검(AI 응답 처리 등)에서 고친 부분의 회귀 테스트."""
import pytest

import reg_agent as ra


def test_json_from_trailing_text_and_type():
    assert ra._json_from('{"a": 1}\n참고: 위 {초안}은 예시입니다.') == {"a": 1}
    assert ra._json_from('```json\n{"a": 2}\n```') == {"a": 2}
    with pytest.raises(ValueError):
        ra._json_from('[1, 2]')


@pytest.mark.parametrize("v,want", [("15-2", "15의2"), ("제5조 제1항", "5"), ("제7조의3", "7의3"), ("부칙", ""), (3, "3")])
def test_art_no(v, want):
    assert ra._art_no(v) == want


def _fake(out):
    ra._CTX["ai_generate"] = lambda *a, **k: out


@pytest.fixture
def ai(monkeypatch):
    old = ra._CTX.get("ai_generate")
    yield _fake
    ra._CTX["ai_generate"] = old


AI = {"provider": "claude", "api_key": "k", "model": "claude-x"}


def test_enact_falls_back_to_template(client, ai):
    for out in [("", "과부하"), ("not json", ""), ('{"articles": "x"}', ""), ("[1]", "")]:
        ai(out)
        j = client.post("/api/regagent/draft", json=dict(AI, mode="enact", title="드론 운영지침")).get_json()
        assert j["success"] and j["draft"]["articles"] and "표준 조문 골격" in j["notice"]


def test_enact_normalizes_types(client, ai):
    ai(('{"articles":[{"no":"1","title":"목적","body":"x"},{"no":"1","title":"b","body":"y"}],"reason":{"main":"한 줄"},"notes":"n"}', ""))
    j = client.post("/api/regagent/draft", json=dict(AI, mode="enact", title="x 지침")).get_json()
    assert j["draft"]["reason"]["main"] == ["한 줄"] and j["draft"]["notes"] == ["n"] and "겹칩니다" in j["notice"]


def test_amend_dedup_and_drop_notice(client, ai):
    ai(('{"changes":[{"no":"부칙","body":"x"},{"no":"5","body":"a"},{"no":"제5조","body":"b"},"s"]}', ""))
    j = client.post("/api/regagent/draft", json=dict(AI, mode="amend", intent="수정", reg="여비규정")).get_json()
    assert [c["body"] for c in j["draft"]["changes"]] == ["b"] and "2건" in j["notice"]


def test_plan_coerces_types(client, ai):
    ai(('{"mode":"upper","law":"근로기준법","arts":"제31조"}', ""))
    j = client.post("/api/regagent/plan", json=dict(AI, request="근로기준법이 바뀌었어")).get_json()
    assert j["plan"]["arts"] == ["31"]
    ai(('{"mode":"amend","intent":["여비규정 출장비 인상"]}', ""))
    r = client.post("/api/regagent/plan", json=dict(AI, request="여비규정 출장비를 올려줘"))
    assert r.status_code == 200


# ── 법제처·표기·형식 점검 ─────────────────────────────────────────────────
import notation as nt  # noqa: E402


@pytest.mark.parametrize("text", ["100000000000000000000원", "경쟁률 1:10", "문서번호 2024-12-1호", "버전 2020.1.2"])
def test_notation_no_false_or_crash(text):
    assert not [f for f in nt.check(text, "law") if f["rule"] in ("MONEY", "TIME", "DATE_FORMAT", "DATE_DOT")]


def test_notation_money_includes_geum_and_tilde_keeps_colon():
    f = [x for x in nt.check("금 30000원", "law") if x["rule"] == "MONEY"][0]
    assert f["match"] == "금 30000원"
    t = [x for x in nt.check("기간: ~20일", "law") if x["rule"] == "TILDE"][0]
    assert ":" not in t["match"]


def test_lint_ho_attached_and_appx_brackets():
    arts = [{"no": "1", "title": "목적", "body": "다음 각 호와 같다.\n1.「병역법」에 따른 자\n2. 나\n3. 다", "deleted": False},
            {"no": "2", "title": "서식", "body": "별지 제7호 서식에 따른다. 「다른규정」 별표 3을 따른다.", "deleted": False}]
    items = ra.lint_articles(arts, "부칙\n이 규정은 발령한 날부터 시행한다.", "〔별지 제7호 서식〕 신청서", "x 규정", full=True)
    codes = [i["code"] for i in items]
    assert "ho" not in codes and "appx" not in codes


def test_parse_deleted_with_title():
    r = ra.parse_text("제13조(가) 내용\n제14조(보고사항) <삭제 2023.06.28.>\n제15조(다) 내용", clean=True)
    assert [a["deleted"] for a in r["articles"]] == [False, True, False]


def test_law_api_fails_fast(client, monkeypatch):
    import api_server
    import requests

    def boom(*a, **k):
        raise requests.exceptions.ProxyError("blocked")
    monkeypatch.setattr(api_server._LAW_SESSION, "get", boom)
    r = client.get("/api/law/articles?name=근로기준법")
    assert r.status_code == 502


def test_health_issues_have_detail(client):
    rows = client.get("/api/regagent/health").get_json()["rows"]
    iss = [i for r in rows for i in r["issues"]]
    assert iss and all("art_title" in i and "snip" in i for i in iss)
    stale = [i for i in iss if i["code"] == "stale"]
    assert all(i.get("term") and i.get("new") for i in stale)
    regname = [i for i in iss if i["code"] == "regname" and i.get("new")]
    assert all(i["term"] in i["snip"] for i in regname)


def test_regs_catalog_and_search(client):
    regs = client.get("/api/regagent/catalog").get_json()["regs"]
    assert regs and all("rev_date" in r and "live" in r for r in regs)
    d = client.get("/api/regagent/regs/search?q=출장 비").get_json()   # 띄어쓰기 무시
    assert d["regs"] and all(x["hits"] > 0 and x["first"]["no"] for x in d["regs"])
    assert client.get("/api/regagent/regs/search?q=x").get_json()["regs"] == []


# ── 점검·제개정 강화 ───────────────────────────────────────────────────────
def test_lint_xref_other_reg_article():
    arts = [{"no": "1", "title": "목적", "body": "「여비규정」 제999조 및 「여비규정」 제1조에 따른다.", "deleted": False}]
    iss = [i for i in ra.lint_articles(arts, "", "", "가상 지침") if i["code"] == "xref"]
    assert len(iss) == 1 and "제999조" in iss[0]["msg"] and iss[0]["reg"] == "여비규정"


def test_delegation_check_finds_uncovered():
    r = next(x for x in ra.all_regs() if x["title"] == "인사규정")
    res = ra.delegation_check(r["title"], r["articles"])
    assert res and any(d["no"] == "16" and not d["covered"] for d in res)
    assert sum(1 for d in res if d["covered"]) >= len(res) // 2


def test_lint_compare_with_base(client):
    r = next(x for x in ra.all_regs() if x["title"] == "여비규정")
    text = "\n".join(f"제{a['no']}조({a['title']}) {a['body']}" for a in r["articles"] if not a["deleted"])
    text += "\n제90조(신설) 제999조에 따른다."
    d = client.post("/api/regagent/lint", json={"text": text, "title": "여비규정", "base_slug": r["slug"]}).get_json()
    assert d["base"] == "여비규정" and "fixed" in d
    assert any(i.get("is_new") and "제999조" in i["msg"] for i in d["issues"])


# ── 내규 조회·관련법령 ───────────────────────────────────────────────────
def test_jun_relations_and_users(client):
    r = next(x for x in ra.all_regs() if x["title"] == "이사회 운영규정")
    rel = {j["no"]: j for j in ra.jun_relations(r)}
    assert [t["name"] for t in rel["8"]["targets"]] == ["상법"] and rel["8"]["targets"][0]["arts"] == ["제391조", "제391조의3"]
    assert any(t["name"] == "임원추천위원회 운영규정" and t["kind"] == "reg" for t in rel["16"]["targets"])
    u = client.get("/api/regagent/law-users?law=공운법").get_json()          # 약칭도 정식 명칭과 같게
    assert u["jun"] and u["cite"]
    d = client.get("/api/regagent/relations?slug=" + r["slug"]).get_json()
    assert d["jun"] and d["laws"] and any(l["jun"] for l in d["laws"])


def test_upper_marks_jun(client):
    d = client.post("/api/regagent/upper", json={"law": "상법"}).get_json()
    assert any(s.startswith("준용") for c in d["candidates"] for s in c["specific"])


def test_law_rel_parser_and_fail_fast(client, monkeypatch):
    import xml.etree.ElementTree as ET
    import api_server
    import requests
    x = ("<LawSearch><law><법령명>근로기준법</법령명><관련법령명>선원법</관련법령명><관련구분>피준용</관련구분></law>"
         "<상하위법><시행령><법령명>근로기준법 시행령</법령명></시행령></상하위법></LawSearch>")
    items = api_server._law_rel_items(ET.fromstring(x), "근로기준법")
    assert {(i["name"], i["rel"]) for i in items} == {("선원법", "피준용"), ("근로기준법 시행령", "하위법")}
    monkeypatch.setattr(api_server._LAW_SESSION, "get", lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ProxyError("x")))
    assert client.get("/api/law/related?name=근로기준법").status_code == 502


def test_regs_search_returns_articles(client):
    d = client.get("/api/regagent/regs/search?q=출장비").get_json()
    assert d["regs"][0]["arts"] and d["regs"][0]["n_arts"] >= len(d["regs"][0]["arts"])


# ── 최근 기능 점검 보완 ──────────────────────────────────────────────────
def test_jun_only_last_clause_targets():
    by = {r["title"]: {j["no"]: j for j in ra.jun_relations(r)} for r in ra.all_regs()}
    assert "30" not in by["연구개발성과 사업화 관리규칙"]                       # “이 규칙을 준용” — 다른 법령 준용 아님
    assert [t["name"] for t in by["분석시험 의뢰 및 처리규칙"]["11"]["targets"]] == ["행정절차법 시행령"]
    assert [t["name"] for t in by["ESG경영에 관한 규칙"]["26"]["targets"]] == ["통합공시매뉴얼"]
    assert [t["name"] for t in by["치유농업사 자격시험 규칙 시행세칙"]["7"]["targets"]] == ["강사수당 지급기준"]


def test_upper_jun_boost_needs_article_hit(client):
    d = client.post("/api/regagent/upper", json={"law": "공운법", "arts": ["11"]}).get_json()
    c = {(x["reg"], x["no"]): x for x in d["candidates"]}
    assert "준용" not in " ".join(c.get(("한국농업기술진흥원 정관", "11"), {"specific": []})["specific"])


def test_relations_merge_law_alias(client):
    r = next(x for x in ra.all_regs() if x["title"].endswith("정관"))
    laws = client.get("/api/regagent/relations?slug=" + r["slug"]).get_json()["laws"]
    names = [x["name"] for x in laws]
    assert "공운법" not in names and len(names) == len(set(names))
    assert next(x for x in laws if x["name"] == "공공기관의 운영에 관한 법률")["jun"]


def test_lint_compare_flag_and_appendix(client):
    r = next(x for x in ra.all_regs() if x["title"] == "직원채용지침")
    text = "\n".join(f"제{a['no']}조({a['title']}) {a['body']}" for a in r["articles"] if not a["deleted"])
    d = client.post("/api/regagent/lint", json={"text": text, "title": r["title"], "base_slug": r["slug"]}).get_json()
    assert not [i for i in d["fixed"] if i["code"] == "appx"]                   # 별표는 원 내규 것으로 본다
    plain = client.post("/api/regagent/lint", json={"text": "제1조(목적) 이 규정은 실용화재단의 업무를 정한다."}).get_json()
    assert all("is_new" not in i for i in plain["issues"])                      # 비교 없이는 “이번 개정” 표시 없음


def test_xref_checks_own_gangryeong_and_branch_delegation():
    r = next(x for x in ra.all_regs() if x["title"] == "윤리경영규정")
    iss = ra.lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"])
    assert any(i["code"] == "xref" and "행동강령" in i["msg"] for i in iss)
    h = next(x for x in ra.all_regs() if x["title"] == "인사규정")
    cov = {d["no"]: d["covered"] for d in ra.delegation_check(h["title"], h["articles"])}
    assert cov["32의2"] is False


def test_stale_skips_quoted_law_article_title():
    arts = ra.parse_text("제1조(목적) 「농촌진흥법」 부칙 제2조(실용화재단 직원의 임용등에 관한 특례)에 따른다.")["articles"]
    assert not [i for i in ra.lint_articles(arts, "", "", "인사규정") if i["code"] == "stale"]


def test_ref_after_quoted_definition_is_external():
    assert ra.internal_refs("이 세칙은 “치유농업사 자격시험 규칙(이하”규칙“이라 한다)” 제44조제1항에 의하여") == []


# ── 점검 라운드: API 견고성·점검 오탐 ───────────────────────────────────────
def test_api_bad_types_no_500(client):
    assert client.post("/api/regagent/health", json={"law_info": {"공공기관의 운영에 관한 법률": "20240101"}}).status_code == 200
    r = client.post("/api/regagent/similar", data='{"query":"출장","limit":1e400}', content_type="application/json")
    assert r.status_code == 200
    assert client.post("/api/regagent/upper", json={"law": "가" * 300}).status_code == 400


def test_parse_nested_title_and_mismatched_annot():
    p = ra.parse_text("제38조(후속(연계 지원)) ① 가.\n② 나.")
    assert p["articles"][0]["title"] == "후속(연계 지원)" and p["articles"][0]["body"].startswith("①")
    p = ra.parse_text("제25조(평가) [제24조에서 이동, 종전 제24조는 삭제 2023.01.11〕 ① 가.\n② 나.")
    assert p["articles"][0]["body"].startswith("①")


def test_term_def_ira_hameun_and_abbr_fragments():
    arts = ra.parse_text("제1조(목적) 이 규칙은 치유농업사 자격시험을 정한다.\n"
                         "제2조(정의) 1. “감사인” 이라 함은 감사를 하는 사람을 말한다.\n"
                         "제3조(시험) 치유농업사 자격시험(이하 “자격시험”이라 한다)은 감사인이 본다. 자격시험은 매년 한다.")["articles"]
    msgs = " ".join(m for _, _, m in ra.term_check(arts))
    assert "“감사인”이 다른 곳에서" not in msgs and "먼저 씁니다" not in msgs


def test_bulk_josa_non_hangul_and_join_locs():
    assert ra._bulk_sentence([("제1조", ("ESG", "지속가능경영"))], "ESG", "지속가능경영") == "제1조 중 “ESG”를 “지속가능경영”으로 한다."
    assert ra._ro("제1") == "로" and ra._ro("제3") == "으로"
    assert ra._join_locs(["제5조제1항제1호", "제5조제1항제3호", "제5조제2항"]) == "제5조제1항제1호, 같은 항 제3호 및 같은 조 제2항"
    assert ra._join_locs(["제3조제1항 본문", "제3조제1항 단서"]) == "제3조제1항"


def test_template_purpose_forms():
    t = ra.template_enact({"title": "안전관리규정", "purpose": "안전관리에 관한 사항을 정함"})
    assert "사항을 정함에 필요한" not in t["articles"][0]["body"] and "안전관리에 필요한 사항" in t["articles"][0]["body"]
    assert "에 관한 사항에 필요한" not in ra.template_enact({"title": "X 지침"})["articles"][0]["body"]
