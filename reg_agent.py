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

import reg_chunks

bp = Blueprint("reg_agent", __name__)
_CTX: dict = {}


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
    r"|\s*〔[^〕\n]{0,80}(?:이동|종전|신설|개정)[^〕\n]{0,60}〕")
_CHAP_LINE = re.compile(r"^제\s*(\d+)\s*(장|절|관|편)\s*(.{0,40})$")
_ART_LINE = re.compile(
    r"^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:[(（]\s*([^)）\n]{0,60}?)\s*[)）]|(?=\s*(?:[<＜〔\[]\s*)?(?:삭제|종전))|\s*$)")
_ADDENDA_LINE = re.compile(r"^부\s*칙\b|^부\s*칙\s*[<＜(（]")
_APPX_LINE = re.compile(r"^[\[［]\s*(별표|별지)")
_HANG_CH = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_MOK_CH = "가나다라마바사아자차카타파하"

# 내규 명칭 접미어(상위법과 구분하는 데 쓴다)
_REG_SUFFIX = ("정관", "규정", "규칙", "세칙", "지침", "요령", "기준", "매뉴얼",
               "강령", "헌장", "수칙", "예규")
# 기관명·직위 변경 전 구 명칭(기관 프로필 stale_terms·stale_words)
_STALE_TERMS = [tuple(x) for x in ORG.get("stale_terms") or []]
_STALE_WORDS = [tuple(x) for x in ORG.get("stale_words") or []]   # 단어 경계로만 찾는 짧은 말
# 알기 쉬운 표기(법제처 「알기 쉬운 법령 정비기준」 중 내규에 자주 나오는 것)
_STYLE_RULES = [
    (r"각호", "각 호"), (r"각항", "각 항"), (r"동조", "같은 조"), (r"동항", "같은 항"),
    (r"동호", "같은 호"), (r"동법", "같은 법"), (r"당해", "해당"), (r"익일", "다음 날"),
    (r"익월", "다음 달"), (r"금번", "이번"), (r"기타\s", "그 밖의 "), (r"상기", "위"),
    (r"제반", "여러"), (r"감안하여", "고려하여"), (r"을 요하는", "이 필요한"),
    (r"를 요하는", "가 필요한"),
]


def _tidy(s: str) -> str:
    """hwp 변환 잔재(괄호·따옴표 안쪽 공백, 가운뎃점 변형) 정리."""
    s = (s.replace("․", "·").replace("ㆍ", "·").replace("\u00a0", " ")
         .replace("｢", "「").replace("｣", "」").replace("➀", "①"))
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
        if clean:
            body = "\n".join(x for x in (strip_annot(l) for l in body.split("\n")) if x)
        deleted = not a["title"] and (not body or bool(re.match(r"^[<＜〔\[]?\s*(?:삭제|종전)", body)))
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
    r"\(\s*이하[^)]{0,30}\)|"
    r"(?:법|령|시행령|시행규칙|영|규칙|규정|정관|지침|세칙|요령|기준|매뉴얼|훈령|고시|예규|조례|협약)\s*)\s*$")
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
        if not ext and prev_ext_end >= 0 and re.fullmatch(r"(?:\s*[(（][^)）]{0,24}[)）])?[\s,및또는ㆍ·와과]*", text[prev_ext_end:m.start()]):
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
def _josa(word: str, pair=("은", "는")) -> str:
    if not word:
        return pair[0]
    ch = word.strip()[-1]
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[0]


def _kind_of(title: str) -> str:
    """규정명 → '규정'·'규칙'·'지침' 등 자기 지칭어."""
    t = (title or "").strip()
    for suf in ("시행세칙", "정관", "규정", "규칙", "세칙", "지침", "요령", "기준", "매뉴얼", "강령"):
        if t.endswith(suf):
            return suf
    return "규정"


