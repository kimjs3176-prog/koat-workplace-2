"""공문서 표기 점검(notation.py) — 행정업무운영편람 표기 규칙."""
import pytest

import notation as nt


def rules(text, kind="doc"):
    return {f["rule"] for f in nt.check(text, kind)}


@pytest.mark.parametrize("text,rule", [
    ("기간: 2026.10.06", "DATE_FORMAT"),
    ("기간: 2026-10-06", "DATE_FORMAT"),
    ("기간: 2026. 03. 05.", "DATE_ZERO"),
    ("기간: 2026. 3. 5 까지", "DATE_DOT"),
    ("2026. 3. 5. ~ 2026. 3. 9.", "TILDE"),
    ("일시: 9:30", "TIME"),
    ("금액은 30000원으로 한다", "MONEY"),
    ("시행일 : 2026. 1. 1.", "COLON_SPACE"),
    ("시행일:2026. 1. 1.", "COLON_SPACE"),
    ("위험을 줄인다 — 시범 운영", "DASH"),
    ("<공공기관의 운영에 관한 법률>에 따라", "LAW_BRACKET"),
    ("리스크를 관리한다", "LOANWORD"),
    ("붙임: 신구조문대비표 1부.  끝.", "BUNIM_COLON"),
    ("붙임 신구조문대비표 1부.  끝.", "BUNIM_SPACE"),
    ("붙임  신구조문대비표 1부. 끝.", "END_SPACE"),
    ("본문만 있고 끝 표시가 없음", "END_MISSING"),
])
def test_rule_detected(text, rule):
    assert rule in rules(text)


def test_compliant_document_has_no_findings():
    doc = ("「여비규정」 개정(안) 사전예고\n\n"
           "1. 의견 제출\n  가. 기간: 2026. 10. 6.∼2026. 10. 26.(20일 이상)\n  나. 시각: 09:00\n"
           "  다. 금액: 금30,000원(금삼만원)\n  라. 제출처: 경영지원팀(전화 063-919-1000, https://www.koat.or.kr)\n\n"
           "붙임  신구조문대비표 1부.  끝.")
    assert nt.check(doc) == []


def test_law_kind_skips_document_rules():
    r = rules("제1조(목적) 이 규정은 목적을 정한다.", "law")
    assert "END_MISSING" not in r and "BUNIM_SPACE" not in r


def test_hangul_amount():
    assert nt.hangul_amount(30000) == "삼만"
    assert nt.hangul_amount(113560) == "일십일만삼천오백육십"
    assert nt.hangul_amount(1200000) == "일백이십만"


def test_notation_endpoint(client):
    d = client.post("/api/regagent/notation", json={"texts": {"a": "붙임: 표 1부. 끝.", "law": "제1조(목적) 2026.01.01 시행"},
                                                    "kinds": {"law": "law"}}).get_json()
    assert d["success"]
    assert "BUNIM_COLON" in {f["rule"] for f in d["results"]["a"]}
    assert {"DATE_FORMAT"} <= {f["rule"] for f in d["results"]["law"]}
    assert "END_MISSING" not in {f["rule"] for f in d["results"]["law"]}
    assert client.post("/api/regagent/notation", json={"texts": {}}).status_code == 400


def test_lint_reports_notation_as_info(client):
    d = client.post("/api/regagent/lint", json={"text": "제1조(목적) 기간은 2026.01.01 ~ 2026.12.31로 한다.", "title": "x"}).get_json()
    nots = [i for i in d["issues"] if i["code"] == "notation"]
    assert nots and all(i["level"] == "info" for i in nots)


def test_loanword_inside_name_is_ignored():
    assert "LOANWORD" not in rules("「ESG 리스크 관리지침」 제3조에 따른다.  끝.")
    assert "LOANWORD" in rules("리스크 관리 강화  끝.")
