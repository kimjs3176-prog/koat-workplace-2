"""지자체 자치법규 예시(samples/local_gov) — 기관 프로필·규정 폴더만 바꿔 조례·시행규칙에 같은 엔진이 동작하는지(별도 프로세스에서 환경변수로 띄운다)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = r'''
import sys, json
sys.path.insert(0, %r)
import api_server, reg_agent as ra
from api_server import app
c = app.test_client()
regs = ra.all_regs()
out = {"org": [ra.ORG["org_name"], ra.ORG["head"], ra.ORG["reg_word"]],
       "regs": [[r["title"], len(r["articles"]), bool(r["appendix"])] for r in regs]}
h = c.get("/api/regagent/health").get_json()
out["health"] = [[x["title"], x["score"], x["laws"]] for x in h["rows"]]
p = c.post("/api/regagent/plan", json={"request": "농업기계 임대사업 운영 조례 제5조 임대 기간을 5일로 늘려줘"}).get_json()["plan"]
out["plan"] = [p["mode"], p["reg"]["title"], [a["no"] for a in p["articles"]]]
slug = next(r["slug"] for r in regs if r["title"].endswith("운영 조례"))
im = c.post("/api/regagent/impact", json={"slug": slug, "nos": ["7"]}).get_json()
out["impact"] = [im["summary"], im["children"]]
out["enact"] = ra.template_enact({"title": "가온군 치유농업 육성 및 지원 조례", "purpose": "치유농업 육성"})["addenda"]
out["kind"] = [ra._kind_of("가온군 농업기계 임대사업 운영 조례"), ra._kind_of("가온군 ○○ 조례 시행규칙"), ra._kind_of("농림축산식품부 ○○ 훈령")]
print("@@" + json.dumps(out, ensure_ascii=False))
''' % ROOT


def test_local_gov_profile_runs_same_engine():
    env = dict(os.environ, ORG_CONFIG=os.path.join(ROOT, "samples/local_gov/org_config.json"),
               REG_DIR=os.path.join(ROOT, "samples/local_gov/regulations"),
               REG_MANIFEST=os.path.join(ROOT, "samples/local_gov/regulations_manifest.json"))
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.split("@@", 1)[1])
    assert out["org"] == ["가온군", "군수", "자치법규"]
    assert sorted(out["regs"]) == [["가온군 농업기계 임대사업 운영 조례", 10, True], ["가온군 농업기계 임대사업 운영 조례 시행규칙", 5, False]]
    laws = dict((t, l) for t, _, l in out["health"])
    assert "농업기계화 촉진법" in laws["가온군 농업기계 임대사업 운영 조례"] and "지방자치법" in laws["가온군 농업기계 임대사업 운영 조례"]
    assert out["plan"] == ["amend", "가온군 농업기계 임대사업 운영 조례", ["5"]]
    assert out["impact"][0]["appendix"] == 1 and out["impact"][1] == ["가온군 농업기계 임대사업 운영 조례 시행규칙"]
    assert out["enact"] == ["이 조례는 공포한 날부터 시행한다."]
    assert out["kind"] == ["조례", "규칙", "훈령"]