def lint_articles(arts: list, addenda: str = "", appendix: str = "", title: str = "",
                  full: bool = True) -> list:
    """조문 목록 점검 → [{level, code, no, msg, fix?}]. level: error|warn|info"""
    issues = []
    regnames = _reg_names()

    def add(level, code, no, msg, fix=""):
        issues.append({"level": level, "code": code, "no": no, "msg": msg, "fix": fix})

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
                f"{miss}가 없습니다. 삭제한 조는 번호를 남기고 '삭제'로 표시합니다(「{ORG['rules_name']}」 제6조제2항).")
        prev = k
    if arts and art_key(arts[0]["no"]) != (1, 0):
        add("warn", "first", arts[0]["no"], "첫 조문이 제1조가 아닙니다.")
    have = {art_key(a["no"]) for a in arts}

    for a in arts:
        no, body = a["no"], a.get("body", "")
        lbl = art_label(no)
        if a.get("deleted"):
            continue
        # (2) 조 제목
        if not a.get("title"):
            add("warn", "title", no, f"{lbl}에 조문 제목이 없습니다. 각 조에는 내용을 요약한 제목을 붙입니다(제5조제3호).")
        if not body.strip():
            add("error", "empty", no, f"{lbl}의 본문이 비어 있습니다.")
            continue
        # (3) 항·호·목 순서
        hangs = [c for c in re.findall(r"(?:^|\n)\s*([" + _HANG_CH + "])", body)]
        if hangs:
            exp = _HANG_CH[:len(hangs)]
            if "".join(hangs) != exp:
                add("error", "hang", no, f"{lbl}의 항 번호 순서가 맞지 않습니다({' '.join(hangs)}).")
            if len(hangs) == 1:
                add("info", "hang1", no, f"{lbl}에 항이 ①만 있습니다. 항이 하나면 번호를 붙이지 않습니다.")
        for seg in re.split(r"(?:^|\n)\s*[" + _HANG_CH + "]", body):
            hos = [int(x) for x in re.findall(r"(?:^|\n)\s*(\d{1,2})\.\s", seg)]
            if hos and hos != list(range(1, len(hos) + 1)):
                add("warn", "ho", no, f"{lbl}의 호 번호가 1부터 차례대로가 아닙니다({', '.join(map(str, hos))}).")
            moks = re.findall(r"(?:^|\n)\s*([가-하])\.\s", seg)
            if moks:
                expm = "".join(_MOK_CH[:len(moks)])
                if "".join(moks) != expm and len(moks) <= len(_MOK_CH):
                    add("warn", "mok", no, f"{lbl}의 목 기호 순서가 맞지 않습니다({' '.join(moks)}).")
        # (4) 내부 인용 대상
        seen = set()
        for rno, raw, pos in internal_refs(body):
            if art_key(rno) not in have and rno not in seen:
                seen.add(rno)
                add("error", "ref", no, f"{lbl}에서 인용한 {art_label(rno)}가 이 내규에 없습니다: “{raw.strip()}”")
        # (5) 「내규명」 확인
        for m in _QUOTED_NAME.finditer(body):
            nm = m.group(1).strip()
            if "법" in nm or nm.endswith(("령", "조례")):
                continue
            if not nm.endswith(_REG_SUFFIX):
                continue
            if _nk(nm) in regnames or _nk(nm) == _nk(title) or nm == "정관":
                continue
            near = [regnames[k] for k in difflib.get_close_matches(_nk(nm), list(regnames), n=2, cutoff=0.8)]
            own = any(t and t in nm for t in [ORG["org_short"], ORG["org_name"]] + [o for o, _ in _STALE_TERMS + _STALE_WORDS])
            if not near and not own:
                continue                  # 정부 규정·지침 등 외부 규범으로 본다
            add("warn", "regname", no,
                f"{lbl}의 「{nm}」은(는) 현행 내규 목록에 없습니다. 명칭 변경·폐지 여부를 확인하세요."
                + (f" (유사: {', '.join('「'+x+'」' for x in near)})" if near else ""))
        # (6) 구 명칭
        for old, new in _STALE_TERMS:
            if old in body:
                add("warn", "stale", no, f"{lbl}에 구 명칭 “{old}”이(가) 있습니다.", f"“{old}” → “{new}”")
        for old, new in _STALE_WORDS:
            if re.search(r"(?<![가-힣])" + re.escape(old) + r"(?:은|는|이|가|의|에|에서|과|와|을|를)?(?![가-힣])", body):
                add("warn", "stale", no, f"{lbl}에 구 명칭 “{old}”이(가) 있습니다.", f"“{old}” → “{new}”")
        # (7) 알기 쉬운 표기
        if full:
            for pat, rep in _STYLE_RULES:
                mm = re.search(pat, body)
                if mm:
                    add("info", "style", no, f"{lbl}: “{mm.group(0).strip()}” → “{rep.strip()}” 표기를 권장합니다.",
                        f"“{mm.group(0).strip()}” → “{rep.strip()}”")
            if re.search(r"제\s+\d+\s+조", body):
                add("info", "space", no, f"{lbl}: “제 N 조”는 붙여 “제N조”로 씁니다.")

    if full:
        # (8) 약칭 정의 후 정식 명칭 재사용
        joined = "\n".join(a.get("body", "") for a in arts)
        for m in re.finditer(r"([가-힣A-Za-z]{2,30})\s*\(\s*이하\s*[“\"']([^”\"']{1,20})[”\"']\s*(?:이)?라\s*한다\s*\)", joined):
            full_nm, abbr = m.group(1), m.group(2)
            later = joined[m.end():]
            if full_nm != abbr and full_nm in later:
                add("info", "abbr", "", f"“{full_nm}”을(를) “{abbr}”(으)로 줄여 정의한 뒤에도 정식 명칭을 다시 씁니다. 약칭으로 통일을 검토하세요.")
        # (9) 부칙·시행일
        if not (addenda or "").strip():
            add("warn", "addenda", "", "부칙이 없습니다. 시행일을 정하는 부칙을 두세요(제5조제5호).")
        elif not re.search(r"시행", addenda):
            add("warn", "addenda", "", "부칙에 시행일 규정이 보이지 않습니다.")
        # (10) 별표·별지 인용 ↔ 존재
        body_all = joined
        cited = set(re.findall(r"별표\s*(\d+)", body_all))
        exist = set(re.findall(r"[\[［]\s*별표\s*(\d+)", appendix or ""))
        for c in sorted(cited - exist, key=int):
            if appendix or exist:
                add("warn", "appx", "", f"본문에서 [별표 {c}]를 인용하지만 별표가 없습니다.")
        cited_f = set(re.findall(r"별지\s*제?\s*(\d+)\s*호", body_all))
        exist_f = set(re.findall(r"[\[［]\s*별지\s*제?\s*(\d+)\s*호", appendix or ""))
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


def _tokens(q: str) -> list:
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", q or ""):
        w2 = _JOSA_TAIL.sub("", w) if len(w) > 2 else w
        w2 = w2 if len(w2) >= 2 else w
        if w2 in _STOP or w in _STOP:
            continue
        if w2 not in out:
            out.append(w2)
    return out[:14]


def similar_search(query: str, exclude: str = "", limit: int = 8) -> dict:
    toks = _tokens(query)
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
def _rules() -> str:
    lines = [ofmt(x) for x in ORG.get("drafting_rules") or []]
    return f"[{ORG['org_short']} 내규 작성 기준 — 「{ORG['rules_name']}」]\n" + "\n".join("- " + x for x in lines)


def _json_from(text: str):
    clean = re.sub(r"```(?:json)?|```", "", text or "").strip()
    try:
        return json.loads(clean)
    except Exception:
        m = re.search(r"\{.*\}", clean, re.S)
        if m:
            return json.loads(m.group(0))
        raise


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
        t = f"- 「{r.get('reg', '')}」 {art_label(r.get('no', ''))}({r.get('title', '')}) {r.get('body', '')}"
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


