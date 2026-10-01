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
작성 기준은 「내규관리규칙」 제5조(내규의 체제)·제6조(개정 방식)를 따른다.
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
# 2022.3.1. 기관명 변경 부칙(「내규관리규칙」 부칙 2022.02.24.) 기준 구 명칭
_STALE_TERMS = [
    ("농업기술실용화재단", "한국농업기술진흥원"),
    ("실용화재단", "농진원"),
    ("이사장", "원장"),
    ("총괄본부장", "부원장"),
]
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


def _reg_names() -> dict:
    """정규화 내규명 → 정식 명칭."""
    return {_nk(r["title"]): r["title"] for r in all_regs()}


# ══════════════════════════════════════════════════════════════════════════
# 2. 인용 탐지
# ══════════════════════════════════════════════════════════════════════════
_REF = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?(?:\s*제\s*(\d+)\s*호)?"
    r"(?:\s*(부터|내지|및|또는|ㆍ|·|,|와|과)\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*(까지)?))?")
_QUOTED_NAME = re.compile(r"「\s*([^」]{2,60}?)\s*」")
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
                f"{miss}가 없습니다. 삭제한 조는 번호를 남기고 '삭제'로 표시합니다(「내규관리규칙」 제6조제2항).")
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
        regnames = _reg_names()
        for m in _QUOTED_NAME.finditer(body):
            nm = m.group(1).strip()
            if "법" in nm or nm.endswith(("령", "조례")):
                continue
            if not nm.endswith(_REG_SUFFIX):
                continue
            if _nk(nm) in regnames or _nk(nm) == _nk(title) or nm == "정관":
                continue
            near = [regnames[k] for k in difflib.get_close_matches(_nk(nm), list(regnames), n=2, cutoff=0.8)]
            own = re.search(r"농진원|농업기술진흥원|실용화재단|재단", nm)
            if not near and not own:
                continue                  # 정부 규정·지침 등 외부 규범으로 본다
            add("warn", "regname", no,
                f"{lbl}의 「{nm}」은(는) 현행 내규 목록에 없습니다. 명칭 변경·폐지 여부를 확인하세요."
                + (f" (유사: {', '.join('「'+x+'」' for x in near)})" if near else ""))
        # (6) 구 명칭
        for old, new in _STALE_TERMS:
            if old in body:
                add("warn", "stale", no, f"{lbl}에 구 명칭 “{old}”이(가) 있습니다.", f"“{old}” → “{new}”")
        if re.search(r"(?<![가-힣])재단(?:은|는|이|가|의|에|에서|과|와|을|를)?(?![가-힣])", body):
            add("warn", "stale", no, f"{lbl}에 구 명칭 “재단”이 있습니다.", "“재단” → “농진원”")
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
         "농진원", "한국농업기술진흥원", "그리고", "또는", "하기", "위해", "통해",
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
_RULES = """[농진원 내규 작성 기준 — 「내규관리규칙」 제5조·제6조]
- 내규는 총칙·본칙·부칙으로 구성. 장·절·조·항·호·목 순으로 구분(조문이 적으면 장·절 생략 가능).
- 각 조에는 내용을 요약한 제목을 붙인다: "제1조(목적)". 항은 ①②③, 호는 "1." "2.", 목은 "가." "나.".
- 조문 숫자는 아라비아 숫자. 한글 가로쓰기·띄어쓰기, 쉬운 우리말(“각호”→“각 호”, “당해”→“해당”, “기타”→“그 밖의”).
- 기관 명칭은 첫 조문에서 한국농업기술진흥원(이하 “농진원”이라 한다)으로 정의하고 이후 “농진원”, 기관장은 “원장”.
- 일부 개정 시 조를 추가하면 “제0조의2”로 번호를 붙이고, 조를 삭제하면 번호를 남기고 “삭제”로 표시(기존 조 번호를 당기거나 밀지 않는다).
- 개정 조문이 기존 조문의 3분의 2 이상이면 전부개정 방식.
- 부칙에는 시행일, 경과조치, 다른 내규의 개정 등을 둔다(5개 이내면 항 ①②, 초과 시 조).
- 상위 법령·정관·상위 내규에 저촉되지 않게 하고 위임 근거를 명확히 한다. 다른 내규와 중복·상충 금지."""


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
         "body": f"이 {kind}{eun} {basis}한국농업기술진흥원(이하 “농진원”이라 한다)의 {purpose}에 필요한 사항을 정함을 목적으로 한다."},
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
                     "body": f"① {desc}\n② 제1항에 따른 ○○에 필요한 사항은 원장이 따로 정한다."})
        n += 1
    arts.append({"no": str(n), "title": "세부사항",
                 "body": f"이 {kind}에서 정한 사항 외에 {purpose}에 필요한 세부사항은 원장이 따로 정한다."})
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
    system = f"""당신은 한국농업기술진흥원(농진원) 내규 입안 전문가입니다.
주어진 제정 목적·주요 내용·상위법 위임 조항·유사 내규를 바탕으로 새 내규의 조문 체계와 표준 조문 초안을 작성하세요.
{_RULES}

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
    reg = find_reg(b.get("slug", ""), b.get("reg", ""))
    reg_title = reg["title"] if reg else (b.get("reg") or "")
    toc = ""
    if reg:
        toc = "\n".join(f"{art_label(a['no'])}({a['title'] or '삭제'})" for a in reg["articles"])[:3500]
    targets = b.get("targets") or []
    tgt = "\n\n".join(f"{art_label(t.get('no', ''))}({t.get('title', '')})\n{t.get('body', '')}" for t in targets)[:9000]
    system = f"""당신은 한국농업기술진흥원(농진원) 내규 개정 전문가입니다.
개정 의도에 맞춰 대상 조문의 수정안을 작성하세요. 필요하면 조문 신설·삭제도 제안하세요.
{_RULES}

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
        if reg:
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
    r = find_reg(b.get("slug", ""), b.get("reg", ""))
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
    return jsonify({"success": True, "reg": r["title"], "targets": nos, "inner": inner,
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
    if b.get("slug") or b.get("reg"):
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
