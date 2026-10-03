"""내규 원문 등록(/upload) + 저장소 자동 커밋.

에이전트가 참고하는 기관 내규 원문을 실무 담당자가 웹에서 최신으로 유지하는 경로.
· 쓰기 가능한 서버(로컬·VM): regulations/ 와 매니페스트에 바로 저장(이전본은 .backup 보관)
· 읽기전용 서버리스(Vercel 등): GITHUB_TOKEN·GITHUB_REPO 가 있으면 저장소에 커밋 → 자동 재배포
· 업로드 토큰(REG_UPLOAD_TOKEN)으로 보호. 저장소 커밋 환경에서는 토큰이 없으면 거부(fail-closed)
변환은 reg_import.py(일괄 등록 스크립트와 공용)를 쓴다.
"""
from __future__ import annotations

import base64  # noqa: F401
import io as _io  # noqa: F401
import json
import os
import re
import time
import zipfile  # noqa: F401
from datetime import datetime
from urllib.parse import quote

import requests as req_lib
from flask import Blueprint, Response, jsonify, request

import hmac
from urllib.parse import quote as _q

import reg_import as ri
from reg_import import (REG_DIR, REG_MANIFEST_PATH, _KST, now_kst as _now_kst,  # noqa: F401
                        reg_slug as _reg_slug, guess_category as _guess_reg_category,
                        _convert_upload, norm_key as _norm_key, ALLOWED_EXT as _ALLOWED_EXT)

bp = Blueprint("reg_upload", __name__)
_SESSION = req_lib.Session()

REG_UPLOAD_TOKEN = os.environ.get("REG_UPLOAD_TOKEN", "").strip()
REG_UPLOAD_MAX_MB = int(os.environ.get("REG_UPLOAD_MAX_MB", "40"))
REG_CATEGORIES = ["정관", "규정", "규칙", "세칙", "예규", "매뉴얼", "기타"]
_REG_MANIFEST: list | None = None


def register(app):
    app.register_blueprint(bp)


def _load_reg_manifest() -> list:
    global _REG_MANIFEST
    if _REG_MANIFEST is None:
        _REG_MANIFEST = ri.load_manifest()
    return _REG_MANIFEST


def _save_reg_manifest(man: list) -> None:
    ri.save_manifest(man)


