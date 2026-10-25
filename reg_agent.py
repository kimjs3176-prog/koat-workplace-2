"""규정 제·개정 에이전트 — 내규 제정·개정 실무 지원 API.

기능
  · 내규 조문 구조 조회(장·조·항, 개정 이력 주석 제거)
  · 유사 규정·조문 검색(키워드 가중 + 의미 검색 결합)
  · 개정 조문 인용 영향 분석(같은 내규 내부 인용·다른 내규 인용·별표/별지 관련 조문)
  · 상위법 개정 영향 분석(상위법을 인용하는 내규 조문 탐지 → 개정 후보)
  · 조문 점검(조 번호·항/호 순서·인용 대상·구 명칭·내규명·어문 표기)과 전체 내규 일괄 점검
  · AI 초안 작성(제정: 조문 체계·표준 조문 / 개정: 조문 수정안·개정 이유)
    — AI 키가 없으면 표준 조문 골격(제정)을 템플릿으로 만들어 준다
  · 제·개정 문서 세트 한글(.hwpx) 저장

api_server.register 시 공통 헬퍼(AI 호출·의미 검색·HWPX 베이스)를 넘겨받는다.
작성 기준·절차·기관 명칭은 기관 프로필(org_config.json, ORG_CONFIG)에서 읽는다.
"""
from __future__ import annotations

import difflib
import io
import json
import os
import re
import threading
import time
import zipfile

from flask import Blueprint, Response, jsonify, request

import alio
import notation
import reg_chunks

bp = Blueprint("reg_agent", __name__)
_CTX: dict = {}

# ── 요청 본문 정리: 잘못된 형식(배열·숫자 본문, 필드 타입 오류)은 기본값으로 바꿔 500 대신 400/정상 처리 ──
_STR_KEYS = {"text", "title", "reg", "slug", "query", "exclude", "law", "old", "new", "mode", "purpose", "intent",
             "effective", "contents", "filename", "request", "category", "dept", "provider", "api_key", "model",
             "q", "kw", "idx", "question"}
_STRLIST_KEYS = {"nos", "arts", "slugs", "names", "main", "focus", "orgs"}
_DICTLIST_KEYS = {"delegations", "targets", "refs", "blocks", "alio_refs", "history"}
_DICT_KEYS = {"moves", "ans", "law_info", "texts", "kinds"}
_MAX_LIST = 2000


_SURR = re.compile(r"[\ud800-\udfff]")


def _clean(v, depth=0):
    """짝 잃은 UTF-16 대리 문자(잘린 이모지 등)는 지운다 — 그대로 두면 UTF-8 로 쓸 때 500."""
    if isinstance(v, str):
        return _SURR.sub("", v)
    if depth > 8:
        return v
    if isinstance(v, list):
        return [_clean(x, depth + 1) for x in v]
    if isinstance(v, dict):
        return {(_clean(k) if isinstance(k, str) else k): _clean(x, depth + 1) for k, x in v.items()}
    return v


def _body() -> dict:
    b = request.get_json(silent=True)
    if not isinstance(b, dict):
        return {}
    b = _clean(b)
    out = dict(b)
    for k, v in b.items():
        if k in _STR_KEYS and not isinstance(v, str):
            out[k] = str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else ""
        elif k in _STRLIST_KEYS:
            out[k] = [str(x) for x in v if isinstance(x, (str, int)) and not isinstance(x, bool)][:_MAX_LIST] \
                if isinstance(v, list) else []
        elif k in _DICTLIST_KEYS:
            out[k] = [x for x in v if isinstance(x, dict)][:_MAX_LIST] if isinstance(v, list) else []
        elif k in _DICT_KEYS:
            out[k] = {str(a): (c if isinstance(c, (str, dict, bool)) else str(c)) for a, c in v.items()} \
                if isinstance(v, dict) else {}
    if "addenda" in out and not isinstance(out["addenda"], (str, list)):
        out["addenda"] = ""
    return out