def template_enact(b: dict) -> dict:
    """AI 없이 쓰는 표준 조문 골격."""
    title = (b.get("title") or "○○ 운영규칙").strip()
    kind = _kind_of(title)
    eun = _josa(kind)
    purpose = (b.get("purpose") or "○○에 관한 사항").strip().rstrip(".")
    dels = b.get("delegations") or []
    basis = ""
    if dels:
        d0 = dels[0]
        basis = f"「{d0.get('law', '')}」 {d0.get('art', '')}".strip() + "에 따라 "
    arts = [
        {"no": "1", "title": "목적",
         "body": f"이 {kind}{eun} {basis}{ORG['org_name']}(이하 “{ORG['org_short']}”{_josa(ORG['org_short'], ('이라', '라'))} 한다)의 {purpose}에 필요한 사항을 정함을 목적으로 한다."},
        {"no": "2", "title": "정의",
         "body": f"이 {kind}에서 사용하는 용어의 뜻은 다음과 같다.\n1. “○○”이란 ○○을 말한다.\n2. “○○”이란 ○○을 말한다."},
        {"no": "3", "title": "적용범위",
         "body": f"○○에 관하여 다른 내규에 특별한 규정이 있는 경우를 제외하고는 이 {kind}에서 정하는 바에 따른다."},
    ]
    n = 4
    for line in [x.strip(" -·•\t") for x in (b.get("contents") or "").split("\n") if x.strip()]:
        head = re.split(r"[:：]", line, 1)
        t = head[0].strip()[:20] if len(head) > 1 else re.sub(r"\s.*$", "", line)[:14]
        desc = head[1].strip() if len(head) > 1 else line
        arts.append({"no": str(n), "title": t or "○○",
                     "body": f"① {desc}\n② 제1항에 따른 ○○에 필요한 사항은 {ORG['head']}{_josa(ORG['head'], ('이', '가'))} 따로 정한다."})
        n += 1
    arts.append({"no": str(n), "title": "세부사항",
                 "body": f"이 {kind}에서 정한 사항 외에 {purpose}에 필요한 세부사항은 {ORG['head']}{_josa(ORG['head'], ('이', '가'))} 따로 정한다."})
    eff = (b.get("effective") or "").strip() or "발령한 날"
    addenda = f"이 {kind}{eun} {eff}부터 시행한다."
    return {"title": title, "articles": arts, "addenda": [addenda],
            "reason": {"purpose": f"{purpose}에 필요한 사항을 정하기 위하여 「{title}」을(를) 제정하려는 것임.",
                       "main": [f"{a['title']}에 관한 사항을 정함(안 {art_label(a['no'])})" for a in arts[2:-1]]},
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
  "addenda": ["부칙 ① 시행일 …", "② 경과조치 …(필요할 때만)"],
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
            f"[참고할 유사 내규 조문]\n{_ref_block(b.get('refs')) or '(없음)'}")
    text, err = _CTX["ai_generate"](provider, key, mdl, system, user,
                                    max_tokens=6000, temperature=0.2, json_mode=True)
    if err:
        return None, f"AI 오류: {err}"
    try:
        d = _json_from(text)
    except Exception:
        return None, "AI 응답을 해석하지 못했습니다. 다시 시도해 주세요."
    arts = []
    for a in d.get("articles") or []:
        no = re.sub(r"[^0-9의]", "", str(a.get("no", ""))) or str(len(arts) + 1)
        arts.append({"chapter": str(a.get("chapter") or "").strip(), "no": no,
                     "title": str(a.get("title") or "").strip(),
                     "body": str(a.get("body") or "").strip()})
    if not arts:
        return None, "AI가 조문을 만들지 못했습니다. 입력을 보완해 다시 시도해 주세요."
    d["articles"] = arts
    d["title"] = d.get("title") or title
    d["model"] = f"{provider}:{mdl}"
    return d, ""


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
  "addenda": ["① 시행일 …", "② 경과조치 …(필요할 때만)"],
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
    ch = []
    for c in d.get("changes") or []:
        t = str(c.get("type") or "modify").lower()
        if t not in ("modify", "insert", "delete"):
            t = "modify"
        no = re.sub(r"[^0-9의]", "", str(c.get("no", "")))
        if not no:
            continue
        old = None
        if reg and reg.get("articles"):
            old = next((a for a in reg["articles"] if a["no"] == no), None)
        ch.append({"type": t, "no": no, "title": str(c.get("title") or (old or {}).get("title", "")).strip(),
                   "body": str(c.get("body") or "").strip(), "why": str(c.get("why") or "").strip(),
                   "old_title": (old or {}).get("title", ""), "old_body": (old or {}).get("body", "")})
    if not ch:
        return None, "AI가 수정안을 만들지 못했습니다. 개정 의도를 구체적으로 적어 다시 시도해 주세요."
    d["changes"] = ch
    d["model"] = f"{provider}:{mdl}"
    return d, ""


# ══════════════════════════════════════════════════════════════════════════
# 6. 라우트
# ══════════════════════════════════════════════════════════════════════════
@bp.route("/api/regagent/catalog")
def ra_catalog():
    regs = all_regs()
    return jsonify({"success": True, "count": len(regs),
                    "regs": [{"slug": r["slug"], "title": r["title"], "category": r["category"],
                              "revision": r["revision"], "n": len(r["articles"])} for r in regs]})


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
    b = request.get_json(silent=True) or {}
    q = (b.get("query") or "").strip()
    if len(q) < 2:
        return jsonify({"success": False, "error": "검색할 내용을 입력하세요."}), 400
    try:
        lim = max(1, min(int(b.get("limit") or 8), 15))
    except (TypeError, ValueError):
        lim = 8
    res = similar_search(q[:600], b.get("exclude") or "", lim)
    return jsonify({"success": True, **res})


@bp.route("/api/regagent/impact", methods=["POST"])
def ra_impact():
    """개정 조문 → 영향 범위. body: {slug, nos:[...], moves:{"5":"6"}, rename:"새 내규명"}"""
    b = request.get_json(silent=True) or {}
    r = resolve_reg(b)
    if not r:
        return jsonify({"success": False, "error": "내규를 찾을 수 없습니다."}), 404
    nos = [re.sub(r"[^0-9의]", "", str(x)) for x in (b.get("nos") or [])]
    nos = [x for x in nos if x]
    moves = {re.sub(r"[^0-9의]", "", str(k)): re.sub(r"[^0-9의]", "", str(v))
             for k, v in (b.get("moves") or {}).items()}
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