def _reg_writable() -> bool:
    """regulations/ 에 실제로 쓸 수 있는지(Vercel 등 읽기전용 FS 판별)."""
    try:
        os.makedirs(REG_DIR, exist_ok=True)
        probe = os.path.join(REG_DIR, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return os.access(REG_MANIFEST_PATH, os.W_OK) or not os.path.exists(REG_MANIFEST_PATH)
    except Exception:
        return False



def _local_reg_text(slug: str) -> str:
    try:
        p = os.path.join(REG_DIR, slug, "text.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        print(f"[reg-upload] 로컬 본문 읽기 실패({slug}): {e}")
    return ""


def _uploaded_regs() -> list:
    return [m for m in _load_reg_manifest() if m.get("uploaded_at") or m.get("history")]



REG_BACKUP_DIR = os.path.join(REG_DIR, ".backup")


def _backup_reg_dir(slug: str) -> str:
    """개정본으로 덮어쓰기 전 기존 규정 폴더를 보관한다(되돌리기용). 보관 경로명 반환."""
    src = os.path.join(REG_DIR, slug)
    if not os.path.isdir(src):
        return ""
    import shutil
    os.makedirs(REG_BACKUP_DIR, exist_ok=True)
    name = f"{slug}__{datetime.now(_KST).strftime('%Y%m%d-%H%M%S')}"
    dst = os.path.join(REG_BACKUP_DIR, name)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return name


def _restore_reg_dir(slug: str, backup_name: str) -> bool:
    """보관해 둔 이전 규정 폴더를 되돌린다."""
    if not backup_name:
        return False
    src = os.path.join(REG_BACKUP_DIR, os.path.basename(backup_name))
    dst = os.path.join(REG_DIR, slug)
    if not os.path.isdir(src):
        return False
    import shutil
    shutil.rmtree(dst, ignore_errors=True)
    shutil.move(src, dst)
    return True


def _write_reg_files(slug: str, view_html: str, text: str,
                     orig_filename: str, raw: bytes) -> str:
    """regulations/<slug>/ 에 열람 HTML·본문·원본을 쓴다. 저장된 원본 파일명 반환."""
    d = os.path.join(REG_DIR, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(view_html)
    if text:
        with open(os.path.join(d, "text.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    ext = os.path.splitext(orig_filename)[1].lower()
    stored = ("original.pdf" if ext == ".pdf" else f"original{ext}")
    with open(os.path.join(d, stored), "wb") as f:
        f.write(raw)
    return stored


def _upsert_manifest(entry: dict, backup_name: str = "") -> dict:
    """
    manifest 에 등록/갱신. 같은 규정명이 있으면 개정판으로 교체하고
    이전 항목 전체를 이력에 남긴다(되돌리기로 복원 가능).
    """
    man = list(_load_reg_manifest())
    key = _norm_key(entry["title"])
    idx = next((i for i, m in enumerate(man)
                if _norm_key(m.get("title", "")) == key), -1)
    if idx >= 0:
        old = dict(man[idx])
        history = list(old.pop("history", None) or [])
        history.insert(0, {"revision": old.get("revision", ""),
                           "src": old.get("src", ""),
                           "replaced_at": entry.get("uploaded_at", ""),
                           "backup": backup_name,
                           "entry": old})
        entry = {**old, **entry, "history": history[:20]}
        man[idx] = entry
    else:
        man.append(entry)
    # 정렬하지 않는다 — 기존 항목 순서를 유지해 커밋 diff 를 최소화한다
    _save_reg_manifest(man)
    global _REG_MANIFEST
    _REG_MANIFEST = man
    return entry


def _upload_authorized() -> tuple[bool, str]:
    """업로드 허용 여부와 거부 사유를 반환한다.

    fail-closed 원칙: 업로드가 리포지토리에 그대로 커밋·배포되는 환경
    (_gh_enabled)에서 REG_UPLOAD_TOKEN 이 설정돼 있지 않으면 익명 업로드가
    저장소를 오염시킬 수 있으므로 거부한다. 토큰이 설정된 경우에는 일치해야
    한다. 로컬 쓰기 전용(비-GitHub) 개발 환경에서는 토큰 없이도 허용한다.
    """
    if not REG_UPLOAD_TOKEN:
        if _gh_enabled():
            return (False, "이 서버는 업로드가 리포지토리에 자동 커밋되므로 "
                           "REG_UPLOAD_TOKEN 설정이 필요합니다. 관리자에게 문의하세요.")
        # 토큰이 없으면 이 PC에서 띄운 개발 서버(루프백)만 허용한다. 공개 서버에서 익명 업로드를
        # 허용하려면 REG_UPLOAD_ALLOW_ANON=1 을 명시해야 한다(fail-closed).
        if os.environ.get("REG_UPLOAD_ALLOW_ANON", "").strip() == "1" or \
                (request.remote_addr or "") in ("127.0.0.1", "::1"):
            return (True, "")
        return (False, "업로드 토큰(REG_UPLOAD_TOKEN)이 설정되지 않은 서버입니다. 관리자에게 문의하세요.")
    tok = (request.form.get("token") or request.headers.get("X-Upload-Token") or "").strip()
    if hmac.compare_digest(tok.encode("utf-8"), REG_UPLOAD_TOKEN.encode("utf-8")):
        return (True, "")
    return (False, "업로드 토큰이 올바르지 않습니다.")


# ── GitHub 직접 커밋 (읽기전용 배포에서 업로드를 반영하는 경로) ────────────────
# 업로드 → 변환 → 리포지토리에 커밋 → Vercel 자동 배포.
# regulations/ 를 그대로 단일 출처로 유지하고, 개정 이력이 git 히스토리로 남는다.
def _env_clean(name: str, default: str = "") -> str:
    """환경변수 값 정리 — 붙여넣기 과정에서 딸려오는 따옴표·공백·개행을 털어낸다.

    Vercel 대시보드에 토큰을 붙여넣을 때 따옴표가 함께 들어가면 401 이 난다.
    """
    v = (os.environ.get(name, default) or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


GITHUB_TOKEN  = _env_clean("GITHUB_TOKEN")
GITHUB_REPO   = _env_clean("GITHUB_REPO").strip("/")               # 예: owner/repo
GITHUB_BRANCH = _env_clean("GITHUB_BRANCH", "main") or "main"
GITHUB_API    = _env_clean("GITHUB_API", "https://api.github.com").rstrip("/")
# GitHub 연결 점검 결과 캐시 — 업로드 화면에서 미리 알려주기 위한 용도
_GH_CHECK: dict = {"ts": 0.0, "ok": False, "error": ""}


def _gh_enabled() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def _gh_headers() -> dict:
    return {"Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _gh_hint(status: int, detail: str, path: str = "") -> str:
    """GitHub 오류를 담당자가 바로 조치할 수 있는 안내로 바꾼다."""
    d = (detail or "").lower()
    if status == 401:
        return ("GITHUB_TOKEN 이 유효하지 않습니다(만료·폐기되었거나 값이 잘못 입력됨). "
                "GitHub → Settings → Developer settings 에서 토큰을 새로 발급한 뒤 "
                "Vercel 환경변수 GITHUB_TOKEN 을 교체하고 재배포하세요. "
                "값에 따옴표·공백·줄바꿈이 섞이지 않았는지도 확인해주세요.")
    if status == 403:
        if "rate limit" in d:
            return "GitHub API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요."
        return (f"토큰에 저장소({GITHUB_REPO}) 쓰기 권한이 없습니다. "
                "Fine-grained 토큰이면 해당 저장소를 Repository access 에 포함하고 "
                "Contents 권한을 Read and write 로 설정하세요.")
    if status == 404:
        return (f"저장소나 브랜치를 찾을 수 없습니다(GITHUB_REPO={GITHUB_REPO or '미설정'}, "
                f"GITHUB_BRANCH={GITHUB_BRANCH}). 값이 'owner/repo' 형식인지, "
                "브랜치 이름이 맞는지, 비공개 저장소라면 토큰 권한 범위에 포함됐는지 확인하세요.")
    if status == 409:
        return "다른 커밋과 충돌했습니다. 잠시 후 다시 시도하세요."
    if status == 422:
        return f"GitHub 가 요청을 거부했습니다: {detail}"
    return f"GitHub 오류({status}): {detail}"


def _gh(method: str, path: str, **kw):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}{path}"
    r = _SESSION.request(method, url, headers=_gh_headers(), timeout=30, **kw)
    if r.status_code >= 400:
        detail = ""
        try:
            detail = (r.json() or {}).get("message", "")
        except Exception:
            detail = (r.text or "")[:160]
        print(f"[gh] {method} {path} → {r.status_code} {detail}")
        err = RuntimeError(_gh_hint(r.status_code, detail, path))
        err.status = r.status_code            # 404(정상 미존재)와 그 외 오류 구분용
        raise err
    return r.json() if r.content else {}


def _gh_check(force: bool = False) -> dict:
    """토큰·저장소·브랜치가 실제로 쓸 수 있는 상태인지 확인(5분 캐시).

    업로드를 끝까지 진행한 뒤에야 401 을 만나는 일이 없도록 화면에서 미리 알린다.
    """
    if not _gh_enabled():
        return {"ok": False, "error": ""}
    if not force and time.time() - _GH_CHECK["ts"] < 300:
        return {"ok": _GH_CHECK["ok"], "error": _GH_CHECK["error"]}
    try:
        _gh("GET", f"/git/ref/heads/{GITHUB_BRANCH}")
        _GH_CHECK.update({"ts": time.time(), "ok": True, "error": ""})
    except Exception as e:
        _GH_CHECK.update({"ts": time.time(), "ok": False, "error": str(e)})
    return {"ok": _GH_CHECK["ok"], "error": _GH_CHECK["error"]}


def _gh_commit_files(files: dict, message: str, deletes=None):
    """여러 파일을 한 커밋으로 반영. files={경로: bytes|str}, deletes=[경로].

    Git Data API(blob→tree→commit→ref)로 원자적으로 커밋한다.
    Contents API를 파일마다 호출하면 커밋이 쪼개지고 중간 실패 시 상태가 깨진다.
    """
    ref = _gh("GET", f"/git/ref/heads/{GITHUB_BRANCH}")
    head_sha = ref["object"]["sha"]
    base_tree = _gh("GET", f"/git/commits/{head_sha}")["tree"]["sha"]

    tree = []
    for path, content in (files or {}).items():
        if isinstance(content, str):
            content = content.encode("utf-8")
        blob = _gh("POST", "/git/blobs",
                   json={"content": base64.b64encode(content).decode("ascii"),
                         "encoding": "base64"})
        tree.append({"path": path, "mode": "100644", "type": "blob",
                     "sha": blob["sha"]})
    for path in (deletes or []):
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
    if not tree:
        raise RuntimeError("커밋할 파일이 없습니다.")

    new_tree = _gh("POST", "/git/trees",
                   json={"base_tree": base_tree, "tree": tree})
    commit = _gh("POST", "/git/commits",
                 json={"message": message, "tree": new_tree["sha"],
                       "parents": [head_sha]})
    _gh("PATCH", f"/git/refs/heads/{GITHUB_BRANCH}",
        json={"sha": commit["sha"], "force": False})
    return commit["sha"]


def _gh_get_manifest():
    """리포지토리의 현재 manifest 를 읽어온다(로컬 파일이 낡았을 수 있으므로).

    GitHub 연동이 켜진 상태에서 원격 읽기가 '네트워크/HTTP 오류'로 실패하면,
    낡은 로컬 manifest 로 커밋해 다른 인스턴스가 추가한 항목을 덮어써 유실시킬
    위험이 있다. 따라서 그런 경우엔 폴백하지 않고 예외를 올려 커밋을 중단시킨다.
    저장소에 아직 manifest 가 없는 정상적인 404 는 로컬/빈 목록으로 폴백해도 안전하다.
    """
    if not _gh_enabled():
        return list(_load_reg_manifest())
    try:
        d = _gh("GET", "/contents/regulations_manifest.json",
                params={"ref": GITHUB_BRANCH})
        raw = base64.b64decode(d.get("content", "") or "")
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        if getattr(e, "status", None) == 404:
            print(f"[gh] manifest 없음(404), 로컬 사용")
            return list(_load_reg_manifest())
        print(f"[gh] manifest 조회 실패(안전을 위해 중단): {e}")
        raise RuntimeError("저장소 상태를 읽지 못해 안전을 위해 중단했습니다. "
                           "잠시 후 다시 시도하세요.")


def _gh_dir(path: str, ref: str = ""):
    """저장소 디렉터리 목록. 없으면 []."""
    try:
        d = _gh("GET", f"/contents/{_q(path, safe='/')}", params={"ref": ref or GITHUB_BRANCH})
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _gh_file(path: str, ref: str = ""):
    """저장소 파일 내용(bytes). 없으면 None."""
    try:
        d = _gh("GET", f"/contents/{_q(path, safe='/')}", params={"ref": ref or GITHUB_BRANCH})
        if isinstance(d, dict) and d.get("content"):
            return base64.b64decode(d["content"])
        # 1MB 초과 파일은 content 가 비므로 blob 으로 받는다
        if isinstance(d, dict) and d.get("sha"):
            b = _gh("GET", f"/git/blobs/{d['sha']}")
            return base64.b64decode(b.get("content", "") or "")
    except Exception:
        pass
    return None


def _gh_prev_commit(path: str) -> str:
    """이 경로에 개정본이 올라오기 '직전' 상태의 커밋 sha. 없으면 ''.

    업로드 화면이 만든 커밋('내규 등록/개정: …')을 먼저 찾아 그 부모를 쓴다.
    그 뒤에 다른 수정 커밋이 끼어 있어도 개정 이전 원본을 정확히 되살리기 위함이다.
    """
    try:
        cs = _gh("GET", "/commits", params={"path": path, "sha": GITHUB_BRANCH,
                                            "per_page": 10})
        if not isinstance(cs, list) or not cs:
            return ""
        for c in cs:
            msg = ((c.get("commit") or {}).get("message") or "")
            if msg.startswith("내규 등록:") or msg.startswith("내규 개정:"):
                parents = c.get("parents") or []
                if parents:
                    return parents[0].get("sha", "")
                break
        return cs[1].get("sha", "") if len(cs) >= 2 else ""
    except Exception as e:
        print(f"[gh] 이전 커밋 조회 실패({path}): {e}")
    return ""


def _merge_manifest(man: list, entry: dict):
    """같은 규정명이 있으면 교체(이전 개정은 history 에 누적), 없으면 추가."""
    key = _norm_key(entry.get("title", ""))
    out, replaced, prev = [], False, None
    for m in man:
        if _norm_key(m.get("title", "")) == key:
            prev = {k: v for k, v in m.items() if k != "history"}
            hist = list(m.get("history") or [])
            # 이력 스키마를 _upsert_manifest 와 통일: 이전 개정 라벨 + 교체 시각 기록.
            # entry 는 유지(되돌리기 복원에 사용).
            hist.insert(0, {"revision": prev.get("revision", ""),
                            "replaced_at": entry.get("uploaded_at", ""),
                            "entry": prev})
            entry = dict(entry)
            entry["history"] = hist[:20]
            out.append(entry); replaced = True
        else:
            out.append(m)
    if not replaced:
        out.append(entry)
    return out, replaced



@bp.route("/upload")
@bp.route("/upload.html")
def upload_page():
    """개정 내규 업로드 페이지."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload.html")
        with open(p, encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    except FileNotFoundError:
        return Response("<h1>upload.html not found</h1>", status=404)


@bp.route("/api/regs/upload/status")
def reg_upload_status():
    """업로드 가능 여부·카테고리·업로드 이력."""
    ups = _uploaded_regs()
    chk = _gh_check(force=bool(request.args.get("recheck")))
    return jsonify({
        "success": True,
        "writable": _reg_writable(),
        "github": _gh_enabled(),
        "github_repo": GITHUB_REPO if _gh_enabled() else "",
        "github_branch": GITHUB_BRANCH if _gh_enabled() else "",
        "github_ok": chk["ok"],
        "github_error": chk["error"],
        "token_required": bool(REG_UPLOAD_TOKEN),
        "max_mb": REG_UPLOAD_MAX_MB,
        "categories": REG_CATEGORIES,
        "allowed_ext": sorted(_ALLOWED_EXT),
        "total": len(_load_reg_manifest()),
        "uploaded": [
            {"title": m.get("title"), "revision": m.get("revision"),
             "category": m.get("category"), "slug": m.get("slug"),
             "html": m.get("html"), "src": m.get("src"),
             "uploaded_at": m.get("uploaded_at"),
             "uploader": m.get("uploader", ""),
             "searchable": bool(_local_reg_text(m.get("slug", ""))),
             "history": m.get("history") or []}
            for m in sorted(ups, key=lambda x: x.get("uploaded_at", ""), reverse=True)
        ],
    })


@bp.route("/api/regs/names")
def reg_names_for_upload():
    """등록된 규정명 목록 — 업로드 화면의 '기존 규정 개정' 자동완성용."""
    man = _load_reg_manifest()
    return jsonify({"success": True, "names": [
        {"title": m.get("title", ""), "category": m.get("category", ""),
         "revision": m.get("revision", ""), "uploaded_at": m.get("uploaded_at", "")}
        for m in man if m.get("title")]})


@bp.route("/api/regs/upload", methods=["POST"])
def reg_upload():
    """개정 내규 업로드 — 변환·저장·manifest 등록."""
    _ok, _why = _upload_authorized()
    if not _ok:
        return jsonify({"error": _why}), 401

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "파일을 선택해주세요."}), 400
    filename = os.path.basename(f.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXT:
        return jsonify({"error": f"지원하지 않는 형식입니다({ext}). "
                                f"가능: {', '.join(sorted(_ALLOWED_EXT))}"}), 400

    raw = f.read()
    if not raw:
        return jsonify({"error": "빈 파일입니다."}), 400
    if len(raw) > REG_UPLOAD_MAX_MB * 1024 * 1024:
        return jsonify({"error": f"파일이 너무 큽니다(최대 {REG_UPLOAD_MAX_MB}MB)."}), 413

    # 규정명: 입력값 우선, 없으면 파일명에서 추출 ("감사규정(2023년도 7월 일부개정).hwpx")
    title = (request.form.get("title") or "").strip()
    stem = os.path.splitext(filename)[0]
    m_par = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", stem)
    if not title:
        title = (m_par.group(1) if m_par else stem).strip()
    revision = (request.form.get("revision") or "").strip()
    if not revision and m_par:
        revision = m_par.group(2).strip()
    if not title:
        return jsonify({"error": "규정명을 입력해주세요."}), 400

    # 구분 결정: 개정판이면 기존 등록 구분을 잇고, 없으면 규정명으로 추정한다.
    # 사람이 고른 값이라도 이름과 어긋나는 '정관'은 받지 않는다(정관은 기관당 1건).
    category = (request.form.get("category") or "").strip()
    guessed = _guess_reg_category(title)
    prev_cat = ""
    for _m in (_load_reg_manifest() or []):
        if _norm_key(_m.get("title") or "") == _norm_key(title):
            prev_cat = (_m.get("category") or "").strip()
            break
    if category in ("", "자동", "자동 분류"):
        category = prev_cat or guessed
    if category == "정관" and guessed != "정관":
        print(f"[upload] '{title}' 구분 정관 → {prev_cat or guessed} 로 교정")
        category = prev_cat if prev_cat and prev_cat != "정관" else guessed
    if category not in REG_CATEGORIES:
        category = guessed

    meta = {
        "category": category,
        "revision": revision,
        "effective_date": (request.form.get("effective_date") or "").strip(),
        "department": (request.form.get("department") or "").strip(),
        "note": (request.form.get("note") or "").strip(),
        "uploader": (request.form.get("uploader") or "").strip()[:40],
        "uploaded_at": _now_kst(),
    }

    try:
        conv = _convert_upload(filename, raw, title, meta)
    except zipfile.BadZipFile:
        return jsonify({"error": "파일을 열 수 없습니다. HWPX/DOCX 파일이 손상되었을 수 있습니다."}), 400
    except Exception as e:
        return jsonify({"error": f"변환 실패: {e}"}), 400

    slug = _reg_slug(title)
    if not slug:
        return jsonify({"error": "규정명에서 저장 폴더명을 만들 수 없습니다."}), 400
    # 서로 다른 규정명이 같은 폴더(slug)로 모이면 기존 규정 파일을 덮어쓰게 되므로 막는다
    clash = next((m for m in _load_reg_manifest()
                  if m.get("slug") == slug and _norm_key(m.get("title", "")) != _norm_key(title)), None)
    if clash:
        return jsonify({"error": f"「{clash.get('title')}」과(와) 저장 폴더가 겹칩니다. 규정명을 정확히 입력하세요."}), 409

    stored_ext = ".pdf" if ext == ".pdf" else ext
    entry = {
        "title": title,
        "revision": revision or meta["uploaded_at"][:10] + " 개정",
        "category": category,
        "slug": slug,
        "src": filename,
        # 기존 manifest 형식과 동일하게 인코딩하지 않은 경로로 저장
        "html": f"/regulations/{slug}/index.html",
        "pdf": f"pdf/{slug}.pdf",
        "effective_date": meta["effective_date"],
        "department": meta["department"],
        "note": meta["note"],
        "uploader": meta["uploader"],
        "uploaded_at": meta["uploaded_at"],
        "original": f"/regulations/{slug}/original{stored_ext}",
        "searchable": bool(conv["text"]),
    }

    # ── GitHub 직접 커밋: 읽기전용 배포에서도 업로드를 반영한다 ──
    want_zip = (request.args.get("as") or request.form.get("as") or "") == "zip"
    if not want_zip and _gh_enabled():
        try:
            base = f"regulations/{slug}"
            stored_name = f"original{stored_ext}"
            entry["original"] = f"/{base}/{stored_name}"
            man, replaced = _merge_manifest(_gh_get_manifest(), entry)
            files = {
                f"{base}/index.html": conv["view_html"],
                f"{base}/{stored_name}": raw,
                "regulations_manifest.json":
                    json.dumps(man, ensure_ascii=False, indent=1) + "\n",
            }
            if conv["text"]:
                files[f"{base}/text.txt"] = conv["text"]
            # F03: 변환 불가 파일(PDF/HWP 등)로 교체할 때 이전 추출 본문(text.txt)과
            # 확장자가 바뀐 구 원본을 명시적으로 제거한다. 그대로 두면 최신 개정일이
            # 표시되는데 검색·전문은 구버전 text.txt를 반환하는 불일치가 생긴다.
            deletes = []
            try:
                existing = {f.get("name") for f in _gh_dir(base)
                            if isinstance(f, dict) and f.get("name")}
            except Exception:
                existing = set()
            if replaced and not conv["text"] and "text.txt" in existing:
                deletes.append(f"{base}/text.txt")
            for nm in existing:                      # 확장자가 바뀐 구 원본 정리
                if nm.startswith("original.") and nm != stored_name:
                    deletes.append(f"{base}/{nm}")
            who = meta.get("uploader") or "익명"
            msg = (f"내규 {'개정' if replaced else '등록'}: {title}"
                   + (f" ({revision})" if revision else "")
                   + f"\n\n업로더: {who}"
                   + (f"\n개정사유: {meta['note']}" if meta.get("note") else "")
                   + "\n\n업로드 화면(/upload)에서 자동 커밋됨")
            sha = _gh_commit_files(files, msg, deletes=deletes or None)
            print(f"[reg-upload] GitHub 커밋 완료: {title} → {sha[:7]}"
                  + (f" (삭제 {len(deletes)}건)" if deletes else ""))
            return jsonify({
                "success": True, "entry": entry, "replaced": replaced,
                "searchable": bool(conv["text"]), "warning": conv["warning"],
                "committed": True, "commit_sha": sha[:7],
                "commit_url": f"https://github.com/{GITHUB_REPO}/commit/{sha}",
                "message": "리포지토리에 커밋했습니다. 배포 반영까지 1~2분 걸립니다.",
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"error": f"GitHub 커밋 실패: {e}"}), 502

    # ── 읽기 전용 배포에서 GitHub 미설정: 변환 결과를 ZIP 으로 내려준다 ──
    if want_zip or not _reg_writable():
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            base = f"regulations/{slug}"
            z.writestr(f"{base}/index.html", conv["view_html"])
            if conv["text"]:
                z.writestr(f"{base}/text.txt", conv["text"])
            z.writestr(f"{base}/original{stored_ext}", raw)
            z.writestr("manifest_entry.json",
                       json.dumps(entry, ensure_ascii=False, indent=2))
            z.writestr("READ_ME.txt",
                       "이 ZIP 을 리포지토리 루트에 풀고 manifest_entry.json 의 내용을\n"
                       "regulations_manifest.json 배열에 추가(같은 규정명이 있으면 교체)한 뒤\n"
                       "커밋·푸시하면 배포본에 반영됩니다.\n")
        if not want_zip and not _reg_writable():
            print(f"[reg-upload] 읽기 전용 FS — ZIP 응답으로 대체: {title}")
        buf.seek(0)
        return Response(
            buf.read(), mimetype="application/zip",
            headers={"Content-Disposition":
                     f"attachment; filename*=UTF-8''{quote(slug)}.zip",
                     "X-Reg-Readonly": "1" if not _reg_writable() else "0",
                     "X-Reg-Warning": quote(conv["warning"] or "")})

    try:
        backup = _backup_reg_dir(slug)      # 기존 규정 폴더 보관(되돌리기용)
        stored = _write_reg_files(slug, conv["view_html"], conv["text"], filename, raw)
        entry["original"] = f"/regulations/{slug}/{stored}"
        entry = _upsert_manifest(entry, backup)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"저장 실패: {e}"}), 500

    print(f"[reg-upload] 등록 완료: {title} ({revision}) → {slug}")
    return jsonify({"success": True, "entry": entry,
                    "warning": conv["warning"],
                    "searchable": bool(conv["text"]),
                    "view_url": entry["html"],
                    "replaced": bool(entry.get("history"))})


def _gh_revert(slug: str):
    """GitHub 커밋으로 개정 되돌리기.

    이전 개정이 있으면 그 개정본을 올리기 직전 커밋에서 파일을 되살리고,
    신규 등록이었으면 폴더 파일을 지운다. manifest 와 함께 한 커밋으로 반영한다.
    """
    man = _gh_get_manifest()
    idx = next((i for i, m in enumerate(man) if m.get("slug") == slug), -1)
    if idx < 0:
        return jsonify({"error": "해당 규정을 찾을 수 없습니다."}), 404
    cur = man[idx]
    if not cur.get("uploaded_at") and not cur.get("history"):
        return jsonify({"error": "업로드로 등록된 규정만 되돌릴 수 있습니다."}), 400

    base = f"regulations/{slug}"
    now_files = [f.get("name") for f in _gh_dir(base) if f.get("type") == "file"]
    history = list(cur.get("history") or [])
    files, deletes, warning = {}, [], ""

    if history:                                   # ── 이전 개정본으로 복원 ──
        h = history.pop(0)
        prev = dict(h.get("entry") or {})
        prev.pop("history", None)
        if history:
            prev["history"] = history
        # 이번 개정을 커밋하기 직전 상태(= 이전 개정본)를 git 에서 되살린다
        ref = _gh_prev_commit(f"{base}/index.html")
        old_files = [f.get("name") for f in _gh_dir(base, ref)] if ref else []
        for name in old_files:
            data = _gh_file(f"{base}/{name}", ref)
            if data is not None:
                files[f"{base}/{name}"] = data
        for name in now_files:                    # 이전에 없던 파일(확장자 변경 등)은 정리
            if name not in old_files:
                deletes.append(f"{base}/{name}")
        if not files:
            warning = ("이전 개정본 파일을 저장소 이력에서 찾지 못해 등록 정보만 되돌렸습니다. "
                       "문서 내용은 현재 개정본이 그대로 남아 있습니다.")
            print(f"[gh-revert] 이전 파일 복원 실패: {base} (ref={ref or '없음'})")
        man[idx] = prev
        restored_rev = prev.get("revision", "")
    else:                                         # ── 신규 등록 → 등록 해제 ──
        man.pop(idx)
        deletes = [f"{base}/{n}" for n in now_files]
        restored_rev = ""

    files["regulations_manifest.json"] = (
        json.dumps(man, ensure_ascii=False, indent=1) + "\n")
    title = cur.get("title", slug)
    msg = (f"내규 되돌리기: {title}"
           + (f" → {restored_rev}" if restored_rev else " (등록 해제)")
           + "\n\n업로드 화면(/upload)에서 자동 커밋됨")
    sha = _gh_commit_files(files, msg, deletes=deletes)
    print(f"[gh-revert] 완료: {title} → {sha[:7]}")
    return jsonify({
        "success": True, "removed": title,
        "restored": bool(restored_rev), "restored_revision": restored_rev,
        "files_restored": not warning, "warning": warning,
        "committed": True, "commit_sha": sha[:7],
        "commit_url": f"https://github.com/{GITHUB_REPO}/commit/{sha}",
        "message": "리포지토리에 커밋했습니다. 배포 반영까지 1~2분 걸립니다.",
    })


@bp.route("/api/regs/upload/delete", methods=["POST"])
def reg_upload_delete():
    """
    업로드한 개정 내규 되돌리기.
      · 이전 개정이 있으면 그 개정본(파일·manifest 항목)으로 복원한다
      · 이전 개정이 없으면(신규 등록) 등록을 해제하고 파일을 삭제한다
    """
    _ok, _why = _upload_authorized()
    if not _ok:
        return jsonify({"error": _why}), 401
    jb = request.get_json(silent=True)
    slug = str(request.form.get("slug") or (jb.get("slug") if isinstance(jb, dict) else "") or "").strip()
    if not slug or "/" in slug or "\\" in slug or slug.startswith("."):
        return jsonify({"error": "slug 값이 올바르지 않습니다."}), 400

    # 읽기 전용 배포(서버리스)에서는 업로드와 같은 경로로 GitHub 에 커밋해 되돌린다.
    if not _reg_writable():
        if not _gh_enabled():
            return jsonify({"error": "읽기 전용 환경이고 GitHub 연동도 없어 되돌릴 수 없습니다. "
                                     "GITHUB_TOKEN·GITHUB_REPO 를 설정하세요."}), 503
        try:
            return _gh_revert(slug)
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"error": f"되돌리기 실패: {e}"}), 502

    man = list(_load_reg_manifest())
    idx = next((i for i, m in enumerate(man) if m.get("slug") == slug), -1)
    if idx < 0:
        return jsonify({"error": "해당 규정을 찾을 수 없습니다."}), 404
    cur = man[idx]
    if not cur.get("uploaded_at") and not cur.get("history"):
        return jsonify({"error": "업로드로 등록된 규정만 되돌릴 수 있습니다."}), 400

    history = list(cur.get("history") or [])
    restored_rev, files_restored = "", True
    if history:                                   # 이전 개정본으로 복원
        h = history.pop(0)
        prev = dict(h.get("entry") or {})
        prev.pop("history", None)
        if history:                               # 남은 이력이 없으면 키를 만들지 않는다
            prev["history"] = history
        files_restored = _restore_reg_dir(slug, h.get("backup", ""))
        man[idx] = prev
        restored_rev = prev.get("revision", "")
    else:                                         # 신규 등록 → 완전 삭제
        man.pop(idx)
        d = os.path.join(REG_DIR, slug)
        if os.path.isdir(d) and os.path.abspath(d).startswith(
                os.path.abspath(REG_DIR) + os.sep):
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    _save_reg_manifest(man)
    global _REG_MANIFEST
    _REG_MANIFEST = man

    return jsonify({"success": True, "removed": cur.get("title", ""),
                    "restored": bool(restored_rev),
                    "restored_revision": restored_rev,
                    "files_restored": files_restored,
                    "warning": ("" if files_restored else
                                "이전 개정본 파일 보관분을 찾지 못해 등록 정보만 되돌렸습니다. "
                                "regulations/ 폴더는 git 에서 복원해주세요(git checkout -- regulations/).")})