@bp.errorhandler(Exception)
def _api_error(e):
    """처리 중 예외는 HTML 대신 JSON 으로 돌려준다(HTTP 오류는 그 코드를 유지)."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        msg = {413: "보낸 내용이 너무 큽니다. 조문이나 표를 나눠서 다시 시도하세요.",
               400: "요청 형식이 올바르지 않습니다.", 404: "요청한 기능을 찾지 못했습니다.",
               405: "허용되지 않는 요청 방식입니다.", 429: "요청이 너무 잦습니다. 잠시 후 다시 시도하세요."}.get(e.code)
        return jsonify({"success": False, "error": msg or e.description or e.name}), e.code
    import traceback
    traceback.print_exc()
    return jsonify({"success": False, "error": "요청을 처리하지 못했습니다. 입력 형식을 확인하세요."}), 500


def register(app, **ctx):
    """api_server 에서 호출. ctx: ai_generate, default_model_for, semantic_search,
    user_gemini_key, vec_ready, hwpx_base_bytes, hwpx_full_border."""
    _CTX.update(ctx)
    app.register_blueprint(bp)


# ══════════════════════════════════════════════════════════════════════════
# 0. 기관 프로필(org_config.json) — 기관명·기관장·내규관리 규칙·절차·심의기준
# ══════════════════════════════════════════════════════════════════════════
_ORG_DEFAULT = {
    "org_name": "○○기관", "org_short": "기관", "head": "기관장", "deputy": "부기관장",
    "reg_word": "내규", "rules_name": "내규관리규칙", "email_domain": "example.or.kr",
    "notice_days": 20, "staff_days": 7, "stale_terms": [], "stale_words": [],
    "drafting_rules": [], "rules_summary": [], "review_criteria": [],
    "procedure": {"questions": [], "steps": []},
}


def load_org() -> dict:
    path = os.environ.get("ORG_CONFIG") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "org_config.json")
    org = dict(_ORG_DEFAULT)
    try:
        with open(path, encoding="utf-8") as f:
            org.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    except FileNotFoundError:
        print(f"[reg-agent] 기관 프로필 없음({path}) — 기본값 사용")
    except Exception as e:
        print(f"[reg-agent] 기관 프로필 읽기 실패({path}): {e} — 기본값 사용")
    return _check_org(org)


def _check_org(org: dict) -> dict:
    """프로필 형식 검증 — 잘못된 항목은 버리고 경고만 남긴다(점검·검토 API 가 500 나지 않도록)."""
    def warn(msg):
        print(f"[reg-agent] 기관 프로필 경고: {msg}")
    for k in ("org_name", "org_short", "head", "deputy", "reg_word", "rules_name", "email_domain"):
        if not isinstance(org.get(k), str) or not org.get(k):
            warn(f"{k} 가 문자열이 아니어서 기본값을 씁니다.")
            org[k] = _ORG_DEFAULT[k]
    for k in ("notice_days", "staff_days"):
        try:
            org[k] = max(0, int(org.get(k)))
        except (TypeError, ValueError):
            warn(f"{k} 가 숫자가 아니어서 기본값을 씁니다.")
            org[k] = _ORG_DEFAULT[k]
    for k in ("stale_terms", "stale_words"):
        v = org.get(k) if isinstance(org.get(k), list) else []
        good = [x for x in v if isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(y, str) and y for y in x)]
        if len(good) != len(v):
            warn(f"{k} 에서 [옛 명칭, 새 명칭] 형식이 아닌 항목 {len(v) - len(good)}개를 뺐습니다.")
        org[k] = good
    for k in ("drafting_rules", "rules_summary"):
        if not isinstance(org.get(k), list):
            org[k] = []
    org["rules_summary"] = [x for x in org["rules_summary"] if isinstance(x, (list, tuple)) and len(x) == 2]
    rc = org.get("review_criteria") if isinstance(org.get("review_criteria"), list) else []
    org["review_criteria"] = [c for c in rc if isinstance(c, dict) and c.get("id") and c.get("t")]
    if len(org["review_criteria"]) != len(rc):
        warn("review_criteria 에서 id·t 가 없는 항목을 뺐습니다.")
    pr = org.get("procedure") if isinstance(org.get("procedure"), dict) else {}
    pr["questions"] = [q for q in (pr.get("questions") or []) if isinstance(q, dict) and q.get("k") and q.get("q")]
    pr["steps"] = [st for st in (pr.get("steps") or []) if isinstance(st, dict) and st.get("id") and st.get("t")]
    org["procedure"] = pr
    return org


ORG = load_org()


def ofmt(s: str) -> str:
    """문구 속 {org}·{short}·{head}·{deputy}·{rules}·{notice_days}·{staff_days} 치환."""
    rep = {"org": ORG["org_name"], "short": ORG["org_short"], "head": ORG["head"],
           "deputy": ORG["deputy"], "rules": ORG["rules_name"], "reg": ORG["reg_word"],
           "notice_days": str(ORG["notice_days"]), "staff_days": str(ORG["staff_days"])}
    return re.sub(r"\{(\w+)\}", lambda m: rep.get(m.group(1), m.group(0)), str(s or ""))


# ══════════════════════════════════════════════════════════════════════════
# 1. 내규 본문 → 조문 구조
# ══════════════════════════════════════════════════════════════════════════
# 개정 이력 주석: <개정 2020.03.20., 2022.02.24.> · <2020.03.20.> · ＜신설 2013.6.27.＞
_ANNOT_ANGLE = re.compile(
    r"\s*[<＜〈]\s*(?:[가-힣][가-힣\s]{0,10})?\d{4}\s*[.\-]\s*\d{1,2}[^<>＜＞〈〉\n]{0,120}[>＞〉]")
# [본조신설 2020.03.20.] · [전문개정 …] · [본조제목변경 …]
_ANNOT_SQ = re.compile(
    r"\s*\[\s*(?:본조신설|전문개정|본조제목변경|제목개정|본조개정|본조이동|종전)[^\]\n]{0,80}\]"
    r"|\s*[〔\[][^\]〕\n]{0,80}(?:이동|종전|신설|개정)[^\]〕\n]{0,60}[〕\]]")   # 짝이 안 맞는 “[제24조에서 이동 …〕”도
_CHAP_LINE = re.compile(r"^제\s*(\d+)\s*(장|절|관|편)\s*(.{0,40})$")
_ART_LINE = re.compile(
    r"^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:[(（]\s*((?:[^()（）\n]|[(（][^()（）\n]{0,30}[)）]){0,60}?)\s*[)）]|(?=\s*(?:[<＜〔\[]\s*)?(?:삭제|종전))|\s*$)")
_ADDENDA_LINE = re.compile(r"^[<＜【〔\[［]?\s*부\s*칙(?![가-힣])")          # 부칙 · 부 칙2023. 3. 15. · <부칙> · 【부칙】
_APPX_LINE = re.compile(r"^[\[［〔【<＜]\s*(별표|별지)")
_HANG_CH = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_MOK_CH = "가나다라마바사아자차카타파하"

# 내규 명칭 접미어(상위법과 구분하는 데 쓴다)
_REG_SUFFIX = ("정관", "규정", "규칙", "세칙", "지침", "요령", "기준", "매뉴얼",
               "강령", "헌장", "수칙", "예규")
# 기관명·직위 변경 전 구 명칭(기관 프로필 stale_terms·stale_words)
_STALE_TERMS = [tuple(x) for x in ORG.get("stale_terms") or []]
_STALE_WORDS = [tuple(x) for x in ORG.get("stale_words") or []]   # 단어 경계로만 찾는 짧은 말
# 이름이 내규처럼 보이지만 국가 법령·정부 규정인 것(인용 관계·명칭 점검에서 외부 규범으로 본다)
_EXTERNAL_REGS = {re.sub(r"\s+", "", str(x)) for x in ORG.get("external_regs") or [] if str(x).strip()}
# 알기 쉬운 표기(법제처 「알기 쉬운 법령 정비기준」 중 내규에 자주 나오는 것)
_B = r"(?<![가-힣])"      # 앞이 한글이 아님(“공동조사”의 “동조”, “비상기구”의 “상기” 제외)
_STYLE_RULES = [
    (r"각호", "각 호"), (r"각항", "각 항"), (_B + r"동조(?=\s|제|의|에|를|$)", "같은 조"), (_B + r"동항(?=\s|제|의|에|$)", "같은 항"),
    (_B + r"동호(?=\s|의|에|$)", "같은 호"), (_B + r"동법(?![가-힣])", "같은 법"), (r"당해", "해당"), (r"익일", "다음 날"),
    (r"익월", "다음 달"), (r"금번", "이번"), (r"기타\s", "그 밖의 "), (_B + r"상기(?=\s|의|한|와|$)", "위"),
    (r"제반", "여러"), (r"감안하여", "고려하여"), (r"을 요하는", "이 필요한"),
    (r"를 요하는", "가 필요한"),
]


_DINGBAT_HANG = {0x2780 + i: 0x2460 + i for i in range(10)}     # ➀➁…➉ → ①②…⑩


def _tidy(s: str) -> str:
    """hwp 변환 잔재(괄호·따옴표 안쪽 공백, 가운뎃점 변형) 정리."""
    s = (s.replace("․", "·").replace("ㆍ", "·").replace("\u00a0", " ")
         .replace("｢", "「").replace("｣", "」").replace("ⓛ", "①"))
    s = s.translate(_DINGBAT_HANG)
    s = re.sub(r"([「『“‘(\[［〔])\s+", r"\1", s)
    s = re.sub(r"\s+([」』”’)\]］〕])", r"\1", s)
    s = re.sub(r"\s*·\s*", "·", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def strip_annot(s: str) -> str:
    s = _ANNOT_ANGLE.sub("", s)
    s = _ANNOT_SQ.sub("", s)
    return s.strip()


def art_key(no: str):
    m = re.match(r"(\d+)(?:의(\d+))?", str(no or ""))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def art_label(no: str) -> str:
    a, b = art_key(no)
    return f"제{a}조" + (f"의{b}" if b else "")


def parse_text(text: str, clean: bool = True) -> dict:
    """평문(규정 본문 또는 사용자가 쓴 초안) → 조문 구조.

    반환: {articles:[{no,title,body,chapter,deleted}], chapters:[...],
           addenda:str, appendix:str, preamble:str}
    clean=True 면 개정 이력 주석을 제거한다.
    """
    lines = [x for x in (_tidy(x) for x in (text or "").replace("\r", "").split("\n")) if x]
    # 한 줄 안에 여러 조문이 이어진 경우(평문 붙여넣기)를 위해 조문 시작 앞에서 줄을 나눈다
    # "…한다. 제9조" / "(성과급)…" 처럼 조 번호와 제목이 줄로 갈린 경우 다음 줄로 붙인다
    for i in range(len(lines) - 1):
        mt = re.search(r"(?:^|\s)(제\s*\d+\s*조(?:\s*의\s*\d+)?)$", lines[i])
        if mt and lines[i + 1].startswith(("(", "（")):
            lines[i] = lines[i][:mt.start(1)].rstrip()
            lines[i + 1] = mt.group(1) + lines[i + 1]
    split_lines = []
    for ln in lines:
        if not ln:
            continue
        pos = [m.start() for m in reg_chunks._ART_AT.finditer(ln)
               if m.start() > 0 and reg_chunks._valid_start(ln, m.start())]
        pos += [m.start() for m in re.finditer(r"(?<=[.。])\s*(?=제\s*\d+\s*조(?:의\s*\d+)?\s+삭제)", ln)]
        cut = 0
        for p in sorted(set(pos)):
            if ln[cut:p].strip():
                split_lines.append(ln[cut:p].strip())
            cut = p
        split_lines.append(ln[cut:].strip())

    arts, chapters = [], []
    pre, add, appx = [], [], []
    zone = "pre"            # pre → body → addenda → appendix
    cur = None
    chapter = ""
    for ln in split_lines:
        if zone in ("pre", "body"):
            if _ADDENDA_LINE.match(ln):
                zone = "addenda"
                add.append(ln)
                continue
            if _APPX_LINE.match(ln) and arts:
                zone = "appendix"
                appx.append(ln)
                continue
            mc = _CHAP_LINE.match(ln)
            if mc and len(ln) <= 44 and not re.search(r"[.。]$", ln):
                chapter = re.sub(r"\s+", " ", ln).strip()
                chapters.append(chapter)
                continue
            ma = _ART_LINE.match(ln)
            if ma and re.match(r"\s*(?:에\s*따라|에\s*따른|에\s*의하여|에\s*의한|의\s*규정|에서|에도|을|를|은|는|와|과|및)",
                               ln[ma.end():]):
                ma = None                 # 줄 머리에 온 인용(“제2조(…)에 따라 …”)
            if ma:
                no = ma.group(1) + (("의" + ma.group(2)) if ma.group(2) else "")
                # 번호가 제1조로 되돌아가거나 '시행일' 조가 나오면 부칙(조 형식)으로 본다
                ttl = (ma.group(3) or "").strip()
                if arts and (art_key(no) == (1, 0) and art_key(arts[-1]["no"]) >= (2, 0)
                             or ttl in ("시행일", "경과조치", "다른 내규의 개정", "적용례")):
                    zone = "addenda"
                    add.append(ln)
                    continue
                zone = "body"
                rest = ln[ma.end():].strip()
                cur = {"no": no, "title": (ma.group(3) or "").strip(), "lines": [],
                       "chapter": chapter}
                if rest:
                    cur["lines"].append(rest)
                arts.append(cur)
                continue
            if zone == "pre":
                pre.append(ln)
            elif cur is not None:
                cur["lines"].append(ln)
        elif zone == "addenda":
            if _APPX_LINE.match(ln):
                zone = "appendix"
                appx.append(ln)
            else:
                add.append(ln)
        else:
            appx.append(ln)

    out = []
    for a in arts:
        body = "\n".join(a["lines"]).strip()
        raw = body
        if clean:
            body = "\n".join(x for x in (strip_annot(l) for l in body.split("\n")) if x)
        deleted = (not body and (not a["title"] or bool(re.match(r"^[<＜〔\[(（]?\s*삭\s*제", raw)))) or bool(re.match(r"^[<＜〔\[]?\s*(?:삭제|종전)\s*(?:[<＜〔\[(（][^\n]{0,40}[>＞〕\])）]|\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?)?\s*$", body))
        out.append({"no": a["no"], "title": a["title"], "body": body,
                    "chapter": a["chapter"], "deleted": deleted})
    return {"articles": out, "chapters": chapters, "addenda": "\n".join(add),
            "appendix": "\n".join(appx), "preamble": "\n".join(pre)}


# ── 번들 내규 전체 캐시 ────────────────────────────────────────────────────
_REG_CACHE = {"key": None, "regs": None}
_REG_LOCK = threading.Lock()


def _manifest():
    return reg_chunks.load_manifest()


def _reg_raw_text(slug: str) -> str:
    base = os.path.join(reg_chunks.REG_DIR, slug)
    p = os.path.join(base, "text.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    p = os.path.join(base, "index.html")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            return reg_chunks.html_to_text(f.read())
    return ""


def all_regs() -> list:
    """[{slug,title,category,revision,articles,addenda,appendix,body}] — 매니페스트 변경 시 재구성."""
    try:
        key = os.path.getmtime(reg_chunks.MANIFEST)
    except OSError:
        key = 0
    with _REG_LOCK:
        if _REG_CACHE["regs"] is not None and _REG_CACHE["key"] == key:
            return _REG_CACHE["regs"]
        regs = []
        for m in _manifest():
            slug = m.get("slug")
            if not slug:
                continue
            raw = _reg_raw_text(slug)
            if not raw:
                continue
            p = parse_text(raw)
            regs.append({"slug": slug, "title": m.get("title") or slug.replace("_", " "),
                         "category": m.get("category", ""), "revision": m.get("revision", ""),
                         "articles": p["articles"], "chapters": p["chapters"],
                         "addenda": p["addenda"], "appendix": p["appendix"]})
        _REG_CACHE.update({"key": key, "regs": regs})
        return regs


def _nk(s: str) -> str:
    return re.sub(r"[\s·ㆍ․_]", "", s or "").lower()


def find_reg(slug: str = "", title: str = ""):
    regs = all_regs()
    for r in regs:
        if slug and r["slug"] == slug:
            return r
    t = _nk(title)
    if t:
        for r in regs:
            if _nk(r["title"]) == t:
                return r
        for r in regs:
            if t in _nk(r["title"]):
                return r
    return None


def resolve_reg(b: dict):
    """요청의 대상 내규: 등록된 내규(slug·reg) 또는 붙여넣은 원문(text). 없으면 None."""
    if (b.get("text") or "").strip() and not b.get("slug"):
        p = parse_text(b["text"])
        if not p["articles"]:
            return None
        return {"slug": "", "title": (b.get("reg") or "붙여넣은 내규").strip(), "category": "",
                "revision": "", "articles": p["articles"], "chapters": p["chapters"],
                "addenda": p["addenda"], "appendix": p["appendix"], "pasted": True}
    return find_reg(b.get("slug", ""), b.get("reg", ""))


def _reg_arts(title: str) -> dict:
    """내규명 → {조 번호 키: 조문}. 다른 내규 조문 인용을 확인할 때 쓴다."""
    r = next((x for x in all_regs() if x["title"] == title), None)
    return {art_key(a["no"]): a for a in r["articles"]} if r and r["articles"] else {}


_DELEG_RE = re.compile(r"(시행세칙|세칙)(?:으로|로|에서)\s*(?:따로\s*)?정한다")


def delegation_check(title: str, arts: list) -> list:
    """「X」에서 “…은 시행세칙으로 정한다”고 맡긴 조문 → 「X 시행세칙」이 그 조를 받았는지.
    받았다고 보는 경우: 시행세칙이 「X」·규정 제N조를 인용하거나, 시행세칙 조 제목에 위임 조 제목의 낱말이 있음.
    “이 규정 시행에 필요한 사항” 같은 일반 위임(조 제목 ‘시행세칙’ 등)은 보지 않는다."""
    if not title:
        return []
    child = next((r for r in all_regs() if _nk(r["title"]) == _nk(title + " 시행세칙")), None)
    if not child:
        return []
    live = [a for a in child["articles"] if not a["deleted"]]
    cbody = "\n".join(a["body"] for a in live)
    ctitles = " ".join(a["title"] for a in live)
    tp = r"\s*".join(map(re.escape, re.sub(r"\s+", "", title)))
    out = []
    for a in arts:
        if a.get("deleted"):
            continue
        m = _DELEG_RE.search(a.get("body", ""))
        if not m or re.search(r"시행세칙|위임|시행", a.get("title", "")) or re.search(r"이\s*(?:규정|규칙)\s*(?:의\s*)?시행에\s*필요한", a["body"]):
            continue
        n, _, g = a["no"].partition("의")          # 가지조(제32조의2)는 “제32조의2”로 인용해야 받은 것
        tail = r"\s*조\s*의\s*" + g + r"(?!\d)" if g else r"\s*조(?!\s*의)"
        cited = re.search(r"(?:「\s*" + tp + r"\s*」|규정|규칙|정관)\s*제\s*" + n + tail, cbody)
        sent = re.split(r"[.。]\s*|\n", a["body"][:m.start()])[-1]          # 위임 문장 앞부분(“장표의 기록 등에 관하여 …”)
        stop = {"관한", "관하여", "사항", "구체적인", "필요한", "세부사항", "세부", "구체적", "기준", "방법", "절차", "그밖에", "밖에"}
        stop |= {"대한", "관련", "등의", "여부"}
        tw = {_JOSA_TAIL.sub("", w) for w in re.findall(r"[가-힣]{2,}", a.get("title", ""))} - stop
        sw = {_JOSA_TAIL.sub("", w) for w in re.findall(r"[가-힣]{2,}", sent)} - stop
        cts = [a2["title"] for a2 in live]
        # 받은 것으로 보는 조 제목: 위임 조 제목 낱말 둘 이상, 세 글자 이상 낱말, 또는 두 글자 낱말이 여러 조 제목에 걸침(“장표”)
        # — “점검” 한 낱말이 엉뚱한 조 하나에 걸린 것만으로는 받았다고 보지 않는다
        tw = {w for w in tw if len(w) >= 2}
        topical = any(sum(w in ct for w in tw) >= 2 for ct in cts) or any(
            (len(w) >= 3 and any(w in ct for ct in cts)) or sum(w in ct for ct in cts) >= 2
            for w in tw | sw if len(w) >= 2)                   # 조사를 떼고 남은 한 글자(“관”)는 보지 않는다
        out.append({"no": a["no"], "title": a.get("title", ""), "child": child["title"], "phrase": m.group(0),
                    "covered": bool(cited or topical)})
    return out


def _reg_names() -> dict:
    """정규화 내규명 → 정식 명칭."""
    return {_nk(r["title"]): r["title"] for r in all_regs()}


# ══════════════════════════════════════════════════════════════════════════
# 2. 인용 탐지
# ══════════════════════════════════════════════════════════════════════════
_REF = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?(?:\s*제\s*(\d+)\s*호)?"
    r"(?:\s*(부터|내지|및|또는|ㆍ|·|,|와|과)\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*(까지)?))?")
_QUOTED_NAME = re.compile(r"「\s*([^「」]{2,60}?)\s*」")
_EXT_BEFORE = re.compile(
    r"(?:「[^」]{1,60}」|(?:같은|동|이|해당)\s*법(?:\s*시행령|\s*시행규칙)?|"
    r"\(\s*이하[^)]{0,30}\)[”\"’']?|"          # “… 규칙(이하 “규칙”이라 한다)” 제44조
    r"(?:(?<![방불편문용])법|(?<![명수발지])령|시행령|시행규칙|(?<![운경반수])영|규칙|규정|정관|지침|세칙|요령|기준|매뉴얼|훈령|고시|예규|조례|협약)\s*)\s*$")
# ↑ “방법·운영·명령” 같은 일반 낱말 뒤의 “제N조”는 외부 인용으로 보지 않는다
_SELF_BEFORE = re.compile(
    r"(?:이|본)\s*(?:규정|규칙|지침|정관|요령|기준|세칙|매뉴얼|강령)\s*$")


def _ref_is_external(text: str, pos: int) -> bool:
    """pos 위치의 '제N조'가 다른 법령·내규 인용인지(바로 앞 문맥 기준)."""
    before = text[max(0, pos - 40):pos]
    if _SELF_BEFORE.search(before):
        return False
    return bool(_EXT_BEFORE.search(before))


def internal_refs(text: str):
    """본문 속 같은 내규 내부 인용 → [(조 번호 문자열, 원문 표기, 위치)].

    「개인정보 보호법」 제15조, 제17조 및 제22조처럼 외부 인용에 이어진 나열은 외부로 본다."""
    out = []
    prev_ext_end = -1
    for m in _REF.finditer(text or ""):
        ext = _ref_is_external(text, m.start())
        if not ext and prev_ext_end >= 0 and re.fullmatch(r"(?:\s*[(（][^)）]{0,24}[)）])?(?:의\s*[가-힣]{1,12})?[\s,및또는ㆍ·와과]*", text[prev_ext_end:m.start()]):
            ext = True
        if ext:
            prev_ext_end = m.end()
            continue
        prev_ext_end = -1
        a = m.group(1) + (("의" + m.group(2)) if m.group(2) else "")
        if m.group(1).strip("0") == "":
            continue                      # “제00조” 같은 자리표시
        out.append((a, m.group(0), m.start()))
        if m.group(6):
            b = int(m.group(6))
            if m.group(5) in ("부터", "내지") and not m.group(7):
                for k in range(int(m.group(1)) + 1, min(b, int(m.group(1)) + 60) + 1):
                    out.append((str(k), m.group(0), m.start()))
            else:
                out.append((m.group(6) + (("의" + m.group(7)) if m.group(7) else ""),
                            m.group(0), m.start()))
    return out


def retarget_refs(text: str, moves: dict):
    """같은 내규 내부 인용의 조 번호를 이동표(moves: {"7": "8", "7의2": "8"})대로 바꾼다.

    다른 법령·내규 인용(「…」 제N조, 같은 법 제N조 등)은 건드리지 않는다. 반환: (새 본문, 바꾼 수)"""
    if not moves or not text:
        return text, 0
    reps = []
    prev_ext_end = -1
    for m in _REF.finditer(text):
        ext = _ref_is_external(text, m.start())
        if not ext and prev_ext_end >= 0 and re.fullmatch(r"(?:\s*[(（][^)）]{0,24}[)）])?[\s,및또는ㆍ·와과]*", text[prev_ext_end:m.start()]):
            ext = True
        if ext:
            prev_ext_end = m.end()
            continue
        prev_ext_end = -1
        for gm, gs in ((1, 2), (6, 7)):
            if not m.group(gm):
                continue
            no = m.group(gm) + (("의" + m.group(gs)) if m.group(gs) else "")
            if no not in moves:
                continue
            new = moves[no]
            k = art_key(new)
            jo = text.index("조", m.end(gm))
            end = m.end(gs) if m.group(gs) else jo + 1
            reps.append((m.start(gm), end, f"{k[0]}조" + (f"의{k[1]}" if k[1] else "")))
    out = text
    for a, e, t in sorted(reps, reverse=True):
        out = out[:a] + t + out[e:]
    return out, len(reps)


def _snip(text: str, pos: int, span: int = 60) -> str:
    s = max(0, pos - span)
    e = min(len(text), pos + span)
    return ("…" if s else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def external_reg_refs(text: str, title: str):
    """본문에서 「title」 제N조 / title 제N조 인용 → [(조 번호, 표기, 위치)]. 조 번호가 없으면 ''."""
    out = []
    t = re.escape(title).replace(r"\ ", r"\s*")
    pat = re.compile(r"「\s*" + t + r"\s*」|(?<![가-힣])" + t + r"(?![가-힣])")
    for m in pat.finditer(text or ""):
        tail = text[m.end():m.end() + 24]
        mr = re.match(r"\s*(?:\(\s*이하[^)]*\)\s*)?제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", tail)
        no = (mr.group(1) + (("의" + mr.group(2)) if mr.group(2) else "")) if mr else ""
        out.append((no, text[m.start():m.end() + (mr.end() if mr else 0)], m.start()))
    return out


# ══════════════════════════════════════════════════════════════════════════
# 3. 점검(lint)
# ══════════════════════════════════════════════════════════════════════════
def _bat(word: str) -> int:
    """끝 글자 받침: 0 없음, 1 있음, 2 ㄹ(‘로’를 씀). 숫자·영문·한자는 읽는 소리로(JS raBat 과 같다)."""
    t = re.sub(r"[”\"’'\]」』>〕］】]+$", "", (word or "").strip())
    while t.endswith(")") and t.rfind("(") > 0:
        t = t[:t.rfind("(")].rstrip()                 # “원장(부원장을 포함한다)” → “원장”
    c = t[-1:] or " "
    if "\u4e00" <= c <= "\u9fff":
        return 1
    if "가" <= c <= "힣":
        j = (ord(c) - 0xAC00) % 28
        return 0 if not j else 2 if j == 8 else 1
    if c.isdigit():
        return {"0": 1, "1": 2, "3": 1, "6": 1, "7": 2, "8": 2}.get(c, 0)   # 영·일·삼·육·칠·팔
    if c.lower() in "lr":
        return 2 if c.lower() == "l" else 0
    return 1 if c.lower() in "mn" else 0


def _josa(word: str, pair=("은", "는")) -> str:
    if not (word or "").strip():
        return pair[0]
    return pair[0] if _bat(word) else pair[1]


def _kind_of(title: str) -> str:
    """규정명 → '규정'·'규칙'·'지침' 등 자기 지칭어."""
    t = (title or "").strip()
    for suf in ("시행세칙", "정관", "규정", "규칙", "세칙", "지침", "요령", "기준", "매뉴얼", "강령"):
        if t.endswith(suf):
            return suf
    return "규정"


def _lref(key: str) -> str:
    """점검 메시지의 근거 조항 — 기관 프로필 lint_refs 에 있을 때만 “(「내규관리규칙」 제N조)”로 붙인다."""
    ref = (ORG.get("lint_refs") or {}).get(key) if isinstance(ORG.get("lint_refs"), dict) else ""
    return f"(「{ORG['rules_name']}」 {ref})" if ref else ""


# 용어 정의 — 정의 조항의 “X”란 …, 본문의 (이하 “X”라 한다)
_DEF_LINE = re.compile(r"(?:^|\n)\s*(?:[①-⑳]\s*)?(?:\d{1,2}\.\s*)?[“\"‘']([^”\"’'\n(]{1,30})[”\"’']\s*(?:\([^)]{0,30}\)\s*)?(?:(?:이)?란|(?:이)?라\s*함은)\s")
_ABBR_DEF = re.compile(r"\(\s*이하\s*(?:이\s*조에서\s*|이\s*장에서\s*)?[“\"‘']([^”\"’']{1,20})[”\"’']\s*(?:이)?라\s*한다\s*\)")
_TERM_GENERIC = {"위원회", "위원장", "심의회", "협의회", "위원", "기관", "규정", "규칙", "지침", "세칙", "요령", "기준", "법", "영"}


def _term_uses(text: str, term: str) -> int:
    t = re.sub(r"\s+", "", term)
    if len(t) >= 3:
        return re.sub(r"\s+", "", text).count(t)
    return len(re.findall(r"(?<![가-힣])" + re.escape(t), re.sub(r"\s+", " ", text)))


def term_check(arts: list, cap: int = 8) -> list:
    """정의한 용어·약칭의 쓰임 점검 → [(level, no, msg)].
    중복 정의, 정의만 하고 쓰지 않는 용어, 약칭을 정의하기 전에 먼저 쓰는 경우."""
    live = [a for a in arts if not a.get("deleted")]
    defs = {}
    for i, a in enumerate(live):
        body = a.get("body", "")
        for m in _DEF_LINE.finditer(body):
            t = re.sub(r"\s+", " ", m.group(1)).strip()
            if m.group(0).rstrip().endswith("함은"):          # 원문 오기 “발간등록번호라” 라 함은 → 발간등록번호
                t = re.sub(r"(?<=[가-힣]{2})(?:이|라)$", "", t)
            defs.setdefault(t, []).append((i, "def", m))
        for m in _ABBR_DEF.finditer(body):
            defs.setdefault(re.sub(r"\s+", " ", m.group(1)).strip(), []).append((i, "abbr", m))
    out = []
    for term, occ in defs.items():
        if not term or re.search(r"[○△□◇]", term):
            continue
        i, kind, m = occ[0]
        no = live[i]["no"]
        if len(occ) > 1:
            where = [art_label(n_) for n_ in sorted({live[o[0]]["no"] for o in occ}, key=art_key)]
            out.append(("warn", live[occ[1][0]]["no"],
                        f"“{term}”{_josa(term, ('을', '를'))} 두 번 정의합니다({', '.join(where)}). 한 곳에서만 정의하세요."))
        body = live[i].get("body", "")
        if kind == "def":                 # 정의 줄(“X”란 … 말한다) 자체는 쓰임으로 세지 않는다
            end = body.find("\n", m.end())
            rest = body[:m.start()] + body[(len(body) if end < 0 else end):]
            others = "\n".join(x.get("body", "") for j, x in enumerate(live) if j != i)
        else:
            rest = body[m.end():]
            others = "\n".join(x.get("body", "") for x in live[i + 1:])
        if (len(re.sub(r"\s+", "", term)) >= 2 and term not in (ORG["org_short"], ORG["org_name"])
                and _term_uses(rest + "\n" + others, term) == 0):
            what = "정의한 용어" if kind == "def" else "약칭으로 정한"
            out.append(("info", no, f"{art_label(no)}에서 {what} “{term}”{_josa(term, ('이', '가'))} 다른 곳에서 쓰이지 않습니다. 빼거나 본문에서 그 용어로 쓰세요."))
        if kind == "abbr" and len(re.sub(r"\s+", "", term)) >= 3 and term not in _TERM_GENERIC:
            tb = r"\s*".join(map(re.escape, re.sub(r"\s+", "", term)))
            fp = re.search(r"([가-힣A-Za-z]+)\s*" + tb + r"\s*$", body[:m.start()])   # 정식 명칭 “치유농업사 자격시험”의 앞말
            fp = fp.group(1) if fp else ""

            def used(t):                               # 정식 명칭 안의 낱말(“치유농업사 자격시험을”)은 약칭 쓰임이 아니다
                return any(not (fp and t[:u.start()].rstrip().endswith(fp))
                           for u in re.finditer(r"(?<![가-힣])" + tb, t))
            pre = [x for x in live[:i]                 # 더 긴 낱말의 일부(“실증단지위탁자”의 “위탁자”)는 쓰임이 아니다
                   if used(x.get("body", ""))]
            if pre:
                out.append(("info", pre[0]["no"],
                            f"약칭 “{term}”{_josa(term, ('을', '를'))} 정의한 {art_label(no)}보다 앞선 {art_label(pre[0]['no'])}에서 먼저 씁니다. "
                            "처음 나오는 곳에서 정의하세요."))
    return out[:cap]


def lint_articles(arts: list, addenda: str = "", appendix: str = "", title: str = "",
                  full: bool = True, draft_base=None) -> list:
    """draft_base: 초안 점검일 때 — None 이 아니면 자리표시(○○) 점검을 하고, 원 내규 조문({조 번호: 본문})과 같은 조는 뺀다"""
    """조문 목록 점검 → [{level, code, no, msg, fix?}]. level: error|warn|info"""
    issues = []
    regnames = _reg_names()

    def add(level, code, no, msg, fix="", **ex):
        issues.append({"level": level, "code": code, "no": no, "msg": msg, "fix": fix, **ex})

    names = {}
    for a in arts:
        k = art_key(a["no"])
        names.setdefault(k, []).append(a)
    # (1) 조 번호: 중복·순서·결번
    prev = None
    for a in arts:
        k = art_key(a["no"])
        if len(names.get(k, [])) > 1 and names[k][0] is a:
            add("error", "dup", a["no"], f"{art_label(a['no'])}가 {len(names[k])}번 나옵니다.")
        if prev and k <= prev:
            add("error", "order", a["no"], f"{art_label(a['no'])}가 앞 조문보다 번호가 작거나 같습니다(순서 확인).")
        if prev and k[1] == 0 and k[0] > prev[0] + 1:
            miss = f"제{prev[0] + 1}조" + (f"~제{k[0] - 1}조" if k[0] - 1 > prev[0] + 1 else "")
            add("warn", "gap", a["no"],
                f"{miss}가 없습니다. 삭제한 조는 번호를 남기고 '삭제'로 표시합니다{_lref('deleted')}.")
        prev = k
    if arts and art_key(arts[0]["no"]) != (1, 0):
        add("warn", "first", arts[0]["no"], "첫 조문이 제1조가 아닙니다.")
    have = {art_key(a["no"]) for a in arts}
    gone = {art_key(a["no"]) for a in arts if a.get("deleted")}

    for a in arts:
        no, body = a["no"], a.get("body", "")
        lbl = art_label(no)
        if a.get("deleted"):
            continue
        # (2) 조 제목
        if not a.get("title"):
            add("warn", "title", no, f"{lbl}에 조문 제목이 없습니다. 각 조에는 내용을 요약한 제목을 붙입니다{_lref('title')}.")
        if not body.strip():
            add("error", "empty", no, f"{lbl}의 본문이 비어 있습니다.")
            continue
        # (3) 항·호·목 순서
        # 줄 머리 또는 문장 끝(“… 한다. ②”) 뒤의 항 기호 — 한 줄로 붙여 넣은 조문도 센다
        hangs = [c for c in re.findall(r"(?:^|\n|[.。]\s+)\s*([" + _HANG_CH + "])", body)]
        if hangs:
            exp = _HANG_CH[:len(hangs)]
            if "".join(hangs) != exp:
                add("error", "hang", no, f"{lbl}의 항 번호 순서가 맞지 않습니다({' '.join(hangs)}).")
            if len(hangs) == 1:
                add("info", "hang1", no, f"{lbl}에 항이 ①만 있습니다. 항이 하나면 번호를 붙이지 않습니다.")
        for seg in re.split(r"(?:^|\n)\s*[" + _HANG_CH + "]", body):
            hos = [int(x) for x in re.findall(r"(?:^|\n)\s*(\d{1,2})\.(?!\d)", seg)]   # “1.「병역법」”처럼 붙여 쓴 호도 센다
            if hos and hos != list(range(1, len(hos) + 1)):
                # 한 줄에 이어 쓴 호(“…같다. 1. 사업개요 2. …”)까지 세면 차례가 맞으면 오류로 보지 않는다
                hos2 = [int(x) for x in re.findall(r"(?:^|\n|[.:：다]\s+|\s/\s|\s)(\d{1,2})\.(?!\d)\s*(?=\S)", seg)]
                if hos2 == list(range(1, len(hos2) + 1)):
                    hos = []
            if hos and hos != list(range(1, len(hos) + 1)):
                add("warn", "ho", no, f"{lbl}의 호 번호가 1부터 차례대로가 아닙니다({', '.join(map(str, hos))}).")
            for hseg in re.split(r"(?:^|\n)\s*\d{1,2}\.(?!\d)", seg):          # 목은 호마다 “가”부터 다시
                moks = re.findall(r"(?:^|\n)\s*([가-하])\.\s", hseg)
                if moks:
                    expm = "".join(_MOK_CH[:len(moks)])
                    if "".join(moks) != expm and len(moks) <= len(_MOK_CH):
                        add("warn", "mok", no, f"{lbl}의 목 기호 순서가 맞지 않습니다({' '.join(moks)}).")
                        break
        # (4) 내부 인용 대상
        seen = set()
        for rno, raw, pos in internal_refs(body):
            if art_key(rno) not in have and rno not in seen:
                seen.add(rno)
                add("error", "ref", no, f"{lbl}에서 인용한 {art_label(rno)}가 이 내규에 없습니다: “{raw.strip()}”", term=raw.strip())
            elif art_key(rno) in gone and rno not in seen:
                seen.add(rno)
                add("error", "ref", no, f"{lbl}에서 삭제된 {art_label(rno)}를 인용합니다: “{raw.strip()}”", term=raw.strip())
        # (5) 「내규명」 확인
        for m in _QUOTED_NAME.finditer(body):
            nm = m.group(1).strip()
            ours = _nk(nm) in regnames            # 「임직원 행동강령」·「소송 및 법률자문 규칙」도 우리 내규면 조문 인용을 본다
            if not ours and ("법" in nm or nm.endswith(("령", "조례"))):
                continue
            if not ours and not nm.endswith(_REG_SUFFIX):
                continue
            if ours and _nk(nm) != _nk(title):
                # (5-1) 다른 내규의 조문 인용: 「여비규정」 제30조 → 그 내규에 제30조가 있는지·삭제됐는지
                mr = re.match(r"\s*(?:\(\s*이하[^)]{0,30}\)\s*)?제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", body[m.end():m.end() + 40])
                if mr:
                    rno = mr.group(1) + (("의" + mr.group(2)) if mr.group(2) else "")
                    tgt = _reg_arts(regnames[_nk(nm)])
                    a2 = tgt.get(art_key(rno)) if tgt else None
                    raw = body[m.start():m.end() + mr.end()].strip()
                    if tgt and a2 is None:
                        add("error", "xref", no, f"{lbl}에서 인용한 「{nm}」 {art_label(rno)}가 그 {ORG['reg_word']}에 없습니다: “{raw}”",
                            term=raw, reg=regnames[_nk(nm)])
                    elif a2 is not None and a2["deleted"]:
                        add("error", "xref", no, f"{lbl}에서 인용한 「{nm}」 {art_label(rno)}는 삭제된 조문입니다: “{raw}”",
                            term=raw, reg=regnames[_nk(nm)])
                continue
            if _nk(nm) in regnames or _nk(nm) == _nk(title) or nm == "정관" or re.sub(r"\s+", "", nm) in _EXTERNAL_REGS:
                continue
            ownp = [t for t in [ORG["org_short"], ORG["org_name"]] + [o for o, _ in _STALE_TERMS + _STALE_WORDS] if t]
            if re.sub(r"^(?:" + "|".join(map(re.escape, ownp)) + r")\s*", "", nm) == "정관":
                continue                  # 「농진원 정관」 등 우리 기관 정관(인용 관계와 같은 기준)
            near = [regnames[k] for k in difflib.get_close_matches(_nk(nm), list(regnames), n=3, cutoff=0.8)
                    if k != _nk(title)][:2]               # 자기 자신을 “유사 내규”로 권하지 않는다
            own = any(t and t in nm for t in [ORG["org_short"], ORG["org_name"]] + [o for o, _ in _STALE_TERMS + _STALE_WORDS])
            if not near and not own:
                continue                  # 정부 규정·지침 등 외부 규범으로 본다
            add("warn", "regname", no,
                f"{lbl}의 「{nm}」{_josa(nm)} 현행 내규 목록에 없습니다. 명칭 변경·폐지 여부를 확인하세요."
                + (f" (유사: {', '.join('「'+x+'」' for x in near)})" if near else ""),
                term=nm, **({"new": near[0]} if len(near) == 1 else {"cands": near}))
        # (6) 구 명칭
        # 법령 조문 제목 인용(“농촌진흥법 부칙<…> 제2조(실용화재단 직원의 임용등에 관한 특례)”)은 법령의 글이라 고칠 수 없다
        sbody = re.sub(r"(?:법|령|규칙)\s*」?\s*(?:부\s*칙\s*(?:<[^>]{0,40}>)?\s*)?제\s*\d+\s*조(?:\s*의\s*\d+)?\s*\([^)]{0,60}\)", " ", body)
        for old, new in _STALE_TERMS:
            if old in sbody:
                add("warn", "stale", no, f"{lbl}에 구 명칭 “{old}”{_josa(old, ('이', '가'))} 있습니다.", f"“{old}” → “{new}”", term=old, new=new)
        for old, new in _STALE_WORDS:
            if re.search(r"(?<![가-힣])" + re.escape(old) + r"(?:은|는|이|가|의|에|에서|과|와|을|를)?(?![가-힣])", sbody):
                add("warn", "stale", no, f"{lbl}에 구 명칭 “{old}”{_josa(old, ('이', '가'))} 있습니다.", f"“{old}” → “{new}”", term=old, new=new, word=True)
        # (7) 알기 쉬운 표기
        if full:
            for pat, rep in _STYLE_RULES:
                mm = re.search(pat, body)
                if mm:
                    add("info", "style", no, f"{lbl}: “{mm.group(0).strip()}” → “{rep.strip()}” 표기를 권장합니다.",
                        f"“{mm.group(0).strip()}” → “{rep.strip()}”")
            if re.search(r"제\s+\d+\s+조", body):
                add("info", "space", no, f"{lbl}: “제 N 조”는 붙여 “제N조”로 씁니다.")
            # (7-1) 법령 약칭·잘못 쓴 이름 — 낫표 안에는 정식 명칭을 쓴다(「청탁금지법」 → 「부정청탁 및 금품등 수수의 금지에 관한 법률」)
            for nm in dict.fromkeys(re.sub(r"\s+", " ", m_.group(1)).strip() for m_ in _QUOTED_NAME.finditer(body)):
                full_ = law_official(nm) if _LAW_NAME_OK.search(nm) else nm
                if _nk(full_) != _nk(nm):
                    add("info", "lawname", no, f"{lbl}: 「{nm}」{_josa(nm)} 법령의 정식 명칭이 아닙니다. 「{full_}」{_ro(full_)} 씁니다.",
                        f"「{nm}」 → 「{full_}」", term=nm, new=full_)
            # (7-2) 공문서 표기(행정업무운영편람): 날짜·기간·시각·금액·쌍점·낫표 등 — 조문에서는 표기 제안(info)으로, 규칙당 1건
            seen_rule = set()
            for fnd in notation.check(body, "law"):
                if fnd["rule"] in seen_rule or len(seen_rule) >= 3:
                    continue
                seen_rule.add(fnd["rule"])
                fix = "" if fnd["suggest"].startswith(("예)", "…")) else f"“{fnd['match']}” → “{fnd['suggest']}”"
                add("info", "notation", no, f"{lbl}: {fnd['label']}, “{fnd['match']}”. {fnd['message']}", fix)

    ph = [a["no"] for a in arts if draft_base is not None and not a.get("deleted")
          and re.search(r"[○△□]{2}", (a.get("title") or "") + (a.get("body") or ""))
          and draft_base.get(a["no"]) != a.get("body")]   # 등록된 내규의 예시(“○○ 연구소”)는 그대로 둔다
    if ph or (draft_base == {} and re.search(r"[○△□]{2}", addenda or "")):         # 초안 골격의 자리표시(○○)가 남아 있으면 확정 전에 채워야 한다
        where = ", ".join(art_label(n_) for n_ in ph[:6]) + (" 등" if len(ph) > 6 else "") or "부칙"
        add("warn", "ph", ph[0] if ph else "", f"채우지 않은 자리표시(○○·△△)가 남아 있습니다: {where}. 실제 내용으로 바꾸세요.")
    if full:
        # (8) 약칭 정의 후 정식 명칭 재사용
        joined = "\n".join(a.get("body", "") for a in arts)
        for m in re.finditer(r"([가-힣A-Za-z]{2,30})\s*\(\s*이하\s*[“\"']([^”\"']{1,20})[”\"']\s*(?:이)?라\s*한다\s*\)", joined):
            full_nm, abbr = m.group(1), m.group(2)
            pc, pc1 = joined[:m.start(1)].rstrip()[-1:], joined[max(0, m.start(1) - 1):m.start(1)]
            if pc1 in ("”", "\"", "’") or pc in ("·", ",", "，", "ㆍ"):
                continue                  # 이름 일부만 잡힘(“정”보관책임자, 단체표준·…·국제표준, …, 가감점평정)
            if len(full_nm) < 4 or full_nm in abbr or abbr in full_nm and len(abbr) >= len(full_nm):
                continue                  # 앞 낱말 하나만 잡힌 경우(“위원(이하 ‘외부위원’)”)·조각은 판단하지 않는다
            later = re.sub(r"「[^」]*」", " ", joined[m.end():]).replace(abbr, " ")
            if full_nm != abbr and re.search(r"(?<![가-힣])" + re.escape(full_nm), later):
                add("info", "abbr", "", f"“{full_nm}”{_josa(full_nm, ('을', '를'))} “{abbr}”{_ro(abbr)} 줄여 정의한 뒤에도 정식 명칭을 다시 씁니다. 약칭으로 통일을 검토하세요.")
        # (8-2) 용어 정의 — 중복 정의·쓰지 않는 용어·정의 전 사용
        for lv, tno, msg in term_check(arts):
            add(lv, "term", tno, msg)
        # (8-3) 시행세칙 위임 — 이 내규가 “시행세칙으로 정한다”고 맡긴 사항을 시행세칙이 받았는지
        for dg in delegation_check(title, arts):
            if not dg["covered"]:
                add("info", "deleg", dg["no"],
                    f"{art_label(dg['no'])}({dg['title']})에서 시행세칙으로 위임했지만 「{dg['child']}」에서 이 조를 받은 조문이 보이지 않습니다. 위임 사항이 정해졌는지 확인하세요.",
                    term=dg["phrase"], reg=dg["child"])
        # (9) 부칙·시행일
        if not (addenda or "").strip():
            add("warn", "addenda", "", f"부칙이 없습니다. 시행일을 정하는 부칙을 두세요{_lref('addenda')}.")
        elif not re.search(r"시행", addenda):
            add("warn", "addenda", "", "부칙에 시행일 규정이 보이지 않습니다.")
        # (10) 별표·별지 인용 ↔ 존재
        body_all = joined
        def own_cites(kind_re):
            """본문의 별표·별지 인용 가운데 다른 법령·내규의 것(「…」·법·시행령 뒤)은 뺀다."""
            out = set()
            for mm in re.finditer(kind_re, body_all):
                pre = body_all[max(0, mm.start() - 18):mm.start()]
                if re.search(r"」|법\s*$|법\s+|시행령|시행규칙|훈령|고시|예규", pre):
                    continue
                out.add(mm.group(1))
            return out
        _OPEN = r"[\[［〔❲【<〈＜(（]\s*"                  # “(별지 제1호 서식)”도 서식 머리로 본다
        cited = own_cites(r"별표\s*(\d+)")
        exist = set(re.findall(_OPEN + r"별표\s*(\d+)", appendix or ""))
        for c in sorted(cited - exist, key=int):
            if appendix or exist:
                add("warn", "appx", "", f"본문에서 [별표 {c}]를 인용하지만 별표가 없습니다.")
        cited_f = own_cites(r"별지\s*제?\s*(\d+)\s*호")
        exist_f = set(re.findall(_OPEN + r"별지\s*제?\s*(\d+)\s*호", appendix or ""))
        for c in sorted(cited_f - exist_f, key=int):
            if appendix or exist_f:
                add("warn", "appx", "", f"본문에서 [별지 제{c}호 서식]을 인용하지만 서식이 없습니다.")
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda x: (order.get(x["level"], 3), art_key(x["no"])))
    return issues


# ══════════════════════════════════════════════════════════════════════════
# 4. 유사 규정 검색
# ══════════════════════════════════════════════════════════════════════════
_JOSA_TAIL = re.compile(
    r"(으로서|으로써|에서는|에게서|으로|에서|에게|까지|부터|이나|이며|이고|하는|하고|하여|한다|"
    r"에|의|을|를|은|는|이|가|와|과|도|만|로|및|등)$")
_STOP = {"관한", "대한", "위한", "따른", "있는", "없는", "경우", "사항", "필요한", "규정", "규칙",
         "지침", "내규", "제정", "개정", "만들", "새로", "운영", "관련", "정함", "목적", "기관",
         ORG["org_short"], ORG["org_name"], "그리고", "또는", "하기", "위해", "통해",
         "정하는", "정한", "하는", "있도록", "지침을", "규정을", "만들어야", "만들기"}


# 일상어 → 내규 용어(검색 보강). 원문에 있는 말만 더한다. 기관 프로필 "synonyms": {"일상어": ["내규 용어", …]}로 더하거나 바꾼다
_SYN_BASE = {
    "출장비": ["여비"], "월급": ["보수"], "급여": ["보수"], "급료": ["보수"], "임금": ["보수"],
    "야근": ["시간외근무"], "초과근무": ["시간외근무"], "잔업": ["시간외근무"], "특근": ["휴일근무"], "주말근무": ["휴일근무"],
    "연차": ["연차유급휴가"], "연차휴가": ["연차유급휴가"], "연가": ["연차유급휴가"], "반차": ["반일"],
    "갑질": ["괴롭힘"], "해외출장": ["국외출장"], "숙직": ["당직"], "업추비": ["업무추진비"], "법카": ["법인카드"],
    "보너스": ["성과급"], "인센티브": ["성과급"], "성과상여금": ["성과급"], "식대": ["식비"], "교통비": ["운임"],
    "기간제": ["계약직원"], "비정규직": ["계약직원"], "퇴직금": ["퇴직급여"], "겸업": ["겸직"], "부업": ["겸직"],
    "외부강연": ["외부강의"], "강의료": ["외부강의"], "복지포인트": ["선택적복지"], "인사이동": ["전보"], "육휴": ["육아휴직"],
    "경조사비": ["경조금", "경조사"], "축의금": ["경조금", "경조사"], "조의금": ["경조금", "경조사"], "재택": ["재택근무"],
}
_SYN = dict(_SYN_BASE)
_SYN.update({str(k): [str(x) for x in v if str(x).strip()] for k, v in
             (ORG["synonyms"].items() if isinstance(ORG.get("synonyms"), dict) else []) if isinstance(v, list)})


def _syn(word: str) -> list:
    """일상어의 내규 용어(원문에 나오는 것만). “출장비” → [“여비”]"""
    if word not in _SYN:
        return []
    corpus = _corpus_text()
    return [s for s in _SYN[word] if s != word and re.sub(r"\s+", "", s) in corpus]


def _strip_josa(w: str) -> str:
    """끝 조사를 뗀다. 다만 “연차휴가”·“성과평가”처럼 끝 글자가 조사꼴인 낱말은 원문에 그 꼴로 나오면 그대로 둔다."""
    w2 = _JOSA_TAIL.sub("", w) if len(w) > 2 else w
    if w2 != w and re.fullmatch(r"[가-힣]+", w):
        corpus = _corpus_text()
        n_full, n_stem = corpus.count(w), corpus.count(w2)
        if n_full and n_full * 2 >= n_stem:
            return w
    return w2


def _tokens(q: str) -> list:
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", q or ""):
        w2 = _strip_josa(w)
        w2 = w2 if len(w2) >= 2 else w
        if w2 in _STOP or w in _STOP:
            continue
        if w2 not in out:
            out.append(w2)
    return out[:14]


def similar_search(query: str, exclude: str = "", limit: int = 8) -> dict:
    toks = _tokens(query)
    toks += [s for t in list(toks) for s in _syn(t) if s not in toks]     # “출장비” → 여비
    regs = all_regs()
    docs = []
    for r in regs:
        if exclude and (r["slug"] == exclude or _nk(r["title"]) == _nk(exclude)):
            continue
        for a in r["articles"]:
            if a["deleted"] or reg_chunks.is_boilerplate(a["title"], a["body"]):
                continue
            docs.append((r, a, (a["title"] + " " + a["body"]).lower()))
    n = max(1, len(docs))
    import math
    df = {t: sum(1 for d in docs if t.lower() in d[2]) for t in toks}
    idf = {t: math.log(1 + n / (1 + df[t])) for t in toks}
    scored = {}
    for r, a, txt in docs:
        s = 0.0
        for t in toks:
            tl = t.lower()
            if tl in txt:
                s += idf[t] * (1 + min(txt.count(tl), 4) * 0.25)
                if tl in a["title"].lower():
                    s += idf[t] * 1.2
            if tl in r["title"].lower():
                s += idf[t] * 0.9
        if s > 0:
            scored[(r["slug"], a["no"])] = [s, r, a, "kw"]
    # 의미 검색 결합(키·색인이 있을 때)
    sem_used = False
    try:
        key = _CTX["user_gemini_key"]() if _CTX.get("user_gemini_key") else ""
        if key and _CTX.get("vec_ready") and _CTX["vec_ready"]():
            sem = _CTX["semantic_search"](query, key, top_k=40)
            sem_used = True
            mx = max([s for s, *_ in scored.values()] or [1.0])
            bys = {r["slug"]: r for r in regs}
            for h in sem:
                if h.get("score", 0) < 0.5:
                    continue
                r = bys.get(h["slug"])
                if not r or (exclude and r["slug"] == exclude):
                    continue
                a = next((x for x in r["articles"] if x["no"] == str(h["no"])), None)
                if not a:
                    continue
                bonus = (h["score"] - 0.45) * 2.2 * mx
                k = (r["slug"], a["no"])
                if k in scored:
                    scored[k][0] += bonus
                    scored[k][3] = "kw+sem"
                else:
                    scored[k] = [bonus, r, a, "sem"]
    except Exception as e:
        print(f"[reg-agent] 의미 검색 생략: {e}")
    flat = sorted(scored.values(), key=lambda x: -x[0])
    groups = {}
    for s, r, a, src in flat:
        g = groups.setdefault(r["slug"], {"slug": r["slug"], "title": r["title"],
                                          "category": r["category"], "revision": r["revision"],
                                          "score": 0.0, "articles": [],
                                          "n_articles": len(r["articles"]),
                                          "chapters": r["chapters"][:12]})
        if len(g["articles"]) < 4:
            g["articles"].append({"no": a["no"], "title": a["title"], "body": a["body"][:900],
                                  "score": round(s, 3), "src": src})
        g["score"] += s if len(g["articles"]) <= 1 else s * 0.35
    out = sorted(groups.values(), key=lambda g: -g["score"])[:limit]
    for g in out:
        g["score"] = round(g["score"], 2)
        # 목차(조 제목) — 체계 참고용
        r = next(x for x in regs if x["slug"] == g["slug"])
        g["toc"] = [f"{art_label(a['no'])}({a['title']})" if a["title"] else f"{art_label(a['no'])} 삭제"
                    for a in r["articles"]][:60]
    return {"tokens": toks, "semantic": sem_used, "regs": out}


# ══════════════════════════════════════════════════════════════════════════
# 5. AI 프롬프트
# ══════════════════════════════════════════════════════════════════════════
# 공문서 표기법 — 행정안전부 「행정업무운영편람」 기준. 제·개정 이유·주요 내용·검토의견에 적용
_GONGMUN_RULES = [
    "날짜는 “2026. 10. 6.”처럼 온점 뒤 한 칸, 월·일의 0은 쓰지 않고 끝에도 온점. 기간은 물결표를 붙여 “10. 6.∼10. 26.”",
    "법령·내규명은 낫표 「」로 쓰고, 쌍점은 앞말에 붙이고 뒤에 한 칸(“시행일: …”)",
    "제·개정 이유와 주요 내용은 개조식 명사형(“…하려는 것임”, “…을 정함”)으로 씀(조문 본문은 종전대로 “…한다” 체)",
    "줄표(— – ―)·작은따옴표 강조·선언형 문장은 쓰지 않고, 외래어는 행정용어로(파일럿→시범, 리스크→위험 요인, 벤치마크→준용)",
    "금액은 숫자와 한글을 함께(“금30,000원(금삼만원)”), 시각은 24시각제(“09:00”)",
]


def _rules() -> str:
    lines = [ofmt(x) for x in ORG.get("drafting_rules") or []]
    return (f"[{ORG['org_short']} 내규 작성 기준 — 「{ORG['rules_name']}」]\n" + "\n".join("- " + x for x in lines)
            + "\n[공문서 표기법 — 행정업무운영편람]\n" + "\n".join("- " + x for x in _GONGMUN_RULES))


def _json_from(text: str) -> dict:
    """AI 응답 → JSON 객체. 코드 울타리·앞뒤 설명을 걷어 내고 첫 객체만 읽는다. 객체가 아니면 ValueError."""
    clean = re.sub(r"```(?:json)?|```", "", text or "").strip()
    try:
        d = json.loads(clean)
    except Exception:
        k = clean.find("{")
        if k < 0:
            raise ValueError("JSON 객체가 없습니다")
        d, _ = json.JSONDecoder().raw_decode(clean[k:])     # 객체 뒤 덧붙인 설명은 버린다
    if not isinstance(d, dict):
        raise ValueError("JSON 객체가 아닙니다")
    return d


def _art_no(v) -> str:
    """AI 가 준 조 번호 → '15' · '15의2'. “제5조 제1항”·“15-2” 같은 표기도 받는다. 못 읽으면 ''."""
    m = re.match(r"\s*제?\s*(\d+)\s*조?\s*(?:(?:의|-|_)\s*(\d+))?", str(v or ""))
    return (m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")) if m else ""


def _strs(v, limit=40) -> list:
    """문자열 목록으로(문자열 하나면 한 줄짜리 목록)."""
    if isinstance(v, str):
        v = [v] if v.strip() else []
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:limit]


def _norm_reason(r) -> dict:
    if isinstance(r, str):
        return {"purpose": r.strip(), "main": []}
    r = r if isinstance(r, dict) else {}
    return {"purpose": str(r.get("purpose") or "").strip() if isinstance(r.get("purpose"), (str, int)) else "",
            "main": _strs(r.get("main"))}


def _ai_conf(body: dict):
    provider = (body.get("provider") or os.environ.get("SCENARIO_AI_PROVIDER", "gemini")).lower()
    api_key = (body.get("api_key") or os.environ.get(f"{provider.upper()}_API_KEY", "")
               or (os.environ.get("OPENAI_API_KEY", "") if provider in ("gpt", "openai") else "")).strip()
    model = (body.get("model") or os.environ.get("SCENARIO_AI_MODEL", "")).strip()
    if provider == "openai":
        provider = "gpt"
    return provider, api_key, model


def _ref_block(refs: list, cap: int = 7000) -> str:
    out, n = [], 0
    for r in refs or []:
        org = f"[다른 기관: {r['org']}] " if r.get("org") else ""     # 알리오에서 고른 다른 기관 사규(참고만, 그대로 옮기지 않음)
        t = f"- {org}「{r.get('reg', '')}」 {art_label(r.get('no', ''))}({r.get('title', '')}) {r.get('body', '')}"
        t = t[:1400]
        if n + len(t) > cap:
            break
        out.append(t)
        n += len(t)
    return "\n".join(out)


def _deleg_block(dels: list, cap: int = 6000) -> str:
    out, n = [], 0
    for d in dels or []:
        t = f"- 「{d.get('law', '')}」 {d.get('art', '')} {d.get('text', '')}".strip()
        t = t[:2000]
        if n + len(t) > cap:
            break
        out.append(t)
        n += len(t)
    return "\n".join(out)


def _clean_addenda(v) -> list:
    """AI 부칙 → 줄 목록. 머리말 “부칙”은 문서에서 따로 붙이므로 뗀다."""
    items = v if isinstance(v, list) else [v] if isinstance(v, str) else []
    out = []
    for x in items:
        t = re.sub(r"^\s*부\s*칙\s*(?:[<＜〈(（][^>＞〉)）]{0,30}[>＞〉)）])?\s*", "", str(x or "")).strip()
        if t:
            out.append(t)
    return out


def _del_ref(d: dict) -> str:
    """위임 조항 표기: 「법령」 제N조(제목은 뺀다)."""
    art = re.sub(r"\s*\([^)]*\)\s*$", "", str(d.get("art") or "")).strip()
    return f"「{d.get('law', '')}」 {art}".strip()


# “직원은 1주 전까지 신청”처럼 끝이 이 말(…하다)이면 “…하여야 한다.”로 맺는다. “… 받은 경우”처럼 다른 말로 끝나면 맺지 않는다
_ACT_NOUNS = {"신청", "승인", "제출", "보고", "기록", "통보", "통지", "결정", "지정", "관리", "운영", "작성", "보관", "심사", "검토",
              "허가", "지급", "처리", "실시", "시행", "평가", "점검", "확인", "공개", "공고", "협의", "의결", "등록", "신고", "교육",
              "감독", "조사", "요청", "위촉", "임명", "선정", "수립", "이행", "준수", "유지", "정산", "반납", "납부", "환수", "게시",
              "설치", "구성", "개최", "소집", "집행", "부담", "지원", "추진", "보완", "제공", "배정", "배치", "회신", "결재"}


def template_enact(b: dict) -> dict:
    """AI 없이 쓰는 표준 조문 골격."""
    title = (b.get("title") or "○○ 운영규칙").strip()
    kind = _kind_of(title)
    if kind == "시행세칙":
        kind = "세칙"                                         # “이 세칙은 …” 이 표준 자기 지칭
    eun = _josa(kind)
    purpose = (b.get("purpose") or "○○").strip().rstrip(".")
    # “안전관리에 관한 사항을 정함” → “안전관리” (뒤에 “에 필요한 사항”을 붙이므로 겹치지 않게)
    purpose = re.sub(r"\s*(?:에\s*관한|에\s*필요한)\s*사항(?:\s*을\s*정함|\s*을\s*정한다)?$|\s*을\s*정함$", "", purpose) or "○○"
    dels = b.get("delegations") or []
    basis = ""
    if dels:
        d0 = dels[0]
        basis = _del_ref(d0) + "에 따라 "
    head_ga = f"{ORG['head']}{_josa(ORG['head'], ('이', '가'))}"
    parent = re.sub(r"\s*시행세칙$", "", title) if title.endswith("시행세칙") else ""
    if parent and parent != title:                            # 시행세칙: 모 규정 위임 사항을 정하는 표준 문형
        names = _reg_names()                                  # “보안업무 시행세칙” → 실제 모 규정명(「보안업무규정」)
        parent = next((names[_nk(x)] for x in (parent, parent + "규정", parent + " 규정", parent + "규칙", parent + " 규칙")
                       if _nk(x) in names), parent if parent.endswith(_REG_SUFFIX) else "○○규정")
        purpose_body = f"이 세칙은 「{parent}」에서 위임된 사항과 그 시행에 필요한 사항을 규정함을 목적으로 한다."
    elif basis:                                               # 상위법 위임: “…에서 위임된 사항과 그 시행에 필요한 사항”
        purpose_body = f"이 {kind}{eun} {basis[:-len('에 따라 ')]}에서 위임된 사항과 그 시행에 필요한 사항을 정함을 목적으로 한다."
    else:                                                     # 약칭은 조문에서 쓰지 않으므로 “(이하 …)” 정의를 두지 않는다
        purpose_body = f"이 {kind}{eun} {ORG['org_name']}의 {purpose}에 필요한 사항을 정함을 목적으로 한다."
    arts = [
        {"no": "1", "title": "목적", "body": purpose_body},
        {"no": "2", "title": "정의",
         "body": f"이 {kind}에서 사용하는 용어의 뜻은 다음과 같다.\n1. “○○”이란 ○○을 말한다.\n2. “△△”이란 △△을 말한다."},
        {"no": "3", "title": "적용범위",
         "body": f"○○에 관하여 다른 내규에 특별한 규정이 있는 경우를 제외하고는 이 {kind}에서 정하는 바에 따른다."},
    ]
    n = 4
    for line in [x.strip(" -·•\t") for x in (b.get("contents") or "").split("\n") if x.strip()]:
        head = re.split(r"[:：]", line, maxsplit=1)
        t = head[0].strip()[:20] if len(head) > 1 else (line if len(line) <= 20 else re.sub(r"\s.*$", "", line)[:14])
        desc = (head[1].strip() if len(head) > 1 else line).rstrip(".")
        if re.search(r"(다|한다|된다|있다|없다)$", desc):          # 이미 완결된 문장
            body = desc + "."
        elif re.match(r"^[가-힣]{2,}(?:은|는|이|가)\s+\S", desc) and desc.rsplit(None, 1)[-1] in _ACT_NOUNS:
            body = f"{desc}하여야 한다."                          # “직원은 1주 전까지 신청” → “… 신청하여야 한다.”
        else:                                                 # “출장 신청” 같은 명사구 → 서술어를 갖춘 조문
            desc = re.sub(r"(?<=[가-힣])(?:을|를)\s+([가-힣]{2,6})$", r"의 \1", desc)   # “운영책임자를 지정” → “운영책임자의 지정”
            body = (f"{desc}{_josa(desc, ('은', '는'))} 다음 각 호의 기준에 따라 {head_ga} 정한다."
                    f"\n1. ○○\n2. ○○")
        arts.append({"no": str(n), "title": t or "○○", "body": body})
        n += 1
    arts.append({"no": str(n), "title": "세부사항",
                 "body": f"이 {kind}에서 정한 사항 외에 {purpose}에 필요한 세부사항은 {head_ga} 따로 정한다."})
    eff = (b.get("effective") or "").strip() or "발령한 날"
    addenda = f"이 {kind}{eun} {eff}부터 시행한다."
    return {"title": title, "articles": arts, "addenda": [addenda],
            "reason": {"purpose": f"{purpose}에 필요한 사항을 정하기 위하여 「{title}」{_josa(title, ('을', '를'))} 제정하려는 것임.",
                       "main": [f"{a['title']}에 관한 사항을 정함(안 {art_label(a['no'])})" for a in arts[3:-1]]
                       or [f"{purpose}에 필요한 사항을 정함"]},
            "template": True}


def ai_enact(b: dict):
    provider, key, model = _ai_conf(b)
    if not key and provider != "ollama":
        return template_enact(b), "AI 키가 없어 표준 조문 골격으로 작성했습니다. [✦ AI 설정]에서 키를 넣으면 AI 초안을 만들 수 있습니다."
    mdl = model or _CTX["default_model_for"](provider, key)
    title = (b.get("title") or "").strip()
    system = f"""당신은 {ORG['org_name']}({ORG['org_short']}) {ORG['reg_word']} 입안 전문가입니다.
