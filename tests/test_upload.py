"""내규 원문 등록(/api/regs/upload) — 임시 폴더에서 별도 프로세스로 실행해 실제 regulations/ 를 건드리지 않는다."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = textwrap.dedent(r'''
    import io, json, sys
    import api_server
    c = api_server.app.test_client()
    out = {}

    def up(title, body, remote="127.0.0.1", token=None):
        data = {"title": title, "file": (io.BytesIO(body.encode("utf-8")), "a.txt")}
        if token:
            data["token"] = token
        r = c.post("/api/regs/upload", data=data, content_type="multipart/form-data",
                   environ_base={"REMOTE_ADDR": remote})
        return r.status_code

    out["first"] = up("인사 규정", "제1조(목적) 가.")
    out["clash"] = up("인사_규정", "제1조(목적) 나.")
    out["remote_anon"] = up("복무 규칙", "제1조(목적) 다.", remote="10.0.0.5")
    out["long_title"] = up("가" * 120, "제1조(목적) 라.")
    r = c.post("/api/regs/upload/delete", json=[1])
    out["delete_bad_json"] = [r.status_code, r.is_json]
    print(json.dumps(out))
''')


def test_upload_rules(tmp_path):
    reg = tmp_path / "regulations"
    reg.mkdir()
    man = tmp_path / "manifest.json"
    man.write_text("[]", encoding="utf-8")
    env = {**os.environ, "REG_DIR": str(reg), "REG_MANIFEST": str(man), "REG_UPLOAD_TOKEN": "",
           "GITHUB_TOKEN": "", "GITHUB_REPO": "", "REG_UPLOAD_ALLOW_ANON": ""}
    p = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["first"] == 200
    assert out["clash"] == 409                      # 같은 폴더로 모이는 다른 규정명
    assert out["remote_anon"] in (401, 403)         # 토큰 없는 서버는 원격 익명 업로드 거부
    assert out["long_title"] == 200                 # 긴 한글 규정명도 폴더명 한도 안에서 저장
    assert out["delete_bad_json"][0] == 400 and out["delete_bad_json"][1]
