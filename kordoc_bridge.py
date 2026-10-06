"""kordoc(Node) 연동 — 로컬 Flask 서버에서 /api/kordoc/<action> 을 처리한다.

Vercel 에서는 vercel.json 이 /api/kordoc/* 를 Node 함수(api/kordoc.mjs)로 보내므로 이 경로를 거치지 않는다.
로컬에서는 같은 처리 모듈(kordoc_core.mjs)을 `node kordoc_cli.mjs <action>` 하위 프로세스로 부른다.
Node 또는 kordoc 패키지가 없으면 503 을 돌려주고, 화면은 내장 한글(.hwpx) 생성기로 대신한다.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("kordoc_bridge", __name__)
_ROOT = os.path.dirname(os.path.abspath(__file__))
_CLI = os.path.join(_ROOT, "kordoc_cli.mjs")
_ACTIONS = {"status", "lint", "bundle"}


def _available() -> str:
    """사용 불가 사유(빈 문자열이면 사용 가능)."""
    if not shutil.which("node"):
        return "Node.js 가 설치되어 있지 않습니다."
    if not os.path.isdir(os.path.join(_ROOT, "node_modules", "kordoc")):
        return "kordoc 패키지가 없습니다. 프로젝트 폴더에서 `npm install` 을 실행하세요."
    return ""


@bp.route("/api/kordoc/<action>", methods=["GET", "POST"])
def kordoc_action(action):
    if action not in _ACTIONS:
        return jsonify({"success": False, "error": "알 수 없는 요청입니다."}), 404
    why = _available()
    if why:
        return jsonify({"success": False, "error": why, "unavailable": True}), 503
    body = request.get_json(silent=True) if request.method == "POST" else {}
    try:
        p = subprocess.run(["node", _CLI, action], input=json.dumps(body if isinstance(body, dict) else {}),
                           capture_output=True, text=True, timeout=60, cwd=_ROOT)
        out = json.loads(p.stdout or "{}")
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "공문서 변환 시간이 초과되었습니다."}), 504
    except (OSError, ValueError) as e:
        print(f"[kordoc] 실행 실패: {e} {getattr(locals().get('p'), 'stderr', '')[:300]}")
        return jsonify({"success": False, "error": "공문서 변환기를 실행하지 못했습니다."}), 500
    if "b64" in out:
        headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(out.get("filename") or "문서.hwpx")}
        if out.get("warnings"):
            headers["X-Kordoc-Warnings"] = quote(" | ".join(out["warnings"][:5]))[:1500]
        return Response(base64.b64decode(out["b64"]), status=out.get("status", 200),
                        mimetype=out.get("type") or "application/octet-stream", headers=headers)
    return jsonify(out.get("json") or {"success": False, "error": "응답 오류"}), out.get("status", 500)


def register(app):
    app.register_blueprint(bp)