주어진 제정 목적·주요 내용·상위법 위임 조항·유사 내규를 바탕으로 새 내규의 조문 체계와 표준 조문 초안을 작성하세요.
{_rules()}

반드시 아래 JSON만 반환(설명·코드블록 금지):
{{
  "title": "내규명",
  "articles": [{{"chapter": "제1장 총칙(장을 두지 않으면 빈 문자열)", "no": "1", "title": "목적", "body": "조문 본문(항은 줄바꿈 후 ①, 호는 줄바꿈 후 1.)"}}],
  "addenda": ["제1조(시행일) 이 규칙은 … 시행한다.", "제2조(경과조치) …(필요할 때만. 시행일만 있으면 “이 규칙은 발령한 날부터 시행한다.” 한 문장)"],
  "reason": {{"purpose": "제정 이유(2~3문장, ~하려는 것임 체)", "main": ["주요내용 1(안 제N조)", "주요내용 2(안 제N조)"]}},
  "notes": ["입안 시 확인할 점(상위법 저촉 여부, 다른 내규와 중복, 위임 근거 등)"]
}}
- 목적 → 정의 → 적용범위 → 본칙(절차·기준·위원회·의무 등) → 위임·세부사항 순으로.
- 상위법 위임 조항이 있으면 제1조(목적)에 근거를 밝히고 위임 범위를 넘지 않게 작성.
- 정해지지 않은 숫자·기간·금액은 “○○” 자리표시로 남긴다. 사실을 지어내지 말 것."""
    user = (f"내규명: {title or '(제안해 주세요)'}\n종류: {b.get('category', '')}\n"
            f"소관부서: {b.get('dept', '')}\n시행일: {b.get('effective', '') or '공포(발령)한 날'}\n"
            f"제정 목적: {b.get('purpose', '')}\n주요 내용:\n{b.get('contents', '')}\n\n"
            f"[상위법 위임 조항]\n{_deleg_block(b.get('delegations')) or '(없음)'}\n\n"
            f"[참고할 유사 내규 조문(“다른 기관”은 알리오 공시 사규 — 구조·표현만 참고하고 기관명·직위는 우리 기관에 맞게)]\n{_ref_block(b.get('refs')) or '(없음)'}")
    text, err = _CTX["ai_generate"](provider, key, mdl, system, user,
                                    max_tokens=6000, temperature=0.2, json_mode=True)

    def fallback(why):                    # AI 가 실패해도 빈손으로 돌려보내지 않고 표준 골격을 준다
        return template_enact(b), f"{why} 표준 조문 골격으로 작성했습니다. 다시 시도하면 AI 초안을 받을 수 있습니다."
    if err:
        return fallback(f"AI 오류({err})로")
    try:
        d = _json_from(text)
    except Exception:
        return fallback("AI 응답을 해석하지 못해")
    arts, seen, dup = [], set(), []
    for a in d.get("articles") if isinstance(d.get("articles"), list) else []:
        if not isinstance(a, dict):
            continue
        no = _art_no(a.get("no")) or str(len(arts) + 1)
        if no in seen:
            dup.append(art_label(no))
        seen.add(no)
        arts.append({"chapter": str(a.get("chapter") or "").strip(), "no": no,
                     "title": str(a.get("title") or "").strip(),
                     "body": str(a.get("body") or "").strip()})
    if not arts:
        return fallback("AI가 조문을 만들지 못해")
    d["articles"] = arts
    d["addenda"] = _clean_addenda(d.get("addenda"))
    d["title"] = d.get("title") if isinstance(d.get("title"), str) and d.get("title").strip() else title
    d["reason"] = _norm_reason(d.get("reason"))
    d["notes"] = _strs(d.get("notes"))
    d["model"] = f"{provider}:{mdl}"
    return d, (f"AI 초안에 같은 조 번호가 겹칩니다({', '.join(dict.fromkeys(dup))}). 조 번호를 확인하세요." if dup else "")


def ai_amend(b: dict):
    provider, key, model = _ai_conf(b)
    if not key and provider != "ollama":
        return None, "AI 키가 없습니다. [✦ AI 설정]에서 키를 넣거나, 개정안을 직접 입력하세요."
    mdl = model or _CTX["default_model_for"](provider, key)
    reg = resolve_reg(b)
    reg_title = reg["title"] if reg else (b.get("reg") or "")
    toc = ""
    if reg:
        toc = "\n".join(f"{art_label(a['no'])}({a['title'] or '삭제'})" for a in reg["articles"])[:3500]
    targets = b.get("targets") or []
    tgt = "\n\n".join(f"{art_label(t.get('no', ''))}({t.get('title', '')})\n{t.get('body', '')}" for t in targets)[:9000]
    system = f"""당신은 {ORG['org_name']}({ORG['org_short']}) {ORG['reg_word']} 개정 전문가입니다.
개정 의도에 맞춰 대상 조문의 수정안을 작성하세요. 필요하면 조문 신설·삭제도 제안하세요.
{_rules()}

