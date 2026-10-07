"""공문서 표기 점검 — 행정안전부 「행정업무운영편람」의 표기 원칙을 규칙으로 옮긴 자체 구현(외부 엔진 없음).

check(text, kind) → [{line, rule, level, label, match, message, suggest}]
kind: "doc"(이유서·공고·의견서처럼 본문·붙임·끝이 있는 문서) | "law"(규정 조문 — 붙임·끝 규칙 제외)
"""
from __future__ import annotations

import re

_LEVELS = ("error", "warn", "info")

# 숫자 → 한글 금액 읽기(금30,000원(금삼만원))
_DIG = "영일이삼사오육칠팔구"
_UNIT_S = ["", "십", "백", "천"]
_UNIT_L = ["", "만", "억", "조", "경"]


def hangul_amount(n: int) -> str:
    if n <= 0:
        return "영"
    out, li = [], 0
    while n > 0:
        n, chunk = divmod(n, 10000)
        if chunk:
            s = ""
            for i in range(3, -1, -1):
                d = chunk // (10 ** i) % 10
                if d:
                    s += _DIG[d] + _UNIT_S[i]
            out.append(s + _UNIT_L[li])
        li += 1
    return "".join(reversed(out))


def _fmt_date(y, m, d) -> str:
    return f"{int(y)}. {int(m)}. {int(d)}."


# 외래어·어려운 말 → 행정용어(편람·국립국어원 다듬은 말). “매뉴얼”은 내규 형식 이름으로 쓰여 제외
_LOANWORDS = [
    ("파일럿", "시범"), ("리스크", "위험 요인"), ("벤치마킹", "본뜨기·견주기"), ("벤치마크", "기준"),
    ("프로세스", "절차"), ("이슈", "쟁점"), ("가이드라인", "지침"), ("피드백", "의견"), ("모니터링", "점검"),
    ("니즈", "수요"), ("로드맵", "단계별 이행안"), ("인센티브", "유인책"), ("컨트롤타워", "총괄 기구"),
    ("거버넌스", "협치"), ("태스크포스", "전담 조직"), ("워크숍", "공동 연수"),
    ("어젠다", "의제"), ("마스터플랜", "종합 계획"), ("인프라", "기반 시설"), ("투트랙", "병행"),
]
_LOAN_RE = re.compile("|".join(re.escape(a) for a, _ in sorted(_LOANWORDS, key=lambda x: -len(x[0]))))
_LOAN = dict(_LOANWORDS)

_RULES = {
    "DATE_FORMAT": "날짜 표기",
    "DATE_ZERO": "날짜 0 표기",
    "DATE_DOT": "날짜 끝 온점",
    "TILDE": "기간 물결표",
    "BUNIM_COLON": "붙임 쌍점",
    "BUNIM_SPACE": "붙임 띄어쓰기",
    "END_SPACE": "끝 띄어쓰기",
    "END_MISSING": "끝 표시",
    "COLON_SPACE": "쌍점 띄어쓰기",
    "TIME": "시각 표기",
    "MONEY": "금액 표기",
    "DASH": "줄표",
    "QUOTE": "작은따옴표 강조",
    "LAW_BRACKET": "법령명 낫표",
    "LOANWORD": "외래어",
}


def _f(out, line, rule, level, match, message, suggest=""):
    out.append({"line": line, "rule": rule, "level": level, "label": _RULES[rule],
                "match": match[:80], "message": message, "suggest": suggest})


# 2026.10.06 / 2026-10-06 / 2026/10/6 / 2026. 10. 06.
_DATE_RE = re.compile(r"(?<![\d.])((?:19|20)\d{2})\s*([./-])\s*(\d{1,2})\s*\2\s*(\d{1,2})(\.?)(?![\d])")
_TILDE_RE = re.compile(r"\s+[~∼〜～]\s*|\s*[~∼〜～]\s+|[~〜～]")
_TIME_RE = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
_MONEY_RE = re.compile(r"(?<![\d,.])(\d{4,})\s*원")
_MONEY_COMMA_RE = re.compile(r"(?<![\d,.])(금\s*)?(\d{1,3}(?:,\d{3})+)\s*원(?!\s*\(\s*금)")
_COLON_RE = re.compile(r"([가-힣A-Za-z)」])(\s+):|([가-힣A-Za-z)」]):(?=[^\s/])")
_DASH_RE = re.compile(r"[—–―]")
_QUOTE_RE = re.compile(r"(?<![A-Za-z가-힣])'([^'\n]{1,30})'")
_LAW_BR_RE = re.compile(r"[『<《〈]\s*([^』>》〉\n]{2,40}?(?:법|법률|시행령|시행규칙|규정|규칙|지침))\s*[』>》〉]")