@bp.route("/api/regagent/upper", methods=["POST"])
def ra_upper():
    """상위법 개정 → 영향받는 내규 조문. body: {law, arts:[...], old, new}"""
    b = request.get_json(silent=True) or {}
    law = re.sub(r"[「」]", "", (b.get("law") or "")).strip()
    if len(law) < 2:
        return jsonify({"success": False, "error": "상위법 명칭을 입력하세요."}), 400
    arts = [re.sub(r"[^0-9의]", "", str(x)) for x in (b.get("arts") or [])]
    arts = [x for x in arts if x]
    tset = {art_key(x) for x in arts}
    old_t, new_t = (b.get("old") or ""), (b.get("new") or "")
    removed = []
    if old_t or new_t:
        ow = set(_tokens(old_t)) if old_t else set()
        nw = set(_tokens(new_t)) if new_t else set()
        removed = [w for w in (ow - nw) if len(w) >= 2][:12]
    base = re.sub(r"\s*(시행령|시행규칙)$", "", law)
    lp = re.escape(base).replace(r"\ ", r"\s*")
    pat = re.compile(r"「\s*(" + lp + r"(?:\s*시행령|\s*시행규칙)?)\s*」|(?<![가-힣])(" + lp + r")(?![가-힣])")
    cands = []
    for o in all_regs():
        for a in o["articles"]:
            if a["deleted"]:
                continue
            body = a["body"]
            ms = list(pat.finditer(body))
            term_hits = [w for w in removed if w in body]
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
                    exact_law = (_nk(nm) == _nk(law)) or (not re.search(r"시행(령|규칙)$", law) and not re.search(r"시행(령|규칙)", nm))
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
                    "candidates": cands[:120]})


@bp.route("/api/regagent/lint", methods=["POST"])
def ra_lint():
    """조문 점검. body: {text, title} | {slug} | {all:true}"""
    b = request.get_json(silent=True) or {}
    if b.get("all"):
        t0 = time.time()
        rows, tot = [], {"error": 0, "warn": 0, "info": 0}
        for r in all_regs():
            iss = [i for i in lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"], full=False)
                   if i["code"] in ("ref", "regname", "stale", "dup", "order")]
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
        return jsonify({"success": True, "mode": "reg", "reg": r["title"], "issues": iss})
    text = b.get("text") or ""
    if not text.strip():
        return jsonify({"success": False, "error": "점검할 조문이 없습니다."}), 400
    p = parse_text(text, clean=False)
    add = b.get("addenda")
    add = add if isinstance(add, str) else p["addenda"]
    iss = lint_articles(p["articles"], add, p["appendix"], b.get("title", ""))
    if not p["articles"]:
        iss.insert(0, {"level": "error", "code": "noart", "no": "",
                       "msg": "“제1조(목적)” 형식의 조문을 찾지 못했습니다.", "fix": ""})
    return jsonify({"success": True, "mode": "text", "issues": iss,
                    "articles": len(p["articles"])})


@bp.route("/api/regagent/parse", methods=["POST"])
def ra_parse():
    b = request.get_json(silent=True) or {}
    p = parse_text(b.get("text") or "", clean=bool(b.get("clean")))
    return jsonify({"success": True, **p})


@bp.route("/api/regagent/draft", methods=["POST"])
def ra_draft():
    b = request.get_json(silent=True) or {}
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
        return jsonify({"success": False, "error": f"초안 작성 오류: {e}"}), 500
    if d is None:
        need = bool(re.search(r"키", err or ""))
        return jsonify({"success": False, "error": err, "need_key": need}), 400 if need else 502
    return jsonify({"success": True, "mode": mode, "draft": d, "notice": err})


# ── 한글(.hwpx) 문서 세트 ─────────────────────────────────────────────────
def _xesc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_LS = ('<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
       'baseline="850" spacing="600" horzpos="0" horzsize="{w}" flags="393216"/></hp:linesegarray>')


def _para(text, width=47628, page_break=False):
    return (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="{1 if page_break else 0}" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:t>{_xesc(text)}</hp:t></hp:run>'
            + _LS.format(w=width) + '</hp:p>')


def _cell(text, col, row, cspan, width, bf):
    lines = str(text or "").split("\n") or [""]
    paras = "".join(
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="0"><hp:t>{_xesc(ln)}</hp:t></hp:run>{_LS.format(w=max(1000, width - 400))}</hp:p>'
        for ln in lines)
    # 줄 수·폭으로 높이를 어림(한글이 열 때 다시 계산)
    est = sum(max(1, int(len(ln) * 1000 / max(1500, width - 1000)) + 1) for ln in lines)
    h = max(1848, est * 1600 + 600)
    return (f'<hp:tc name="" header="0" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'{paras}</hp:subList><hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{cspan}" rowSpan="1"/><hp:cellSz width="{width}" height="{h}"/>'
            f'<hp:cellMargin left="283" right="283" top="141" bottom="141"/></hp:tc>'), h


