"""개정문 왕복 시험 — 등록된 내규 전체에 무작위 개정을 가해 개정문을 만들고, 그 개정문을 현행에 다시 적용해 수정안과 같은지 센다.

사용: python scripts/roundtrip_amend.py [--seed 7] [--rounds 2] [--json]
결과: 시험 건수·일치 건수·일치율, 어긋난 사례(있으면). 화면의 “개정문 검증”과 같은 함수(raApplyAmend)를 쓴다."""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run(seed: int = 7, rounds: int = 2) -> dict:
    import api_server  # noqa: F401 — 블루프린트 등록
    import reg_agent as ra
    regs = [{"slug": r["slug"], "title": r["title"],
             "articles": [{"no": a["no"], "title": a["title"], "body": a["body"], "chapter": a.get("chapter", ""), "deleted": a["deleted"]} for a in r["articles"]]}
            for r in ra.all_regs()]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(regs, f, ensure_ascii=False)
        path = f.name
    try:
        out = subprocess.run(["node", os.path.join(ROOT, "scripts", "roundtrip_amend.mjs"), path, str(seed), str(rounds)],
                             capture_output=True, text=True, encoding="utf-8", timeout=600)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    return json.loads(out.stdout)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(a.seed, a.rounds)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        s = res["summary"]
        print(f"내규 {s['regs']}건 · 무작위 개정 {s['total']}건 → 개정문을 현행에 되돌려 적용해 수정안과 일치 {s['ok']}건 ({s['rate']}%)")
        for k, v in res["byMut"].items():
            print(f"  어긋남: {k} {v['n'] - v['ok']}/{v['n']}")
        for f_ in res["fails"][:10]:
            print(f"- {f_['reg']} [{f_['mut']}]")
            for e in f_["errors"]:
                print(f"    읽지 못함: {e}")
            for d in f_["diffs"]:
                print(f"    {d['no']}: 수정안 ≠ 적용 결과\n      기대: {d['exp'][:160]}\n      결과: {d['got'][:160]}")
            print(f"    개정문: {f_['law'][:300]}")