반드시 아래 JSON만 반환(설명·코드블록 금지):
{{
  "changes": [{{"type": "modify|insert|delete", "no": "5 또는 5의2", "title": "조 제목", "body": "개정 후 조문 본문 전체(삭제는 빈 문자열)", "why": "이 조문을 바꾸는 이유(1문장)"}}],
  "reason": {{"purpose": "개정 이유(2~3문장, ~하려는 것임 체)", "main": ["주요내용(안 제N조)"]}},
  "addenda": ["제1조(시행일) 이 규정은 … 시행한다.", "제2조(경과조치) …(필요할 때만. 시행일만 있으면 한 문장)"],
  "notes": ["함께 고쳐야 할 수 있는 다른 조문·별표·서식, 상위법 저촉 여부 등"]
}}
- modify 는 기존 조문 번호 그대로, 본문은 개정 후 전체 문장으로.
- 기존 문구는 의도와 무관하면 그대로 둔다(불필요한 표현 수정 금지).
- 새 조는 바로 앞 조 번호에 '의2' 형태로(예: 제7조 다음 → 7의2). 기존 번호를 당기거나 밀지 않는다.
- 정해지지 않은 숫자·기간·금액은 “○○”로 남긴다."""
    user = (f"대상 내규: 「{reg_title}」\n개정 의도: {b.get('intent', '')}\n"
            f"시행일: {b.get('effective', '') or '발령한 날'}\n\n"
            f"[현행 조문 목차]\n{toc or '(없음)'}\n\n[개정 대상 현행 조문]\n{tgt or '(지정 없음 — 목차를 보고 필요한 조문을 고르세요)'}\n\n"
            f"[상위법·참고 자료]\n{_deleg_block(b.get('delegations')) or ''}\n{_ref_block(b.get('refs')) or ''}")
    text, err = _CTX["ai_generate"](provider, key, mdl, system, user,
                                    max_tokens=5000, temperature=0.2, json_mode=True)
    if err:
        return None, f"AI 오류: {err}"
    try:
        d = _json_from(text)
    except Exception:
        return None, "AI 응답을 해석하지 못했습니다. 다시 시도해 주세요."
    ch, idx, dropped, dup = [], {}, 0, []
    for c in d.get("changes") if isinstance(d.get("changes"), list) else []:
        if not isinstance(c, dict):
            dropped += 1
            continue
        t = str(c.get("type") or "modify").lower()
        if t not in ("modify", "insert", "delete"):
            t = "modify"
        no = _art_no(c.get("no"))
        if not no:
            dropped += 1                    # 조 번호 없는 제안(부칙 등)은 뺀다 — 아래 notice 로 알린다
            continue
        if no in idx:                       # 같은 조를 두 번 고치면 뒤의 제안으로 하나만 남긴다
            dup.append(art_label(no))
            ch.pop(idx[no])
            idx = {x["no"]: i for i, x in enumerate(ch)}
        old = None
        if reg and reg.get("articles"):
            old = next((a for a in reg["articles"] if a["no"] == no), None)
        ch.append({"type": t, "no": no, "title": str(c.get("title") or (old or {}).get("title", "")).strip(),
                   "body": str(c.get("body") or "").strip(), "why": str(c.get("why") or "").strip(),
                   "old_title": (old or {}).get("title", ""), "old_body": (old or {}).get("body", "")})
        idx[no] = len(ch) - 1
    if not ch:
        return None, "AI가 수정안을 만들지 못했습니다. 개정 의도를 구체적으로 적어 다시 시도해 주세요."
    d["changes"] = ch
    d["addenda"] = _clean_addenda(d.get("addenda"))
    d["reason"] = _norm_reason(d.get("reason"))
    d["notes"] = _strs(d.get("notes"))
    d["model"] = f"{provider}:{mdl}"
    notice = []
    if dropped:
        notice.append(f"조 번호를 알 수 없는 제안 {dropped}건은 뺐습니다")
    if dup:
        notice.append(f"같은 조를 두 번 고친 제안({', '.join(dict.fromkeys(dup))})은 마지막 것만 남겼습니다")
    return d, ("AI 수정안 확인: " + ", ".join(notice) + ".") if notice else ""


# ══════════════════════════════════════════════════════════════════════════
# 6. 라우트
# ══════════════════════════════════════════════════════════════════════════
@bp.route("/api/regagent/catalog")
def ra_catalog():
    regs = all_regs()
    return jsonify({"success": True, "count": len(regs),
                    "regs": [{"slug": r["slug"], "title": r["title"], "category": r["category"],
                              "revision": r["revision"], "n": len(r["articles"]),
                              "live": sum(1 for a in r["articles"] if not a["deleted"]),
                              "rev_date": rev_date(r.get("revision", ""))} for r in regs]})


@bp.route("/api/regagent/regs/search")
def ra_regs_search():
    """내규 목록 검색: 조 제목·본문에 낱말이 나오는 내규 → [{slug, hits, first:{no,title,snip}}] (많이 나온 순)."""
    q = re.sub(r"\s+", " ", (request.args.get("q") or "")).strip()[:40]
    if len(q.replace(" ", "")) < 2:
        return jsonify({"success": True, "q": q, "regs": []})
    pat = re.compile(r"\s*".join(map(re.escape, q.replace(" ", ""))))      # 띄어쓰기는 무시
    out = []
    for r in all_regs():
        hits, arts = 0, []
        for a in r["articles"]:
            if a["deleted"]:
                continue
            n = len(pat.findall(a["title"])) + len(pat.findall(a["body"]))
            if n:
                hits += n
                m = pat.search(a["body"])
                arts.append({"no": a["no"], "title": a["title"], "n": n,
                             "snip": _snip(a["body"], m.start(), 40) if m else a["title"]})
        if hits:
            arts.sort(key=lambda x: -x["n"])
            out.append({"slug": r["slug"], "hits": hits, "first": arts[0], "arts": arts[:5], "n_arts": len(arts)})
    out.sort(key=lambda x: -x["hits"])
    return jsonify({"success": True, "q": q, "regs": out[:200]})


@bp.route("/api/regagent/articles")
def ra_articles():
    r = find_reg(request.args.get("slug", ""), request.args.get("title", ""))
    if not r:
        return jsonify({"success": False, "error": "내규를 찾을 수 없습니다."}), 404
    return jsonify({"success": True, "slug": r["slug"], "title": r["title"],
                    "category": r["category"], "revision": r["revision"],
                    "chapters": r["chapters"], "articles": r["articles"],
                    "addenda_tail": r["addenda"][-1500:], "has_appendix": bool(r["appendix"])})


@bp.route("/api/regagent/similar", methods=["POST"])
def ra_similar():
    b = _body()
    q = (b.get("query") or "").strip()
    if len(q) < 2:
        return jsonify({"success": False, "error": "검색할 내용을 입력하세요."}), 400
    lim = _clamp_int(b.get("limit"), 1, 15, 8)
    res = similar_search(q[:600], b.get("exclude") or "", lim)
    return jsonify({"success": True, **res})


_ART_NO = re.compile(r"[1-9]\d{0,3}(?:의[1-9]\d?)?")


@bp.route("/api/regagent/impact", methods=["POST"])
def ra_impact():
    """개정 조문 → 영향 범위. body: {slug, nos:[...], moves:{"5":"6"}, rename:"새 내규명"}"""
    b = _body()
    r = resolve_reg(b)
    if not r:
        return jsonify({"success": False, "error": "내규를 찾을 수 없습니다."}), 404
    nos = [re.sub(r"[^0-9의]", "", str(x)) for x in (b.get("nos") or [])]
    nos = [x for x in nos if _ART_NO.fullmatch(x)]
    moves = {}
    for k, v in (b.get("moves") or {}).items():          # 조 번호 형식이 아닌 이동표 항목은 버린다(“제0조” 제안 방지)
        k2, v2 = re.sub(r"[^0-9의]", "", str(k)), re.sub(r"[^0-9의]", "", str(v))
        if _ART_NO.fullmatch(k2) and _ART_NO.fullmatch(v2) and k2 != v2:
            moves[k2] = v2
    targets = set(art_key(x) for x in nos) | set(art_key(x) for x in moves)
    # (a) 같은 내규 내부 인용
    inner, seen_pos = [], set()
    for a in r["articles"]:
        if a["deleted"]:
            continue
        for rno, raw, pos in internal_refs(a["body"]):
            if art_key(rno) in targets and art_key(rno) != art_key(a["no"]):
                if (a["no"], pos) in seen_pos:
                    continue          # “제9조 및 제15조”처럼 한 표기에 대상이 여럿이면 한 번만
                seen_pos.add((a["no"], pos))
                sug = ""
                if rno in moves:
                    sug = f"{art_label(rno)} → {art_label(moves[rno])}"
                inner.append({"no": a["no"], "title": a["title"], "cites": rno,
                              "text": raw.strip(), "snippet": _snip(a["body"], pos), "suggest": sug})
    # (b) 별표·별지 관련 조문 표기
    appx = []
    for m in re.finditer(r"[\[［]\s*(별표|별지)[^\]］]{0,20}[\]］][^\n]{0,80}", r["appendix"] or ""):
        seg = m.group(0)
        for mm in re.finditer(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", seg):
            no = mm.group(1) + (("의" + mm.group(2)) if mm.group(2) else "")
            if art_key(no) in targets:
                appx.append({"form": re.sub(r"\s+", " ", seg)[:80], "cites": no})
    # (c) 다른 내규에서 이 내규 인용
    outer, name_only = [], []
    for o in all_regs():
        if o["slug"] == r["slug"]:
            continue
        hits_art, hits_name = [], []
        for a in o["articles"]:
            if a["deleted"]:
                continue
            for no, raw, pos in external_reg_refs(a["body"], r["title"]):
                rec = {"no": a["no"], "title": a["title"], "cites": no, "text": raw.strip(),
                       "snippet": _snip(a["body"], pos)}
                if no and art_key(no) in targets:
                    if no in moves:
                        rec["suggest"] = f"「{r['title']}」 {art_label(no)} → {art_label(moves[no])}"
                    hits_art.append(rec)
                else:
                    hits_name.append(rec)
        if hits_art:
            outer.append({"slug": o["slug"], "reg": o["title"], "hits": hits_art})
        if hits_name:
            name_only.append({"slug": o["slug"], "reg": o["title"], "hits": hits_name[:6],
                              "count": len(hits_name)})
    # 하위 내규(시행세칙 등)
    base = re.sub(r"\s*시행세칙$", "", r["title"])
    children = [o["title"] for o in all_regs()
                if o["slug"] != r["slug"] and _nk(o["title"]).startswith(_nk(base)) and o["title"] != r["title"]]
    # (d) 조 번호 이동 시 같은 내규 인용 정정안(수정안에 바로 반영할 수 있는 본문)
    fixes = []
    if moves:
        for a in r["articles"]:
            if a["deleted"]:
                continue
            nb, n = retarget_refs(a["body"], moves)
            if n:
                fixes.append({"no": a["no"], "title": a["title"], "old_body": a["body"],
                              "new_body": nb, "count": n})
    return jsonify({"success": True, "reg": r["title"], "targets": nos, "inner": inner, "fixes": fixes,
                    "appendix": appx, "outer": outer, "mentions": name_only,
                    "children": children,
                    "summary": {"inner": len(inner), "appendix": len(appx),
                                "outer": sum(len(x["hits"]) for x in outer),
                                "mention_regs": len(name_only)}})


_LAW_ALIAS = [   # 마지막이 정식 명칭. 내규에 흔한 잘못 쓴 이름(“공공기관 운영에 관한 법률”)도 같은 묶음에 둔다
    ("청탁금지법", "김영란법", "부정청탁 및 금품등 수수의 금지에 관한 법률"),
    ("공운법", "공공기관운영법", "공공기관 운영에 관한 법률", "공공기관의 운영에 관한 법률"),
    ("부패방지권익위법", "부패방지법", "부패방지 및 국민권익위원회 설치와 운영에 관한 법률",
     "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률"),
    ("남녀고용평등법", "남녀고용평등과 일·가정 양립 지원에 관한 법률"),
    ("퇴직급여법", "근로자퇴직급여보장법", "근로자퇴직급여 보장법"),
    ("산안법", "산업안전보건법"),
    ("중대재해처벌법", "중대재해 처벌 등에 관한 법률"),
    ("국가계약법", "국가를 당사자로 하는 계약에 관한 법률"),
    ("이해충돌방지법", "공직자의 이해충돌 방지법"),
    ("정보공개법", "공공기관의 정보공개에 관한 법률"),
    ("개인정보법", "개인정보 보호법"),
    ("공익신고자법", "공익신고자 보호법"),
    ("근기법", "근로기준법"),
]


def law_official(name: str) -> str:
    """법령 약칭·잘못 쓴 이름 → 정식 명칭(시행령·시행규칙 꼬리는 살린다). “청탁금지법 시행령” → “부정청탁 … 법률 시행령”"""
    nm = re.sub(r"\s+", " ", name or "").strip()
    m = re.match(r"^(.*?)\s*(시행령|시행규칙)$", nm)
    base, tail = (m.group(1), " " + m.group(2)) if m and m.group(1) else (nm, "")
    return _law_aliases(base)[-1] + tail


def _law_aliases(name: str) -> list:
    """법령 약칭·정식 명칭을 함께 찾는다(띄어쓰기 무시)."""
    k = _nk(name)
    for grp in _LAW_ALIAS:
        if any(_nk(x) == k for x in grp):
            return list(grp)
    return [name]


def _removed_terms(old_t: str, new_t: str) -> list:
    """개정 전 문구에만 있는 용어(조사 뗀 낱말). 개정 후 글에 그대로 남아 있으면 뺀다."""
    nk = re.sub(r"\s+", "", new_t)
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", old_t):
        w2 = _JOSA_TAIL.sub("", w)
        if len(w2) < 2 or w2 in _STOP or w2 in out or w2 in nk or re.fullmatch(r"제?\d+[조항호]?", w2):
            continue
        out.append(w2)
    return out[:12]


@bp.route("/api/regagent/upper", methods=["POST"])
def ra_upper():
    """상위법 개정 → 영향받는 내규 조문. body: {law, arts:[...], old, new}"""
    b = _body()
    law = re.sub(r"[「」]", "", (b.get("law") or "")).strip()
    if len(law) < 2:
        return jsonify({"success": False, "error": "상위법 명칭을 입력하세요."}), 400
    if len(law) > 100:
        return jsonify({"success": False, "error": "상위법 명칭이 너무 깁니다(100자 이내)."}), 400
    arts = [re.sub(r"[^0-9의]", "", str(x)) for x in (b.get("arts") or [])]
    arts = [x for x in arts if x]
    tset = {art_key(x) for x in arts}
    old_t, new_t = (b.get("old") or "")[:20000], (b.get("new") or "")[:20000]
    removed = _removed_terms(old_t, new_t) if old_t else []
    base = re.sub(r"\s*(시행령|시행규칙)$", "", law)
    names = _law_aliases(base)
    lp = "|".join(r"\s*".join(map(re.escape, re.sub(r"\s+", "", n))) for n in names)   # 띄어쓰기는 어디든 무시
    pat = re.compile(r"「\s*((?:" + lp + r")(?:\s*시행령|\s*시행규칙)?)\s*」|(?<![가-힣])(" + lp + r")(?![가-힣])")
    law_keys = {_nk(n) for n in names} | {_nk(n + law[len(base):]) for n in names}
    cands = []
    jun_keys = {(x["slug"], x["no"]): x["arts"] for x in law_users(law)["jun"]}
    for o in all_regs():
        cites_law = any(pat.search(a["body"]) for a in o["articles"] if not a["deleted"])
        for a in o["articles"]:
            if a["deleted"]:
                continue
            body = a["body"]
            ms = list(pat.finditer(body))
            term_hits = [w for w in removed if w in body] if cites_law else []   # 이 법을 인용하는 내규에서만 용어를 본다
            if not ms and not term_hits:
                continue
            spec, cites, snip = [], [], ""
            for m in ms:
                nm = (m.group(1) or m.group(2) or "").strip()
                tail = body[m.end():m.end() + 40]
                mr = re.match(r"\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?", tail)
                lbl = nm
                if mr:
                    no = mr.group(1) + (("의" + mr.group(2)) if mr.group(2) else "")
                    lbl = f"{nm} {art_label(no)}" + (f"제{mr.group(3)}항" if mr.group(3) else "")
                    exact_law = (_nk(nm) in law_keys) or (not re.search(r"시행(령|규칙)$", law) and not re.search(r"시행(령|규칙)", nm))
                    if tset and art_key(no) in tset and exact_law:
                        spec.append(lbl)
                if lbl not in cites:
                    cites.append(lbl)
                if not snip:
                    snip = _snip(body, m.start())
            # "같은 법 제N조" — 직전에 이 법을 인용한 경우
            if ms and tset:
                for m in re.finditer(r"같은\s*법\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", body):
                    no = m.group(1) + (("의" + m.group(2)) if m.group(2) else "")
                    if art_key(no) in tset and m.start() > ms[0].start():
                        spec.append(f"같은 법 {art_label(no)}")
            jn = jun_keys.get((o["slug"], a["no"]))
            jn_hit = jn is not None and (not tset or not jn or any(   # 준용 조문이 개정 조문에 걸릴 때만
                art_key(x + ("의" + y if y else "")) in tset for x, y in re.findall(r"제(\d+)조(?:의(\d+))?", "".join(jn))))
            if jn_hit:                             # 이 법(의 개정 조문)을 준용하는 조문은 법 개정이 그대로 옮겨 온다
                spec.append("준용" + (f" {', '.join(jn)}" if jn else ""))
            score = len(spec) * 10 + len(term_hits) * 4 + (2 if ms else 0)
            if tset and not spec and not term_hits:
                score = 1
            if not snip and term_hits:
                p = body.find(term_hits[0])
                snip = _snip(body, p)
            cands.append({"slug": o["slug"], "reg": o["title"], "no": a["no"], "title": a["title"],
                          "body": body[:1200], "cites": cites[:6], "specific": spec[:4],
                          "terms": term_hits, "snippet": snip, "score": score})
    cands.sort(key=lambda x: (-x["score"], x["reg"], art_key(x["no"])))
    regs = {}
    for c in cands:
        regs.setdefault(c["reg"], 0)
        regs[c["reg"]] += 1
    return jsonify({"success": True, "law": law, "arts": arts, "removed_terms": removed,
                    "count": len(cands), "reg_count": len(regs),
                    "high": sum(1 for c in cands if c["specific"] or c["terms"]),
                    "candidates": cands[:120], "truncated": len(cands) > 120})


@bp.route("/api/regagent/lint", methods=["POST"])
def ra_lint():
    """조문 점검. body: {text, title} | {slug} | {all:true}"""
    b = _body()
    if b.get("all"):
        t0 = time.time()
        rows, tot = [], {"error": 0, "warn": 0, "info": 0}
        for r in all_regs():
            iss = [i for i in lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"], full=False)
                   if i["code"] in ("ref", "xref", "regname", "stale", "dup", "order")]
            if not iss:
                continue
            for i in iss:
                tot[i["level"]] = tot.get(i["level"], 0) + 1
            rows.append({"slug": r["slug"], "reg": r["title"], "count": len(iss),
                         "errors": sum(1 for i in iss if i["level"] == "error"),
                         "issues": iss[:40]})
        rows.sort(key=lambda x: (-x["errors"], -x["count"]))
        return jsonify({"success": True, "mode": "all", "regs": rows, "total": tot,
                        "checked": len(all_regs()), "elapsed": round(time.time() - t0, 2)})
    if (b.get("slug") or b.get("reg")) and not b.get("text"):
        r = find_reg(b.get("slug", ""), b.get("reg", ""))
        if not r:
            return jsonify({"success": False, "error": "내규를 찾을 수 없습니다."}), 404
        iss = lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"])
        return jsonify({"success": True, "mode": "reg", "reg": r["title"], "slug": r["slug"], "issues": iss})
    text = b.get("text") or ""
    if not text.strip():
        return jsonify({"success": False, "error": "점검할 조문이 없습니다."}), 400
    p = parse_text(text, clean=False)
    add = b.get("addenda")
    add = add if isinstance(add, str) else p["addenda"]
    base = find_reg(b.get("base_slug", ""), "") if b.get("base_slug") else None
    # 개정안 본문에는 별표·서식이 따라오지 않으므로 비교할 때는 원 내규의 것을 쓴다(“해결됨” 오표시 방지)
    iss = lint_articles(p["articles"], add, p["appendix"] or (base["appendix"] if base else ""), b.get("title", ""),
                        draft_base={a["no"]: a["body"] for a in base["articles"]} if base else {})
    if not p["articles"]:
        iss.insert(0, {"level": "error", "code": "noart", "no": "",
                       "msg": "“제1조(목적)” 형식의 조문을 찾지 못했습니다.", "fix": ""})
    out = {"success": True, "mode": "text", "issues": iss, "articles": len(p["articles"])}
    if base:                              # 개정 전후 비교: 이번 개정으로 새로 생긴 문제·해결된 문제
        key = lambda i: (i["code"], re.sub(r"\s+", "", i["msg"]))
        old = lint_articles(base["articles"], base["addenda"], base["appendix"], base["title"])
        ok = {key(i) for i in old}
        nk_ = {key(i) for i in iss}
        for i in iss:
            i["is_new"] = key(i) not in ok     # (“new”는 구 명칭 문제의 바꿀 말)
        out["fixed"] = [i for i in old if key(i) not in nk_ and i["level"] != "info"][:40]
        out["base"] = base["title"]
    return jsonify(out)


@bp.route("/api/regagent/parse", methods=["POST"])
def ra_parse():
    b = _body()
    p = parse_text(b.get("text") or "", clean=bool(b.get("clean")))
    return jsonify({"success": True, **p})


@bp.route("/api/regagent/draft", methods=["POST"])
def ra_draft():
    b = _body()
    mode = (b.get("mode") or "enact").lower()
    try:
        if mode == "amend":
            if not (b.get("intent") or "").strip():
                return jsonify({"success": False, "error": "개정 의도를 입력하세요."}), 400
            d, err = ai_amend(b)
        else:
            if not ((b.get("purpose") or "").strip() or (b.get("title") or "").strip()):
                return jsonify({"success": False, "error": "내규명이나 제정 목적을 입력하세요."}), 400
            d, err = ai_enact(b)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"초안을 만들지 못했습니다({type(e).__name__}). 입력을 확인하고 다시 시도하세요."}), 500
    if d is None:
        need = bool(re.search(r"키", err or ""))
        return jsonify({"success": False, "error": err, "need_key": need}), 400 if need else 502
    return jsonify({"success": True, "mode": mode, "draft": d, "notice": err})


# ── 한글(.hwpx) 문서 세트 ─────────────────────────────────────────────────
_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _xesc(s):
    return (_XML_BAD.sub("", str(s or "")).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_LS = ('<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
       'baseline="850" spacing="600" horzpos="0" horzsize="{w}" flags="393216"/></hp:linesegarray>')


# 문서 서식: 블록·셀 글자 모양 이름 → HWPX charPr/paraPr 번호(build_hwpx 가 header.xml 에 추가해 채운다)
_HS = {"char": {"": "0"}, "para": {"": "0"}}


def _seg_lines(c: dict) -> list:
    """셀 → 줄 목록. 줄은 [(글, 서식)]. 서식: ""·"d"(삭제 밑줄)·"i"(추가 밑줄)·"b"(굵게)."""
    segs = c.get("r") or [{"s": c.get("t", ""), "u": ""}]
    base = "b" if c.get("hd") else ""
    lines = [[]]
    for sg in segs:
        parts = str(sg.get("s", "")).split("\n")
        for k, part in enumerate(parts):
            if k:
                lines.append([])
            if part:
                lines[-1].append((part, sg.get("u") or base))
    return lines


def _para(text, width=47628, page_break=False, style="", align=""):
    ch, pa = _HS["char"].get(style, "0"), _HS["para"].get(align, "0")
    return (f'<hp:p id="0" paraPrIDRef="{pa}" styleIDRef="0" pageBreak="{1 if page_break else 0}" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="{ch}"><hp:t>{_xesc(text)}</hp:t></hp:run>'
            + _LS.format(w=width) + '</hp:p>')


def _cell(c, col, row, cspan, width, bf, hdr=False):
    lines = _seg_lines(c)
    pa = _HS["para"].get("center" if c.get("hd") else "", "0")
    paras = "".join(
        f'<hp:p id="0" paraPrIDRef="{pa}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        + ("".join(f'<hp:run charPrIDRef="{_HS["char"].get(u, "0")}"><hp:t>{_xesc(t)}</hp:t></hp:run>' for t, u in ln)
           or '<hp:run charPrIDRef="0"><hp:t></hp:t></hp:run>')
        + f'{_LS.format(w=max(1000, width - 400))}</hp:p>'
        for ln in lines)
    lines = ["".join(t for t, _ in ln) for ln in lines]
    # 줄 수·폭으로 높이를 어림(한글이 열 때 다시 계산)
    est = sum(max(1, int(len(ln) * 1000 / max(1500, width - 1000)) + 1) for ln in lines)
    h = max(1848, est * 1600 + 600)
    return (f'<hp:tc name="" header="{1 if hdr else 0}" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'{paras}</hp:subList><hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{cspan}" rowSpan="1"/><hp:cellSz width="{width}" height="{h}"/>'
            f'<hp:cellMargin left="283" right="283" top="141" bottom="141"/></hp:tc>'), h


def _table(rows, col_w, bf, bfh=None, page_break=False):
    total = sum(col_w)
    trs, heights = [], []
    nhdr = 0                                   # 쪽이 바뀔 때 되풀이할 제목 행: 맨 위에서 이어지는, 모든 칸이 제목인 행만
    while nhdr < len(rows) and all(c.get("hd") for c in rows[nhdr]):
        nhdr += 1
    for r, cells in enumerate(rows):
        col, tcs, rh = 0, [], 0
        for c in cells:
            cs = int(c.get("cs") or 1)
            w = sum(col_w[col:col + cs])
            x, h = _cell(c, col, r, cs, w, (bfh or bf) if c.get("hd") else bf, hdr=r < nhdr)
            tcs.append(x)
            rh = max(rh, h)
            col += cs
        # 같은 행 셀 높이 통일
        tcs = [re.sub(r'(<hp:cellSz width="\d+" height=")\d+', r"\g<1>" + str(rh), t) for t in tcs]
        heights.append(rh)
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")
    tbl = (f'<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
           f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="{1 if nhdr else 0}" rowCnt="{len(rows)}" colCnt="{len(col_w)}" '
           f'cellSpacing="0" borderFillIDRef="{bf}" noAdjust="0">'
           f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="{sum(heights)}" heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
           f'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="0" right="0" top="283" bottom="283"/>'
           f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>' + "".join(trs) + '</hp:tbl>')
    return (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="{1 if page_break else 0}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{tbl}</hp:run>' + _LS.format(w=47628) + '</hp:p>')


def _clamp_int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError, OverflowError):
        return default


def _norm_runs(v) -> list:
    """셀 서식 구간 [{s, u}] 검증(u: d=삭제·i=추가 밑줄, b=굵게). 잘못된 값이면 빈 목록(평문 t 사용)."""
    if not isinstance(v, list):
        return []
    out = []
    for x in v[:4000]:
        if isinstance(x, dict) and isinstance(x.get("s"), str):
            out.append({"s": x["s"][:20000], "u": x.get("u") if x.get("u") in ("d", "i", "b") else ""})
    return out


def _hwpx_styles(header: str) -> str:
    """header.xml 에 굵게·밑줄(삭제 빨강/추가 파랑 굵게)·제목 글자 모양과 가운데 정렬 문단 모양을 덧붙이고 번호를 _HS 에 담는다."""
    _HS["char"], _HS["para"] = {"": "0"}, {"": "0"}
    m = re.search(r'<hh:charProperties itemCnt="(\d+)">', header)
    c0 = re.search(r'<hh:charPr id="0".*?</hh:charPr>', header, re.S)
    if m and c0:
        n = int(m.group(1))
        add, specs = [], [("b", "#000000", "<hh:bold/>", None), ("d", "#C00000", "", "#C00000"),
                          ("i", "#1F3FBF", "<hh:bold/>", "#1F3FBF"), ("title", "#000000", "<hh:bold/>", None)]
        for k, (name, color, bold, ul) in enumerate(specs):
            x = re.sub(r'id="0"', f'id="{n + k}"', c0.group(0), count=1)
            x = re.sub(r'textColor="[^"]*"', f'textColor="{color}"', x, count=1)
            if name == "title":
                x = re.sub(r'height="\d+"', 'height="1600"', x, count=1)
            x = re.sub(r"<hh:(?:bold|italic)/>|<hh:underline\b[^>]*/>", "", x)
            x = x.replace("<hh:strikeout", bold + (f'<hh:underline type="BOTTOM" shape="SOLID" color="{ul}"/>' if ul else "") + "<hh:strikeout", 1)
            add.append(x)
            _HS["char"][name] = str(n + k)
        end = header.find("</hh:charProperties>")
        header = header[:end] + "".join(add) + header[end:]
        header = header.replace(m.group(0), f'<hh:charProperties itemCnt="{n + len(add)}">', 1)
    m = re.search(r'<hh:paraProperties itemCnt="(\d+)">', header)
    p0 = re.search(r'<hh:paraPr id="0".*?</hh:paraPr>', header, re.S)
    if m and p0:
        n = int(m.group(1))
        x = re.sub(r'id="0"', f'id="{n}"', p0.group(0), count=1).replace('horizontal="JUSTIFY"', 'horizontal="CENTER"', 1)
        end = header.find("</hh:paraProperties>")
        header = header[:end] + x + header[end:]
        header = header.replace(m.group(0), f'<hh:paraProperties itemCnt="{n + 1}">', 1)
        _HS["para"]["center"] = str(n)
    return header


def _norm_blocks(blocks) -> list:
    """문서 블록 정리 — 표의 열 병합(cs)·열 수·행 수를 제한하고 colWidths 를 검증한다(메모리 폭주·0 나누기 방지)."""
    out = []
    for blk in (blocks if isinstance(blocks, list) else [])[:400]:
        if not isinstance(blk, dict):
            continue
        if blk.get("t") != "table":
            out.append(blk)
            continue
        rows = []
        for r in (blk.get("rows") if isinstance(blk.get("rows"), list) else [])[:2000]:
            if not isinstance(r, list):
                continue
            cells = [{"t": str(c.get("t", "")), "hd": bool(c.get("hd")), "cs": _clamp_int(c.get("cs") or 1, 1, 20, 1),
                      "r": _norm_runs(c.get("r"))}
                     for c in r[:20] if isinstance(c, dict)]
            if cells:
                rows.append(cells)
        if not rows:
            continue
        ncol = min(40, max(sum(c["cs"] for c in r) for r in rows))
        cw = blk.get("colWidths")
        ok = isinstance(cw, list) and len(cw) == ncol and all(isinstance(x, (int, float)) and 0 < x < 1e6 for x in cw)
        out.append({"t": "table", "rows": rows, "ncol": ncol, "colWidths": [int(x) for x in cw] if ok else None})
    return out


def build_hwpx(blocks: list) -> bytes:
    base = _CTX["hwpx_base_bytes"]()
    if not base:
        raise RuntimeError("HWPX 기본 서식을 찾을 수 없습니다.")
    zin = zipfile.ZipFile(io.BytesIO(base), "r")
    header = zin.read("Contents/header.xml").decode("utf-8", "ignore")
    sec = zin.read("Contents/section0.xml").decode("utf-8", "ignore")
    bf = _CTX["hwpx_full_border"](header)
    header, bfh = _hwpx_shaded(header, bf)
    with _HWPX_LOCK:
        header = _hwpx_styles(header)
        return _build_hwpx(zin, header, sec, bf, blocks, bfh)


def _hwpx_shaded(header: str, bf: str):
    """표 제목 칸 음영(#EAF2FE) borderFill 을 테두리 서식에서 복제해 추가 → (header, 새 id). Word 출력과 같은 색."""
    m = re.search(r'<hh:borderFill id="' + re.escape(str(bf)) + r'"[^>]*>.*?</hh:borderFill>', header, re.S)
    ids = [int(x) for x in re.findall(r'<hh:borderFill id="(\d+)"', header)]
    if not m or not ids:
        return header, None
    nid = str(max(ids) + 1)
    blk = re.sub(r'<hc:fillBrush>.*?</hc:fillBrush>', '', m.group(0), flags=re.S)
    blk = blk.replace(f'id="{bf}"', f'id="{nid}"', 1).replace(
        '</hh:borderFill>', '<hc:fillBrush><hc:winBrush faceColor="#EAF2FE" hatchColor="#999999" alpha="0"/></hc:fillBrush></hh:borderFill>')
    header = header.replace('</hh:borderFills>', blk + '</hh:borderFills>', 1)
    header = re.sub(r'(<hh:borderFills itemCnt=")(\d+)', lambda x: x.group(1) + str(int(x.group(2)) + 1), header, count=1)
    return header, nid


_HWPX_LOCK = threading.Lock()


def _build_hwpx(zin, header, sec, bf, blocks, bfh=None) -> bytes:
    m = re.search(r'<hs:sec\b[^>]*>', sec)
    prefix, body = sec[:m.end()], sec[m.end():]
    pi = body.find('<hp:p')
    pj = body.find('</hp:p>', pi) + len('</hp:p>')
    first = re.sub(r'<hp:t>.*?</hp:t>', '<hp:t></hp:t>', body[pi:pj], flags=re.S)
    parts, pb = [], False                      # 쪽 나눔은 빈 문단 대신 다음 문단(표)에 건다
    for i, blk in enumerate(_norm_blocks(blocks)):
        t = blk.get("t")
        if t == "table":
            ncol = blk["ncol"]
            parts.append(_table(blk["rows"], blk["colWidths"] or [int(47628 / ncol)] * ncol, bf, bfh, page_break=pb))
            pb = False
        elif t == "break":
            pb = True
        else:
            txt = str(blk.get("text") or "")
            ttl = bool(blk.get("titleBold"))
            for j, ln in enumerate(txt.split("\n")):
                parts.append(_para(ln, page_break=(pb or bool(blk.get("pageBreak"))) and j == 0,
                                   style="title" if ttl and j == 0 else "", align="center" if ttl and j == 0 else ""))
            pb = False
    new_sec = prefix + first + "".join(parts) + _para("") + "</hs:sec>"
    plain = "\n".join(str(b_.get("text") or "") for b_ in _norm_blocks(blocks) if b_.get("t") not in ("table", "break"))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    zout.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
    for n in zin.namelist():
        if n in ("mimetype", "Preview/PrvImage.png"):
            continue
        if n == "Contents/section0.xml":
            data = new_sec.encode("utf-8")
        elif n == "Contents/header.xml":
            data = header.encode("utf-8")
        elif n == "Preview/PrvText.txt":            # 미리보기 글: 기본 서식의 옛 내용 대신 이 문서의 앞부분
            data = plain[:1000].encode("utf-8")
        else:
            data = zin.read(n)
        zout.writestr(n, data)
    zout.close()
    zin.close()
    return out.getvalue()


@bp.route("/api/regagent/hwpx", methods=["POST"])
def ra_hwpx():
    b = _body()
    blocks = b.get("blocks") or []
    if not _norm_blocks(blocks):
        return jsonify({"success": False, "error": "문서 내용이 없습니다."}), 400
    if len(json.dumps(blocks, ensure_ascii=False)) > 1_500_000:
        return jsonify({"success": False, "error": "문서가 너무 큽니다."}), 413
    try:
        data = build_hwpx(blocks)
    except Exception as e:
        print(f"[hwpx] 생성 실패: {e}")
        return jsonify({"success": False, "error": "HWPX 파일을 만들지 못했습니다."}), 500
    from urllib.parse import quote as _q
    fname = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (b.get("filename") or "내규안"))[:80] + ".hwpx"
    return Response(data, mimetype="application/hwp+zip",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + _q(fname)})


# ══════════════════════════════════════════════════════════════════════════
# 7. 기관 프로필 조회
# ══════════════════════════════════════════════════════════════════════════
def _deep_fmt(o):
    if isinstance(o, str):
        return ofmt(o)
    if isinstance(o, list):
        return [_deep_fmt(x) for x in o]
    if isinstance(o, dict):
        return {k: _deep_fmt(v) for k, v in o.items()}
    return o


@bp.route("/api/regagent/config")
def ra_config():
    regs = all_regs()
    return jsonify({"success": True, "org": _deep_fmt(ORG), "reg_count": len(regs),
                    "semantic": bool(_CTX.get("vec_ready") and _CTX["vec_ready"]()), "ledger": ledger_enabled()})