def _table(rows, col_w, bf):
    total = sum(col_w)
    trs, heights = [], []
    for r, cells in enumerate(rows):
        col, tcs, rh = 0, [], 0
        for c in cells:
            cs = int(c.get("cs") or 1)
            w = sum(col_w[col:col + cs])
            x, h = _cell(c.get("t", ""), col, r, cs, w, bf)
            tcs.append(x)
            rh = max(rh, h)
            col += cs
        # 같은 행 셀 높이 통일
        tcs = [re.sub(r'(<hp:cellSz width="\d+" height=")\d+', r"\g<1>" + str(rh), t) for t in tcs]
        heights.append(rh)
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")
    tbl = (f'<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
           f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="{len(rows)}" colCnt="{len(col_w)}" '
           f'cellSpacing="0" borderFillIDRef="{bf}" noAdjust="0">'
           f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="{sum(heights)}" heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
           f'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="283" right="283" top="283" bottom="283"/>'
           f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>' + "".join(trs) + '</hp:tbl>')
    return ('<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{tbl}</hp:run>' + _LS.format(w=47628) + '</hp:p>')


def build_hwpx(blocks: list) -> bytes:
    base = _CTX["hwpx_base_bytes"]()
    if not base:
        raise RuntimeError("HWPX 기본 서식을 찾을 수 없습니다.")
    zin = zipfile.ZipFile(io.BytesIO(base), "r")
    header = zin.read("Contents/header.xml").decode("utf-8", "ignore")
    sec = zin.read("Contents/section0.xml").decode("utf-8", "ignore")
    bf = _CTX["hwpx_full_border"](header)
    m = re.search(r'<hs:sec\b[^>]*>', sec)
    prefix, body = sec[:m.end()], sec[m.end():]
    pi = body.find('<hp:p')
    pj = body.find('</hp:p>', pi) + len('</hp:p>')
    first = re.sub(r'<hp:t>.*?</hp:t>', '<hp:t></hp:t>', body[pi:pj], flags=re.S)
    parts = []
    for i, blk in enumerate(blocks or []):
        t = blk.get("t")
        if t == "table":
            rows = blk.get("rows") or []
            ncol = max((sum(int(c.get("cs") or 1) for c in r) for r in rows), default=1)
            cw = blk.get("colWidths") or [int(47628 / ncol)] * ncol
            parts.append(_table(rows, [int(x) for x in cw], bf))
        elif t == "break":
            parts.append(_para("", page_break=True))
        else:
            txt = str(blk.get("text") or "")
            for j, ln in enumerate(txt.split("\n")):
                parts.append(_para(ln, page_break=bool(blk.get("pageBreak")) and j == 0))
    new_sec = prefix + first + "".join(parts) + _para("") + "</hs:sec>"
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    zout.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
    for n in zin.namelist():
        if n in ("mimetype", "Preview/PrvImage.png"):
            continue
        zout.writestr(n, new_sec.encode("utf-8") if n == "Contents/section0.xml" else zin.read(n))
    zout.close()
    zin.close()
    return out.getvalue()


@bp.route("/api/regagent/hwpx", methods=["POST"])
def ra_hwpx():
    b = request.get_json(silent=True) or {}
    blocks = b.get("blocks") or []
    if not blocks:
        return jsonify({"success": False, "error": "문서 내용이 없습니다."}), 400
    if len(json.dumps(blocks, ensure_ascii=False)) > 1_500_000:
        return jsonify({"success": False, "error": "문서가 너무 큽니다."}), 413
    try:
        data = build_hwpx(blocks)
    except Exception as e:
        return jsonify({"success": False, "error": f"HWPX 생성 실패: {e}"}), 500
    from urllib.parse import quote as _q
    fname = re.sub(r'[\\/:*?"<>|]', "_", (b.get("filename") or "내규안"))[:80] + ".hwpx"
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
                    "semantic": bool(_CTX.get("vec_ready") and _CTX["vec_ready"]())})


