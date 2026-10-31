"""제정 초안: 다른 기관 규정의 조 구성(목차)·고른 조문을 표준 골격과 AI 요청에 반영하고 조별 출처를 남긴다."""
import json

OUT = [{"org": "가공사", "reg": "드론 운영지침", "toc": ["제1조(목적)", "제2조(정의)", "제3조(운영책임자)", "제4조(비행 승인)", "제5조(보험 가입)", "제6조(사고 보고)", "제7조(세부사항)"]},
       {"org": "나공단", "reg": "무인비행장치 관리규정", "toc": ["제1조(목적)", "제2조(적용범위)", "제3조(운영책임자)", "제4조(비행승인)", "제5조(안전점검)", "제6조(사고보고)", "제7조(교육)"]},
       {"org": "다재단", "reg": "드론 관리지침", "toc": ["제1조(목적)", "제2조(운영책임자 등)", "제3조(보험가입)", "제4조(사고 보고)"]}]


def test_outline_common_sections(ra):
    secs = ra.outline_sections(OUT)
    assert [g["title"] for g in secs] == ["운영책임자", "비행 승인", "보험 가입", "사고 보고"]   # 2곳 이상 공통만, 원래 순서
    assert len(secs[0]["orgs"]) == 3 and "다재단 「드론 관리지침」 제2조" in secs[0]["refs"]
    one = ra.outline_sections(OUT[:1])                     # 한 곳뿐이면 그 기관의 조(표준 조 제외)
    assert [g["title"] for g in one] == ["운영책임자", "비행 승인", "보험 가입", "사고 보고"]
    assert ra.outline_sections([{"org": "x", "toc": ["잘못된 줄"]}]) == []


def test_template_uses_outline_and_refs(ra):
    d = ra.template_enact({"title": "업무용 드론 운영지침", "purpose": "업무용 드론의 안전한 운영",
                           "contents": "운영책임자: 부서별 드론 운영책임자를 지정", "outline": OUT,
                           "refs": [{"org": "나공단", "reg": "무인비행장치 관리규정", "no": "5", "title": "안전점검", "body": "…", "src": "alio"}]})
    titles = [a["title"] for a in d["articles"]]
    assert titles == ["목적", "정의", "적용범위", "운영책임자", "비행 승인", "보험 가입", "사고 보고", "안전점검", "세부사항"]
    by = {a["title"]: a for a in d["articles"]}
    assert by["운영책임자"]["src"].startswith("다른 기관 3곳 공통")          # 주요 내용에 있던 조에는 출처만
    assert "나공단 「무인비행장치 관리규정」 제5조" in by["안전점검"]["src"]    # 직접 고른 조문은 한 곳이어도 조로
    assert "○○" in by["비행 승인"]["body"] and "가공사" not in by["비행 승인"]["body"]   # 본문을 옮겨 쓰지 않는다
    assert [s["title"] for s in d["sources"]] == ["운영책임자", "비행 승인", "보험 가입", "사고 보고", "안전점검"]
    plain = ra.template_enact({"title": "업무용 드론 운영지침", "purpose": "x"})
    assert plain["sources"] == [] and len(plain["articles"]) == 4


def test_ai_enact_gets_outline_and_drops_invented_sources(ra, monkeypatch):
    seen = {}

    def gen(provider, key, mdl, system, user, **kw):
        seen["user"] = user
        return json.dumps({"title": "업무용 드론 운영지침", "articles": [
            {"no": "1", "title": "목적", "body": "가.", "src": ""},
            {"no": "2", "title": "비행 승인", "body": "나.", "src": "가공사 「드론 운영지침」 제4조"},
            {"no": "3", "title": "보험", "body": "다.", "src": "없는공사 「규정」 제9조"}],
            "addenda": ["이 지침은 발령한 날부터 시행한다."], "reason": {"purpose": "p", "main": []}, "notes": []}, ensure_ascii=False), ""
    monkeypatch.setitem(ra._CTX, "ai_generate", gen)
    monkeypatch.setitem(ra._CTX, "default_model_for", lambda p, k: "m")
    d, err = ra.ai_enact({"title": "업무용 드론 운영지침", "purpose": "x", "provider": "gemini", "api_key": "k", "outline": OUT})
    assert "[다른 기관 같은 종류 규정의 조 구성]" in seen["user"] and "가공사 「드론 운영지침」: 제1조(목적)" in seen["user"]
    srcs = {s["title"]: s["src"] for s in d["sources"]}
    assert srcs == {"비행 승인": "가공사 「드론 운영지침」 제4조"}     # 받은 자료에 없는 기관은 지운다
