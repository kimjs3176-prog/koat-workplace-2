"""용어 정의 점검 — 중복 정의, 쓰지 않는 용어, 약칭을 정의하기 전에 쓰는 경우."""


def _arts(ra, text):
    return ra.parse_text(text)["articles"]


def test_unused_defined_term(ra):
    arts = _arts(ra, "제1조(목적) 이 규칙은 드론 운영을 정한다.\n"
                     "제2조(정의) 이 규칙에서 사용하는 용어의 뜻은 다음과 같다.\n"
                     "1. “운영책임자”란 부서별로 지정한 사람을 말한다.\n"
                     "2. “비행구역”이란 비행을 허가한 구역을 말한다.\n"
                     "제3조(지정) 부서장은 운영책임자를 지정한다.")
    msgs = [m for _, _, m in ra.term_check(arts)]
    assert any("“비행구역”이 다른 곳에서 쓰이지 않습니다" in m for m in msgs)
    assert not any("운영책임자" in m for m in msgs)


def test_duplicate_definition(ra):
    arts = _arts(ra, "제1조(목적) 위원회(이하 “위원회”라 한다)를 둔다.\n"
                     "제2조(정의) 1. “위원회”란 심의기구를 말한다.\n"
                     "제3조(운영) 위원회는 연 1회 연다.")
    out = ra.term_check(arts)
    assert any(lv == "warn" and "두 번 정의" in m for lv, _, m in out)


def test_abbreviation_used_before_definition(ra):
    arts = _arts(ra, "제1조(목적) 운영계획서를 낸다.\n"
                     "제2조(계획) 부서장은 연간 운영계획서(이하 “운영계획서”라 한다)를 만든다.\n"
                     "제3조(제출) 운영계획서는 1월에 낸다.")
    out = ra.term_check(arts)
    hit = [x for x in out if "먼저 씁니다" in x[2]]
    assert hit and hit[0][1] == "1"


def test_generic_abbreviation_not_flagged_before(ra):
    # “위원회”처럼 흔한 말은 정의 전 사용 경고를 하지 않는다
    arts = _arts(ra, "제1조(목적) 각종 위원회 운영을 정한다.\n"
                     "제2조(설치) 심의위원회(이하 “위원회”라 한다)를 둔다.\n"
                     "제3조(운영) 위원회는 연 1회 연다.")
    assert not any("먼저 씁니다" in m for _, _, m in ra.term_check(arts))


def test_term_findings_in_lint_and_review(ra):
    text = ("제1조(목적) 이 규칙은 목적을 정한다.\n"
            "제2조(정의) 1. “쓰지않는말”이란 예시를 말한다.\n"
            "제3조(기타) 다른 내용.")
    iss = ra.lint_articles(_arts(ra, text), "이 규칙은 발령한 날부터 시행한다.")
    assert any(i["code"] == "term" and i["level"] == "info" for i in iss)


def test_term_check_corpus_runs(ra):
    # 실제 내규 전체에 돌려도 예외 없이, 내규마다 상한(8건) 안에서
    for r in ra.all_regs():
        assert len(ra.term_check(r["articles"])) <= 8