# ══════════════════════════════════════════════════════════════════════════
# 8. 용어·명칭 일괄 정비 — 모든 내규에서 찾아 바꾸고 조사까지 맞춘다
# ══════════════════════════════════════════════════════════════════════════
_PARTICLES = [("으로", "로"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"), ("이나", "나"), ("이라", "라")]


def _has_batchim(w: str) -> bool:
    ch = (w or " ").strip()[-1:] or " "
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return bool(re.match(r"[0-9a-zA-Z]", ch)) and ch.lower() in "136780lmnr"


def _rjosa(word: str, part: str) -> str:
    """조사 하나를 새 단어 받침에 맞게."""
    has = _has_batchim(word)
    ends_rieul = has and (ord(word.strip()[-1]) - 0xAC00) % 28 == 8 if "가" <= word.strip()[-1:] <= "힣" else False
    for a, b in _PARTICLES:
        if part in (a, b):
            if a == "으로":
                return "로" if (not has or ends_rieul) else "으로"
            return a if has else b
    return part


def replace_term(text: str, old: str, new: str, whole: bool = True):
    """old→new 치환 + 뒤따르는 조사 교정. 반환: (새 본문, [(위치, 원래 표기)])."""
    if not old:
        return text, []
    pat = re.compile((r"(?<![가-힣A-Za-z0-9])" if whole else "") + re.escape(old)
                     + r"(으로|이나|이라|은|는|이|가|을|를|과|와|로|나|라)?(?=[^가-힣]|$)?")
    hits, out, last = [], [], 0
    for m in pat.finditer(text):
        part = m.group(1) or ""
        # 조사로 본 글자 뒤에 한글이 이어지면(예: “이사장이며”) 조사가 아니다
        after = text[m.end():m.end() + 1]
        if part and after and "가" <= after <= "힣":
            part_fixed = part
        else:
            part_fixed = _rjosa(new, part) if part else ""
        out.append(text[last:m.start()] + new + part_fixed)
        last = m.end()
        hits.append((m.start(), m.group(0)))
    out.append(text[last:])
    return "".join(out), hits


def _loc_label(art: dict, pos: int) -> str:
    """본문 위치 → “제5조제2항” 같은 개정문용 위치."""
    lbl = art_label(art["no"])
    before = art["body"][:pos]
    hs = re.findall(r"(?:^|\n)\s*([" + _HANG_CH + "])", before)
    if hs:
        lbl += f"제{_HANG_CH.index(hs[-1]) + 1}항"
        seg = before[before.rfind(hs[-1]):]
    else:
        seg = before
    ho = re.findall(r"(?:^|\n)\s*(\d{1,2})\.\s", seg)
    if ho:
        lbl += f"제{ho[-1]}호"
    return lbl


@bp.route("/api/regagent/bulk", methods=["POST"])
def ra_bulk():
    """용어·명칭 일괄 정비. body: {old, new, whole:true, slugs:[...](선택)}"""
    b = request.get_json(silent=True) or {}
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
            locs = []
            for pos, _ in hits:
                lb = _loc_label(a, pos)
                if lb not in locs:
                    locs.append(lb)
            if thits:
                locs.insert(0, f"{art_label(a['no'])} 제목")
            arts.append({"no": a["no"], "title": a["title"], "new_title": nt, "old_body": a["body"],
                         "new_body": nb, "count": len(hits) + len(thits), "locs": locs})
            total += len(hits) + len(thits)
        if arts:
            regs_out.append({"slug": r["slug"], "reg": r["title"], "articles": arts,
                             "count": sum(x["count"] for x in arts)})
    regs_out.sort(key=lambda x: -x["count"])
    q_old = f"“{old}”{_josa(old, ('을', '를'))}"
    q_new = f"“{new}”{'로' if (not _has_batchim(new) or (('가' <= new[-1] <= '힣') and (ord(new[-1]) - 0xAC00) % 28 == 8)) else '으로'}"
    for g in regs_out:
        locs = [l for a in g["articles"] for l in a["locs"]]
        each = "각각 " if len(locs) > 1 else ""
        g["amend_text"] = f"「{g['reg']}」 일부를 다음과 같이 개정한다.\n{', '.join(locs)} 중 {q_old} {each}{q_new} 한다."
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
    # 적합성
    if mode == "enact" and _kind_of(title) in ("시행세칙", "세칙") and not dels:
        f("fit", "warn", "시행세칙인데 위임 근거(상위 규정 조항)가 없습니다.")
    if dels:
        f("fit", "ok", "상위 근거: " + ", ".join(f"「{d.get('law', '')}」 {d.get('art', '')}".strip() for d in dels[:4]))
    laws = sorted({m.group(1) for a in arts for m in _QUOTED_NAME.finditer(a.get("body", ""))
                   if re.search(r"법|령$", m.group(1))})
    if laws:
        f("fit", "check", "인용 법령의 현행 여부·조문 번호를 확인하세요: " + ", ".join(f"「{x}」" for x in laws[:8]))
    for i in lint:
        if i["code"] in ("regname", "stale"):
            f("fit", "warn", i["msg"])
    # 통일성·조화성
    if mode == "enact" and title and _nk(title) in _reg_names():
        f("unity", "warn", f"같은 이름의 {ORG['reg_word']}이(가) 이미 있습니다: 「{title}」")
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
    style = [i for i in lint if i["code"] in ("style", "space", "abbr")]
    if style:
        f("clear", "check", f"알기 쉬운 표기 제안 {len(style)}건: " + "; ".join(i["fix"] or i["msg"] for i in style[:5]))
    longs = [a for a in arts for s_ in re.split(r"(?<=[.다])\s", a.get("body", "")) if len(s_) > 180]
    if longs:
        f("clear", "check", "한 문장이 180자를 넘는 조문: " + ", ".join(sorted({art_label(a["no"]) for a in longs}, key=lambda x: art_key(re.sub(r"[제조]", "", x)))[:6]) + " — 나누어 쓰는 것을 검토하세요.")
    if not style and not longs:
        f("clear", "ok", "표기·문장 길이에서 특이사항이 없습니다.")
    # 체제·효력
    st = [i for i in lint if i["code"] in ("dup", "order", "gap", "first", "title", "empty", "hang", "ho", "mok", "ref", "addenda", "appx", "noart")]
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
            f("open", "check", f"국민 권리·의무 관련 — 대국민 사전예고({ORG['notice_days']}일 이상) 대상입니다.")
        if ans.get("multi") == "y":
            f("open", "check", "2개 이상 부서 소관 — 사전 합의·협의 결과를 첨부하세요.")
        if ans.get("impact") == "y":
            f("open", "check", "국민 생활·기업 영향 — 부패영향평가 요청 대상입니다.")
        if ans.get("burden") == "y":
            f("open", "check", "유사 행정규제 — 자체 규제심사서를 함께 제출하세요.")
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
    b = request.get_json(silent=True) or {}
    if not (b.get("text") or "").strip():
        return jsonify({"success": False, "error": "검토할 조문이 없습니다."}), 400
    try:
        res = review_draft(b)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"검토 오류: {e}"}), 500
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
def _w_run(t):
    return f'<w:r><w:t xml:space="preserve">{_xesc(t)}</w:t></w:r>'


def _w_para(t, bold=False, center=False, page_break=False):
    ppr = ""
    if center or page_break:
        ppr = "<w:pPr>" + ("<w:pageBreakBefore/>" if page_break else "") + ('<w:jc w:val="center"/>' if center else "") + "</w:pPr>"
    r = f'<w:r>{"<w:rPr><w:b/></w:rPr>" if bold else ""}<w:t xml:space="preserve">{_xesc(t)}</w:t></w:r>'
    return f"<w:p>{ppr}{r}</w:p>"


def build_docx(blocks: list) -> bytes:
    body = []
    pb = False
    for blk in blocks or []:
        t = blk.get("t")
        if t == "break":
            pb = True
            continue
        if t == "table":
            rows = blk.get("rows") or []
            ncol = max((sum(int(c.get("cs") or 1) for c in r) for r in rows), default=1)
            grid = "".join(f'<w:gridCol w:w="{int(9000 / ncol)}"/>' for _ in range(ncol))
            trs = []
            for i, r in enumerate(rows):
                tcs = []
                for c in r:
                    cs = int(c.get("cs") or 1)
                    paras = "".join(_w_para(x, bold=bool(c.get("hd")), center=bool(c.get("hd")))
                                    for x in str(c.get("t", "")).split("\n"))
                    tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="{int(9000 / ncol) * cs}" w:type="dxa"/>'
                               + (f'<w:gridSpan w:val="{cs}"/>' if cs > 1 else "")
                               + (('<w:shd w:val="clear" w:color="auto" w:fill="EAF2FE"/>') if c.get("hd") else "")
                               + f'</w:tcPr>{paras}</w:tc>')
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
            body.append(_w_para(ln, bold=(j == 0 and bool(blk.get("titleBold"))), page_break=(pb and j == 0)))
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
    b = request.get_json(silent=True) or {}
    blocks = b.get("blocks") or []
    if not blocks:
        return jsonify({"success": False, "error": "문서 내용이 없습니다."}), 400
    if len(json.dumps(blocks, ensure_ascii=False)) > 1_500_000:
        return jsonify({"success": False, "error": "문서가 너무 큽니다."}), 413
    from urllib.parse import quote as _q
    fname = re.sub(r'[\\/:*?"<>|]', "_", (b.get("filename") or "내규안"))[:80] + ".docx"
    return Response(build_docx(blocks),
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + _q(fname)})


