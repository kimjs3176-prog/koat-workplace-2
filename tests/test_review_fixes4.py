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


# ── AI 산출물의 사람 검토: 인용 검증 · 작업 실적 대장 ─────────────────────────
def test_quote_ok():
    body = "① 국내여행자의 일비·숙박비 및 식비는 〔별표 2〕, 국외여행자의 경우는 〔별표 4〕에서 정하는 바에 따라 지급한다."
    assert ra._quote_ok("국내여행자의 일비·숙박비 및 식비는 〔별표 2〕", body)
    assert ra._quote_ok("국내여행자의 일비 … 정하는 바에 따라 지급한다", body)           # 줄인 인용은 조각마다
    assert not ra._quote_ok("일비는 3만원으로 한다", body)
    assert not ra._quote_ok("정하는 바에 따라 지급한다 … 국내여행자의 일비", body)        # 조각의 차례가 바뀌면 원문 일치가 아니다
    assert not ra._quote_ok("", body)


def test_advise_ai_quotes_marked(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "default_model_for", lambda p, k: "m")
    monkeypatch.setitem(ra._CTX, "ai_generate", lambda *a, **k: (json.dumps({
        "conclusion": "해당 규정", "answer": "별표 2에 따라 지급합니다 [1].",
        "basis": [{"src": 1, "point": "국내여행자의 일비·숙박비 및 식비는 〔별표 2〕"}, {"src": 1, "point": "숙박비는 무제한 지급한다"}]}), ""))
    d = client.post("/api/regagent/advise", json={"question": "국내 출장 숙박비 상한액은?", "slug": "여비규정",
                                                  "provider": "gemini", "api_key": "k"}).get_json()
    assert [b["verified"] for b in d["basis"]] == [True, False]
    assert d["cite_check"] == {"n": 2, "ok": 1} and "그대로 확인하지 못했습니다" in d["caveats"][0] and "⚠" not in d["caveats"][0]
    d = client.post("/api/regagent/advise", json={"question": "국내 출장 숙박비 상한액은?", "slug": "여비규정"}).get_json()
    assert all(b["verified"] for b in d["basis"])                     # 규칙 기반 근거는 조문에서 뽑은 문장