# ══════════════════════════════════════════════════════════════════════════
# 8. 용어·명칭 일괄 정비 — 모든 내규에서 찾아 바꾸고 조사까지 맞춘다
# ══════════════════════════════════════════════════════════════════════════
_PARTICLES = [("으로", "로"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"), ("이나", "나"), ("이라", "라")]


def _has_batchim(w: str) -> bool:
    return _bat(w) > 0


def _rjosa(word: str, part: str) -> str:
    """조사 하나를 새 단어 받침에 맞게."""
    has, ends_rieul = _bat(word) > 0, _bat(word) == 2
    for a, b in _PARTICLES:
        if part in (a, b):
            if a == "으로":
                return "로" if (not has or ends_rieul) else "으로"
            return a if has else b
    return part


# 받침과 상관없는 조사 — 짧은 용어 뒤에 붙어도 다른 낱말이 아니다(“이사장의”·“이사장에게”·“재단도”)
_NEUTRAL_JOSA = re.compile(r"(?:의|에게|에서|에|도|만|께서|께|부터|까지|보다|마다|처럼)(?:는|도|만|의|서)?(?![가-힣])")


def replace_term(text: str, old: str, new: str, whole: bool = True):
    """old→new 치환 + 뒤따르는 조사 교정. 반환: (새 본문, [(위치, 원래 표기, 바뀐 표기)])."""
    if not old:
        return text, []
    pat = re.compile((r"(?<![가-힣A-Za-z0-9])" if whole else "") + re.escape(old)
                     + r"(으로|이나|이라|은|는|이|가|을|를|과|와|로|나|라)?(?=[^가-힣]|$)?")
    hits, out, last = [], [], 0
    for m in pat.finditer(text):
        part = m.group(1) or ""
        after = text[m.end():m.end() + 1]
        # 낱말 단위(whole)일 때 짧은 용어(3자 이하)는 뒤에 한글이 바로 붙으면 다른 낱말로 본다(“이사”→“이사장”·“이사회” 제외).
        # 긴 명칭(“기획운영본부장”의 “기획운영본부”)은 파생어까지 바꾼다.
        if (whole and len(old) <= 3 and not part and after and "가" <= after <= "힣"
                and not _NEUTRAL_JOSA.match(text, m.end())):
            continue
        if part and after and "가" <= after <= "힣":
            # “와의·과는·로부터·으로서”처럼 조사가 겹친 경우만 조사로 보고 고친다(“이사이며”의 “이”는 그대로)
            tail = text[m.end():m.end() + 2]
            part_fixed = _rjosa(new, part) if part in ("과", "와", "로", "으로") and re.match(r"(의|는|도|만|부터|서|써)", tail) else part
        else:
            part_fixed = _rjosa(new, part) if part else ""
        out.append(text[last:m.start()] + new + part_fixed)
        last = m.end()
        hits.append((m.start(), m.group(0), new + part_fixed))
    out.append(text[last:])
    return "".join(out), hits


def _loc_label(art: dict, pos: int) -> str:
    """본문 위치 → “제5조제2항” 같은 개정문용 위치. 호가 딸린 항(조)의 머리글이면 “각 호 외의 부분”,
    단서가 있는 항·호면 “본문”·“단서”를 붙인다."""
    lbl = art_label(art["no"])
    body = art["body"]
    before = body[:pos]
    hs = list(re.finditer(r"(?:^|\n)\s*([" + _HANG_CH + "])", before))
    if hs:
        lbl += f"제{_HANG_CH.index(hs[-1].group(1)) + 1}항"
        u0 = hs[-1].start(1)
    else:
        u0 = 0
    nxt = re.search(r"\n\s*[" + _HANG_CH + "]", body[pos:])
    u1 = pos + nxt.start() if nxt else len(body)                    # 이 항(또는 조 본문)의 끝
    seg = body[u0:pos]
    ho = list(re.finditer(r"(?:^|\n)\s*(\d{1,2})\.(?!\d)", seg))
    if ho:
        lbl += f"제{ho[-1].group(1)}호"
        h0 = u0 + ho[-1].start(1)
        nh = re.search(r"\n\s*\d{1,2}\.(?!\d)", body[pos:u1])
        unit = body[h0:pos + nh.start() if nh else u1]
        upos = pos - h0
    else:
        has_ho = re.search(r"(?:^|\n)\s*\d{1,2}\.(?!\d)", body[u0:u1])
        if has_ho:
            lbl += " 각 호 외의 부분"
            unit = body[u0:u0 + has_ho.start()]
        else:
            unit = body[u0:u1]
        upos = pos - u0
    d = re.search(r"(?:^|\s)다만[,，]", unit)
    if d:
        lbl += " 단서" if upos >= d.start() else " 본문"
    return lbl


_BULK_MAX_ARTS = 400


def _ro(w: str) -> str:
    return "으로" if _bat(w) == 1 else "로"


def _split_loc(lb: str):
    """“제16조제2항제4호 본문” → (조, 항, 나머지)"""
    m = re.match(r"(제\d+조(?:의\d+)?)(제\d+항)?(.*)$", lb.replace(" 제목", "\x00제목"))
    if not m:
        return lb, "", ""
    return m.group(1), m.group(2) or "", (m.group(3) or "").replace("\x00", " ").strip()


def _join_locs(locs: list) -> str:
    """개정문 위치 나열: 같은 조는 조를 빼고(“제7조제1항 및 제4항”), 같은 항은 “같은 항 제4호”,
    조 제목과 함께면 “제13조의 제목 및 같은 조 제1항”."""
    out, prev = [], (None, None)
    bare = {lb for lb in locs if re.fullmatch(r"제\d+조(?:의\d+)?", lb)}
    locs = [(f"{lb}(제목을 포함한다)" if lb in bare and f"{lb} 제목" in locs else lb)
            for lb in locs if not (lb.endswith(" 제목") and lb[:-3] in bare)]   # 제목과 본문을 함께 고치면 “제24조(제목을 포함한다)”
    for u in [lb[:-3] for lb in locs if lb.endswith(" 본문") and lb[:-3] + " 단서" in locs]:
        i = locs.index(u + " 본문")                # 한 단위의 본문과 단서를 모두 고치면 그 단위째(“제3조제1항”)
        locs = [x for x in locs if x not in (u + " 본문", u + " 단서")]
        locs.insert(i, u)
    prest = ""
    for lb in locs:
        art, hang, rest = _split_loc(lb)
        if rest == "제목":
            txt = f"{art}의 제목"
            hang = "제목"
        elif art == prev[0] and prev[1] == "제목":
            txt = "같은 조" + (f" {hang}{rest}".rstrip() if (hang or rest) else "")
        elif art == prev[0] and hang and hang == prev[1]:
            txt = "같은 항 " + rest.lstrip()
        elif (art == prev[0] and prest and prev[1] != "제목"
              and not (hang == prev[1] and re.match(r"제\d+호", rest) and re.match(r"제\d+호", prest))):   # 호·“각 호 외의 부분” 다음에 다른 항·호로 가면 “같은 조”
            txt = "같은 조 " + (hang + (rest if rest.startswith("제") else (" " + rest if rest else ""))).strip()
        elif art == prev[0]:
            txt = (hang + (rest if rest.startswith("제") else (" " + rest if rest else ""))) or "같은 조"
        else:
            txt = lb
        out.append(txt.strip())
        prev, prest = (art, hang), ("" if rest == "제목" else rest)
    return out[0] if len(out) < 2 else ", ".join(out[:-1]) + " 및 " + out[-1]


def _bulk_sentence(pairs: list, old: str, new: str) -> str:
    """[(위치, (원래 표기, 바뀐 표기))] → 개정문 한 문장.
    조사만 바뀌는 곳(“부원장은”→“총괄이사는”)은 그 표기째 쓴다. 같은 바꿈은 “각각”으로 묶고 “…하고,”로 잇는다."""
    groups = {}
    for lb, (o_, n_) in pairs:
        key = (old, new) if (o_[len(old):] == n_[len(new):]) else (o_, n_)
        locs = groups.setdefault(key, [])
        if lb not in locs:
            locs.append(lb)
    def lkey(lb):                                  # 조·항·호 순서(제목은 그 조 맨 앞)
        art, hang, rest = _split_loc(lb)
        ho = re.search(r"제(\d+)호", rest)
        return (art_key(art.replace("제", "").replace("조", "")), -1 if rest == "제목" else int(re.sub(r"\D", "", hang) or 0),
                int(ho.group(1)) if ho else 0)
    for k in groups:
        groups[k].sort(key=lkey)
    parts, last = [], None
    for (o_, n_), locs in sorted(groups.items(), key=lambda kv: lkey(kv[1][0])):
        each = "각각 " if len(locs) > 1 else ""
        where = _join_locs(locs)
        art = _split_loc(locs[0])[0]
        if last and art == last:                   # 앞 문장과 같은 조에서 이어지면 “같은 조”
            where = re.sub(r"^" + re.escape(art) + r"(?=제|의|\s|$)", "같은 조 ", where).replace("같은 조 의", "같은 조의").replace("  ", " ")
        parts.append(f"{where} 중 “{o_}”{_josa(o_, ('을', '를'))} {each}“{n_}”{_ro(n_)} ")
        last = _split_loc(locs[-1])[0]
    return "하고, ".join(parts) + "한다."


@bp.route("/api/regagent/bulk", methods=["POST"])
def ra_bulk():
    """용어·명칭 일괄 정비. body: {old, new, whole:true, slugs:[...](선택)}"""
    b = _body()
    old, new = (b.get("old") or "").strip(), (b.get("new") or "").strip()
    if len(old) < 2 or not new or old == new:
        return jsonify({"success": False, "error": "바꿀 용어(2자 이상)와 새 용어를 입력하세요."}), 400
    only = set(b.get("slugs") or [])
    whole = b.get("whole", True) is not False
    regs_out, total = [], 0
    for r in all_regs():
        if only and r["slug"] not in only:
            continue
        arts = []
        for a in r["articles"]:
            if a["deleted"] or old not in a["body"] and old not in a["title"]:
                continue
            nb, hits = replace_term(a["body"], old, new, whole)
            nt, thits = replace_term(a["title"], old, new, whole)
            if not hits and not thits:
                continue
            locs, pairs = [], []
            for pos, o_, n_ in hits:
                lb = _loc_label(a, pos)
                if lb not in locs:
                    locs.append(lb)
                pairs.append((lb, (o_, n_)))
            if thits:
                locs.insert(0, f"{art_label(a['no'])} 제목")
                pairs[:0] = [(f"{art_label(a['no'])} 제목", (o_, n_)) for _, o_, n_ in thits[:1]]
            arts.append({"no": a["no"], "title": a["title"], "new_title": nt, "old_body": a["body"],
                         "new_body": nb, "count": len(hits) + len(thits), "locs": locs, "pairs": pairs})
            total += len(hits) + len(thits)
        if arts:
            regs_out.append({"slug": r["slug"], "reg": r["title"], "articles": arts,
                             "count": sum(x["count"] for x in arts)})
    regs_out.sort(key=lambda x: -x["count"])
    n_arts = sum(len(g["articles"]) for g in regs_out)
    # “한다”·“따라”처럼 흔한 말은 명칭 정비 대상이 아니다(응답도 수 MB 로 커짐). 기관장·부기관장·옛 명칭처럼
    # 기관이 명칭으로 등록한 말은 직제 개편 때 실제로 모든 내규를 고쳐야 하므로 상한을 넓힌다
    named = old in {ORG["head"], ORG["deputy"], ORG["org_name"], ORG["org_short"]} | {o_ for o_, _ in _STALE_TERMS + _STALE_WORDS}
    if n_arts > (_BULK_MAX_ARTS * 4 if named else _BULK_MAX_ARTS):
        return jsonify({"success": False, "error": f"“{old}”{_josa(old, ('이', '가'))} {len(regs_out)}개 내규 {n_arts}개 조문에 있어 일괄 정비 범위를 넘습니다. "
                                                   f"더 구체적인 명칭(예: 부서명·직위명 전체)으로 찾으세요."}), 400
    for g in regs_out:
        g["amend_text"] = f"{g['reg']} 일부를 다음과 같이 개정한다.\n" + _bulk_sentence(
            [pr for a in g["articles"] for pr in a.pop("pairs")], old, new)
    return jsonify({"success": True, "old": old, "new": new, "total": total,
                    "reg_count": len(regs_out), "regs": regs_out})


# ══════════════════════════════════════════════════════════════════════════
# 9. 심의 사전검토 — 기관 심의기준(review_criteria)별 점검 + AI 검토의견
# ══════════════════════════════════════════════════════════════════════════
def review_draft(b: dict) -> dict:
    title = (b.get("title") or "").strip()
    p = parse_text(b.get("text") or "", clean=False)
    arts = p["articles"]
    addenda = b.get("addenda") if isinstance(b.get("addenda"), str) else p["addenda"]
    lint = lint_articles(arts, addenda or "", p["appendix"], title)
    focus = {re.sub(r"[^0-9의]", "", str(x)) for x in (b.get("focus") or []) if str(x).strip()}
    if focus:                                          # 개정: 고친 조문(과 조문 없는 전체 지적)만
        lint = [i for i in lint if not i.get("no") or i["no"] in focus]
    purpose = (b.get("purpose") or "").strip()
    main = [x for x in (b.get("main") or []) if str(x).strip()]
    dels = b.get("delegations") or []
    ans = b.get("ans") or {}
    mode = b.get("mode") or "enact"
    F = {}

    def f(cid, status, msg):
        F.setdefault(cid, []).append({"status": status, "msg": msg})

    # 필요성
    if len(purpose) < 20:
        f("need", "warn", "제·개정 이유가 비어 있거나 짧습니다. 필요성·기대효과·시행상 문제점을 적으세요.")
    else:
        f("need", "ok", "제·개정 이유가 적혀 있습니다.")
    if not main:
        f("need", "warn", "주요 내용이 정리되지 않았습니다.")
    al = [r for r in (b.get("alio_refs") or []) if isinstance(r, dict) and r.get("org")][:12]
    if al:
        orgs = sorted({str(r["org"]) for r in al})
        f("need", "ok", f"다른 공공기관 운영 사례 {len(orgs)}곳(알리오): " + "; ".join(
            f"{r['org']} 「{r.get('reg', '')}」 {art_label(str(r.get('no', '')))}({r.get('title', '')})" for r in al[:4])
          + (f" 외 {len(al) - 4}건" if len(al) > 4 else ""))
    # 적합성
    if mode == "enact" and _kind_of(title) in ("시행세칙", "세칙") and not dels:
        f("fit", "warn", "시행세칙인데 위임 근거(상위 규정 조항)가 없습니다.")
    if dels:
        f("fit", "ok", "상위 근거: " + ", ".join(_del_ref(d) for d in dels[:4]))
    laws = sorted({m.group(1) for a in arts for m in _QUOTED_NAME.finditer(a.get("body", ""))
                   if re.search(r"법|령$", m.group(1))})
    if laws:
        f("fit", "check", "인용 법령의 현행 여부·조문 번호를 확인하세요: " + ", ".join(f"「{x}」" for x in laws[:8]))
    for i in lint:
        if i["code"] in ("regname", "stale"):
            f("fit", "warn", i["msg"])
    # 통일성·조화성
    if mode == "enact" and title and _nk(title) in _reg_names():
        f("unity", "warn", f"같은 이름의 {ORG['reg_word']}{_josa(ORG['reg_word'], ('이', '가'))} 이미 있습니다: 「{title}」")
    q = " ".join([title, purpose] + [str(x) for x in main])[:600]
    if len(q) >= 4:
        sim = similar_search(q, b.get("slug") or "", 4)
        top = [g for g in sim["regs"] if g["score"] >= 6][:3]
        if top:
            f("unity", "check", "비슷한 내용이 있는 내규와 중복·상충 여부를 확인하세요: "
              + "; ".join(f"「{g['title']}」 " + ", ".join(f"{art_label(a['no'])}({a['title']})" for a in g["articles"][:2]) for g in top))
        else:
            f("unity", "ok", "내용이 크게 겹치는 내규를 찾지 못했습니다.")
    # 명료성
    style = [i for i in lint if i["code"] in ("style", "space", "abbr", "term", "notation")]
    if style:
        f("clear", "check", f"알기 쉬운 표기 제안 {len(style)}건: " + "; ".join(i["fix"] or i["msg"] for i in style[:5]))
    longs = [a for a in arts for s_ in re.split(r"(?<=[.다])\s", a.get("body", "")) if len(s_) > 180]
    if longs:
        f("clear", "check", "한 문장이 180자를 넘는 조문: " + ", ".join(sorted({art_label(a["no"]) for a in longs}, key=lambda x: art_key(re.sub(r"[제조]", "", x)))[:6]) + ". 나누어 쓰는 것을 검토하세요.")
    if not style and not longs:
        f("clear", "ok", "표기·문장 길이에서 특이사항이 없습니다.")
    # 체제·효력
    st = [i for i in lint if i["code"] in ("dup", "order", "gap", "first", "title", "empty", "hang", "ho", "mok", "ref", "xref", "deleg", "addenda", "appx", "noart")]
    for i in st[:8]:
        f("form", "warn" if i["level"] != "info" else "check", i["msg"])
    if not arts:
        f("form", "warn", "“제1조(목적)” 형식의 조문을 찾지 못했습니다.")
    if re.search(r"(발령|공포|결재)한\s*날부터", addenda or ""):
        f("form", "check", "시행일이 즉시 시행입니다. 시행 공문이 모든 부서에 도달하는 기간을 고려했는지 확인하세요.")
    if not st and arts:
        f("form", "ok", "조 번호·항호 순서·인용·부칙 형식에 문제가 없습니다.")
    # 공개·협의
    if not ans:
        f("open", "check", "절차 안내 탭에서 해당 여부(국민 권리·의무 관련, 부서 협의 등)를 답하면 필요한 절차를 확인합니다.")
    else:
        if ans.get("public") == "y":
            f("open", "check", f"국민 권리·의무 관련: 대국민 사전예고({ORG['notice_days']}일 이상) 대상입니다.")
        if ans.get("multi") == "y":
            f("open", "check", "2개 이상 부서 소관: 사전 합의·협의 결과를 첨부하세요.")
        if ans.get("impact") == "y":
            f("open", "check", "국민 생활·기업 영향: 부패영향평가 요청 대상입니다.")
        if ans.get("burden") == "y":
            f("open", "check", "유사 행정규제: 자체 규제심사서를 함께 제출하세요.")
        if not F.get("open"):
            f("open", "ok", "추가 협의·예고 대상이 아닌 것으로 답했습니다.")
    rows = []
    for c in ORG.get("review_criteria") or []:
        items = F.get(c["id"], [])
        stv = "warn" if any(x["status"] == "warn" for x in items) else \
              "check" if any(x["status"] == "check" for x in items) or not items else "ok"
        rows.append({"id": c["id"], "t": ofmt(c["t"]), "ref": ofmt(c.get("ref", "")), "d": ofmt(c.get("d", "")),
                     "status": stv, "items": items, "ai": ""})
    return {"rows": rows, "lint_count": len(lint)}


@bp.route("/api/regagent/review", methods=["POST"])
def ra_review():
    b = _body()
    if not (b.get("text") or "").strip():
        return jsonify({"success": False, "error": "검토할 조문이 없습니다."}), 400
    try:
        res = review_draft(b)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"검토하지 못했습니다({type(e).__name__}). 입력을 확인하고 다시 시도하세요."}), 500
    notice = ""
    if b.get("ai"):
        provider, key, model = _ai_conf(b)
        if key or provider == "ollama":
            mdl = model or _CTX["default_model_for"](provider, key)
            crit = "\n".join(f"- {r['id']}: {r['t']} — {r['d']}" for r in res["rows"])
            system = f"""당신은 {ORG['org_name']} {ORG['reg_word']}심의위원회 간사입니다. 「{ORG['rules_name']}」의 심의기준으로 {ORG['reg_word']}안을 검토해 의견을 쓰세요.
심의기준:
{crit}
반드시 JSON만 반환: {{"opinions": {{"기준id": "2~3문장 검토의견(보완 필요 사항은 구체적으로)"}}, "delegation": "상위 법령 위임 범위를 넘거나 저촉 우려가 있는 조문(없으면 빈 문자열)", "overall": "종합의견 2문장"}}
사실을 지어내지 말고, 확인이 필요한 사항은 '확인 필요'로 쓰세요."""
            user = (f"{ORG['reg_word']}명: {b.get('title', '')}\n구분: {'제정' if b.get('mode') != 'amend' else '개정'}\n"
                    f"이유: {b.get('purpose', '')}\n상위 근거:\n{_deleg_block(b.get('delegations')) or '(없음)'}\n\n"
                    f"[{ORG['reg_word']}안]\n{(b.get('text') or '')[:12000]}\n\n[부칙]\n{b.get('addenda') or ''}")
            text, err = _CTX["ai_generate"](provider, key, mdl, system, user, max_tokens=2500, temperature=0.2, json_mode=True)
            if err:
                notice = f"AI 검토의견을 받지 못했습니다: {err}"
            else:
                try:
                    d = _json_from(text)
                    ops = d.get("opinions") or {}
                    for r in res["rows"]:
                        r["ai"] = str(ops.get(r["id"]) or "").strip()
                    res["delegation"] = str(d.get("delegation") or "").strip()
                    res["overall"] = str(d.get("overall") or "").strip()
                    res["model"] = f"{provider}:{mdl}"
                except Exception:
                    notice = "AI 검토의견을 해석하지 못했습니다."
        else:
            notice = "AI 키가 없어 자동 점검 결과만 보여 줍니다."
    return jsonify({"success": True, **res, "notice": notice})


# ══════════════════════════════════════════════════════════════════════════
# 10. Word(.docx) 저장 — 한글이 없는 기관용
# ══════════════════════════════════════════════════════════════════════════
def _w_run(t, u=""):
    rpr = {"b": "<w:b/>", "d": '<w:color w:val="C00000"/><w:u w:val="single"/>',
           "i": '<w:b/><w:color w:val="1F3FBF"/><w:u w:val="single"/>'}.get(u, "")
    return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{_xesc(t)}</w:t></w:r>'


def _w_para(t, bold=False, center=False, page_break=False):
    ppr = ""
    if center or page_break:
        ppr = "<w:pPr>" + ("<w:pageBreakBefore/>" if page_break else "") + ('<w:jc w:val="center"/>' if center else "") + "</w:pPr>"
    r = f'<w:r>{"<w:rPr><w:b/></w:rPr>" if bold else ""}<w:t xml:space="preserve">{_xesc(t)}</w:t></w:r>'
    return f"<w:p>{ppr}{r}</w:p>"


def build_docx(blocks: list) -> bytes:
    body = []
    pb = False
    for blk in _norm_blocks(blocks):
        t = blk.get("t")
        if t == "break":
            pb = True
            continue
        if t == "table":
            rows, ncol = blk["rows"], blk["ncol"]
            cw = blk["colWidths"] or [1] * ncol             # 화면에서 준 열 너비 비율을 본문 폭(9000)에 맞춘다
            ws = [max(300, int(9000 * w / sum(cw))) for w in cw]
            grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in ws)
            trs = []
            for i, r in enumerate(rows):
                tcs, col = [], 0
                for c in r:
                    cs = c["cs"]
                    jc = '<w:pPr><w:jc w:val="center"/></w:pPr>' if c.get("hd") else ""
                    paras = "".join(f"<w:p>{jc}" + "".join(_w_run(t, u) for t, u in ln) + "</w:p>" for ln in _seg_lines(c))
                    tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="{sum(ws[col:col + cs])}" w:type="dxa"/>'
                               + (f'<w:gridSpan w:val="{cs}"/>' if cs > 1 else "")
                               + (('<w:shd w:val="clear" w:color="auto" w:fill="EAF2FE"/>') if c.get("hd") else "")
                               + f'</w:tcPr>{paras}</w:tc>')
                    col += cs
                trs.append("<w:tr>" + ('<w:trPr><w:tblHeader/></w:trPr>' if i == 0 else "") + "".join(tcs) + "</w:tr>")
            bd = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="444444"/>'
                         for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
            if pb:
                body.append(_w_para("", page_break=True))
                pb = False
            body.append(f'<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:tblBorders>{bd}</w:tblBorders>'
                        f'<w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
                        f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')
            continue
        for j, ln in enumerate(str(blk.get("text") or "").split("\n")):
            ttl = j == 0 and bool(blk.get("titleBold"))
            body.append(_w_para(ln, bold=ttl, center=ttl, page_break=(pb and j == 0)))
        pb = False
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1300" w:bottom="1440" w:left="1300" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>'
           '</w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults>'
              '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:hAnsi="Malgun Gothic" w:eastAsia="맑은 고딕"/>'
              '<w:sz w:val="21"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
              '</w:docDefaults></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", drels)
    return out.getvalue()


@bp.route("/api/regagent/docx", methods=["POST"])
def ra_docx():
    b = _body()
    blocks = b.get("blocks") or []
    if not _norm_blocks(blocks):
        return jsonify({"success": False, "error": "문서 내용이 없습니다."}), 400
    if len(json.dumps(blocks, ensure_ascii=False)) > 1_500_000:
        return jsonify({"success": False, "error": "문서가 너무 큽니다."}), 413
    from urllib.parse import quote as _q
    fname = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (b.get("filename") or "내규안"))[:80] + ".docx"
    return Response(build_docx(blocks),
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + _q(fname)})


# ══════════════════════════════════════════════════════════════════════════
# 11. 규정 건강검진 — 내규별 건강 점수·정비 우선순위
# ══════════════════════════════════════════════════════════════════════════
_REV_DATE = re.compile(r"((?:19|20)\d\d)\s*년(?:도)?(?:\s*(\d{1,2})\s*월)?(?:\s*(\d{1,2})\s*일)?")
_LAW_NAME_OK = re.compile(r"(법|법률|시행령|시행규칙)$")


def _kst_today() -> str:
    """서버(Vercel 은 UTC)와 무관하게 한국 날짜."""
    import datetime as _dt
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=9)).strftime("%Y%m%d")


def rev_date(rev: str) -> str:
    """'2023년도 7월 일부개정' → '20230701'. 모르면 ''."""
    m = _REV_DATE.search(rev or "")
    if not m:
        return ""
    return f"{m.group(1)}{int(m.group(2) or 1):02d}{int(m.group(3) or 1):02d}"


def cited_laws(reg: dict, official: bool = False) -> list:
    """내규 본문(부칙 제외)이 인용하는 국가 법령명(「…법」·시행령·시행규칙).
    official=True 면 약칭(「청탁금지법」)을 정식 명칭으로 바꿔 한 번만 센다(법제처 조회용)."""
    names = []
    for a in reg["articles"]:
        if a["deleted"]:
            continue
        for m in _QUOTED_NAME.finditer(a["body"]):
            nm = re.sub(r"\s+", " ", m.group(1)).strip()
            if official and _LAW_NAME_OK.search(nm):
                nm = law_official(nm)
            if _LAW_NAME_OK.search(nm) and nm not in names and len(nm) <= 40 + 40 * official:
                names.append(nm)
    return names


# 감점(건당, 상한). 점수 기준은 화면에도 그대로 안내한다
_H_W = {"ref": (10, 30), "xref": (8, 24), "dup": (8, 16), "order": (8, 16), "regname": (6, 18), "stale": (5, 15), "dupreg": (10, 10)}
_H_GRADE = [("A", 95), ("B", 85), ("C", 75), ("D", 60), ("E", 0)]
_DUPREG = {"key": None, "v": {}}


def dup_regs() -> dict:
    """본문이 거의 같은 내규 — 파일명 오타 등으로 같은 내규가 두 번 등록된 경우(“직업창업규칙” ↔ 「직원창업규칙」).
    → {slug: [{"slug","title","revision","ratio"}]}"""
    regs = all_regs()
    if _DUPREG["key"] == id(regs):
        return _DUPREG["v"]
    sig = []
    for r in regs:
        live = [a for a in r["articles"] if not a["deleted"]]
        sig.append((r, len(live), {re.sub(r"\s+", "", a["title"]) for a in live if a["title"]},
                    [re.sub(r"[\s「」“”\"]+", "", a["title"] + a["body"]) for a in live]))
    out = {}
    for i, (ra_, na, ta, xa) in enumerate(sig):
        for rb, nb, tb, xb in sig[i + 1:]:
            if not na or not nb or min(na, nb) / max(na, nb) < 0.8 or len(ta & tb) / max(1, len(ta | tb)) < 0.7:
                continue
            # 조문 단위로 견준다(글자 단위 비교는 느리다): 개정분이 있어도 조문 대부분이 그대로면 같은 내규
            ratio = difflib.SequenceMatcher(None, xa, xb, autojunk=False).ratio()
            if ratio >= 0.6 and difflib.SequenceMatcher(None, "".join(xa)[:3000], "".join(xb)[:3000]).quick_ratio() >= 0.95:
                for x, y in ((ra_, rb), (rb, ra_)):
                    out.setdefault(x["slug"], []).append({"slug": y["slug"], "title": y["title"],
                                                          "revision": y.get("revision", ""), "ratio": round(ratio, 3)})
    _DUPREG.update(key=id(regs), v=out)
    return out