def check(text: str, kind: str = "doc") -> list:
    out: list = []
    text = str(text or "")
    lines = text.replace("\r\n", "\n").split("\n")
    for n, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        # 날짜
        for m in _DATE_RE.finditer(ln):
            y, sep, mo, d, dot = m.groups()
            if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
                continue
            good = _fmt_date(y, mo, d)
            raw = m.group(0)
            if sep != ".":
                _f(out, n, "DATE_FORMAT", "error", raw, "날짜는 온점으로 연·월·일을 구분합니다.", good)
            elif re.search(r"\.\S", raw.rstrip(".")):
                _f(out, n, "DATE_FORMAT", "error", raw, "날짜 온점 뒤는 한 칸 띄웁니다.", good)
            elif re.search(r"\.\s*0\d", raw):
                _f(out, n, "DATE_ZERO", "error", raw, "월·일 앞의 0은 쓰지 않습니다.", good)
            elif not dot:
                _f(out, n, "DATE_DOT", "warn", raw, "날짜 끝(일 다음)에도 온점을 찍습니다.", good)
        # 기간 물결표: 앞뒤를 붙여 쓰고 '∼'(물결표) 사용
        for m in _TILDE_RE.finditer(ln):
            raw = m.group(0)
            msg = "기간을 나타내는 물결표(∼)는 앞뒤를 붙여 씁니다." if raw.strip() in ("∼",) else "기간은 물결표 ‘∼’를 붙여 씁니다."
            _f(out, n, "TILDE", "warn", raw.strip() or raw, msg, "예) 2026. 10. 6.∼10. 26.")
        # 시각: 24시각제, 시·분 두 자리
        for m in _TIME_RE.finditer(ln):
            h, mi = int(m.group(1)), int(m.group(2))
            if h <= 24 and mi < 60 and len(m.group(1)) == 1:
                _f(out, n, "TIME", "warn", m.group(0), "시각은 24시각제로 시·분을 두 자리로 씁니다.", f"{h:02d}:{mi:02d}")
        # 금액: 쉼표·한글 병기
        for m in _MONEY_RE.finditer(ln):
            v = int(m.group(1))
            _f(out, n, "MONEY", "warn", m.group(0), "금액은 세 자리마다 쉼표를 찍고 한글을 함께 씁니다.", f"금{v:,}원(금{hangul_amount(v)}원)")
        if kind == "doc":
            for m in _MONEY_COMMA_RE.finditer(ln):
                v = int(m.group(2).replace(",", ""))
                _f(out, n, "MONEY", "info", m.group(0), "공문서 금액은 한글을 괄호로 함께 씁니다.", f"금{v:,}원(금{hangul_amount(v)}원)")
        # 쌍점: 앞말에 붙이고 뒤는 한 칸(시각·비율·URL 제외)
        if "://" not in ln:
            for m in _COLON_RE.finditer(ln):
                _f(out, n, "COLON_SPACE", "warn", m.group(0).strip(), "쌍점은 앞말에 붙이고 뒤는 한 칸 띄웁니다.", "예) 시행일: 2026. 1. 1.")
        # 줄표·작은따옴표 강조(생성형 문체 흔적)
        for m in _DASH_RE.finditer(ln):
            _f(out, n, "DASH", "warn", m.group(0), "줄표(—)는 공문서에 쓰지 않습니다. 쉼표·괄호·가운뎃점으로 풀어 씁니다.")
        for m in _QUOTE_RE.finditer(ln):
            _f(out, n, "QUOTE", "info", m.group(0), "작은따옴표 강조 대신 담백하게 서술합니다.")
        # 법령명은 낫표 「」
        for m in _LAW_BR_RE.finditer(ln):
            _f(out, n, "LAW_BRACKET", "warn", m.group(0), "법령·내규명은 낫표로 묶습니다.", f"「{m.group(1).strip()}」")
        # 외래어 → 행정용어(「…」 안의 고유 명칭은 제외)
        names = [(q.start(), q.end()) for q in re.finditer(r"「[^」]*」", ln)]
        for m in _LOAN_RE.finditer(ln):
            if any(a <= m.start() < b for a, b in names):
                continue
            _f(out, n, "LOANWORD", "info", m.group(0), "외래어 대신 행정용어를 씁니다.", _LOAN[m.group(0)])
        if kind == "doc":
            mb = re.match(r"\s*(?:\d+\.\s*)?붙임(\s*:\s*|\s?)(?=\S)", ln)
            if mb:
                if ":" in mb.group(1):
                    _f(out, n, "BUNIM_COLON", "error", ln.strip()[:20], "‘붙임’ 다음에 쌍점을 쓰지 않고 두 칸 띄웁니다.", "붙임  신구조문대비표 1부.  끝.")
                elif mb.group(1) == " " or mb.group(1) == "":
                    _f(out, n, "BUNIM_SPACE", "warn", ln.strip()[:20], "‘붙임’ 다음은 두 칸 띄웁니다.", "붙임  신구조문대비표 1부.  끝.")
            for m in re.finditer(r"(\S)( ?)끝\.\s*$", ln):
                if m.group(2) != "  " and not re.search(r"\S {2}끝\.\s*$", ln) and ln.strip() != "끝.":
                    _f(out, n, "END_SPACE", "warn", ln.strip()[-12:], "‘끝’은 본문·붙임 마지막 글자에서 두 칸 띄웁니다.", "…1부.  끝.")
    if kind == "doc" and text.strip() and not re.search(r"끝\.\s*$", text.strip()):
        _f(out, len(lines), "END_MISSING", "warn", text.strip()[-12:], "본문(또는 붙임) 마지막에 ‘끝.’을 표시합니다.", "…  끝.")
    order = {lv: i for i, lv in enumerate(_LEVELS)}
    out.sort(key=lambda x: (x["line"], order[x["level"]]))
    return out