def test_ledger_record_and_summary(client, tmp_path, monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        ra.ledger_record({"kind": "x"})
    r = ra.ledger_record({"kind": "amend", "reg": "여비규정", "ai": "gemini:m<script>", "total": 3, "edited": 9, "reviewed": 1,
                          "body": "본문은 남기지 않는다", "who": "홍길동"})
    assert r["ai"] == "gemini:mscript" and r["edited"] == 3 and "body" not in r and "who" not in r
    monkeypatch.setenv("LEDGER_DIR", str(tmp_path))
    monkeypatch.setenv("LEDGER_ENABLED", "1")
    monkeypatch.setattr(ra, "_ledger_gh", lambda: None)
    ra._LEDGER_RATE.clear()
    ra._LEDGER_SUM.update(at=0, v=None)
    for k in ("advise", "amend", "amend"):
        d = client.post("/api/regagent/ledger", json={"kind": k, "reg": "여비규정", "ai": "gemini:m" if k == "amend" else "",
                                                      "total": 4, "edited": 1, "reviewed": True, "cites": 2, "cites_ok": 2}).get_json()
        assert d["stored"] and d["where"] == "local"
    assert client.post("/api/regagent/ledger", json={"kind": "nope"}).status_code == 400
    s = client.get("/api/regagent/ledger").get_json()
    m = s["months"][0]
    assert s["available"] and m["count"] == 3 and m["kinds"] == {"advise": 1, "amend": 2} and m["ai"] == 2 and m["reviewed"] == 3
    assert "reg" not in json.dumps(s["months"])                         # 기관 대장은 집계만 내준다
    client.post("/api/regagent/ledger", json={"kind": "bulk", "reg": "여비규정", "total": 50})
    m = client.get("/api/regagent/ledger").get_json()["months"][0]
    assert m["count"] == 4                                              # 새 기록은 집계 캐시를 비운다
    assert m["total"] == 8                                              # AI 조문 수는 AI 산출물(amend 2건 × 4)만


def test_ledger_github_branch(client, monkeypatch):
    import base64

    class E(RuntimeError):
        def __init__(self, status):
            super().__init__(str(status))
            self.status = status
    files, refs, calls = {}, {"main": "abc"}, []

    def gh(method, path, **kw):
        calls.append((method, path))
        if method == "GET" and path.startswith("/git/ref/heads/"):
            br = path.rsplit("/", 1)[1]
            if br not in refs:
                raise E(404)
            return {"object": {"sha": refs[br]}}
        if method == "POST" and path == "/git/refs":
            refs[kw["json"]["ref"].rsplit("/", 1)[1]] = kw["json"]["sha"]
            return {}
        if method == "GET" and path == "/contents/ledger":
            return [{"name": n.rsplit("/", 1)[1]} for n in files]
        if method == "GET" and path.startswith("/contents/"):
            p = path[len("/contents/"):]
            if p not in files:
                raise E(404)
            return {"content": "", "sha": "big", "size": len(files[p])}       # 1MB 넘는 파일처럼 content 를 비워 준다
        if method == "GET" and path == "/git/blobs/big":
            return {"content": base64.b64encode(list(files.values())[0]).decode()}
        if method == "PUT":
            assert kw["json"]["branch"] == "ledger-data"
            files[path[len("/contents/"):]] = base64.b64decode(kw["json"]["content"])
            return {}
        raise AssertionError((method, path))

    fake = type("G", (), {"_gh": staticmethod(gh), "GITHUB_BRANCH": "main"})
    monkeypatch.setenv("LEDGER_ENABLED", "1")
    monkeypatch.setattr(ra, "_ledger_gh", lambda: fake)
    monkeypatch.delenv("LEDGER_BRANCH", raising=False)
    ra._LEDGER_RATE.clear()
    for _ in range(2):
        d = client.post("/api/regagent/ledger", json={"kind": "advise", "reg": "여비규정", "ai": "gemini:m", "reviewed": True}).get_json()
        assert d["stored"] and d["where"] == "github"
    assert "ledger-data" in refs and len(list(files.values())[0].decode().splitlines()) == 2   # 배포 브랜치가 아닌 곳에 덧붙인다
    ra._LEDGER_SUM.update(at=0, v=None)
    s = client.get("/api/regagent/ledger").get_json()
    assert s["available"] and s["months"][0]["count"] == 2



# ── 검증 에이전트 지적 보완: 인용 대조·AI 결론·실적 대장 재전송 ─────────────────
def test_quote_ok_rejects_loose_fragments():
    r = ra.find_reg("", "여비규정")
    b15 = next(a for a in r["articles"] if a["no"] == "15")["body"]
    ap = r["appendix"]
    assert ra._quote_ok("상한액: 서울특별시 100,000…광역시 80,000", ap)
    assert not ra._quote_ok("상한액: 서울 … 70,000", ap)                 # 짧은 조각은 아무 데서나 맞는다 — 대조 불가
    assert not ra._quote_ok("국외 … 10분의 3을", b15)
    assert not ra._quote_ok("지급한다", b15)
    assert ra._quote_ok("숙박비 상한액의 10분의 3을 … 추가로 지급할 수 있다", b15)
    far = "국내여행자의 일비·숙박비 및 식비는 … 증거자료를 갖추어 회계"         # 조각 사이가 80자를 넘으면 다른 문맥
    assert not ra._quote_ok(far, b15)


def test_advise_all_quotes_unverified_downgrades(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "default_model_for", lambda p, k: "m")
    monkeypatch.setitem(ra._CTX, "ai_generate", lambda *a, **k: (json.dumps({
        "conclusion": "가능", "answer": "가능합니다 [1].", "basis": [{"src": 1, "point": "숙박비는 무제한 지급한다"}]}), ""))
    d = client.post("/api/regagent/advise", json={"question": "국내 출장 숙박비 상한액은?", "slug": "여비규정",
                                                  "provider": "gemini", "api_key": "k"}).get_json()
    assert d["cite_check"] == {"n": 1, "ok": 0} and d["conclusion"] == "확인 필요"


def test_ledger_retry_and_client_address(client, tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DIR", str(tmp_path))
    monkeypatch.setenv("LEDGER_ENABLED", "1")
    monkeypatch.setattr(ra, "_ledger_gh", lambda: None)
    monkeypatch.setattr(ra, "_LEDGER_PER_HOUR", 2)
    ra._LEDGER_RATE.clear()
    post = lambda xff: client.post("/api/regagent/ledger", json={"kind": "advise"}, headers={"X-Forwarded-For": xff}).get_json()
    assert post("1.1.1.1")["stored"] and post("2.2.2.2")["stored"]
    d = post("3.3.3.3")                                                   # X-Forwarded-For 를 바꿔도 같은 접속으로 센다
    assert not d["stored"] and d["retry"]                                 # 버리지 않고 화면이 다시 보내게 한다
    import datetime as _dt
    import time as _t
    ts = (_t.time() - 2 * 86400) * 1000
    kst = (_dt.datetime.fromtimestamp(ts / 1000, _dt.timezone.utc) + _dt.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
    assert ra.ledger_record({"kind": "advise", "ts": ts, "resend": True})["at"] == kst   # 다시 보낸 기록은 처음 저장한 때(KST)로
    assert ra.ledger_record({"kind": "advise", "ts": ts})["at"] != kst                  # 처음 보내는 기록은 서버 시각
    assert ra.ledger_record({"kind": "advise", "at": "2026-10-20 09:00"})["at"] != "2026-10-20 09:00"   # 화면이 정한 시각은 받지 않는다
    assert ra.ledger_record({"kind": "advise", "ts": 0, "resend": True})["at"] != "1970-01-01 09:00"



def test_ledger_off_by_default(client, tmp_path, monkeypatch):
    monkeypatch.delenv("LEDGER_ENABLED", raising=False)
    monkeypatch.setenv("LEDGER_DIR", str(tmp_path))
    ra._LEDGER_SUM.update(at=0, v=None)
    d = client.post("/api/regagent/ledger", json={"kind": "advise", "reg": "여비규정"}).get_json()
    assert d["disabled"] and not d["stored"] and "retry" not in d       # 기본은 서버에 남기지 않는다
    assert not any(tmp_path.iterdir())
    g = client.get("/api/regagent/ledger").get_json()
    assert g["disabled"] and not g["available"]
    assert client.get("/api/regagent/config").get_json()["ledger"] is False
    monkeypatch.setenv("LEDGER_ENABLED", "1")
    assert client.get("/api/regagent/config").get_json()["ledger"] is True



def test_advise_abridged_quote_not_verified(client, monkeypatch):
    monkeypatch.setitem(ra._CTX, "default_model_for", lambda p, k: "m")
    q = "국내여행의 경우에는 … 2분의 1을 넘지 아니하는 범위에서 여비를 추가로 지급할 수 있다"   # 뜻을 바꾼 줄인 인용
    monkeypatch.setitem(ra._CTX, "ai_generate", lambda *a, **k: (json.dumps({
        "conclusion": "해당 규정", "answer": "추가 지급할 수 있습니다 [1].", "basis": [{"src": 1, "point": q}]}), ""))
    d = client.post("/api/regagent/advise", json={"question": "국내 출장 숙박비 상한액을 넘으면?", "slug": "여비규정",
                                                  "provider": "gemini", "api_key": "k"}).get_json()
    b = d["basis"][0]
    assert b["abridged"] and b["verified"] is False and d["cite_check"]["ok"] == 0