def health_row(r: dict, law_info: dict, today: str) -> dict:
    iss = [i for i in lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"], full=False)
           if i["code"] in _H_W]
    n_lint = len(iss)
    for o in dup_regs().get(r["slug"], []):                  # 화면 고른 상태가 순번으로 저장되므로 기존 문제 뒤에 붙인다
        iss.append({"level": "warn", "code": "dupreg", "no": "", "term": "", "other": o["slug"],
                    "msg": f"「{o['title']}」({o['revision'] or '개정 정보 없음'})과 조문 {round(o['ratio'] * 100)}%가 같습니다. "
                           f"파일명 오타 등으로 같은 {ORG['reg_word']}가 두 번 등록됐는지 확인하고, 맞으면 한쪽을 내규 등록 화면에서 정리하세요."})
    cnt = {}
    for i in iss:
        cnt[i["code"]] = cnt.get(i["code"], 0) + 1
    pen, reasons = 0, []
    labels = {"ref": "없는 조문 인용", "xref": "다른 내규의 없는·삭제된 조문 인용", "dup": "조 번호 중복", "order": "조 번호 순서 오류",
              "regname": "현행 목록에 없는 내규명 인용", "stale": "옛 기관명·직위", "dupreg": "중복 등록 의심"}
    for code, n in cnt.items():
        w, cap = _H_W[code]
        pen += min(n * w, cap)
        reasons.append(f"{labels[code]} {n}건")
    rd = rev_date(r.get("revision", ""))
    age = None
    if rd:
        y, mth = int(rd[:4]), int(rd[4:6])
        ty, tm = int(today[:4]), int(today[4:6])
        age = round(((ty - y) * 12 + (tm - mth)) / 12, 1)
        ap = 15 if age >= 5 else 8 if age >= 3 else 4 if age >= 2 else 0
        if ap:
            pen += ap
            reasons.append(f"개정 후 {age:g}년 경과")
    laws = cited_laws(r, official=True)
    stale_laws = []
    for nm in laws:
        info = law_info.get(nm)
        info = info if isinstance(info, dict) else {}
        ef = re.sub(r"\D", "", str(info.get("ef") or ""))[:8]
        if info.get("found") is False:
            continue
        if rd and len(ef) == 8 and rd < ef <= today:
            stale_laws.append({"law": nm, "ef": ef})
    if stale_laws:
        pen += min(len(stale_laws) * 8, 32)
        reasons.append(f"내규 개정 뒤 시행된 상위법 {len(stale_laws)}건")
    score = max(0, 100 - pen)
    grade = next(g for g, cut in _H_GRADE if score >= cut)
    by_no = {a["no"]: a for a in r["articles"]}
    detail = []
    for i in iss[:min(n_lint, 30)] + iss[n_lint:]:   # 화면에서 바로 확인하도록 조 제목과 문제 부분 앞뒤 글을 붙인다(중복 등록 안내는 항상 포함)
        a = by_no.get(i["no"]) or {}
        body = a.get("body", "")
        k = body.find(i["term"]) if i.get("term") else -1
        snip = _snip(body, k) if k >= 0 else body[:90] + ("…" if len(body) > 90 else "")
        detail.append({**i, "art_title": a.get("title", ""), "snip": snip})
    return {"slug": r["slug"], "title": r["title"], "category": r["category"], "revision": r.get("revision", ""),
            "rev_date": rd, "age": age, "score": score, "grade": grade, "counts": cnt,
            "issues": detail, "laws": laws, "stale_laws": stale_laws, "reasons": reasons,
            "n_articles": len(r["articles"])}


@bp.route("/api/regagent/health", methods=["GET", "POST"])
def ra_health():
    """전체 내규 건강검진. POST {law_info:{법령명:{ef:YYYYMMDD}}} 를 주면 상위법 최신성까지 반영."""
    b = _body()
    law_info = b.get("law_info") if isinstance(b.get("law_info"), dict) else {}
    today = _kst_today()
    rows = [health_row(r, law_info, today) for r in all_regs()]
    rows.sort(key=lambda x: (x["score"], -(x["age"] or 0)))
    grades = {g: sum(1 for x in rows if x["grade"] == g) for g in "ABCDE"}
    all_laws = sorted({nm for x in rows for nm in x["laws"]})
    n = len(rows) or 1
    return jsonify({"success": True, "today": today, "count": len(rows),
                    "rules": {"weights": _H_W, "grades": _H_GRADE,
                              "age": "2년 -4 · 3년 -8 · 5년 이상 -15", "law": "상위법 건당 -8(최대 -32)"},
                    "avg": round(sum(x["score"] for x in rows) / n, 1), "grades": grades,
                    "with_errors": sum(1 for x in rows if x["counts"].get("ref") or x["counts"].get("xref") or x["counts"].get("dup") or x["counts"].get("order")),
                    "with_issues": sum(1 for x in rows if x["reasons"]),
                    "issue_total": sum(sum(x["counts"].values()) for x in rows),
                    "stale_regs": sum(1 for x in rows if x["stale_laws"]),
                    "old_regs": sum(1 for x in rows if (x["age"] or 0) >= 3),
                    "laws": all_laws, "law_checked": len(law_info), "rows": rows})


_LAW_FRESH: dict = {}


@bp.route("/api/regagent/health/laws", methods=["POST"])
def ra_health_laws():
    """상위법 최신 시행일 조회(법제처). body {names:[...]} — 서버리스 시간 제한에 맞춰 한 번에 최대 12건."""
    b = _body()
    names = [str(x).strip() for x in (b.get("names") or []) if str(x).strip()][:12]
    look = _CTX.get("law_info")
    if not look:
        return jsonify({"success": False, "error": "법령 조회를 사용할 수 없습니다."}), 503
    out = {}
    todo = []
    for nm in names:
        c = _LAW_FRESH.get(nm)
        if c and time.time() - c["at"] < 6 * 3600:
            out[nm] = c["v"]
        else:
            todo.append(nm)
    if todo:
        import concurrent.futures as cf

        def one(nm):
            try:
                v = look(nm) or {}
                if v.get("error"):
                    return nm, {"error": str(v["error"])[:120]}
                return nm, {"ef": v.get("ef", ""), "status": v.get("status", ""), "name": v.get("name", ""),
                            "found": bool(v.get("mst") or v.get("id")) and v.get("rank", 99) <= 1}
            except Exception as e:
                return nm, {"error": str(e)[:120]}
        # 서버리스 시간 제한 안에서 끝내도록 전체 대기 시간을 제한한다(늦은 건은 실패로 돌려 다시 시도하게 함)
        ex = cf.ThreadPoolExecutor(max_workers=6)
        futs = {ex.submit(one, nm): nm for nm in todo}
        done, pending = cf.wait(futs, timeout=float(os.environ.get("LAW_LOOKUP_BUDGET", "15")))
        for f in done:
            nm, v = f.result()
            out[nm] = v
            if "error" not in v:
                _LAW_FRESH[nm] = {"at": time.time(), "v": v}
        for f in pending:
            out[futs[f]] = {"error": "법제처 응답 지연"}
        ex.shutdown(wait=False, cancel_futures=True)
    return jsonify({"success": True, "laws": out,
                    "failed": sum(1 for v in out.values() if v.get("error"))})


# ══════════════════════════════════════════════════════════════════════════
# 11-1. 공문서 표기 점검(행정업무운영편람) — 이유서·사전예고문·공고·의견서 등 문서 글
# ══════════════════════════════════════════════════════════════════════════
@bp.route("/api/regagent/notation", methods=["POST"])
def ra_notation():
    """body: {texts:{문서키: 글}, kind:"doc"|"law", kinds:{문서키: "law"}} → {results:{문서키: [발견]}}
    kind: doc(이유서·공고처럼 붙임·끝이 있는 문서, 기본) · law(조문 — 붙임·끝 규칙 제외)"""
    b = _body()
    texts = b.get("texts") if isinstance(b.get("texts"), dict) else {}
    kinds = b.get("kinds") if isinstance(b.get("kinds"), dict) else {}
    dflt = "law" if b.get("kind") == "law" else "doc"
    if not texts:
        return jsonify({"success": False, "error": "점검할 글이 없습니다."}), 400
    results = {}
    for k, v in list(texts.items())[:12]:
        if isinstance(v, str):
            kind = "law" if kinds.get(k) == "law" else ("doc" if kinds.get(k) == "doc" else dflt)
            results[str(k)[:40]] = notation.check(v[:300_000], kind)
    return jsonify({"success": True, "results": results})


# ══════════════════════════════════════════════════════════════════════════
# 11-2. 인용 관계망 — 어떤 내규가 어떤 내규를 「내규명」으로 인용하는지(개정·폐지 영향 범위)
# ══════════════════════════════════════════════════════════════════════════
_GRAPH_CACHE = {"key": None, "v": None}


def _reg_text(r: dict) -> str:
    """본칙 조문만(부칙은 당시 명칭을 그대로 둬야 하는 연혁이라 제외)."""
    return "\n".join(a.get("body", "") for a in r["articles"] if not a.get("deleted"))


# ── 준용 관계: “…은 「상법」 제391조를 준용한다” → 이 내규가 다른 법령·내규(또는 자기 조문)를 준용 ──
_JUN_SENT = re.compile(r"[^.。\n]*준용한다")
_ART_AFTER = re.compile(r"\s*(?:\([^)]{0,30}\)\s*)?(제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?(?:\s*(?:부터|및|·|,)\s*제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*까지)?)*)")
_JUN_CACHE = {"key": None, "v": None}


def jun_relations(r: dict, regnames: dict = None) -> list:
    """한 내규의 준용 조문 → [{no, title, text, targets:[{name, kind:law|reg|self|other, arts}]}]"""
    regnames = regnames if regnames is not None else _reg_names()
    out = []
    for a in r["articles"]:
        if a["deleted"] or "준용" not in a["body"]:
            continue
        for sm in _JUN_SENT.finditer(a["body"]):
            sent = sm.group(0).strip()
            seg = sent[:sent.rfind("준용")]
            cut = list(re.finditer(r"(?:따라|따른|따르며|따르고|의하여|의한)(?=[\s,])", seg))
            if cut:                                   # “「민원처리법」 제19조에 따라 …, 「X」를 준용” → 준용 대상은 마지막 절에만
                seg = seg[cut[-1].end():]
            if re.search(r"이\s*(?:규칙|규정|지침|세칙|요령|기준|정관)\s*(?:을|를)?\s*(?:각각\s*)?$", seg):
                continue                              # “… 사항은 이 규칙을 준용한다” — 다른 법령을 준용하는 게 아니다
            tg, last = [], None

            def push(name, kind, arts):
                arts = re.sub(r"\s+", "", arts or "")
                for t in tg:
                    if t["name"] == name:
                        if arts and arts not in t["arts"]:
                            t["arts"].append(arts)
                        return
                tg.append({"name": name, "kind": kind, "arts": [arts] if arts else []})
            spans = []
            for m in _QUOTED_NAME.finditer(seg):
                nm = re.sub(r"법\s+률$", "법률", re.sub(r"\s+", " ", m.group(1)).strip())
                ma = _ART_AFTER.match(seg[m.end():m.end() + 80])
                k = _nk(nm)
                kind = "reg" if k in regnames else "law" if _LAW_NAME_OK.search(nm) else "other"
                if kind == "law":
                    nm = _law_aliases(nm)[-1]         # 약칭(공운법)은 정식 명칭으로
                push(regnames.get(k, nm), kind, ma.group(1) if ma else "")
                last = (regnames.get(k, nm), kind)
                spans.append((m.start(), m.end() + (ma.end() if ma else 0)))
            for m in re.finditer(r"(?:동법|같은\s*법)\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)", seg):
                if last:
                    push(last[0], last[1], m.group(1))
                spans.append((m.start(), m.end()))
            bare = re.sub(r"「[^」]*」", " ", seg)           # 낫표 안 이름은 위에서 처리했다
            for k, t in regnames.items():          # 낫표 없이 쓴 우리 내규명(“임원추천위원회 운영규정을 준용”)
                if len(k) < 4 or any(x["name"] == t for x in tg) or _nk(t) == _nk(r["title"]):
                    continue
                if re.search(r"(?<![가-힣])" + r"\s*".join(map(re.escape, k)) + r"(?![가-힣]*(?:시행세칙|세칙))(?=\s*(?:제|을|를|의|과|와|및|·|,|\s|$))", bare):
                    push(t, "reg", "")
            if re.search(r"(?<![가-힣」])정관\s*제\s*\d+", seg):
                own = next((t for k, t in regnames.items() if t.endswith("정관")), "정관")
                for m in re.finditer(r"(?<![가-힣」])정관\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)", seg):
                    push(own, "reg", m.group(1))
                    spans.append((m.start(), m.end()))
            rest = seg
            for s0, e0 in sorted(spans, reverse=True):
                rest = rest[:s0] + " " * (e0 - s0) + rest[e0:]
            for m in re.finditer(r"(?<![가-힣」\d])(제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?)", rest):
                pre = rest[max(0, m.start() - 6):m.start()]
                if re.match(r"\s*\d*\s*\(", rest[m.end():m.end() + 4]) and m.start() < 3:
                    continue                          # 본문 앞에 붙은 조 머리(“제4조2(…)”)
                if (re.search(r"이\s*(?:규칙|규정|지침|세칙|요령|기준)\s*$", pre)
                        or not re.search(r"[가-힣]법\s*$|령\s*$|칙\s*$|(?:규정|지침|요령|기준)\s*$", pre)):
                    push(r["title"], "self", m.group(1))
            if not tg:
                m = re.search(r"([가-힣A-Za-z·]{2,30}(?:법|법령|법률|기준|규정))\s*(?:등\s*)?(?:을|를)\s*(?:각각\s*)?준용", sent[:sent.rfind("준용") + 2])
                if m and m.start(1) >= len(sent[:sent.rfind("준용")]) - len(seg) and not re.match(r"(?:관련|관계|해당|위|이|그)", m.group(1)):
                    nm, w = m.group(1), re.search(r"([가-힣]{2,10})\s+$", sent[:m.start(1)])
                    if w and w.group(1)[-1] not in "은는이가을를에의도와과로서며고면":
                        nm = w.group(1) + " " + nm           # “강사수당 지급기준” — 앞 낱말까지 이름으로
                    push(nm, "other", "")
            if tg:
                out.append({"no": a["no"], "title": a["title"], "text": sent[-220:], "targets": tg})
    return out


def jun_index() -> dict:
    """전체 내규 준용 관계 캐시: {slug: [준용 조문…]}, 피준용 {대상 이름: [(slug, title, no, arts)]}"""
    regs = all_regs()
    if _JUN_CACHE["key"] == id(regs):
        return _JUN_CACHE["v"]
    names = _reg_names()
    by, inv = {}, {}
    for r in regs:
        rel = jun_relations(r, names)
        by[r["slug"]] = rel
        for j in rel:
            for t in j["targets"]:
                if t["kind"] == "self":
                    continue
                inv.setdefault(_nk(t["name"]), []).append({"slug": r["slug"], "reg": r["title"], "no": j["no"],
                                                          "title": j["title"], "arts": t["arts"], "text": j["text"]})
    v = {"by": by, "inv": inv}
    _JUN_CACHE.update(key=id(regs), v=v)
    return v


def law_users(law: str) -> dict:
    """이 법령을 준용·인용하는 우리 내규. {jun:[...], cite:[{slug, reg, n}]}"""
    names = _law_aliases(re.sub(r"\s*(시행령|시행규칙)$", "", law.strip()))
    suffix = re.search(r"\s*(시행령|시행규칙)$", law.strip())
    keys = {_nk(n + (suffix.group(0) if suffix else "")) for n in names}
    ji = jun_index()
    jun = [x for k in keys for x in ji["inv"].get(k, [])]
    cite = []
    for r in all_regs():
        n = sum(1 for nm in cited_laws(r) if _nk(nm) in keys)
        if n:
            cite.append({"slug": r["slug"], "reg": r["title"], "category": r["category"]})
    return {"jun": jun, "cite": cite}


@bp.route("/api/regagent/law-users")
def ra_law_users():
    law = re.sub(r"[「」]", "", request.args.get("law", "")).strip()
    if len(law) < 2:
        return jsonify({"success": False, "error": "법령명을 입력하세요."}), 400
    return jsonify({"success": True, "law": law, **law_users(law)})


@bp.route("/api/regagent/relations")
def ra_relations():
    """한 내규의 관계: 인용하는/인용받는 내규, 인용 법령, 준용하는 법령·내규, 이 내규를 준용하는 내규."""
    r = find_reg(request.args.get("slug", ""), request.args.get("reg", ""))
    if not r:
        return jsonify({"success": False, "error": "내규를 찾을 수 없습니다."}), 404
    g = citation_graph()
    idx = {n["slug"]: i for i, n in enumerate(g["nodes"])}
    me = idx.get(r["slug"])
    node = lambda i: {"slug": g["nodes"][i]["slug"], "title": g["nodes"][i]["title"], "category": g["nodes"][i]["category"]}
    cites = [dict(node(e["t"]), n=e["n"]) for e in g["edges"] if e["s"] == me]
    cited_by = [dict(node(e["s"]), n=e["n"]) for e in g["edges"] if e["t"] == me]
    ji = jun_index()
    laws = {}
    for nm in cited_laws(r):
        cnt = sum(len(re.findall(r"「\s*" + r"\s*".join(map(re.escape, nm.replace(" ", ""))) + r"\s*」", a["body"]))
                  for a in r["articles"] if not a["deleted"])
        full = _law_aliases(nm)[-1]                    # 약칭(공운법)과 정식 명칭은 한 줄로
        x = laws.setdefault(full, {"name": full, "count": 0,
                                   "jun": any(t["name"] == full for j in ji["by"].get(r["slug"], []) for t in j["targets"])})
        x["count"] += cnt
    laws = list(laws.values())
    laws.sort(key=lambda x: (-x["jun"], -x["count"]))
    return jsonify({"success": True, "slug": r["slug"], "title": r["title"],
                    "cites": sorted(cites, key=lambda x: -x["n"]), "cited_by": sorted(cited_by, key=lambda x: -x["n"]),
                    "laws": laws, "jun": ji["by"].get(r["slug"], []), "jun_by": ji["inv"].get(_nk(r["title"]), []),
                    "broken": [b for b in g["broken"] if b["from"] == r["slug"]]})


def citation_graph() -> dict:
    """노드=내규, 간선=A가 B를 「B」로 인용(인용 횟수). 현행 목록에 없는 내규명 인용은 broken."""
    regs = all_regs()
    key = id(regs)
    if _GRAPH_CACHE["key"] == key:
        return _GRAPH_CACHE["v"]
    idx = {_nk(r["title"]): i for i, r in enumerate(regs)}
    names = list(idx)
    own = [t for t in [ORG["org_short"], ORG["org_name"]] if t] + [o for o, _ in _STALE_TERMS + _STALE_WORDS]
    edges, broken, memo = {}, {}, {}

    def resolve(nm):
        """「nm」 → (내규 번호|None, 옛 명칭 여부, 비슷한 현행 내규명)"""
        if nm in memo:
            return memo[nm]
        k = _nk(nm)
        if k in idx:
            res = (idx[k], False, "")
        else:
            cur = nm
            for old, new in _STALE_TERMS:
                cur = cur.replace(old, new)
            kc = _nk(cur)
            if kc != k and kc in idx:
                res = (idx[kc], True, regs[idx[kc]]["title"])
            elif ("법" in nm or nm.endswith(("령", "조례")) or not nm.endswith(_REG_SUFFIX)
                  or re.sub(r"^(?:" + "|".join(re.escape(t) for t in own[:2]) + r")\s*", "", nm) == "정관"):
                res = (None, False, None)
            else:
                near = difflib.get_close_matches(k, names, n=1, cutoff=0.8)
                ext = not near and not any(t in nm for t in own)       # 정부 규정 등 외부 규범
                res = (None, False, None if ext else (regs[idx[near[0]]]["title"] if near else ""))
        memo[nm] = res
        return res

    for i, r in enumerate(regs):
        txt = _reg_text(r)
        for m in _QUOTED_NAME.finditer(txt):
            nm = m.group(1).strip()
            # 「보안업무규정」(대통령령)·「…규정」(이하 “영”이라 한다)처럼 국가 법령으로 밝힌 인용은 외부 규범
            if re.match(r"\s*\(\s*(?:대통령령|총리령|[가-힣]+부령|이하\s*[“\"‘']?(?:영|시행령|규정)[”\"’']?)", txt[m.end():m.end() + 24]):
                continue
            if re.sub(r"\s+", "", nm) in _EXTERNAL_REGS:
                continue
            j, stale, near = resolve(nm)
            if near and _nk(near) == _nk(r["title"]):
                near = None                    # 자기 자신과 비슷한 이름은 상위 법령을 인용한 것으로 본다
            if j is not None and j != i:
                edges[(i, j)] = edges.get((i, j), 0) + 1
            if (j is None and near is not None) or stale:
                b = broken.setdefault((i, nm), {"from": r["slug"], "from_title": r["title"], "name": nm, "count": 0,
                                                "near": near or "", "kind": "stale" if stale else "missing"})
                b["count"] += 1
    indeg, outdeg = [0] * len(regs), [0] * len(regs)
    for (a, b), n in edges.items():
        outdeg[a] += 1
        indeg[b] += 1
    nodes = [{"slug": r["slug"], "title": r["title"], "category": r.get("category", ""), "revision": r.get("revision", ""),
              "in": indeg[i], "out": outdeg[i]} for i, r in enumerate(regs)]
    v = {"nodes": nodes, "edges": [{"s": a, "t": b, "n": n} for (a, b), n in sorted(edges.items())],
         "broken": sorted(broken.values(), key=lambda x: (-x["count"], x["from_title"])),
         "stats": {"regs": len(regs), "edges": len(edges), "linked": sum(1 for i in range(len(regs)) if indeg[i] or outdeg[i]),
                   "isolated": sum(1 for i in range(len(regs)) if not indeg[i] and not outdeg[i]),
                   "broken": len(broken)}}
    _GRAPH_CACHE.update({"key": key, "v": v})
    return v


# ══════════════════════════════════════════════════════════════════════════
# 다른 기관 사규(알리오) — 기관 목록·규정 검색·본문(조문) 참고
# ══════════════════════════════════════════════════════════════════════════
def _alio_err(e):
    kind = getattr(e, "kind", "")
    hint = {"SCHEMA": " 알리오 사이트가 바뀌었을 수 있습니다.", "NETWORK": " 잠시 뒤 다시 시도하세요."}.get(kind, "")
    if hint.strip() and hint.strip() in str(e):
        hint = ""                                  # 알리오 오류 문구에 이미 있으면 되풀이하지 않는다
    return jsonify({"success": False, "error": f"{e}{hint}", "kind": kind}), 502 if kind in ("NETWORK", "SCHEMA", "HTTP") else 400


@bp.route("/api/regagent/alio/orgs")
def ra_alio_orgs():
    """알리오 기관 목록 + 우리 기관·유관 기관(org_config.json alio.peer_depts·peers)."""
    try:
        orgs = alio.list_orgs()
    except alio.AlioError as e:
        return _alio_err(e)
    cfg = ORG.get("alio") or {}
    me = cfg.get("apba_id") or next((o["id"] for o in orgs if _nk(o["name"]) == _nk(ORG["org_name"])), "")
    depts = set(cfg.get("peer_depts") or [])
    if not depts and me:
        depts = {o["dept"] for o in orgs if o["id"] == me}
    peers = [o["id"] for o in orgs if o["id"] != me and (o["dept"] in depts or o["id"] in set(cfg.get("peers") or []))]
    return jsonify({"success": True, "orgs": orgs, "self": me, "peers": peers, "categories": alio.CATEGORIES,
                    "batch": alio.MAX_ORGS_PER_CALL})


@bp.route("/api/regagent/alio/search", methods=["POST"])
def ra_alio_search():
    """알리오 규정명 검색. body: {q, orgs:[기관ID ≤12], category}. 화면이 기관을 나눠 여러 번 부른다."""
    b = _body()
    q = (b.get("q") or "").strip()[:40]
    ids = [str(x) for x in (b.get("orgs") or []) if re.fullmatch(r"[A-Za-z0-9]{2,12}", str(x))]
    cat = b.get("category") if b.get("category") in alio.CATEGORIES else ""
    if not ids:
        return jsonify({"success": False, "error": "조회할 기관을 고르세요."}), 400
    if not q and not cat and not b.get("all"):
        return jsonify({"success": False, "error": "규정명 검색어(예: 여비, 드론)를 넣으세요."}), 400
    try:
        r = alio.search(q, ids[:alio.MAX_ORGS_PER_CALL], cat)
    except alio.AlioError as e:
        return _alio_err(e)
    return jsonify({"success": True, **r})


_RANK_STOP = {"정하기", "위함", "위하여", "필요한", "사항", "관한", "대한", "지급", "기준", "규정", "운영", "관리", "업무", "경우", "따른"}


def _alio_rank(arts: list, q: str, kw: str = "") -> list:
    """조문을 검색어 일치도로 정렬. 핵심 검색어(kw)는 3배, 이 규정 안에서 드문 낱말일수록 높게(idf),
    조 제목 일치에 가중. 점수가 맨 위의 40% 이상이면 rel(관련)로 표시한다."""
    import math
    live = [a for a in arts if not a["deleted"]]
    kws = [t for t in _tokens(kw)]
    toks = kws + [t for t in _tokens(q) if t not in kws and t not in _RANK_STOP]
    n = len(live) or 1
    idf = {t: math.log((n + 1) / (sum(1 for a in live if t in a["title"] or t in a["body"]) + 0.5)) for t in toks}
    out = []
    for a in live:
        sc = 0.0
        for t in toks:
            hit = 3 * a["title"].count(t) + min(a["body"].count(t), 4)
            if hit:
                sc += hit * max(idf[t], 0.1) * (3 if t in kws else 1)
        out.append({"no": a["no"], "title": a["title"], "body": a["body"][:1500], "score": round(sc, 2)})
    top = max((x["score"] for x in out), default=0)
    for x in out:
        x["rel"] = bool(top) and x["score"] >= max(0.5, top * 0.4)
    if toks:
        out.sort(key=lambda x: (-x["score"], art_key(x["no"])))
    return out


@bp.route("/api/regagent/alio/rule", methods=["POST"])
def ra_alio_rule():
    """알리오 규정 현행본 → 조문. body: {orgId, idx, category, table, idxName, mod, q}"""
    b = _body()
    rule = {"orgId": str(b.get("orgId") or ""), "idx": str(b.get("idx") or ""), "category": str(b.get("category") or ""),
            "table": str(b.get("table") or "COMM_RULE"), "idxName": str(b.get("idxName") or "RULE_NO"), "mod": str(b.get("mod") or "")}
    if not re.fullmatch(r"[A-Za-z0-9]{2,12}", rule["orgId"]) or not re.fullmatch(r"\d{1,12}", rule["idx"]) \
            or not re.fullmatch(r"[A-Z_]{1,30}", rule["table"]) or not re.fullmatch(r"[A-Z_]{1,30}", rule["idxName"]) \
            or (rule["category"] and rule["category"] not in alio.CATEGORIES):
        return jsonify({"success": False, "error": "규정 정보가 올바르지 않습니다."}), 400
    try:
        r = alio.rule_text(rule)
    except alio.AlioError as e:
        return _alio_err(e)
    p = parse_text(r["text"], clean=True)
    ranked = _alio_rank(p["articles"], b.get("q") or "", str(b.get("kw") or "")[:40])
    warn = "" if p["articles"] else "“제N조” 형식의 조문을 찾지 못했습니다. 원문 링크로 확인하세요."
    return jsonify({"success": True, "file": r["file"], "versions": len(r["files"]), "count": len(p["articles"]),
                    "toc": [f"{art_label(a['no'])}({a['title']})" for a in p["articles"] if not a["deleted"]][:80],
                    "articles": ranked[:12], "url": alio.BASE + alio.detail_url(rule), "warning": warn,
                    "excerpt": "" if p["articles"] else r["text"][:3000]})