# ══════════════════════════════════════════════════════════════════════════
# 11. 규정 건강검진 — 내규별 건강 점수·정비 우선순위
# ══════════════════════════════════════════════════════════════════════════
_REV_DATE = re.compile(r"((?:19|20)\d\d)\s*년(?:도)?(?:\s*(\d{1,2})\s*월)?(?:\s*(\d{1,2})\s*일)?")
_LAW_NAME_OK = re.compile(r"(법|법률|시행령|시행규칙)$")


def rev_date(rev: str) -> str:
    """'2023년도 7월 일부개정' → '20230701'. 모르면 ''."""
    m = _REV_DATE.search(rev or "")
    if not m:
        return ""
    return f"{m.group(1)}{int(m.group(2) or 1):02d}{int(m.group(3) or 1):02d}"


def cited_laws(reg: dict) -> list:
    """내규 본문(부칙 제외)이 인용하는 국가 법령명(「…법」·시행령·시행규칙)."""
    names = []
    for a in reg["articles"]:
        if a["deleted"]:
            continue
        for m in _QUOTED_NAME.finditer(a["body"]):
            nm = re.sub(r"\s+", " ", m.group(1)).strip()
            if _LAW_NAME_OK.search(nm) and nm not in names and len(nm) <= 40:
                names.append(nm)
    return names


# 감점(건당, 상한). 점수 기준은 화면에도 그대로 안내한다
_H_W = {"ref": (10, 30), "dup": (8, 16), "order": (8, 16), "regname": (6, 18), "stale": (5, 15)}
_H_GRADE = [("A", 95), ("B", 85), ("C", 75), ("D", 60), ("E", 0)]


def health_row(r: dict, law_info: dict, today: str) -> dict:
    iss = [i for i in lint_articles(r["articles"], r["addenda"], r["appendix"], r["title"], full=False)
           if i["code"] in _H_W]
    cnt = {}
    for i in iss:
        cnt[i["code"]] = cnt.get(i["code"], 0) + 1
    pen, reasons = 0, []
    labels = {"ref": "없는 조문 인용", "dup": "조 번호 중복", "order": "조 번호 순서 오류",
              "regname": "현행 목록에 없는 내규명 인용", "stale": "옛 기관명·직위"}
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
            reasons.append(f"{age:g}년째 개정 없음")
    laws = cited_laws(r)
    stale_laws = []
    for nm in laws:
        info = law_info.get(nm) or {}
        ef = re.sub(r"\D", "", str(info.get("ef") or ""))[:8]
        if rd and len(ef) == 8 and rd < ef <= today:
            stale_laws.append({"law": nm, "ef": ef})
    if stale_laws:
        pen += min(len(stale_laws) * 8, 32)
        reasons.append(f"내규 개정 뒤 시행된 상위법 {len(stale_laws)}건")
    score = max(0, 100 - pen)
    grade = next(g for g, cut in _H_GRADE if score >= cut)
    return {"slug": r["slug"], "title": r["title"], "category": r["category"], "revision": r.get("revision", ""),
            "rev_date": rd, "age": age, "score": score, "grade": grade, "counts": cnt,
            "issues": iss[:12], "laws": laws, "stale_laws": stale_laws, "reasons": reasons,
            "n_articles": len(r["articles"])}


@bp.route("/api/regagent/health", methods=["GET", "POST"])
def ra_health():
    """전체 내규 건강검진. POST {law_info:{법령명:{ef:YYYYMMDD}}} 를 주면 상위법 최신성까지 반영."""
    b = request.get_json(silent=True) or {}
    law_info = b.get("law_info") if isinstance(b.get("law_info"), dict) else {}
    today = time.strftime("%Y%m%d")
    rows = [health_row(r, law_info, today) for r in all_regs()]
    rows.sort(key=lambda x: (x["score"], -(x["age"] or 0)))
    grades = {g: sum(1 for x in rows if x["grade"] == g) for g in "ABCDE"}
    all_laws = sorted({nm for x in rows for nm in x["laws"]})
    n = len(rows) or 1
    return jsonify({"success": True, "today": today, "count": len(rows),
                    "rules": {"weights": _H_W, "grades": _H_GRADE,
                              "age": "2년 -4 · 3년 -8 · 5년 이상 -15", "law": "상위법 건당 -8(최대 -32)"},
                    "avg": round(sum(x["score"] for x in rows) / n, 1), "grades": grades,
                    "with_errors": sum(1 for x in rows if x["counts"].get("ref") or x["counts"].get("dup") or x["counts"].get("order")),
                    "with_issues": sum(1 for x in rows if x["reasons"]),
                    "issue_total": sum(sum(x["counts"].values()) for x in rows),
                    "stale_regs": sum(1 for x in rows if x["stale_laws"]),
                    "old_regs": sum(1 for x in rows if (x["age"] or 0) >= 3),
                    "laws": all_laws, "law_checked": len(law_info), "rows": rows})


_LAW_FRESH: dict = {}


@bp.route("/api/regagent/health/laws", methods=["POST"])
def ra_health_laws():
    """상위법 최신 시행일 조회(법제처). body {names:[...]} — 서버리스 시간 제한에 맞춰 한 번에 최대 12건."""
    b = request.get_json(silent=True) or {}
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
                return nm, {"ef": v.get("ef", ""), "status": v.get("status", ""), "name": v.get("name", ""),
                            "found": bool(v.get("mst") or v.get("id")) and v.get("rank", 99) <= 1}
            except Exception as e:
                return nm, {"error": str(e)[:120]}
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for nm, v in ex.map(one, todo):
                out[nm] = v
                if "error" not in v:
                    _LAW_FRESH[nm] = {"at": time.time(), "v": v}
    return jsonify({"success": True, "laws": out,
                    "failed": sum(1 for v in out.values() if v.get("error"))})


