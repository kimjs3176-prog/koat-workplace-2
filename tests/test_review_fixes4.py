"""기능 점검 5차: 자문 검색어(조사·일상어·함께 다룬 조문), 중복 등록, 법령 약칭, 제정 골격 문장."""
import json
import os
import subprocess
import sys
import textwrap

import reg_agent as ra

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_strip_josa_keeps_nouns_ending_like_josa():
    assert ra._strip_josa("연차휴가") == "연차휴가"          # 끝 글자 “가”는 조사가 아니다(원문에 “연차휴가”가 있다)
    assert ra._strip_josa("출장비가") == "출장비"
    assert ra._strip_josa("드론을") == "드론"                # 원문에 없는 새 낱말도 조사는 뗀다


def test_synonyms_expand_search():
    assert "여비" in ra._syn("출장비") and ra._syn("없는말") == []
    p = ra.heuristic_plan("출장비 규정 고쳐줘")
    ra._resolve_targets(p, "출장비 규정 고쳐줘")
    assert p["reg"]["title"] == "여비규정"


def test_advise_gap_when_no_article_covers_all_words(client):
    d = client.post("/api/regagent/advise", json={"question": "연차휴가 이월이 가능한가요?"}).get_json()
    assert d["conclusion"] == "확인 필요" and d["gap"] == ["이월"]
    assert d["sources"][0]["reg"] == "복무규정"                 # 예산 이월 조문이 앞에 오지 않는다
    assert "함께 다룬 조문은 찾지 못했습니다" in d["answer"]
    d = client.post("/api/regagent/advise", json={"question": "야근하면 수당 나오나요?"}).get_json()
    assert d["mapped"] == {"야근": ["시간외근무"]} and not d["unmatched"] and "시간외근무수당" in d["sources"][0]["title"]


def test_advise_skips_other_regs_appendix(client):
    d = client.post("/api/regagent/advise", json={"question": "경조사비 지급 기준"}).get_json()
    assert not any(s["role"] == "appx" and s["reg"] == "복리후생규칙" for s in d["sources"])   # 「복무규정」〔별표2〕는 복리후생규칙의 별표가 아니다


def test_advise_ai_gets_gap_caveat(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "default_model_for", lambda p, k: "m")
    seen = {}

    def gen(provider, key, mdl, system, user, **k):
        seen["user"] = user
        return json.dumps({"conclusion": "가능", "answer": "가능합니다 [1].", "basis": [{"src": 1, "point": "연차유급휴가"}]}), ""
    monkeypatch.setitem(ra._CTX, "ai_generate", gen)
    d = client.post("/api/regagent/advise", json={"question": "연차휴가 이월이 가능한가요?", "provider": "gemini", "api_key": "k"}).get_json()
    assert "“이월”을 직접 다룬 조문은 찾지 못했습니다" in seen["user"]
    assert any("이월" in c for c in d["caveats"]) and d["conclusion"] == "확인 필요"


def test_dup_regs_and_health():
    d = ra.dup_regs()
    assert any(o["slug"] == "직업창업규칙" for o in d.get("직원창업규칙", []))
    row = ra.health_row(ra.find_reg("직업창업규칙"), {}, "20261025")
    assert row["counts"].get("dupreg") == 1 and row["issues"][-1]["other"] == "직원창업규칙"   # 기존 문제 순번(화면 고른 상태)을 밀지 않게 뒤에


def test_law_official_and_lint():
    assert ra.law_official("청탁금지법 시행령") == "부정청탁 및 금품등 수수의 금지에 관한 법률 시행령"
    assert ra.law_official("공공기관 운영에 관한 법률") == "공공기관의 운영에 관한 법률"
    assert ra.law_official("근로기준법") == "근로기준법"
    arts = ra.parse_text("제1조(목적) 이 규정은 「공운법」 및 「근로기준법」에 따른다.")["articles"]
    iss = [i for i in ra.lint_articles(arts, "이 규정은 발령한 날부터 시행한다.", "", "시험규정") if i["code"] == "lawname"]
    assert len(iss) == 1 and iss[0]["new"] == "공공기관의 운영에 관한 법률"
    r = ra.find_reg("", "임직원 행동강령")
    assert "청탁금지법 시행령" not in ra.cited_laws(r, official=True)


def test_template_enact_clause_sentences():
    d = ra.template_enact({"title": "재택근무 운영지침", "purpose": "재택근무", "contents": "신청: 직원은 1주 전까지 신청\n복무관리: 근무상황을 기록"})
    bodies = {a["title"]: a["body"] for a in d["articles"]}
    assert bodies["신청"] == "직원은 1주 전까지 신청하여야 한다."
    assert bodies["복무관리"].startswith("근무상황의 기록은")
    d = ra.template_enact({"title": "재택근무 운영지침", "purpose": "재택근무", "contents": "예외: 직원은 상급자의 승인을 받은 경우"})
    assert "경우하여야" not in d["articles"][3]["body"]


UPLOAD = textwrap.dedent(r'''
    import io, json
    import api_server
    c = api_server.app.test_client()
    body = "직원창업규칙\n\n제1조(목적) 이 규칙은 직원의 창업 활동 보장과 지원에 필요한 사항을 정함을 목적으로 한다.\n제2조(신청) 창업직원은 신청서를 제출하여야 한다."

    def up(title, text, **extra):
        data = {"title": title, "file": (io.BytesIO(text.encode("utf-8")), "a.txt"), **extra}
        r = c.post("/api/regs/upload", data=data, content_type="multipart/form-data", environ_base={"REMOTE_ADDR": "127.0.0.1"})
        return r.status_code, (r.get_json(silent=True) or {})

    out = {"first": up("직원창업규칙", body)[0]}
    out["typo"] = up("직업창업규칙", body)
    out["typo_ok"] = up("직업창업규칙", body, new_ok="1")[0]
    print(json.dumps(out, ensure_ascii=False))
''')


def test_upload_guards_misnamed_duplicate(tmp_path):
    reg = tmp_path / "regulations"
    reg.mkdir()
    man = tmp_path / "manifest.json"
    man.write_text("[]", encoding="utf-8")
    env = {**os.environ, "REG_DIR": str(reg), "REG_MANIFEST": str(man), "REG_UPLOAD_TOKEN": "",
           "GITHUB_TOKEN": "", "GITHUB_REPO": "", "REG_UPLOAD_ALLOW_ANON": ""}
    p = subprocess.run([sys.executable, "-c", UPLOAD], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["first"] == 200
    code, data = out["typo"]
    assert code == 409 and data["similar"] == "직원창업규칙"
    assert out["typo_ok"] == 200                             # 새 규정이 맞다고 확인하면 등록