@bp.route("/api/regagent/graph")
def ra_graph():
    return jsonify({"success": True, **citation_graph()})


# ══════════════════════════════════════════════════════════════════════════
# 12. 에이전트 모드 — 한 문장 지시 → 작업 계획(종류·대상 내규·조문·의도)
# ══════════════════════════════════════════════════════════════════════════
_ENACT_RE = re.compile(r"(제정|새로\s*만들|새\s*(?:내규|규정|규칙|지침)|만들어\s*(?:줘|주세요|야)|만들고\s*싶|신규\s*(?:내규|규정|지침))")
_BULK_RE = re.compile(r"[“\"'「]?([가-힣A-Za-z0-9·()\s]{2,24}?)[”\"'」]?\s*(?:을|를|에서)\s*[“\"'「]?([가-힣A-Za-z0-9·()\s]{2,24}?)[”\"'」]?\s*(?:으로|로)\s*[가-힣\s]{0,14}?(?:바꾸|바꿔|바뀌|변경|정비|교체|고치|고쳐)")
_ARROW_RE = re.compile(r"[“\"'「]?([가-힣A-Za-z0-9·()]{2,24})[”\"'」]?\s*(?:→|->|=>)\s*[“\"'「]?([가-힣A-Za-z0-9·()]{2,24})[”\"'」]?")
_LAW_IN_RE = re.compile(r"「([^」]{2,40}(?:법|법률|시행령|시행규칙))」|([가-힣·\s]{2,30}?(?:법|법률)(?:\s*시행령|\s*시행규칙)?)(?=\s|이|가|의|을|를|에|$)")


_COMPARE_RE = re.compile(r"(다른\s*(?:공공)?기관|타\s*기관|타\s*공공기관|공공기관들?|알리오|ALIO|벤치마킹|사례)", re.I)
_COMPARE_STOP = {"다른", "기관", "기관은", "기관들", "공공기관", "타기관", "알리오", "어떻게", "규정했", "규정했는지", "정했는지",
                 "정했어", "알려줘", "알려", "찾아줘", "찾아", "보여줘", "비교", "비교해줘", "사례", "있는지", "있어", "궁금해",
                 "벤치마킹", "참고", "하는지", "운영하는지", "운영", "관리", "규정", "규칙", "지침", "내규", "사규", "기준"}


def compare_keyword(t: str) -> str:
    """“다른 기관은 재택근무를 어떻게 규정했어?” → “재택근무” (규정명 검색어)."""
    q = re.search(r"[「“\"']([^」”\"']{2,20})[」”\"']", t or "")
    if q:
        return re.sub(r"\s*(규정|규칙|지침|요령|기준|세칙)$", "", q.group(1)).strip()
    # “직장 내 괴롭힘 규정” → 규정·지침 바로 앞 낱말(앞의 꾸밈말 1~2개 포함)
    m = re.search(r"([가-힣]{2,10})\s*(?:관련\s*)?(?:규정|지침|규칙|요령|기준)(?![가-힣])", t or "")
    if m and not re.match(r"(벤치마킹|다른|공공기관|알리오|어떤|무슨|관련|기관|내부)", m.group(1)):
        return m.group(1)[:20]                          # 규정명 검색은 글자 그대로 맞추므로 바로 앞 한 낱말
    best = ""
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", t or ""):
        w2 = _JOSA_TAIL.sub("", w) if len(w) > 2 else w
        w2 = re.sub(r"(규정|규칙|지침|요령|기준|세칙)$", "", w2) or w2
        if (len(w2) < 2 or w in _COMPARE_STOP or w2 in _COMPARE_STOP or w2 in _STOP
                or re.search(r"기관\S*$|^기관", w2) or re.match(r"(규정|정했|정하|어떻|알려|찾아|보여|궁금|있는|하는|되어|됐|했|벤치마킹|참고|만들|새로|공시|수정|운영법)", w2)
                or re.fullmatch(r"제?\d+(조|년|월|일|항|호)?(의\d+)?", w2)):
            continue
        if len(w2) > len(best):
            best = w2
    return best[:20]


_ASK_RE = re.compile(r"(\?|？|나요|인가요|있나요|되나요|까요|습니까|ㄴ가요|는지|궁금|어떻게\s*(?:되|하)|얼마|누가|누구|언제|어디|무엇|뭐야|뭔가요|맞나요|해도\s*되"
                     r"|알려\s*(?:줘|주세요|줄래|주실|달라)|며칠|몇\s*(?:일|시간|명|회|번|개월|년)|이야\s*$|가능해|한도|기준은)")
# 고치라는 요청 — “개정된·신설된·삭제된·반영되” 같은 수식어는 고치라는 뜻이 아니다
_EDIT_RE = re.compile(r"(개정(?![된되])|고쳐|고치|바꿔|바꾸|신설(?![된되])|삭제(?![된되])|만들어|제정(?![된되])|정비(?![된되])|반영(?![된되])|올려|내려|늘려|줄여|추가해|빼\s*줘|작성해)")
_ASK_FIRST = re.compile(r"((?<=[가-힣])도\s*되나|해야\s*하나|해야\s*되나|하면\s*되나|할\s*수\s*있나)")   # “올려도 되나요?”는 묻는 말


def heuristic_plan(req: str) -> dict:
    t = (req or "").strip()
    plan = {"mode": "amend", "intent": t, "reasoning": []}
    if ((_ASK_RE.search(t) and not _EDIT_RE.search(t)) or _ASK_FIRST.search(t)) and not _COMPARE_RE.search(t):
        plan.update(mode="advise", question=t)
        plan["reasoning"].append("내규 해석·적용을 묻는 질의로 판단 — 근거 조문을 찾아 회신")
        return plan
    if (_COMPARE_RE.search(t) and not _ENACT_RE.search(t) and not re.search(r"(개정|고쳐|고치|바꿔|바꾸|정비|수정|신설|삭제|반영)", t)
            and not re.search(r"제\s*\d+\s*조", t)):
        kw = compare_keyword(t)
        if kw:
            plan.update(mode="compare", keyword=kw)
            plan["reasoning"].append(f"다른 공공기관 사례를 묻는 요청으로 판단 — 알리오에서 “{kw}” 규정 조회")
            return plan
    bulk_kw = re.search(r"(모든|전체|일괄|모두|전\s*내규|명칭|부서명|직위|기관명|이름이\s*바뀌)", t)
    if not bulk_kw and not re.search(r"(규정|규칙|지침|세칙|요령|정관|기준|매뉴얼|제\s*\d+\s*조)", t):
        mb = _BULK_RE.search(t)                # “경영지원팀을 경영관리팀으로 바꿔줘” — 특정 내규 없이 조직·직위명만 바꾸면 일괄 정비
        if mb and re.search(r"(팀|부|실|처|본부|단|센터|과|원장|사장|이사|위원회|위원장|관|국)$", mb.group(1).strip()):
            bulk_kw = mb
    m = _ARROW_RE.search(t) or (_BULK_RE.search(t) if bulk_kw else None)
    if m and (bulk_kw or "→" in t or "->" in t):
        _clean = lambda w: re.sub(r"\s*(?:명칭|이름|용어|표현|표기|단어|문구)$", "", w.strip()).strip()
        plan.update(mode="bulk", old=_clean(m.group(1)), new=_clean(m.group(2)))
        plan["reasoning"].append(f"“{plan['old']}” → “{plan['new']}” 용어 변경이므로 모든 내규 일괄 정비로 판단")
        return plan
    lm = None
    if re.search(r"(개정|바뀌|변경|시행|신설|삭제)", t):
        for mm in _LAW_IN_RE.finditer(t):
            nm = (mm.group(1) or mm.group(2) or "").strip()
            if nm and not nm.endswith(("규정", "규칙")) or (nm and "법" in nm):
                lm = nm
                break
    short_law = re.search(r"([가-힣]{2,30}법)\s*(?:이|가|은|는|을|를)?\s*(?:개정|바뀌|변경|시행)", t)   # “청탁금지법이 바뀌었어”
    if not lm and short_law:
        lm = short_law.group(1)
    if lm and (re.search(r"(상위법|법령|법률|시행령|시행규칙|「)", t) or short_law) and not re.search(r"(내규|규정|규칙|지침)을\s*(?:고치|개정)", t):
        plan.update(mode="upper", law=re.sub(r"\s+", " ", lm),
                    arts=[re.sub(r"\s+", "", x) for x in re.findall(r"제\s*\d+\s*조(?:\s*의\s*\d+)?", t)])
        plan["reasoning"].append(f"상위 법령 「{plan['law']}」 개정에 따른 영향 분석으로 판단")
        return plan
    if _ENACT_RE.search(t) and not re.search(r"개정", t):
        tm = re.search(r"([가-힣A-Za-z0-9·\s]{2,30}?(?:규정|규칙|지침|요령|기준|세칙))", t)
        title = re.sub(r"^(새로운?|신규|새)\s*", "", tm.group(1).strip()) if tm else ""
        if not title:                                  # “드론 관련 내규를 새로 만들어줘” → “드론 운영지침”
            kw = compare_keyword(t)
            title = f"{kw} 운영지침" if kw else ""
        core = re.sub(r"\s*(시행세칙|운영지침|운영규정|운영규칙|관리규정|관리규칙|관리지침|규정|규칙|세칙|지침|요령|기준)$", "", title).strip()
        plan.update(mode="enact", title=title, purpose=f"{core}에 관한 사항" if core else "", contents="")
        plan["reasoning"].append("새 내규를 만드는 요청으로 판단" + (f" — 내규명 「{title}」" if title else ""))
        return plan
    plan["reasoning"].append("기존 내규 조문을 고치는 요청으로 판단")
    return plan


def _resolve_targets(plan: dict, req: str):
    """개정: 대상 내규·조문을 고른다(명시된 내규명 우선, 없으면 유사 검색)."""
    reg = None
    for r in sorted(all_regs(), key=lambda x: -len(x["title"])):
        if _nk(r["title"]) and _nk(r["title"]) in _nk(req):
            reg = r
            break
    if not reg and plan.get("reg_hint"):
        reg = find_reg("", plan["reg_hint"])
    q = " ".join(x for x in [plan.get("intent") or req, req] if x)[:600]
    sim = similar_search(q, "", 15)
    if not reg and sim["regs"]:
        reg = find_reg(sim["regs"][0]["slug"])
        plan["reasoning"].append(f"유사 검색으로 「{reg['title']}」{_josa(reg['title'], ('을', '를'))} 대상으로 선택(관련도 1위)")
    elif reg:
        plan["reasoning"].append(f"요청에 내규명 「{reg['title']}」{_josa(reg['title'], ('이', '가'))} 있어 대상으로 선택")
    if not reg:
        return
    plan["reg"] = {"slug": reg["slug"], "title": reg["title"], "category": reg["category"]}
    nos = [re.sub(r"\s+", "", x).replace("제", "").replace("조", "") for x in re.findall(r"제\s*\d+\s*조(?:\s*의\s*\d+)?", req)]
    asked = nos
    nos = [n for n in nos if any(a["no"] == n and not a["deleted"] for a in reg["articles"])]
    missing = [n for n in asked if n not in nos]
    if missing:
        plan["reasoning"].append(f"요청한 {', '.join(art_label(n) for n in missing)}는 「{reg['title']}」에 없거나 삭제된 조라 "
                                 + ("나머지 조문만 대상으로 합니다" if nos else "내용 일치도로 조문을 골랐습니다"))
        plan["missing"] = missing
    if not nos:
        g = next((g for g in sim["regs"] if g["slug"] == reg["slug"]), None)
        if not g:
            g = (similar_search(q + " " + reg["title"], "", 15)["regs"] or [{}])
            g = next((x for x in g if x.get("slug") == reg["slug"]), None)
        if g:
            top = g["articles"][0]["score"] if g["articles"] else 0
            nos = [a["no"] for a in g["articles"] if a["score"] >= top * 0.55][:3]
            if nos:
                plan["reasoning"].append("관련 조문: " + ", ".join(art_label(n) for n in nos) + " (내용 일치도 기준)")
    else:
        plan["reasoning"].append("요청에 적힌 조문: " + ", ".join(art_label(n) for n in nos))
    plan["articles"] = [{"no": a["no"], "title": a["title"]} for a in reg["articles"] if a["no"] in nos]


@bp.route("/api/regagent/plan", methods=["POST"])
def ra_plan():
    b = _body()
    req = (b.get("request") or "").strip()
    if len(req) < 4:
        return jsonify({"success": False, "error": "무엇을 하고 싶은지 한 문장으로 적어 주세요."}), 400
    plan = heuristic_plan(req)
    provider, key, model = _ai_conf(b)
    plan["ai"] = False
    if key or provider == "ollama":
        mdl = model or _CTX["default_model_for"](provider, key)
        system = f"""당신은 {ORG['org_name']} {ORG['reg_word']} 제·개정 에이전트의 작업 계획 담당입니다.
사용자의 한 문장 요청을 분석해 JSON만 반환하세요.
{{"mode": "enact|amend|bulk|upper|compare|advise",
  "intent": "개정·제정 의도를 실무 문장으로 1~2문장",
  "reg_hint": "개정 대상 내규명(알 수 있으면, 없으면 빈 문자열)",
  "title": "제정 시 내규명(없으면 제안)", "purpose": "제정 목적", "contents": "제정 시 주요 내용(줄바꿈 구분, '제목: 내용')",
  "old": "일괄 정비 시 바뀌기 전 용어", "new": "바뀐 뒤 용어",
  "law": "상위법 영향 분석 시 법령명", "arts": ["제N조"],
  "keyword": "compare 일 때 알리오에서 찾을 규정명 핵심어(예: 여비, 재택근무)",
  "why": "이렇게 판단한 이유 1문장"}}
- enact: 새 내규를 만듦 / amend: 특정 내규 조문을 고침 / bulk: 기관명·부서명·직위·내규명 등 용어를 모든 내규에서 바꿈 / upper: 상위 법령이 바뀌어 영향받는 내규를 찾음 / compare: 다른 공공기관(알리오)은 어떻게 정했는지 사례를 찾음 / advise: 내규를 고치지 않고 해석·적용(가능 여부, 금액, 절차 등)을 물음"""
        text, err = _CTX["ai_generate"](provider, key, mdl, system, f"요청: {req}", max_tokens=1200, temperature=0.1, json_mode=True)
        if not err:
            try:
                d = _json_from(text)
                if d.get("mode") in ("enact", "amend", "bulk", "upper", "compare", "advise"):
                    keep = plan.get("reasoning", [])
                    plan = {"mode": d["mode"]}
                    for k in ("intent", "reg_hint", "title", "purpose", "contents", "old", "new", "law", "keyword"):
                        v = d.get(k)
                        if isinstance(v, list):          # 목록으로 와도 문장으로 잇는다
                            v = "\n".join(_strs(v)) if k == "contents" else " ".join(_strs(v))
                        if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip():
                            plan[k] = str(v).strip()[:2000]
                    plan["arts"] = [a for a in (_art_no(x) for x in _strs(d.get("arts"))) if a]
                    plan["reasoning"] = [f"AI 판단: {d.get('why') or plan['mode']}"] + [x for x in keep if x.startswith("“")]
                    plan["ai"] = True
                    plan["model"] = f"{provider}:{mdl}"
            except Exception:
                plan["reasoning"].append("AI 계획을 해석하지 못해 규칙 기반 판단을 사용")
        else:
            plan["reasoning"].append(f"AI 호출 실패로 규칙 기반 판단 사용({err[:60]})")
    if plan["mode"] == "advise":
        plan["question"] = req
    if plan["mode"] == "amend":
        plan.setdefault("intent", req)
        _resolve_targets(plan, req)
        if not plan.get("reg"):
            return jsonify({"success": False, "error": "개정할 내규를 찾지 못했습니다. 내규명을 함께 적어 주세요.", "plan": plan}), 404
    if plan["mode"] == "enact":
        plan.setdefault("purpose", "")
        plan["title"] = plan.get("title") or ""
    if plan["mode"] == "compare":
        plan["keyword"] = str(plan.get("keyword") or compare_keyword(req))[:20]
        if not plan["keyword"]:
            return jsonify({"success": False, "error": "무엇에 관한 규정을 찾을지 적어 주세요. 예) 다른 기관은 재택근무를 어떻게 정했어?", "plan": plan}), 400
    if plan["mode"] == "bulk" and not (plan.get("old") and plan.get("new")):
        plan["mode"] = "amend"
        _resolve_targets(plan, req)
    plan["request"] = req
    return jsonify({"success": True, "plan": plan})


# ══════════════════════════════════════════════════════════════════════════
# 내규 자문 — 질의에 근거 조문을 찾아 답한다(AI 가 있으면 근거 번호를 단 회신, 없으면 관련 문장 안내)
# ══════════════════════════════════════════════════════════════════════════
_ADV_CONCL = ("가능", "불가", "조건부 가능", "해당 규정", "규정 없음", "확인 필요")


def _key_sents(body: str, toks: list, n: int = 2) -> list:
    """조문에서 질의 낱말이 가장 많이 나오는 문장(항·호 단위) — 낱말이 있는 문장에 숫자·금액·기간이 있으면 가산.
    PDF 에서 온 글의 끊긴 띄어쓰기(“숙박비 상 한액”)는 빈칸을 빼고 견준다."""
    units = [u.strip() for u in re.split(r"\n|(?<=다\.)\s+", body or "") if len(u.strip()) >= 6]
    tk = [re.sub(r"\s+", "", t) for t in toks if t]
    scored = []
    for i, u in enumerate(units):
        us = re.sub(r"\s+", "", u)
        hit = sum(2 for t in tk if t in us)
        if hit:
            scored.append((hit + (1 if re.search(r"\d+\s*(?:원|일|개월|년|시간|%|명|회|배|호봉|점)", u) else 0), i, u))
    pick = sorted(sorted(scored, key=lambda x: (-x[0], x[1]))[:n], key=lambda x: x[1])
    return [u[:260] for _, _, u in pick]


# 자문 질의에서 검색어가 되면 안 되는 말: 묻는 말·어미(“얼마인가요”, “받을”, “누구”)
_ADV_QSTOP = {"얼마", "어떻게", "누가", "누구", "언제", "어디", "무엇", "무슨", "며칠", "몇", "어느", "어떤", "왜", "하나요", "되나요",
              "있나요", "없나요", "받을", "받나요", "받아야", "하면", "되면", "되는", "하는", "다른", "해야", "해도", "되어", "인가요",
              "알려", "알려줘", "알려주세요", "궁금", "궁금합니다", "나오", "나와", "주나", "줘야", "되요", "돼요", "경우에", "때", "가능", "가능한가요", "필요", "필요한가요", "내규",
              "규정상", "규정에", "따르면", "기준", "연간", "서면", "이야", "뭐야", "뭔가요", "있어", "돼", "되나"}
_ADV_TAIL = re.compile(r"(?:인가요|이에요|예요|인지요|인지|나요|ㄴ가요|습니까|ㅂ니까|까요|으려면|려면|으면|면서|해야|이야|야|이죠|죠|은지|는지)$")
_ADV_HA = re.compile(r"(?:하려면|하면|했는데|하는데|해서)$")          # “야근하면” → 야근(“겸하려면”은 두 글자가 안 남아 위 규칙으로)
_CORPUS = {"key": None, "txt": ""}


def _corpus_text() -> str:
    regs = all_regs()
    if _CORPUS["key"] != id(regs):
        _CORPUS.update(key=id(regs), txt="\n".join(re.sub(r"\s+", "", a["title"] + a["body"])
                                                    for r in regs for a in r["articles"] if not a["deleted"]))
    return _CORPUS["txt"]


# 질의에 흔히 붙는 말 — 이 말이 들어간 조문이 없다고 “함께 다룬 조문 없음”으로 보지는 않는다
_ADV_GENERIC = {"기간", "절차", "방법", "대상", "지급", "사용", "신청", "범위", "요건", "금액", "한도", "상한", "상한액", "시간",
                "횟수", "일수", "서류", "내용", "처리", "적용", "제출", "승인", "허가", "직원", "임직원", "근무", "조건", "기한",
                "얼마나", "며칠", "가능", "여부", "규정", "경우", "최대", "최소", "이상", "이하", "이내", "수준"}


def _adv_query(q: str):
    """질의 → (검색 문장, 검색어, 어디에도 없는 검색어, 낱말 묶음). 묻는 말을 빼고, 본문에 없는 4자 이상 복합어는 두 글자씩 나눠 본다
    (“연차휴가” → 연차·휴가: 원문은 “연차유급휴가”). 일상어는 내규 용어를 더한다(“출장비” → 여비).
    낱말 묶음 [{w, alts, generic, syn}]은 근거 조문이 질의의 핵심 낱말을 함께 다루는지 볼 때 쓴다."""
    corpus = _corpus_text()
    words, miss = [], []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", q or ""):
        w2 = _ADV_HA.sub("", w) if len(w) > 3 and len(_ADV_HA.sub("", w)) >= 2 else w
        w2 = _ADV_TAIL.sub("", w2) if len(w2) > 2 else w2
        w2 = _strip_josa(w2) if len(w2) > 2 else w2
        if not w2 or w2 in _ADV_QSTOP or w in _ADV_QSTOP or w2 in _STOP or len(w2) < 2:
            continue
        if w2 not in words:
            words.append(w2)
    extra, groups = [], []
    for w in words:
        parts = [w[i:i + 2] for i in range(0, len(w) - 1, 2)] if re.fullmatch(r"[가-힣]{4,}", w) else []
        parts = [p for p in parts if p in corpus and p not in _ADV_QSTOP]
        syn = _syn(w)
        if w not in corpus and not syn:
            miss.append(w)                                    # 원문에 그대로는 없는 말(“가족수당”) — 쪼갠 말로 찾아도 단정하지 않는다
        use = parts if parts and (w not in corpus or len(w) >= 4) else []
        extra += syn + use                                    # “연차휴가” → 연차·휴가(원문 “연차유급휴가”), “출장비” → 여비
        groups.append({"w": w, "alts": [w] + syn + use, "syn": syn,
                       "generic": w in _ADV_GENERIC or (w not in corpus and not syn and not use)})
    toks = words + [p for p in dict.fromkeys(extra) if p not in words]
    return " ".join(toks), toks, miss, groups


def _adv_cover(text: str, groups: list) -> int:
    """조문이 다루는 핵심 낱말 묶음 수(낱말·쪼갠 말·내규 용어 중 하나라도 나오면 그 묶음을 다룬 것으로 본다)."""
    t = re.sub(r"\s+", "", text or "")
    return sum(1 for g in groups if not g["generic"] and any(re.sub(r"\s+", "", a) in t for a in g["alts"]))


_ADV_WEAK_TITLE = re.compile(r"^(?:목적|정의|용어의\s*정의|기타|적용\s*범위)$")


def advise_sources(q: str, slug: str = "", cap: int = 10) -> dict:
    """질의 → 근거 후보 조문(주 조문 + 그 조문이 인용·준용하는 조문 + 시행세칙의 관련 조문 + 인용한 별표)."""
    query, toks, miss, groups = _adv_query(q)
    core = sum(1 for g in groups if not g["generic"])
    regs = {r["slug"]: r for r in all_regs()}
    names = _reg_names()
    flat = []
    # “여비규정 제15조”처럼 조문을 짚어 물으면 그 조를 먼저
    for mm in re.finditer(r"([가-힣A-Za-z·\s]{2,40}?(?:규정|규칙|지침|세칙|요령|기준|정관|매뉴얼))\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", q or ""):
        r = next((x for x in regs.values() if _nk(x["title"]) == _nk(mm.group(1).strip())), None)
        if r and (not slug or r["slug"] == slug):
            flat.append((1e6, r["slug"], mm.group(2) + (("의" + mm.group(3)) if mm.group(3) else "")))
    res = similar_search(query or q, "", 40 if slug else 10) if toks else {"regs": [], "semantic": False}
    for g in res["regs"]:
        if slug and g["slug"] != slug:
            continue
        tboost = 1.5 if any(len(t) >= 3 and t in re.sub(r"\s+", "", g["title"]) for t in toks) else 1.0   # 질의 낱말이 내규명이면 그 내규 조문을 먼저
        for a in g["articles"][:3]:
            w = 0.4 if _ADV_WEAK_TITLE.match(str(a.get("title") or "").strip()) else 1.0                       # 목적·정의·기타 조는 뒤로
            flat.append((a["score"] * w * tboost, g["slug"], a["no"]))
    # 질의 낱말이 내규명이면(“공무국외출장 …”) 그 내규 안에서 나머지 낱말(쪼갠 말 포함)이 나오는 조문을 앞에
    top0 = max([x[0] for x in flat if x[0] < 1e6] or [1.0])
    for r in regs.values():
        rt = re.sub(r"\s+", "", r["title"])
        hit_t = [t for t in toks if len(t) >= 3 and t in rt]
        if not hit_t or (slug and r["slug"] != slug):
            continue
        rest = [t for t in toks if t not in hit_t and not (t in rt)]
        sc_a = []
        for a in r["articles"]:
            if a["deleted"] or _ADV_WEAK_TITLE.match(str(a.get("title") or "").strip()):
                continue
            tx = re.sub(r"\s+", "", a["title"] + a["body"])
            k = sum(2 if t in a["title"] else 1 for t in rest if t in tx)
            if k:
                sc_a.append((k, a["no"]))
        for k, no in sorted(sc_a, key=lambda x: -x[0])[:2]:
            flat.append((top0 * (1.1 + 0.1 * k), r["slug"], no))
    if slug and not flat and slug in regs:                    # 범위를 정했는데 검색어가 안 맞으면 낱말이 나오는 조문이라도
        for a in regs[slug]["articles"]:
            if not a["deleted"] and any(t in re.sub(r"\s+", "", a["title"] + a["body"]) for t in toks):
                flat.append((0.1, slug, a["no"]))
    best = {}
    for sc, sl, no in flat:
        if sc > best.get((sl, no), -1):
            best[(sl, no)] = sc
    if core >= 2:                                             # 질의의 핵심 낱말을 함께 다룬 조문을 앞으로(“연차휴가 이월” — 예산 이월 조문은 뒤로)
        for (sl, no), sc in best.items():
            a = next((x for x in regs[sl]["articles"] if x["no"] == no), None) if sl in regs else None
            if a and sc < 1e6:
                best[(sl, no)] = sc * (0.6 + 0.4 * _adv_cover(a["title"] + a["body"], groups) / core)
    flat = sorted([(sc, sl, no) for (sl, no), sc in best.items()], key=lambda x: -x[0])
    out, seen = [], set()

    def add(sl, no, role, why=""):
        r = regs.get(sl)
        a = next((x for x in r["articles"] if x["no"] == str(no)), None) if r else None
        if not a or a["deleted"] or (sl, a["no"]) in seen or len(out) >= cap:
            return None
        seen.add((sl, a["no"]))
        src = {"id": len(out) + 1, "slug": sl, "reg": r["title"], "no": a["no"], "title": a["title"],
               "body": a["body"][:1500], "role": role, "why": why, "revision": r.get("revision", ""),
               "rev_date": rev_date(r.get("revision", "")), "keys": _key_sents(a["body"], toks),
               "appendix": bool(re.search(r"별표|별지", a["body"]) and r.get("appendix"))}
        out.append(src)
        return src

    def add_appx(m):                                          # 금액·기준표가 별표에 있으면 그 별표도 근거로(“〔별표 2〕에서 정하는 바에 따라”)
        ap = regs[m["slug"]].get("appendix") or ""
        own = [x.group(1) for x in re.finditer(r"별표\s*(\d+)", m["body"])      # 「복무규정」〔별표2〕처럼 다른 내규의 별표는 빼고
               if not re.search(r"」\s*[\[［〔【<＜(]?\s*$", m["body"][max(0, x.start() - 4):x.start()])]
        for bn in (list(dict.fromkeys(own))[:2] if ap else []):
            hs = [(mm.start(), mm.group(1)) for mm in re.finditer(r"^[\[［〔【<＜]\s*별표\s*(\d+)", ap, re.M)]
            for i, (st, num) in enumerate(hs):
                if num == bn and len(out) < cap and (m["slug"], "별표" + bn) not in seen:
                    seen.add((m["slug"], "별표" + bn))
                    blk = ap[st:hs[i + 1][0] if i + 1 < len(hs) else len(ap)].strip()
                    head = blk.split("\n", 2)
                    out.append({"id": len(out) + 1, "slug": m["slug"], "reg": m["reg"], "no": "", "appx": f"별표 {bn}",
                                "title": head[1].strip()[:40] if len(head) > 1 else "", "body": blk[:1800], "role": "appx",
                                "why": f"{art_label(m['no'])}에서 인용", "revision": m["revision"], "rev_date": m["rev_date"],
                                "keys": _key_sents(blk, toks), "appendix": False})
    top = flat[0][0] if flat else 0
    picked = [(sc, add(sl, no, "main")) for sc, sl, no in flat[:5]]
    strong = [m for sc, m in picked if m and (sc >= top * 0.5 or m["id"] <= 2)]   # 약한 주 조문까지 넓히면 잡음만 는다
    for m in strong:
        add_appx(m)
    for m in strong:
        r = regs[m["slug"]]
        for rno, raw, _ in internal_refs(m["body"])[:3]:          # 같은 내규에서 인용한 조문(“제12조에 따른 …”)
            add(m["slug"], rno, "ref", f"{art_label(m['no'])}에서 인용")
        for j in [j for j in jun_relations(r, names) if j["no"] == m["no"]]:   # 준용하는 다른 내규 조문
            for t in j["targets"]:
                if t["kind"] == "reg":
                    tr = next((x for x in regs.values() if x["title"] == t["name"]), None)
                    for an in t["arts"][:2]:
                        mm = re.match(r"제(\d+)조(?:의(\d+))?", an)
                        if tr and mm:
                            add(tr["slug"], mm.group(1) + (("의" + mm.group(2)) if mm.group(2) else ""), "jun",
                                f"「{m['reg']}」 {art_label(m['no'])}에서 준용")
        child = next((x for x in regs.values() if _nk(x["title"]) == _nk(r["title"] + " 시행세칙")), None)
        if child:                                                 # 시행세칙이 이 조를 받아 정한 세부 기준(모 규정을 가리킨 인용만)
            tp = r"\s*".join(map(re.escape, re.sub(r"\s+", "", r["title"])))
            head = r"(?:「\s*" + tp + r"\s*」|(?<![가-힣」])(?:규정|규칙|정관))\s*"
            n0, _, g0 = m["no"].partition("의")
            pat = re.compile(head + r"제\s*" + n0 + (r"\s*조\s*의\s*" + g0 + r"(?!\d)" if g0 else r"\s*조(?!\s*의)"))
            for ca in child["articles"]:
                if not ca["deleted"] and pat.search(ca["body"]):
                    add(child["slug"], ca["no"], "child", f"「{r['title']}」 {art_label(m['no'])}의 세부 기준")
                    break
    laws = {}
    for sc in out:                                                # 근거가 되는 조문(질의 낱말이 나온 주 조문·별표)이 인용한 법령만
        if sc["role"] not in ("main", "appx") or not sc["keys"]:
            continue
        for mm in _QUOTED_NAME.finditer(sc["body"]):
            nm = re.sub(r"\s+", " ", mm.group(1)).strip()
            if _LAW_NAME_OK.search(nm) and _nk(nm) not in names:
                nm = _law_aliases(nm)[-1]
                ma = _ART_AFTER.match(sc["body"][mm.end():mm.end() + 60])
                art = (re.match(r"제\d+조(?:의\d+)?", re.sub(r"\s+", "", ma.group(1))) or [""])[0] if ma else ""
                x = laws.setdefault(nm, {"name": nm, "art": art, "from": sc["id"]})
                if not x["art"] and art:
                    x["art"] = art
    # 핵심 낱말이 둘 이상인데 그 낱말을 모두 다룬 주 조문(별표 포함)이 없으면 — 단정하지 않고 빠진 낱말을 알린다
    gap = []
    if core >= 2:
        cov = [(_adv_cover(x["title"] + x["body"], groups), x) for x in out if x["role"] in ("main", "appx")]
        if cov and max(c for c, _ in cov) < core:
            bx = max(cov, key=lambda c: c[0])[1]
            t = re.sub(r"\s+", "", bx["title"] + bx["body"])
            gap = [g["w"] for g in groups if not g["generic"] and not any(re.sub(r"\s+", "", a) in t for a in g["alts"])]
            gap = gap or [g["w"] for g in groups if not g["generic"]]
    return {"tokens": toks, "unmatched": miss, "semantic": res.get("semantic", False), "sources": out,
            "laws": list(laws.values())[:6], "scoped": bool(slug), "core": [g["w"] for g in groups if not g["generic"]],
            "gap": gap, "mapped": {g["w"]: g["syn"] for g in groups if g["syn"]}}