# ══════════════════════════════════════════════════════════════════════════
# 11-2. 인용 관계망 — 어떤 내규가 어떤 내규를 「내규명」으로 인용하는지(개정·폐지 영향 범위)
# ══════════════════════════════════════════════════════════════════════════
_GRAPH_CACHE = {"key": None, "v": None}


def _reg_text(r: dict) -> str:
    """본칙 조문만(부칙은 당시 명칭을 그대로 둬야 하는 연혁이라 제외)."""
    return "\n".join(a.get("body", "") for a in r["articles"] if not a.get("deleted"))


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
            elif "법" in nm or nm.endswith(("령", "조례")) or not nm.endswith(_REG_SUFFIX) or nm == "정관":
                res = (None, False, None)
            else:
                near = difflib.get_close_matches(k, names, n=1, cutoff=0.8)
                ext = not near and not any(t in nm for t in own)       # 정부 규정 등 외부 규범
                res = (None, False, None if ext else (regs[idx[near[0]]]["title"] if near else ""))
        memo[nm] = res
        return res

    for i, r in enumerate(regs):
        for m in _QUOTED_NAME.finditer(_reg_text(r)):
            nm = m.group(1).strip()
            j, stale, near = resolve(nm)
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


def heuristic_plan(req: str) -> dict:
    t = (req or "").strip()
    plan = {"mode": "amend", "intent": t, "reasoning": []}
    bulk_kw = re.search(r"(모든|전체|일괄|모두|전\s*내규|명칭|부서명|직위|기관명|이름이\s*바뀌)", t)
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
    if lm and re.search(r"(상위법|법령|법률|시행령|시행규칙|「)", t) and not re.search(r"(내규|규정|규칙|지침)을\s*(?:고치|개정)", t):
        plan.update(mode="upper", law=re.sub(r"\s+", " ", lm),
                    arts=[re.sub(r"\s+", "", x) for x in re.findall(r"제\s*\d+\s*조(?:\s*의\s*\d+)?", t)])
        plan["reasoning"].append(f"상위 법령 「{plan['law']}」 개정에 따른 영향 분석으로 판단")
        return plan
    if _ENACT_RE.search(t) and not re.search(r"개정", t):
        tm = re.search(r"([가-힣A-Za-z0-9·\s]{2,30}?(?:규정|규칙|지침|요령|기준|세칙))", t)
        title = re.sub(r"^(새로운?|신규|새)\s*", "", tm.group(1).strip()) if tm else ""
        plan.update(mode="enact", title=title, purpose=t, contents="")
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
        plan["reasoning"].append(f"유사 검색으로 「{reg['title']}」을(를) 대상으로 선택(관련도 1위)")
    elif reg:
        plan["reasoning"].append(f"요청에 내규명 「{reg['title']}」이(가) 있어 대상으로 선택")
    if not reg:
        return
    plan["reg"] = {"slug": reg["slug"], "title": reg["title"], "category": reg["category"]}
    nos = [re.sub(r"\s+", "", x).replace("제", "").replace("조", "") for x in re.findall(r"제\s*\d+\s*조(?:\s*의\s*\d+)?", req)]
    nos = [n for n in nos if any(a["no"] == n for a in reg["articles"])]
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
    b = request.get_json(silent=True) or {}
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
{{"mode": "enact|amend|bulk|upper",
  "intent": "개정·제정 의도를 실무 문장으로 1~2문장",
  "reg_hint": "개정 대상 내규명(알 수 있으면, 없으면 빈 문자열)",
  "title": "제정 시 내규명(없으면 제안)", "purpose": "제정 목적", "contents": "제정 시 주요 내용(줄바꿈 구분, '제목: 내용')",
  "old": "일괄 정비 시 바뀌기 전 용어", "new": "바뀐 뒤 용어",
  "law": "상위법 영향 분석 시 법령명", "arts": ["제N조"],
  "why": "이렇게 판단한 이유 1문장"}}
- enact: 새 내규를 만듦 / amend: 특정 내규 조문을 고침 / bulk: 기관명·부서명·직위·내규명 등 용어를 모든 내규에서 바꿈 / upper: 상위 법령이 바뀌어 영향받는 내규를 찾음"""
        text, err = _CTX["ai_generate"](provider, key, mdl, system, f"요청: {req}", max_tokens=1200, temperature=0.1, json_mode=True)
        if not err:
            try:
                d = _json_from(text)
                if d.get("mode") in ("enact", "amend", "bulk", "upper"):
                    keep = plan.get("reasoning", [])
                    plan = {k: v for k, v in d.items() if k in ("mode", "intent", "reg_hint", "title", "purpose", "contents", "old", "new", "law", "arts")}
                    plan["reasoning"] = [f"AI 판단: {d.get('why') or plan['mode']}"] + [x for x in keep if x.startswith("“")]
                    plan["ai"] = True
                    plan["model"] = f"{provider}:{mdl}"
            except Exception:
                plan["reasoning"].append("AI 계획을 해석하지 못해 규칙 기반 판단을 사용")
        else:
            plan["reasoning"].append(f"AI 호출 실패로 규칙 기반 판단 사용({err[:60]})")
    if plan["mode"] == "amend":
        plan.setdefault("intent", req)
        _resolve_targets(plan, req)
        if not plan.get("reg"):
            return jsonify({"success": False, "error": "개정할 내규를 찾지 못했습니다. 내규명을 함께 적어 주세요.", "plan": plan}), 404
    if plan["mode"] == "enact":
        plan.setdefault("purpose", req)
        plan["title"] = plan.get("title") or ""
    if plan["mode"] == "bulk" and not (plan.get("old") and plan.get("new")):
        plan["mode"] = "amend"
        _resolve_targets(plan, req)
    plan["request"] = req
    return jsonify({"success": True, "plan": plan})
