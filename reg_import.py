"""기관 내규 원문 → 에이전트 데이터(regulations/<slug>/ + regulations_manifest.json) 변환.

HWPX·DOCX·HTML·TXT·MD(·PDF·HWP는 원본 보관만)를 조문 단위로 다룰 수 있는 열람 HTML과
본문 텍스트(text.txt)로 바꾼다. 다른 기관이 자기 내규를 들여올 때는
`python scripts/import_regulations.py <폴더>` 를 쓰면 된다(이 모듈을 사용).
"""
from __future__ import annotations

import io as _io
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone

try:
    import defusedxml.ElementTree as _DET

    def _xml_fromstring(s):
        return _DET.fromstring(s)
except Exception:  # pragma: no cover
    def _xml_fromstring(s):
        return ET.fromstring(s)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REG_DIR = os.environ.get("REG_DIR") or os.path.join(BASE_DIR, "regulations")
REG_MANIFEST_PATH = os.environ.get("REG_MANIFEST") or os.path.join(BASE_DIR, "regulations_manifest.json")
ALLOWED_EXT = {".hwpx", ".hwp", ".docx", ".pdf", ".html", ".htm", ".txt", ".md"}
_KST = timezone(timedelta(hours=9))


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# 규정명 끝말 → 내규 체계상의 구분.
# 기관 내규는 정관 > 규정 > 규칙 > 세칙 > 예규 순이고,
# 지침·요령·기준·수칙·계획 등 하위 문서는 모두 예규로 묶는다.
_REG_CAT_SUFFIX = (
    ("정관", "정관"),
    ("규정", "규정"),
    ("규칙", "규칙"),
    ("세칙", "세칙"),
    ("예규", "예규"),
    ("지침", "예규"), ("요령", "예규"), ("기준", "예규"), ("수칙", "예규"),
    ("준칙", "예규"), ("규준", "예규"), ("요강", "예규"), ("계획", "예규"),
    ("매뉴얼", "매뉴얼"), ("편람", "매뉴얼"), ("가이드", "매뉴얼"),
    ("안내서", "매뉴얼"), ("핸드북", "매뉴얼"),
)


def guess_category(title: str) -> str:
    """규정명으로 구분을 추정. 판단이 서지 않으면 '기타'.

    정관은 기관당 1건뿐이므로 이름이 '정관'으로 끝날 때만 인정한다.
    (예전에는 업로드 폼의 첫 선택지가 정관이라 '보직관리기준'처럼
     끝말이 목록에 없는 규정이 그대로 정관으로 등록되는 사고가 있었다.)
    """
    t = re.sub(r"\s+", "", (title or ""))
    t = re.sub(r"[(（\[【].*$", "", t)          # 뒤에 붙은 (제정 …)·[별표] 등 제거
    for suf, cat in _REG_CAT_SUFFIX:
        if t.endswith(suf):
            return cat
    return "기타"


def now_kst() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d %H:%M")


def reg_slug(title: str) -> str:
    """규정명 → 디렉터리 슬러그. 기존 manifest 규칙(공백→_)을 따른다."""
    s = unicodedata.normalize("NFC", (title or "").strip())
    s = re.sub(r"[\\/:*?\"<>|#%\x00-\x1f\x7f]+", "", s)   # 경로·윈도우 금지문자·URL 예약문자·제어문자 제거
    s = re.sub(r"\s+", "_", s).strip("._")
    # 파일시스템 이름 한도(255바이트) 안에서 자른다 — 한글은 글자당 3바이트
    b = s.encode("utf-8")[:200]
    return b.decode("utf-8", "ignore").strip("._")