def _adv_rule_answer(q: str, S: dict) -> dict:
    src = S["sources"]
    miss = S.get("unmatched") or []
    if not src:
        return {"conclusion": "규정 없음",
                "answer": ("지정한 내규에는 질의와 관련된 조문이 없습니다. 대상을 비우고 모든 내규에서 다시 물어보세요." if S.get("scoped")
                           else "질의와 관련된 조문을 찾지 못했습니다. 낱말을 바꾸거나(예: 출장비 → 여비) 대상 내규를 지정해 다시 물어보세요."),
                "basis": [], "conditions": [], "caveats": ["내규에 정함이 없으면 상위 법령이나 소관 부서의 해석을 확인하세요."], "followups": []}
    mains = [x for x in src if x["role"] == "main"][:3]
    ap = [x for x in src if x["role"] == "appx"]
    lst = ", ".join(f"「{x['reg']}」 {art_label(x['no'])}" + (f"({x['title']})" if x["title"] else "") for x in mains)
    basis = [{"src": x["id"], "point": " / ".join(x["keys"]) or (x["body"][:160] + "…"), "verified": True} for x in mains]   # 조문에서 그대로 뽑은 문장
    extra = [x for x in src if x["role"] not in ("main", "appx")]
    basis += [{"src": x["id"], "point": " / ".join(x["keys"]) or f"{x['appx']} {x['title']}", "verified": True} for x in ap[:2]]
    gap, core = S.get("gap") or [], S.get("core") or []
    weak = bool(miss) or bool(gap) or not any(x["keys"] for x in mains)
    if weak:                                                      # 질의의 핵심 낱말이 어느 조문에도 없으면 단정하지 않는다
        if miss:
            why = f"“{'”, “'.join(miss[:3])}”{_josa(miss[:3][-1], ('이', '가'))} 나오는 조문은 찾지 못했습니다. "
        elif gap:                                                 # 낱말마다 조문은 있지만 함께 다룬 조문이 없다(“연차휴가” + “이월”)
            why = f"“{'”·“'.join(core[:4])}”{_josa(core[:4][-1], ('을', '를'))} 함께 다룬 조문은 찾지 못했습니다(“{'”, “'.join(gap[:3])}” 빠짐). "
        else:
            why = "질의 낱말이 직접 나오는 조문은 찾지 못했습니다. "
        ans = why + f"가까운 조문은 {lst}입니다. 해당 여부를 소관 부서에 확인하세요."
    else:
        ans = f"질의와 관련된 조문은 {lst}입니다. 아래 근거 조문의 해당 문장을 확인하세요."
        if ap:
            ans += f" 금액·기준은 {', '.join('「' + x['reg'] + '」 ' + x['appx'] for x in ap[:2])}에 있습니다."
        if extra:
            ans += f" 이 조문이 인용·준용하는 조문과 세부 기준 {len(extra)}건도 함께 보세요."
    return {"conclusion": "확인 필요" if weak else "해당 규정", "answer": ans, "basis": basis, "conditions": [], "caveats": [], "followups": []}


_ADV_CITE_GROUP = re.compile(r"\[\s*([0-9]+(?:\s*[,~\-–]\s*[0-9]+)+)\s*\]")


def _adv_cites(t: str, ids: set) -> str:
    """근거 번호 정리: [1,2]·[1-3] → [1][2][3], 제시하지 않은 번호·숫자 아닌 괄호 번호는 지운다."""
    def grp(m):
        out = []
        for part in re.split(r"\s*,\s*", m.group(1)):
            ab = re.split(r"\s*[~\-–]\s*", part)
            if len(ab) == 2 and ab[0].isdigit() and ab[1].isdigit() and 0 < int(ab[1]) - int(ab[0]) < 10:
                out += list(range(int(ab[0]), int(ab[1]) + 1))
            elif part.isdigit():
                out.append(int(part))
        return "".join(f"[{i}]" for i in out)
    t = _ADV_CITE_GROUP.sub(grp, str(t or ""))
    return re.sub(r"\[\s*([^\]\s]{1,6})\s*\]", lambda m: m.group(0) if re.fullmatch(r"[0-9]+", m.group(1)) and int(m.group(1)) in ids else "", t).strip()


_QUOTE_MIN, _QUOTE_GAP = 6, 80


def _quote_ok(point: str, body: str) -> bool:
    """AI가 “원문 그대로” 인용했다는 말이 조문에 실제로 있는지(빈칸·따옴표·문장부호 무시).
    “…”로 줄인 인용은 조각마다 6자 이상이어야 하고, 원문에 그 차례대로 80자 안쪽 간격으로 나와야 한다.
    짧은 조각(“국외 … 10분의 3을”)은 아무 곳에서나 맞기 쉬워 대조할 수 없다고 본다(False → 사람이 원문 대조)."""
    norm = lambda t: re.sub(r"[\s“”‘’\"'「」『』〔〕\[\]().,·ㆍ:;]+", "", t or "")
    b = norm(body)
    segs = [x for x in (norm(x) for x in re.split(r"…|\.\.\.|/", point or "")) if x]
    if not segs or any(len(x) < _QUOTE_MIN for x in segs):
        return False
    pos = None
    for x in segs:
        k = b.find(x) if pos is None else b.find(x, pos)
        if k < 0 or (pos is not None and k - pos > _QUOTE_GAP):
            return False
        pos = k + len(x)
    return True


def ai_advise(b: dict, S: dict):
    """AI 회신 → (dict, notice). 근거 번호는 실제 제시한 조문 안에서만 남긴다."""
    provider, key, model = _ai_conf(b)
    if not key and provider != "ollama":
        return None, ""
    if not S["sources"]:
        return None, ""
    mdl = model or _CTX["default_model_for"](provider, key)
    blocks = "\n\n".join(f"[{x['id']}] 「{x['reg']}」 {x.get('appx') or art_label(x['no'])}({x['title']})"
                          + (f" ※{x['why']}" if x["why"] else "") + f"\n{x['body']}" for x in S["sources"])
    _nocite = lambda t: re.sub(r"\[[0-9]+\]", "", str(t or ""))   # 앞 회신의 근거 번호는 이번 조문과 다르므로 뺀다
    hist = "".join(f"이전 질의: {str(h.get('q', ''))[:300]}\n이전 회신 요지: {_nocite(h.get('a'))[:500]}\n"
                   for h in (b.get("history") or [])[-3:] if isinstance(h, dict))
    system = f"""당신은 {ORG['org_name']}({ORG['org_short']}) {ORG['reg_word']} 자문 담당입니다. 직원의 질의에 아래 [근거 조문]만으로 답하세요.
- 조문에 없는 사실·숫자·절차를 지어내지 말 것. 근거가 부족하면 conclusion 을 "규정 없음" 또는 "확인 필요"로 하고 무엇을 확인해야 하는지 쓸 것.
- 답의 문장마다 근거 번호를 [1], [2]처럼 하나씩 붙일 것([1,2]처럼 묶지 말 것). 제시되지 않은 번호는 쓰지 말 것.
- 결론을 먼저, 공문서 문체(“…할 수 있습니다”, “…에 해당합니다”)로 간결하게.
- 해석이 갈릴 수 있는 부분, 상위 법령 확인이 필요한 부분은 caveats 에.
반드시 아래 JSON만 반환(설명·코드블록 금지):
{{"conclusion": "{'|'.join(_ADV_CONCL)} 중 하나",
  "answer": "회신 본문(3~6문장, 근거 번호 포함)",
  "basis": [{{"src": 1, "point": "그 조문에서 답의 근거가 되는 부분(원문 그대로 짧게 인용)"}}],
  "conditions": ["가능하다면 그 조건·절차·서류(조문에 있는 것만)"],
  "caveats": ["유의사항·확인 필요 사항"],
  "followups": ["직원이 이어서 물어볼 만한 질문 2~3개"]}}"""
    gap = S.get("gap") or []
    note = (f"\n※ 검색 참고: 질의의 “{'”, “'.join(gap[:3])}”{_josa(gap[:3][-1], ('을', '를'))} 직접 다룬 조문은 찾지 못했습니다. "
            "근거 조문에 없으면 단정하지 말 것.\n") if gap else ""
    user = f"{hist}질의: {b.get('question', '')}\n{note}\n[근거 조문]\n{blocks}"
    text, err = _CTX["ai_generate"](provider, key, mdl, system, user, max_tokens=2500, temperature=0.1, json_mode=True)
    if err:
        return None, f"AI 오류({err})로 관련 조문 안내만 드립니다."
    try:
        d = _json_from(text)
    except Exception:
        return None, "AI 응답을 해석하지 못해 관련 조문 안내만 드립니다."
    if not isinstance(d, dict) or not isinstance(d.get("answer"), str):
        return None, "AI 회신 형식이 맞지 않아 관련 조문 안내만 드립니다."
    ids = {x["id"] for x in S["sources"]}
    basis = []
    for x in d.get("basis") if isinstance(d.get("basis"), list) else []:
        if not isinstance(x, dict):
            continue
        v = x.get("src")
        if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit())):
            continue                                              # 1.9·true 같은 값은 근거 번호로 보지 않는다
        i = int(v)
        if i in ids and str(x.get("point") or "").strip():
            pt = str(x["point"]).strip()[:400]
            src_body = next((y["body"] for y in S["sources"] if y["id"] == i), "")
            basis.append({"src": i, "point": pt, "verified": _quote_ok(pt, src_body)})
    concl = str(d.get("conclusion") or "").strip()
    out = {"conclusion": concl if concl in _ADV_CONCL else "확인 필요", "answer": _adv_cites(d["answer"], ids)[:3000],
           "basis": basis[:8], "conditions": [_adv_cites(x, ids)[:300] for x in _strs(d.get("conditions"))][:6],
           "caveats": [_adv_cites(x, ids)[:300] for x in _strs(d.get("caveats"))][:6],
           "followups": [str(x).strip()[:120] for x in _strs(d.get("followups"))][:3],
           "model": f"{provider}:{mdl}"}
    if not out["answer"]:
        return None, "AI 회신이 비어 관련 조문 안내만 드립니다."
    bad = sum(1 for x in out["basis"] if not x["verified"])
    out["cite_check"] = {"n": len(out["basis"]), "ok": len(out["basis"]) - bad}
    if bad:                                                    # 사람이 대조할 곳을 짚어 준다(화면에 ⚠ 표시)
        out["caveats"].insert(0, f"AI가 인용한 문장 {bad}건은 근거 조문에서 그대로 확인하지 못했습니다. 해당 조문 원문과 대조하세요.")
    if bad and bad == len(out["basis"]) and out["conclusion"] in ("가능", "불가", "조건부 가능", "해당 규정"):
        out["conclusion"] = "확인 필요"                            # 확인된 인용이 하나도 없으면 단정하지 않는다
    if gap and out["conclusion"] != "규정 없음":
        out["conclusion"] = "확인 필요"                            # 핵심 낱말을 다룬 조문이 없으면 “가능·불가”로 단정하지 않는다
    if gap and not any(all(w in c for w in gap[:3]) for c in out["caveats"]):
        out["caveats"].append(f"질의의 “{'”, “'.join(gap[:3])}”{_josa(gap[:3][-1], ('을', '를'))} 직접 다룬 조문은 찾지 못했습니다. 소관 부서에 확인하세요.")
    if not out["basis"] and out["conclusion"] not in ("규정 없음", "확인 필요"):
        out["conclusion"] = "확인 필요"                            # 근거 없이 “가능·불가”를 단정하지 않는다
        out["caveats"].insert(0, "AI 회신이 근거 조문을 짚지 못했습니다. 아래 근거 조문을 직접 확인하세요.")
    return out, ""


@bp.route("/api/regagent/advise", methods=["POST"])
def ra_advise():
    """내규 자문. body: {question, slug?(대상 내규), history?:[{q,a}], provider/api_key/model}"""
    b = _body()
    q = (b.get("question") or "").strip()
    if len(re.sub(r"\s+", "", q)) < 4:
        return jsonify({"success": False, "error": "질의 내용을 한 문장 이상 적어 주세요."}), 400
    if len(q) > 1000:
        return jsonify({"success": False, "error": "질의가 너무 깁니다(1,000자 이내)."}), 400
    slug = (b.get("slug") or "").strip()
    if slug and not find_reg(slug, ""):
        return jsonify({"success": False, "error": "지정한 내규를 찾을 수 없습니다."}), 404
    S = advise_sources(q, slug)
    ans, notice = ai_advise(b, S)
    hint = ""
    if not ans:
        ans = _adv_rule_answer(q, S)
        provider, key, _ = _ai_conf(b)
        if not key and provider != "ollama":                      # 화면 안내(회신서에는 넣지 않는다)
            hint = "규칙 기반 안내입니다. AI 키를 넣으면 질의에 맞춘 회신(결론·조건·유의사항)을 받을 수 있습니다."
    return jsonify({"success": True, "question": q, "scope": slug, "ai": "model" in ans, "notice": notice or hint,
                    "semantic": S["semantic"], "tokens": S["tokens"], "unmatched": S.get("unmatched", []),
                    "gap": S.get("gap", []), "mapped": S.get("mapped", {}),
                    "sources": S["sources"], "laws": S["laws"], **ans})


# ══════════════════════════════════════════════════════════════════════════
# 작업 실적 대장 — 저장한 산출물(회신서·개정안·제출 패키지 …)의 메타데이터만 남긴다(본문·질의·이름은 남기지 않음)
# 쓰기 가능한 서버(로컬·VM)는 LEDGER_DIR(기본 ledger/)에 월별 JSONL 로 모으고, 읽기 전용 배포는 브라우저 대장만 쓴다
# ══════════════════════════════════════════════════════════════════════════
_LEDGER_KINDS = {"advise": "자문 회신", "enact": "제정안 문서", "amend": "개정안 문서", "submit": "심의 제출 패키지",
                 "bulk": "일괄 정비 문서", "plan": "추진계획표"}
_LEDGER_LOCK = threading.Lock()


def ledger_enabled() -> bool:
    """기관 전체 실적 대장은 기본으로 끈다. LEDGER_ENABLED=1 일 때만 서버에 모은다(브라우저 대장은 늘 동작)."""
    return (os.environ.get("LEDGER_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


def _ledger_dir() -> str:
    return os.environ.get("LEDGER_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger")


def ledger_record(b: dict) -> dict:
    """화면이 보낸 실적 → 저장할 메타데이터(정해진 칸만, 길이·범위 제한)."""
    import datetime as _dt
    kind = str(b.get("kind") or "")
    if kind not in _LEDGER_KINDS:
        raise ValueError("알 수 없는 산출물 종류입니다.")
    n = lambda k: _clamp_int(b.get(k), 0, 9999, 0)
    now = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=9)
    at = now.strftime("%Y-%m-%d %H:%M")
    sent = str(b.get("at") or "")                              # 나중에 다시 보낸 기록은 저장한 때(최근 7일 안)로 남긴다
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", sent):
        try:
            t = _dt.datetime.strptime(sent, "%Y-%m-%d %H:%M").replace(tzinfo=now.tzinfo)
            if now - _dt.timedelta(days=7) <= t <= now + _dt.timedelta(hours=1):
                at = sent
        except ValueError:
            pass
    rec = {"at": at, "kind": kind,
           "reg": re.sub(r"\s+", " ", str(b.get("reg") or ""))[:80], "ai": re.sub(r"[^\w:.\-]", "", str(b.get("ai") or ""))[:60],
           "total": n("total"), "edited": n("edited"), "reviewed": bool(b.get("reviewed")),
           "cites": n("cites"), "cites_ok": n("cites_ok"), "fmt": "docx" if b.get("fmt") == "docx" else "hwpx"}
    rec["edited"] = min(rec["edited"], rec["total"])
    rec["cites_ok"] = min(rec["cites_ok"], rec["cites"])
    return rec


_LEDGER_RATE: dict = {}
_LEDGER_PER_HOUR = _clamp_int(os.environ.get("LEDGER_PER_HOUR"), 1, 100000, 600)


def _ledger_gh():
    """내규 등록과 같은 GitHub 설정(GITHUB_TOKEN·GITHUB_REPO)이 있으면 그 모듈을, 없으면 None."""
    try:
        import reg_upload
        return reg_upload if reg_upload._gh_enabled() else None
    except Exception:
        return None


def _ledger_branch() -> str:
    return (os.environ.get("LEDGER_BRANCH") or "ledger-data").strip() or "ledger-data"


def _ledger_gh_read(gh, path: str, ref: str):
    """(내용 bytes, sha). 1MB 가 넘는 파일은 Contents API 가 content 를 비워 주므로 blob 으로 받는다."""
    import base64
    d = gh._gh("GET", f"/contents/{path}", params={"ref": ref})
    raw = d.get("content") or ""
    if not raw and d.get("sha") and d.get("size", 1):
        raw = (gh._gh("GET", f"/git/blobs/{d['sha']}") or {}).get("content") or ""
    return base64.b64decode(raw), d.get("sha")


def _ledger_gh_append(gh, rec: dict) -> None:
    """읽기 전용 배포: 실적을 별도 브랜치(LEDGER_BRANCH, 기본 ledger-data)의 월별 파일에 덧붙여 커밋한다.
    배포 브랜치가 아니므로 재배포가 일어나지 않는다(vercel.json 에서 이 브랜치 배포를 끈다)."""
    import base64
    br, path = _ledger_branch(), f"ledger/{rec['at'][:7]}.jsonl"
    try:
        gh._gh("GET", f"/git/ref/heads/{br}")
    except Exception as e:
        if getattr(e, "status", None) != 404:
            raise
        head = gh._gh("GET", f"/git/ref/heads/{gh.GITHUB_BRANCH}")["object"]["sha"]
        gh._gh("POST", "/git/refs", json={"ref": f"refs/heads/{br}", "sha": head})
    for attempt in range(2):                                   # 동시에 저장하면 sha 가 어긋난다 — 한 번 다시 읽어 붙인다
        old, sha = b"", None
        try:
            old, sha = _ledger_gh_read(gh, path, br)
        except Exception as e:
            if getattr(e, "status", None) != 404:
                raise
        body = {"message": f"실적 대장: {_LEDGER_KINDS[rec['kind']]} {rec['reg']}".strip(), "branch": br,
                "content": base64.b64encode(old + (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")).decode()}
        if sha:
            body["sha"] = sha
        try:
            gh._gh("PUT", f"/contents/{path}", json=body)
            return
        except Exception as e:
            if attempt or getattr(e, "status", None) not in (409, 422):
                raise


@bp.route("/api/regagent/ledger", methods=["POST"])
def ra_ledger_add():
    if not ledger_enabled():
        return jsonify({"success": True, "stored": False, "disabled": True})
    try:
        rec = ledger_record(_body())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    # 접속 주소는 요청자가 바꿀 수 없는 remote_addr 로 센다(X-Forwarded-For 는 위조 가능). 기관이 한 주소(NAT)로
    # 나가도 막히지 않을 만큼 넉넉히 두고, 넘치면 버리지 않고 화면이 나중에 다시 보내게 한다(retry)
    ip = request.remote_addr or ""
    now = time.time()
    hits = [t for t in _LEDGER_RATE.get(ip, []) if now - t < 3600]
    if len(hits) >= _LEDGER_PER_HOUR:
        return jsonify({"success": True, "stored": False, "retry": True, "record": rec, "why": "잠시 뒤 다시 기록합니다."})
    _LEDGER_RATE[ip] = hits + [now]
    gh = _ledger_gh()
    if gh:
        try:
            _ledger_gh_append(gh, rec)
            _LEDGER_SUM["at"] = 0
            return jsonify({"success": True, "stored": True, "where": "github", "record": rec})
        except Exception as e:
            print(f"[ledger] GitHub 기록 실패: {e}")
            return jsonify({"success": True, "stored": False, "retry": True, "record": rec, "why": "기관 대장에 기록하지 못했습니다."})
    d = _ledger_dir()
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, rec["at"][:7] + ".jsonl")
        if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            return jsonify({"success": True, "stored": False, "record": rec, "why": "이번 달 대장 파일이 가득 찼습니다."})
        with _LEDGER_LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:                                            # 읽기 전용이고 GitHub 설정도 없으면 화면의 브라우저 대장만 남는다
        return jsonify({"success": True, "stored": False, "record": rec})
    _LEDGER_SUM["at"] = 0
    return jsonify({"success": True, "stored": True, "where": "local", "record": rec})


def ledger_summary(recs: list) -> list:
    """월별 집계: 산출물 수·종류별·AI 활용·검토 확인·AI 조문 수정 비율·인용 원문 일치."""
    months = {}
    for r in recs:
        m = months.setdefault(str(r.get("at", ""))[:7], {"month": str(r.get("at", ""))[:7], "count": 0, "kinds": {}, "ai": 0,
                                                         "reviewed": 0, "total": 0, "edited": 0, "cites": 0, "cites_ok": 0})
        m["count"] += 1
        m["kinds"][r.get("kind", "")] = m["kinds"].get(r.get("kind", ""), 0) + 1
        m["ai"] += 1 if r.get("ai") else 0
        m["reviewed"] += 1 if r.get("reviewed") else 0
        for k in (("total", "edited") if r.get("ai") else ()) + ("cites", "cites_ok"):   # AI 조문 수는 AI 산출물에서만 센다
            m[k] += _clamp_int(r.get(k), 0, 9999, 0)
    return sorted(months.values(), key=lambda x: x["month"], reverse=True)


_LEDGER_SUM: dict = {"at": 0, "v": None}


def _ledger_lines() -> tuple:
    """(대장을 읽을 수 있는지, 기록 목록) — GitHub 브랜치 또는 로컬 폴더, 최근 24개월."""
    recs = []

    def take(text):
        for line in (text or "").splitlines():
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue
    gh = _ledger_gh()
    if gh:
        try:
            files = gh._gh("GET", "/contents/ledger", params={"ref": _ledger_branch()})
        except Exception as e:
            return (getattr(e, "status", None) == 404), []        # 아직 기록이 없으면 빈 대장
        for f in sorted([x for x in files if isinstance(x, dict) and str(x.get("name", "")).endswith(".jsonl")],
                        key=lambda x: x["name"])[-24:]:
            try:
                take(_ledger_gh_read(gh, f"ledger/{f['name']}", _ledger_branch())[0].decode("utf-8", "replace"))
            except Exception:
                continue
        return True, recs
    d = _ledger_dir()
    try:
        os.makedirs(d, exist_ok=True)                           # 아직 기록이 없어도 쓸 수 있으면 빈 대장
        if not os.access(d, os.W_OK):
            return False, []
        for fn in sorted(os.listdir(d))[-24:]:
            if fn.endswith(".jsonl"):
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    take(f.read())
    except OSError:
        return False, []
    return True, recs


@bp.route("/api/regagent/ledger", methods=["GET"])
def ra_ledger_sum():
    """기관 전체 실적(월별 집계만 — 개별 기록은 내주지 않는다)."""
    if not ledger_enabled():
        return jsonify({"success": True, "kinds": _LEDGER_KINDS, "available": False, "disabled": True, "months": []})
    if _LEDGER_SUM["v"] is None or time.time() - _LEDGER_SUM["at"] > 120:
        ok, recs = _ledger_lines()
        _LEDGER_SUM.update(at=time.time(), v={"available": ok, "months": ledger_summary(recs) if ok else []})
    return jsonify({"success": True, "kinds": _LEDGER_KINDS, **_LEDGER_SUM["v"]})