# ── 문서 → 블록(단락·표) 추출 ────────────────────────────────────────────────
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_blocks(root: ET.Element, para_tag: str, table_tag: str,
                row_tag: str, cell_tag: str, text_tags: set,
                break_tags: set) -> list:
    """
    OWPML(HWPX)·OOXML(DOCX) 공통 블록 추출.
    표는 단락 안에 중첩되어 나타나므로(HWPX: p > run > tbl) 표를 만나면
    앞까지의 텍스트를 단락으로 끊고 표 블록을 따로 만든다 — 표가 줄글로 풀리지 않게.
    """
    blocks = []
    buf = []

    def flush():
        txt = re.sub(r"[ \t]+", " ", "".join(buf)).strip()
        buf.clear()
        if not txt:
            blocks.append({"type": "p", "text": ""})
            return
        for line in txt.split("\n"):
            blocks.append({"type": "p", "text": line.strip()})

    def cell_text(tc: ET.Element) -> str:
        parts = []
        for el in tc.iter():
            t = _local(el.tag)
            if t in text_tags:
                parts.append(el.text or "")
            elif t == para_tag and parts:
                parts.append(" ")
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    def cell_span(tc: ET.Element):
        """셀 병합 정보(colspan, rowspan). HWPX는 hp:cellSpan, DOCX는 gridSpan/vMerge."""
        cs = rs = 1
        for sub in tc.iter():
            n = _local(sub.tag)
            if n == "cellSpan":                      # HWPX
                cs = int(sub.get("colSpan") or 1)
                rs = int(sub.get("rowSpan") or 1)
            elif n == "gridSpan":                    # DOCX
                try:
                    cs = int(list(sub.attrib.values())[0])
                except (ValueError, IndexError):
                    pass
        return max(cs, 1), max(rs, 1)

    def table_block(tbl: ET.Element):
        rows = []
        for tr in tbl.iter():
            if _local(tr.tag) != row_tag:
                continue
            cells = []
            for tc in tr:
                if _local(tc.tag) != cell_tag:
                    continue
                cs, rs = cell_span(tc)
                cells.append({"t": cell_text(tc), "cs": cs, "rs": rs})
            if cells:
                rows.append(cells)
        _merge_char_cells(rows)      # 세로쓰기로 글자마다 쪼개진 셀 복원
        while rows and not any(c["t"] for c in rows[0]):   # 앞뒤 빈 행 제거
            rows.pop(0)
        while rows and not any(c["t"] for c in rows[-1]):
            rows.pop()
        if not rows:
            return None
        # 1열 표는 제목·안내 박스로 쓰인 레이아웃 표 → 표 대신 단락으로
        if max(sum(c["cs"] for c in r) for r in rows) <= 1:
            for r in rows:
                blocks.append({"type": "p", "text": (r[0]["t"] if r else "").strip()})
            return None
        return {"type": "table", "rows": rows}

    def walk(node, in_para: bool):
        for child in list(node):
            tag = _local(child.tag)
            if tag == table_tag:
                flush()                       # 표 앞 텍스트를 단락으로 마무리
                tb = table_block(child)
                if tb:
                    blocks.append(tb)
                continue
            if tag == para_tag and not in_para:
                buf.clear()
                walk(child, True)
                flush()
                continue
            if tag in text_tags:
                buf.append(child.text or "")
                continue
            if tag in break_tags:
                buf.append("\n")
                continue
            walk(child, in_para)

    walk(root, False)
    if buf:
        flush()
    return blocks


# 업로드 zip(HWPX/DOCX) 압축 해제 폭탄(zip bomb) 방어용 상한
_ZIP_ENTRY_MAX = 80 * 1024 * 1024     # 단일 항목 최대 80MB(압축 해제 기준)
_ZIP_TOTAL_MAX = 200 * 1024 * 1024    # 누적 읽기 최대 200MB


class _ZipBudget:
    """zip 항목의 압축 해제 크기를 검사하며 안전하게 읽는 헬퍼."""
    def __init__(self, z):
        self.z = z
        self.total = 0

    def read(self, name: str) -> bytes:
        try:
            size = self.z.getinfo(name).file_size
        except KeyError:
            size = 0
        if size > _ZIP_ENTRY_MAX:
            raise ValueError("압축 해제 크기 제한 초과")
        if self.total + size > _ZIP_TOTAL_MAX:
            raise ValueError("압축 해제 크기 제한 초과")
        data = self.z.read(name)
        self.total += len(data)
        if self.total > _ZIP_TOTAL_MAX:
            raise ValueError("압축 해제 크기 제한 초과")
        return data


def _hwpx_blocks(raw: bytes) -> list:
    """HWPX(한/글 OWPML, zip) 본문 추출."""
    blocks = []
    with zipfile.ZipFile(_io.BytesIO(raw)) as z:
        budget = _ZipBudget(z)
        names = [n for n in z.namelist()
                 if re.match(r"Contents/section\d+\.xml$", n, re.I)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        if not names:
            raise ValueError("HWPX 본문(Contents/section*.xml)을 찾을 수 없습니다.")
        for n in names:
            root = _xml_fromstring(budget.read(n))
            blocks += _xml_blocks(root, "p", "tbl", "tr", "tc",
                                  {"t"}, {"lineBreak"})
    return blocks


def _docx_blocks(raw: bytes) -> list:
    """DOCX(OOXML) 본문 추출."""
    with zipfile.ZipFile(_io.BytesIO(raw)) as z:
        budget = _ZipBudget(z)
        root = _xml_fromstring(budget.read("word/document.xml"))
    return _xml_blocks(root, "p", "tbl", "tr", "tc", {"t"}, {"br", "cr"})


def _text_blocks(text: str) -> list:
    return [{"type": "p", "text": l.rstrip()} for l in text.replace("\r\n", "\n").split("\n")]


_SCRIPT_RE = re.compile(
    r"<\s*(script|iframe|object|embed|applet|style)\b.*?<\s*/\s*\1\s*>",
    re.I | re.S)
_SCRIPT_OPEN_RE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|applet|link|meta|base)\b[^>]*>", re.I)
_ON_ATTR_RE = re.compile(r"[\s/\"']on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)   # <svg/onload=…> 도
# srcdoc/formaction 은 스크립트 실행 경로가 되므로 속성째 제거
_DANGER_ATTR_RE = re.compile(
    r"\s(srcdoc|formaction)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL_RE = re.compile(
    r"(href|src|action|xlink:href)\s*=\s*(\"|')\s*(?:javascript|data|vbscript):[^\"']*(\2)", re.I)
_JS_URL_BARE_RE = re.compile(r"(href|src|action|xlink:href)\s*=\s*(?:javascript|data|vbscript):[^\s>]*", re.I)
_ENTITY_RE = re.compile(r"&#(x[0-9a-f]+|\d+);?", re.I)


def _unentity_urls(html: str) -> str:
    """href/src 값 속 숫자 문자 참조(jav&#x61;script:)를 풀어 아래 검사에 걸리게 한다."""
    def dec(m):
        v = m.group(1)
        try:
            ch = chr(int(v[1:], 16) if v[0] in "xX" else int(v))
        except (ValueError, OverflowError):
            return m.group(0)
        return ch if ch.isascii() and (ch.isalnum() or ch in ":/") else m.group(0)
    return re.sub(r"((?:href|src|action|xlink:href)\s*=\s*[\"']?)([^\"'\s>]*)",
                  lambda m: m.group(1) + _ENTITY_RE.sub(dec, m.group(2)), html, flags=re.I)


def _sanitize_html(html: str) -> str:
    """업로드된 HTML에서 스크립트·이벤트 핸들러 제거(같은 출처에서 서빙되므로 필수).

    이는 심층 방어(defense-in-depth)일 뿐, 실제 신뢰 경계는 업로드 토큰이다.
    <table>/<tr>/<td>/<span>/<p>/<div>/style="..." 등 규정 서식에 필요한 요소는
    의도적으로 보존한다.
    """
    out = _SCRIPT_RE.sub("", html)
    out = _SCRIPT_OPEN_RE.sub("", out)
    out = _ON_ATTR_RE.sub("", out)
    out = _DANGER_ATTR_RE.sub("", out)
    out = _unentity_urls(out)
    out = _JS_URL_RE.sub(r"\1=\2#\2", out)
    out = _JS_URL_BARE_RE.sub(r'\1="#"', out)
    return out


_ONE_HANGUL = re.compile(r"^[가-힣]$")


def _merge_char_cells(rows: list) -> list:
    """세로쓰기 라벨이 글자마다 별도 셀로 쪼개진 것을 한 셀로 합친다.

    한글 문서에서 '활 용 기' 같은 라벨은 칸을 나눠 글자를 하나씩 넣는 경우가 많다.
    그대로 두면 폭 좁은 빈 칸이 늘어서 표가 어수선해진다.
    합친 셀의 colspan 을 합계로 유지해 열 정렬은 그대로 둔다.
    (숫자·기호는 실제 자료일 수 있으므로 한글 한 글자만 대상으로 한다)
    """
    for r in rows:
        out, i = [], 0
        while i < len(r):
            j = i
            while (j < len(r)
                   and _ONE_HANGUL.match((r[j]["t"] or "").strip())
                   and r[j]["rs"] == r[i]["rs"]):
                j += 1
            if j - i >= 2:
                out.append({"t": "".join((c["t"] or "").strip() for c in r[i:j]),
                            "cs": sum(c["cs"] for c in r[i:j]),
                            "rs": r[i]["rs"]})
                i = j
            else:
                out.append(r[i])
                i += 1
        r[:] = out
    return rows


def _blocks_to_text(blocks: list) -> str:
    lines = []
    for b in blocks:
        if b["type"] == "table":
            for row in b["rows"]:
                lines.append(" | ".join(c["t"] for c in row))
        else:
            lines.append(b.get("text", ""))
    # 3줄 이상 연속 공백 줄은 2줄로 압축
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_ART_HEAD_RE = re.compile(r"^제\s*\d+\s*조(?:\s*의\s*\d+)?\s*(?:\(|$|\s)")
_CHAP_HEAD_RE = re.compile(r"^제\s*\d+\s*(?:편|장|절|관)\b")
_APX_HEAD_RE = re.compile(r"^\[?\s*(?:별표|별지|붙임|서식)")


def _table_html(rows: list) -> str:
    """병합(colspan/rowspan)을 반영해 표를 렌더. 첫 행이 머리글로 보일 때만 thead 사용."""
    def cells(row, tag):
        out = []
        for c in row:
            attr = ""
            if c["cs"] > 1:
                attr += f' colspan="{c["cs"]}"'
            if c["rs"] > 1:
                attr += f' rowspan="{c["rs"]}"'
            out.append(f'<{tag}{attr}>{_esc(c["t"])}</{tag}>')
        return "".join(out)

    if not rows:
        return ""
    # 머리글 판정: 첫 행이 모두 채워져 있고 짧으면 헤더로 본다.
    # (자료 행이 헤더로 올라가 열이 어긋나는 것을 막는다)
    first = rows[0]
    # 날짜·호수·순수 숫자가 있으면 머리글이 아니라 자료 행(예: 연혁 표의 '제정 2010.07.14 …')
    _data_like = re.compile(r"^\s*(?:\d{4}\s*[.\-]|제\s*[\d\-]+\s*호|[\d,]+)\s*\.?\s*$")
    is_head = (len(rows) > 1
               and all(c["t"].strip() for c in first)
               and all(len(c["t"]) <= 20 for c in first)
               and not any(c["rs"] > 1 for c in first)
               and not any(_data_like.match(c["t"]) for c in first))
    head = f"<thead><tr>{cells(first, 'th')}</tr></thead>" if is_head else ""
    body_rows = rows[1:] if is_head else rows
    tb = "".join(f"<tr>{cells(r, 'td')}</tr>" for r in body_rows)
    return f'<div class="tbl-wrap"><table>{head}<tbody>{tb}</tbody></table></div>'


def _blocks_to_view_html(title: str, meta: dict, blocks: list,
                         orig_name: str = "") -> str:
    """열람용 HTML 생성 — 조·장 제목을 구분해 기존 원본 뷰어와 동일하게 읽히도록."""
    body = []
    for b in blocks:
        if b["type"] == "table":
            body.append(_table_html(b["rows"]))
            continue
        t = (b.get("text") or "").strip()
        if not t:
            body.append('<p class="blank"></p>')
        elif _CHAP_HEAD_RE.match(t):
            body.append(f'<h2 class="chap">{_esc(t)}</h2>')
        elif _ART_HEAD_RE.match(t):
            body.append(f'<h3 class="art">{_esc(t)}</h3>')
        elif _APX_HEAD_RE.match(t):
            body.append(f'<h3 class="apx">{_esc(t)}</h3>')
        else:
            body.append(f"<p>{_esc(t)}</p>")

    metarows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in [("규정 구분", meta.get("category")),
                     ("개정 구분", meta.get("revision")),
                     ("시행일자", meta.get("effective_date")),
                     ("담당 부서", meta.get("department")),
                     ("원본 파일", orig_name),
                     ("업로드", meta.get("uploaded_at"))] if v)
    note = meta.get("note") or ""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
 :root{{--tx:#1a1d21;--mu:#5b6472;--bd:#e5e8ec;--g:#1D9E75;--gl:#eafaf3;}}
 body{{font-family:'Malgun Gothic','맑은 고딕',system-ui,sans-serif;color:var(--tx);
   line-height:1.85;max-width:900px;margin:0 auto;padding:28px 26px 60px;font-size:15px;}}
 h1{{font-size:22px;text-align:center;margin:0 0 6px;letter-spacing:2px;}}
 .sub{{text-align:center;color:var(--mu);font-size:13px;margin-bottom:18px;}}
 .meta{{border-collapse:collapse;margin:0 auto 26px;font-size:13px;min-width:60%;}}
 .meta th,.meta td{{border:1px solid var(--bd);padding:5px 12px;text-align:left;}}
 .meta th{{background:var(--gl);color:var(--g);white-space:nowrap;font-weight:700;}}
 .note{{background:#fffbeb;border-left:3px solid #f59e0b;padding:8px 12px;
   font-size:13px;margin-bottom:22px;white-space:pre-wrap;}}
 h2.chap{{font-size:17px;margin:32px 0 12px;padding-bottom:5px;
   border-bottom:1px solid var(--bd);}}
 h3.art{{font-size:15px;margin:22px 0 6px;color:#0f172a;}}
 h3.apx{{font-size:15px;margin:26px 0 8px;color:var(--g);}}
 p{{margin:0 0 4px;white-space:pre-wrap;word-break:keep-all;}}
 p.blank{{height:8px;margin:0;}}
 .tbl-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:10px 0 18px;}}
 table{{border-collapse:collapse;font-size:12.5px;width:100%;table-layout:auto;}}
 th,td{{border:1px solid var(--bd);padding:5px 8px;vertical-align:top;
   word-break:keep-all;overflow-wrap:anywhere;line-height:1.55;}}
 thead th{{background:#f7f8fa;font-weight:700;text-align:center;}}
 /* 좁은 화면: 표를 원래 폭으로 두고 가로 스크롤(줄바꿈으로 뭉개지는 것 방지) */
 @media(max-width:820px){{ table{{width:auto;min-width:100%;}}
   th,td{{white-space:nowrap;}} }}
 @media print{{body{{padding:0;}}}}
</style></head><body>
<h1>{_esc(title)}</h1>
<div class="sub">{_esc(meta.get('revision') or '')}</div>
{f'<table class="meta">{metarows}</table>' if metarows else ''}
{f'<div class="note">{_esc(note)}</div>' if note else ''}
{chr(10).join(body)}
</body></html>"""


def _convert_upload(filename: str, raw: bytes, title: str, meta: dict) -> dict:
    """업로드 파일 → {view_html, text, converted, warning}."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".html", ".htm"):
        html = _sanitize_html(raw.decode("utf-8", errors="replace"))
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"[ \t]+", " ", text)
        return {"view_html": html, "text": re.sub(r"\n{3,}", "\n\n", text).strip(),
                "converted": True, "warning": ""}
    if ext == ".hwpx":
        blocks = _hwpx_blocks(raw)
    elif ext == ".docx":
        blocks = _docx_blocks(raw)
    elif ext in (".txt", ".md"):
        blocks = _text_blocks(_decode(raw))
    elif ext == ".pdf":
        # F08: /regulations/* 의 CSP(object-src/frame-src 'none')는 <embed>/<iframe>
        # 인라인 PDF 표시를 차단한다. 전체 내규의 스크립트 차단을 풀지 않고, 원본 PDF를
        # 새 탭 열기·다운로드 링크로 제공한다(최상위 탐색은 CSP 영향을 받지 않음).
        src = "original.pdf"
        html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{_esc(title)}</title><style>'
                f'body{{margin:0;font-family:system-ui,"Malgun Gothic",sans-serif;background:#f6f7f9;color:#1f2937;}}'
                f'.wrap{{max-width:640px;margin:8vh auto;padding:28px;background:#fff;'
                f'border:1px solid #e5e7eb;border-radius:14px;text-align:center;}}'
                f'.ic{{font-size:44px}}h1{{font-size:18px;margin:10px 0 6px}}'
                f'p{{color:#6b7280;font-size:14px;line-height:1.6}}'
                f'.btns{{margin-top:18px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap}}'
                f'a.btn{{display:inline-block;padding:11px 18px;border-radius:10px;'
                f'font-weight:700;text-decoration:none;font-size:14px}}'
                f'a.p{{background:#256ef4;color:#fff}}'
                f'a.s{{background:#eef2f7;color:#1f2937;border:1px solid #e5e7eb}}'
                f'</style></head><body><div class="wrap"><div class="ic">📄</div>'
                f'<h1>{_esc(title)}</h1>'
                f'<p>이 규정은 PDF 원본으로 등록되어 있습니다.<br>'
                f'아래 버튼으로 원문을 열람하거나 내려받을 수 있습니다.</p>'
                f'<div class="btns"><a class="btn p" href="{src}" target="_blank" rel="noopener">원본 PDF 열기</a>'
                f'<a class="btn s" href="{src}" download>다운로드</a></div>'
                f'<p style="margin-top:16px;font-size:12px">본문 검색이 필요하면 한/글에서 '
                f'HWPX 또는 DOCX로 저장해 다시 올려주세요.</p></div></body></html>')
        return {"view_html": html, "text": "", "converted": False,
                "warning": "PDF는 원본 열기·다운로드로 제공됩니다. 본문 검색이 필요하면 HWPX 또는 DOCX로 올려주세요."}
    elif ext == ".hwp":
        blocks = []
    else:
        raise ValueError(f"지원하지 않는 형식입니다: {ext}")

    if ext == ".hwp":
        html = _blocks_to_view_html(
            title, meta,
            [{"type": "p", "text": "이 규정은 구버전 HWP(바이너리) 형식으로 업로드되어 "
                                   "본문을 자동 변환하지 못했습니다."},
             {"type": "p", "text": "한/글에서 '다른 이름으로 저장 → HWPX'로 저장해 다시 올리면 "
                                   "본문까지 조회·검색됩니다. 원본 파일은 아래 링크로 내려받을 수 있습니다."}],
            orig_name=filename)
        return {"view_html": html, "text": "", "converted": False,
                "warning": "HWP(구버전)는 본문 자동 변환을 지원하지 않습니다. HWPX로 저장해 올리면 본문까지 검색됩니다."}

    text = _blocks_to_text(blocks)
    if not text:
        raise ValueError("본문 텍스트를 추출하지 못했습니다. 파일이 손상되었는지 확인해주세요.")
    return {"view_html": _blocks_to_view_html(title, meta, blocks, orig_name=filename),
            "text": text, "converted": True, "warning": ""}



def norm_key(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def load_manifest() -> list:
    try:
        with open(REG_MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_manifest(man: list) -> None:
    """manifest 저장 — 기존 파일과 같은 포맷(indent=1)으로 써서 diff 를 최소화한다."""
    tmp = REG_MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, REG_MANIFEST_PATH)


def convert(filename: str, raw: bytes, title: str, meta: dict) -> dict:
    """파일 → {view_html, text, converted, warning}"""
    return _convert_upload(filename, raw, title, meta)


def write_reg(slug: str, view_html: str, text: str, orig_filename: str, raw: bytes) -> str:
    """regulations/<slug>/ 에 열람 HTML·본문·원본을 쓴다. 저장된 원본 파일명 반환."""
    d = os.path.join(REG_DIR, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(view_html)
    if text:
        with open(os.path.join(d, "text.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    ext = os.path.splitext(orig_filename)[1].lower()
    stored = f"original{ext}"
    with open(os.path.join(d, stored), "wb") as f:
        f.write(raw)
    return stored


def upsert(man: list, entry: dict) -> list:
    """같은 규정명이 있으면 교체, 없으면 추가(순서 유지)."""
    key = norm_key(entry["title"])
    for i, m in enumerate(man):
        if norm_key(m.get("title", "")) == key:
            man[i] = {**m, **entry}
            return man
    man.append(entry)
    return man
