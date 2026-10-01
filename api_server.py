"""
KOAT 규정 제·개정 에이전트 — API 서버
배포: Vercel / Render / Railway
로컬: python run_local.py
"""

import os, json, re, time, threading, webbrowser, base64
import xml.etree.ElementTree as ET
# 신뢰할 수 없는 XML(업로드 파일·외부 법령 XML)의 엔티티 폭탄(billion laughs) 방어.
# defusedxml 이 있으면 그 파서를 쓰고, 없으면 표준 파서로 폴백한다.
try:
    import defusedxml.ElementTree as _DET
    def _xml_fromstring(s): return _DET.fromstring(s)
except Exception:
    def _xml_fromstring(s): return ET.fromstring(s)
import urllib3
from urllib.parse import quote
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests as req_lib
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
# CORS는 교차 출처(다른 웹사이트) 호출에만 적용된다. 이 앱의 프론트엔드는
# 동일 출처(/api/... 상대경로)라 아래 제한과 무관하게 항상 동작한다.
# 열린 CORS를 두면 임의의 외부 사이트가 브라우저에서 서버의 AI 키를 대신
# 소모할 수 있으므로, 허용 출처를 이 서비스 도메인·로컬 개발로 제한한다.
# 커스텀 도메인 등은 ALLOWED_ORIGINS(쉼표 구분)로 추가할 수 있다.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _origins_env:
    _cors_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
else:
    _cors_origins = [
        re.compile(r"^https://agro-law[\w.-]*\.vercel\.app$"),
        re.compile(r"^http://localhost(:\d+)?$"),
        re.compile(r"^http://127\.0\.0\.1(:\d+)?$"),
    ]
CORS(app, origins=_cors_origins)

OC   = os.environ.get("LAW_OC", "tjsl0919")
BASE = "https://www.law.go.kr/DRF"
HEADERS = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
    "Accept":          "application/json, text/html, */*;q=0.9",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.law.go.kr/",
    "Origin":          "https://www.law.go.kr",
    "Connection":      "keep-alive",
    "Cache-Control":   "no-cache",
}

# ── 재시도 정책이 적용된 requests 세션 ────────────────────────────────────────
def _make_session(verify: bool = True) -> req_lib.Session:
    retry = Retry(
        total=4,                              # 최대 4회 재시도
        backoff_factor=0.8,                   # 0.8→1.6→3.2→6.4s
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST"},
        raise_on_status=False,
        # ConnectionReset/ProtocolError 재시도 허용
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=8,
        pool_maxsize=24,
    )
    s = req_lib.Session()
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    s.headers.update(HEADERS)
    s.verify = verify
    return s

# 기본 세션은 TLS 인증서를 검증한다(GitHub 토큰·Google API 키 전송에 사용).
_SESSION = _make_session()
# 법제처(law.go.kr)는 인증서 체인 문제가 있어 이 호출에만 검증을 끈다.
# 민감한 토큰을 보내는 GitHub/Google 세션과 분리해 노출을 막는다.
_LAW_SESSION = _make_session(verify=False)


# ── 공통 HTTP 헬퍼 ────────────────────────────────────────────────────────────
# 타임아웃: (연결 대기, 읽기 대기)
_T_JSON = (5, 12)   # JSON 검색
_T_XML  = (5, 20)   # XML 조문 전문
_T_LONG = (5, 30)   # 긴 응답 (조문 전문 대용량)

def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "euc-kr"):
        try:
            return raw.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")

def _law_get_json(params: dict, timeout=None) -> dict:
    timeout = timeout or _T_JSON
    last_err = None
    for attempt in range(3):
        try:
            r = _LAW_SESSION.get(
                f"{BASE}/lawSearch.do",
                params={**params, "OC": OC, "type": "JSON"},
                timeout=timeout,
            )
            r.raise_for_status()
            return json.loads(_decode(r.content))
        except (req_lib.exceptions.ConnectionError,
                req_lib.exceptions.ChunkedEncodingError) as e:
            last_err = e
            # 공유 세션을 close() 하면 동시 실행 중인 다른 워커 스레드의 연결이
            # 끊긴다. 재시도는 풀에서 새 연결을 자동으로 받으므로 sleep만 한다.
            time.sleep(1.5 * (attempt + 1))
            continue
    raise last_err

def _law_get_xml(endpoint: str, params: dict, timeout=None) -> ET.Element:
    timeout = timeout or _T_XML
    last_err = None
    for attempt in range(3):
        try:
            r = _LAW_SESSION.get(
                f"{BASE}/{endpoint}",
                params={**params, "OC": OC, "type": "XML"},
                timeout=timeout,
            )
            r.raise_for_status()
            text = _decode(r.content).strip().lstrip("\ufeff")
            text = re.sub(r"<\?xml[^?]*\?>", "", text, count=1).strip()
            if not text:
                raise ValueError("빈 XML 응답")
            return _xml_fromstring(text)
        except (req_lib.exceptions.ConnectionError,
                req_lib.exceptions.ChunkedEncodingError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
            continue
    raise last_err


def _is_valid_law_xml(root: ET.Element) -> bool:
    """법제처 XML 응답이 유효한 법령 데이터인지 확인."""
    for tag in ("message", "Message", "error", "Error"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            txt = el.text.strip()
            if any(w in txt for w in ("없습니다", "없음", "오류", "error", "invalid")):
                return False
    return len({el.tag for el in root.iter()}) > 3


# 번호 태그 목록 (이 태그의 텍스트는 내용에서 제외)
_NO_TAGS = {"항번호","호번호","목번호","조번호","조문번호","항수","호수","목수",
            "조수","장번호","절번호","관번호","편번호"}
# 구조 컨테이너 (직접 텍스트 없이 자식만 가짐)
_SKIP_TAGS = {"조문단위","항","호","목","호목","조문","법령","조문내용그룹"}

def _node_text(el) -> str:
    """단일 노드의 직접 텍스트만 반환 (자식 텍스트 제외)"""
    return (el.text or "").strip()

# ── 항/호/목 계층 깊이 ────────────────────────────────────────────────────────
# 법제처 XML은 <목>을 <호>의 자식이 아니라 <항>의 자식(= <호>의 형제)으로 내려준다.
# 따라서 부모를 따라 깊이를 세면 목이 누락되므로, 태그별 고정 깊이를 사용한다.
_ITEM_DEPTH = {"항": 1, "호": 2, "목": 3, "호목": 3}
# 각 계층의 (번호 태그, 내용 태그)
_ITEM_TAGS = {
    "항":   ("항번호", "항내용"),
    "호":   ("호번호", "호내용"),
    "목":   ("목번호", "목내용"),
    "호목": ("목번호", "목내용"),
}
_CONTENT_TAGS = ("조문내용", "항내용", "호내용", "목내용")

# 내용 텍스트 맨 앞의 항·호·목 번호 패턴
#   ① / 1. / 1의2. / 가. / 가의2. / (1) / 1) / 가)
_NUM_PREFIX_RE = re.compile(
    r"^(?:[①-⑮㉑-㉟]"                       # 동그라미 숫자(항)
    r"|\d{1,3}(?:의\d{1,3})?\s*[.)]"        # 1.  1의2.  1)   (연도 '2024.' 오인 방지: 3자리 이내)
    r"|[가-힣](?:의\d{1,3})?\s*[.)]"        # 가.  가의2.  가)
    r"|\(\s*\d{1,3}\s*\)"                   # (1)
    r")"
)
def _split_no(depth: int, no: str, txt: str) -> tuple:
    """
    (번호, 내용) 을 확정한다.
      · 내용이 번호를 이미 품고 있으면 떼어내어 중복 표기를 막는다
        (예: 번호 '1의2.' + 내용 '1의2. 농업기계의 보급…' → ('1의2.', '농업기계의 보급…'))
      · 번호 태그가 비어 있어도 내용 앞의 번호를 인식해 계층 들여쓰기에 쓴다
      · depth 0(조문 본문)은 '제N조(제목)' 형태를 그대로 두어야 하므로 분리하지 않는다
    """
    no, txt = (no or "").strip(), (txt or "").strip()
    if depth <= 0 or not txt:
        return no, txt

    if no and txt.startswith(no):
        return no, txt[len(no):].lstrip()

    # 번호 태그가 없거나 표기가 달라도(1 vs 1.) 본문 앞 번호를 그대로 신뢰한다
    m = _NUM_PREFIX_RE.match(txt)
    if m:
        return m.group().strip(), txt[m.end():].lstrip()

    return no, txt


def _render_jo_struct(u: ET.Element) -> list:
    """
    <조문단위> 하나를 읽어 계층 구조를 가진 항목 리스트로 반환한다.
      [{"depth": 0, "no": "", "text": "제2조(정의) …"},
       {"depth": 2, "no": "1.", "text": "\"농업기계\"란 …"},
       {"depth": 3, "no": "가.", "text": "농림축산물의 생산에 …"}, …]
    depth 0=조문본문, 1=항, 2=호, 3=목.
    프론트엔드는 이 깊이로 매달린 들여쓰기(hanging indent)를 적용한다.
    """
    items = []

    def _emit(depth: int, no: str, txt: str):
        no, txt = _split_no(depth, no, txt)
        if no or txt:
            items.append({"depth": depth, "no": no, "text": txt})

    def _walk(node: ET.Element, depth: int):
        tag = node.tag

        if tag in _NO_TAGS:
            return                              # 번호 태그는 부모에서 처리

        if tag in _ITEM_TAGS:                   # 항 / 호 / 목
            d = _ITEM_DEPTH.get(tag, depth)
            no_tag, con_tag = _ITEM_TAGS[tag]
            _emit(d, _node_text(node.find(no_tag)) if node.find(no_tag) is not None else "",
                     _node_text(node.find(con_tag)) if node.find(con_tag) is not None else "")
            for child in node:                  # 하위 계층(호·목)은 문서 순서대로
                if child.tag in (no_tag, con_tag):
                    continue
                _walk(child, d)
            return

        if tag in _CONTENT_TAGS:                # 조문내용 등 단독 내용 태그
            _emit(depth, "", _node_text(node))
            if node.tail and node.tail.strip():
                _emit(depth, "", node.tail.strip())
            return

        for child in node:                      # 기타 컨테이너: 자식 순회
            _walk(child, depth)

    for child in u:
        if child.tag in ("조번호", "조문번호", "조문가지번호", "조문제목", "조제목"):
            continue                            # 번호·제목은 별도 필드로 추출
        _walk(child, 0)

    return items


def _struct_to_text(items: list) -> str:
    """계층 항목 리스트를 들여쓴 평문으로 변환(기존 조문내용 필드 호환)."""
    lines = []
    for it in items:
        indent = "  " * max(0, it.get("depth", 0) - 1)
        no, txt = it.get("no", ""), it.get("text", "")
        lines.append(f"{indent}{(no + ' ' + txt).strip() if no else txt}")
    return "\n".join(l for l in lines if l.strip())


def _render_jo(u: ET.Element) -> str:
    """<조문단위> 하나를 읽어서 깔끔한 조문 텍스트를 반환한다."""
    return _struct_to_text(_render_jo_struct(u))


# ── 법령MST 취득 (XML 검색 → 태그 추출) ──────────────────────────────────────
_MST_TAGS  = ("법령MST", "법령Mst", "행정규칙MST", "행정규칙Mst", "lawMst", "MST", "mst",
              "법령일련번호", "행정규칙일련번호")
_NAME_TAGS = ("법령명한글", "법령명", "행정규칙명")


def _mst_of(item: ET.Element) -> str:
    for tag in _MST_TAGS:
        v = (item.findtext(tag) or "").strip()
        if v:
            return v
    return ""


def _lookup_law(law_name: str, target: str = "law") -> dict:
    """
    법령명 → {"mst", "id", "name", "rank"}.
    · 법제처 검색은 질의어를 포함하는 다른 법령을 먼저 주는 경우가 있어
      (예: '특허법' → '특허료 등의 징수규칙') 이름이 정확히 일치하는 항목을 우선한다.
    · 같은 이름이 여러 건(현행·시행예정·연혁)일 때는 '현행'을 우선하고, 그다음
      시행일(오늘 이전) → 공포일이 최신인 항목을 고른다. 첫 항목을 무조건 쓰면
      이전 시행본(MST)에 연결돼 최신 법령과 어긋나던 문제를 막는다.
    · id(법령ID)는 버전과 무관한 법령 식별자라 lawService.do?ID= 로 조회하면
      법제처가 항상 현행 본문을 준다(MST는 특정 시행본의 일련번호).
    """
    out = {"mst": "", "id": "", "name": "", "rank": 99}
    try:
        root = _law_get_xml("lawSearch.do",
                            {"target": target, "query": law_name, "display": "30"})
        items = [el for el in root if _mst_of(el)] or \
                [el for el in root.iter() if el is not root and _mst_of(el)]
        want = _norm_key(law_name)
        today = time.strftime("%Y%m%d")

        def _txt(it, *tags):
            for t in tags:
                v = (it.findtext(t) or "").strip()
                if v:
                    return v
            return ""

        best_key = None
        for it in items:
            nm = _txt(it, *_NAME_TAGS)
            n = _norm_key(nm)
            rank = (0 if n == want else            # 완전 일치
                    1 if n.startswith(want) else   # '특허법 시행령' 류
                    2 if want in n else 3)         # 부분 포함 → 무관
            status = _txt(it, "현행연혁코드", "현행연혁구분", "현행여부")
            ef = re.sub(r"\D", "", _txt(it, "시행일자"))[:8]
            anc = re.sub(r"\D", "", _txt(it, "공포일자", "발령일자"))[:8]
            cur = 0 if (status == "현행" or (not status and (not ef or ef <= today))) else 1
            # 작은 값이 우선: 일치도 → 현행 → (시행일이 오늘 이전인) 최신 시행일 → 최신 공포일
            key = (rank, cur, 0 if (ef and ef <= today) else 1,
                   -int(ef or 0) if ef and ef <= today else 0, -int(anc or 0))
            if best_key is None or key < best_key:
                best_key = key
                out = {"mst": _mst_of(it),
                       "id": _txt(it, "법령ID", "행정규칙ID"),
                       "name": nm, "rank": rank, "status": status, "ef": ef}
        if out["mst"]:
            print(f"[MST] '{law_name}'({target}) → MST={out['mst']} ID={out['id']} "
                  f"(선택:'{out['name']}' 일치도={out['rank']} 상태={out.get('status')} 시행={out.get('ef')})")
            return out

        # 항목 단위 추출이 실패하면 문서 전체에서 첫 태그 사용(구버전 동작)
        for tag in _MST_TAGS:
            el = root.find(f".//{tag}")
            if el is not None and el.text and el.text.strip():
                print(f"[MST] '{law_name}'({target}) fallback {tag}={el.text.strip()}")
                out["mst"] = el.text.strip()
                return out
        print(f"[MST] '{law_name}'({target}) 실패 — 태그: {sorted({e.tag for e in root.iter()})}")
    except Exception as e:
        print(f"[MST] 오류: {e}")
    return out


def _get_mst(law_name: str, target: str = "law") -> str:
    """법령명 → MST(일련번호). 선택 규칙은 _lookup_law 참고."""
    return _lookup_law(law_name, target).get("mst", "")


def _fetch_law_root(law_name: str, target: str = "law", timeout=None, info: dict = None):
    """
    법령명으로 본문 XML(root)을 가져온다. 국가법령은 법령ID(→ 현행 본문)를 먼저 쓰고,
    실패하면 선택된 시행본의 MST로 조회한다. (MST 값을 ID 파라미터로 넣던 과거 폴백은
    전혀 다른 법령을 가져올 수 있어 쓰지 않는다.)
    """
    ref = info if info is not None else _lookup_law(law_name, target)
    endpoint = "admRulService.do" if target == "admrul" else "lawService.do"
    tries = []
    if target == "law" and ref.get("id"):
        tries.append({"target": target, "ID": ref["id"]})
    if ref.get("mst"):
        tries.append({"target": target, "MST": ref["mst"]})
        if target == "admrul":
            tries.append({"target": target, "ID": ref["mst"]})   # 행정규칙은 ID=일련번호
    for params in tries:
        try:
            r = _law_get_xml(endpoint, params, timeout=timeout)
            if _is_valid_law_xml(r):
                print(f"[law] '{law_name}' ← {endpoint} {params}")
                return r
        except Exception as e:
            print(f"[law] '{law_name}' {params} 실패: {e}")
    return None

# 구조 헤더 태그 (장·절·관·편 - 조문이 아님)
_STRUCT_TAGS = {"장", "절", "관", "편", "장번호", "절번호", "관번호", "편번호",
                "장제목", "절제목", "관제목", "편제목"}
_STRUCT_NO_TAGS  = ("장번호","절번호","관번호","편번호")
_STRUCT_TTL_TAGS = ("장제목","절제목","관제목","편제목")
_STRUCT_KIND_MAP = {"장번호":"장","절번호":"절","관번호":"관","편번호":"편"}

# 조문제목·조번호가 장/절/관/편임을 나타내는 패턴
_STRUCT_TITLE_RE = re.compile(r"^제\s*\d+\s*(?:장|절|관|편)")
_STRUCT_NO_RE    = re.compile(r"(?:장|절|관|편)")


def _is_struct_header(u: ET.Element) -> bool:
    """조문단위가 장/절/관/편 구조 헤더인지 판별"""
    child_tags = {c.tag for c in u}

    # ① 자식에 장/절/관/편 전용 태그가 있으면 확실한 헤더
    if child_tags & _STRUCT_TAGS:
        return True

    # ② 조번호 텍스트 자체가 "제N장/절/관/편" 형태인 경우 (법제처 일부 법령)
    jo_no_txt = (u.findtext("조번호") or u.findtext("조문번호") or "").strip()
    if jo_no_txt and _STRUCT_NO_RE.search(jo_no_txt):
        return True

    # ③ 조문제목이 "제N장/절/관/편" 패턴이면 헤더
    title_txt = (u.findtext("조문제목") or u.findtext("조제목") or "").strip()
    if title_txt and _STRUCT_TITLE_RE.match(title_txt):
        return True

    # ④ 조문내용 텍스트가 "제N장/절/관/편 …" 패턴이면 헤더
    #    예: <조번호>제1조</조번호><조문내용>제1장 총칙</조문내용>
    content_el = u.find("조문내용")
    if content_el is not None:
        content_txt = (content_el.text or "").strip()
        has_hang = bool(u.findall(".//항") or u.findall(".//호"))
        if content_txt and _STRUCT_TITLE_RE.match(content_txt) and not has_hang:
            return True

    # ⑤ 조번호가 전혀 없고 실질 내용(항/조문내용/호)도 없으면 헤더
    has_jo_no = bool(jo_no_txt)
    if not has_jo_no:
        has_content = bool(
            u.findall(".//항") or u.findall(".//조문내용") or u.findall(".//호")
        )
        if not has_content:
            return True

    return False


def _struct_label(u: ET.Element) -> tuple:
    """구조 헤더의 (레이블, 제목) 반환  예: ('제1장', '총칙')"""
    # ① 전용 번호 태그 우선
    no_label = ""
    for tag in _STRUCT_NO_TAGS:
        v = (u.findtext(tag) or "").strip()
        if v:
            kind = _STRUCT_KIND_MAP.get(tag, "")
            no_label = v if re.match(r"^제", v) else f"제{v}{kind}"
            break

    # ② 조번호 텍스트가 장/절 형태인 경우
    if not no_label:
        jo_txt = (u.findtext("조번호") or u.findtext("조문번호") or "").strip()
        if jo_txt and _STRUCT_NO_RE.search(jo_txt):
            no_label = jo_txt

    # ③ 전용 제목 태그
    title = ""
    for tag in _STRUCT_TTL_TAGS:
        v = (u.findtext(tag) or "").strip()
        if v:
            title = v; break

    # ④ 조문제목이 "제N장 XXX" 패턴이면 분리
    if not title:
        ttl_txt = (u.findtext("조문제목") or u.findtext("조제목") or "").strip()
        if ttl_txt:
            # "제2장 발명의 진흥" → no_label="제2장", title="발명의 진흥"
            m = re.match(r"^(제\s*\d+\s*(?:장|절|관|편))\s*(.*)", ttl_txt)
            if m:
                if not no_label:
                    no_label = m.group(1).replace(" ", "")
                title = m.group(2).strip()
            else:
                title = ttl_txt

    # ⑤ 조문내용이 "제N장 XXX" 패턴인 경우 (조번호만 있고 조문내용에 장 정보)
    #    예: 조번호="제1조", 조문내용="제1장 총칙"
    if not title:
        content_el = u.find("조문내용")
        if content_el is not None:
            ct = (content_el.text or "").strip()
            m = re.match(r"^(제\s*\d+\s*(?:장|절|관|편))\s*(.*)", ct)
            if m:
                if not no_label:
                    no_label = m.group(1).replace(" ", "")
                title = m.group(2).strip()

    # ⑥ 여전히 제목 없으면 자식 텍스트 fallback
    if not title:
        for c in u:
            if c.tag not in _NO_TAGS and c.tag not in _STRUCT_TAGS:
                txt = (c.text or "").strip()
                if txt and not _STRUCT_TITLE_RE.match(txt):
                    title = txt; break

    return no_label, title


def _art_label(no_d: str, branch: str, no_raw: str = "") -> str:
    """조문 표시번호: 조문번호 + 가지번호 → '제5조의2'."""
    if no_d:
        return f"제{no_d}조" + (f"의{branch}" if branch else "")
    m = re.match(r"^\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)", no_raw or "")
    return m.group(1).replace(" ", "") if m else ""


def _clean_article_title(title: str, art_no: str) -> str:
    """조문제목에서 앞의 '제N조(의M)' 중복 접두사 제거
    예: '제1조(목적)' → '(목적)' 또는 '목적'
        '제100조의2 등록 신청' → '등록 신청'
    """
    if not title or not art_no:
        return title
    # "제N조" 또는 "제N조의M" 접두사 제거
    cleaned = re.sub(r"^제\s*\d+\s*조(?:의\d+)?\s*", "", title).strip()
    # 남은 괄호만 있으면 제거: "(목적)" → "목적"
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    return cleaned if cleaned else title


# ── 조문 XML 파싱 ─────────────────────────────────────────────────────────────
def _parse_articles(root: ET.Element):
    all_tags = {el.tag for el in root.iter()}
    law_name = ""
    for tag in ("법령명한글", "법령명_한글", "법령명", "행정규칙명"):
        el = root.find(f".//{tag}")
        if el is not None and el.text and el.text.strip():
            law_name = el.text.strip(); break

    # 법령 공포일자 (기준일)
    law_date = ""
    for tag in ("공포일자", "시행일자"):
        el = root.find(f".//{tag}")
        if el is not None and el.text and el.text.strip():
            law_date = el.text.strip(); break

    def _get_amend_info(node: ET.Element) -> dict:
        """조문단위에서 개정·신설·삭제 정보 추출"""
        info = {}
        # 개정일자 태그들
        for tag in ("개정일자", "신설일자", "제정일자", "amendDate", "revisionDate"):
            el = node.find(tag)
            if el is not None and el.text and el.text.strip():
                info["amended_date"] = el.text.strip()
                break
        # 신설/개정/삭제 구분
        for tag in ("개정구분", "조문구분", "신구구분"):
            el = node.find(tag)
            if el is not None and el.text and el.text.strip():
                info["amend_type"] = el.text.strip()
                break
        # 법령 공포일자와 일치하면 최근 개정으로 마킹
        if law_date and not info.get("amended_date"):
            # 조문 자체에 날짜 없으면 법령 공포일을 기준으로 표시하지 않음
            pass
        return info

    articles = []

    # ── 전략 1: <조문단위> ──
    units = root.findall(".//조문단위")
    if units:
        print(f"[파싱] 전략1 조문단위 {len(units)}개")
        for u in units:
            if _is_struct_header(u):
                no_label, title = _struct_label(u)
                if title or no_label:
                    articles.append({
                        "조문번호": "", "조문제목": title,
                        "조문내용": "", "type": "header",
                        "header_no": no_label,
                    })
                continue

            no_raw = (u.findtext("조번호") or u.findtext("조문번호") or "").strip()
            title  = (u.findtext("조문제목") or u.findtext("조제목") or "").strip()
            branch = (u.findtext("조문가지번호") or "").strip()

            # 조번호에서 첫 번째 숫자만 추출 ("제5조의2" → "5")
            m_no  = re.search(r"\d+", no_raw)
            no_d  = m_no.group() if m_no else ""

            # 조문제목에서 앞의 "제N조" 중복 접두사 제거
            title = _clean_article_title(title, no_d)

            struct  = _render_jo_struct(u)
            content = _struct_to_text(struct).strip()
            amend   = _get_amend_info(u)
            if no_d or title or content:
                art = {"조문번호": no_d, "조문가지번호": branch,
                       "조문표시번호": _art_label(no_d, branch, no_raw),
                       "조문제목": title,
                       "조문내용": content, "조문구조": struct, "type": "article"}
                art.update(amend)
                articles.append(art)
        if articles:
            return law_name, law_date, articles

    # ── 전략 2: <조문> ──
    jos = root.findall(".//조문")
    if jos:
        print(f"[파싱] 전략2 조문 {len(jos)}개")
        for jo in jos:
            no_raw = (jo.findtext("조번호") or jo.findtext("번호") or "").strip()
            title  = (jo.findtext("조문제목") or jo.findtext("제목") or "").strip()
            branch = (jo.findtext("조문가지번호") or "").strip()
            m_no   = re.search(r"\d+", no_raw)
            no_d   = m_no.group() if m_no else ""
            title  = _clean_article_title(title, no_d)
            struct  = _render_jo_struct(jo)
            content = _struct_to_text(struct).strip()
            amend   = _get_amend_info(jo)
            if no_d or title or content:
                art = {"조문번호": no_d, "조문가지번호": branch,
                       "조문표시번호": _art_label(no_d, branch, no_raw),
                       "조문제목": title,
                       "조문내용": content, "조문구조": struct, "type": "article"}
                art.update(amend)
                articles.append(art)
        if articles:
            return law_name, law_date, articles

    # ── 전략 3: <조번호> 포함 부모 탐색 ──
    if "조번호" in all_tags:
        print("[파싱] 전략3 조번호 기반")
        seen = set()
        for parent in root.iter():
            no_el = parent.find("조번호")
            if no_el is None: continue
            no_raw = (no_el.text or "").strip()
            # 장/절/관/편 번호는 건너뜀
            if _STRUCT_NO_RE.search(no_raw): continue
            if no_raw in seen: continue
            seen.add(no_raw)
            title   = (parent.findtext("조문제목") or parent.findtext("제목") or "").strip()
            branch  = (parent.findtext("조문가지번호") or "").strip()
            m_no    = re.search(r"\d+", no_raw)
            no_d    = m_no.group() if m_no else ""
            title   = _clean_article_title(title, no_d)
            struct  = _render_jo_struct(parent)
            content = _struct_to_text(struct).strip()
            amend   = _get_amend_info(parent)
            if no_d or title:
                art = {"조문번호": no_d, "조문가지번호": branch,
                       "조문표시번호": _art_label(no_d, branch, no_raw),
                       "조문제목": title,
                       "조문내용": content, "조문구조": struct, "type": "article"}
                art.update(amend)
                articles.append(art)
        if articles:
            return law_name, law_date, articles

    print(f"[파싱] 실패 — 태그: {sorted(all_tags)[:40]}")
    return law_name, law_date, articles




# ── Flask 라우트 ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # 로컬 실행 시 index.html 서빙
    # Vercel에서는 vercel.json이 index.html을 직접 서빙함
    try:
        import os
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(html_path, encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    except FileNotFoundError:
        return Response("<h1>index.html not found</h1>", status=404)



@app.route("/api/law/articles")
def get_law_articles():
    """법령명으로 조문 전체 조회"""
    law_name = request.args.get("name", "").strip()
    if not law_name:
        return jsonify({"error": "name 파라미터가 필요합니다"}), 400
    try:
        # Step 1~3: 법령ID(현행 본문) → 현행 시행본 MST 순으로 조회
        tried = []
        info = _lookup_law(law_name, "law")
        root = None
        if info.get("rank", 99) > 1:
            # 국가법령 중 이름이 맞는 게 없으면(부분 일치뿐) 행정규칙에 정확히 같은 이름이
            # 있는지 먼저 본다 — 엉뚱한 법령 본문을 여는 것 방지
            adm = _lookup_law(law_name, "admrul")
            if adm.get("rank") == 0:
                root = _fetch_law_root(law_name, "admrul", timeout=(5, 20), info=adm)
                tried.append("admrul(정확일치):" + ("성공" if root is not None else "실패"))
        if root is None:
            root = _fetch_law_root(law_name, "law", info=info)
            tried.append("law:" + ("성공" if root is not None else "실패"))

        # Step 4: 행정규칙(admrul) fallback — lawService.do 모두 실패한 경우
        if root is None:
            try:
                mst_admrul = _get_mst(law_name, target="admrul")
                if mst_admrul:
                    for param_name in ("MST", "ID"):
                        try:
                            r_adm = _law_get_xml("admRulService.do",
                                                 {"target": "admrul", param_name: mst_admrul},
                                                 timeout=(5, 20))
                            if _is_valid_law_xml(r_adm):
                                root = r_adm
                                tried.append(f"admrul:{param_name}={mst_admrul}(성공)")
                                break
                        except Exception as e_adm:
                            tried.append(f"admrul:{param_name}={mst_admrul}({e_adm})")
                else:
                    tried.append("admrul:MST 없음")
            except Exception as e4:
                print(f"[articles] Step4(admrul) 오류: {e4}")

        print(f"[articles] '{law_name}' 시도 내역: {tried}")

        if root is None:
            return jsonify({
                "success": True, "law_name": law_name, "count": 0, "articles": [],
                "message": f"조문 데이터를 가져올 수 없습니다. 법제처에서 직접 확인해주세요."
            })

        lname, law_date, articles = _parse_articles(root)
        return jsonify({"success": True, "law_name": lname or law_name,
                        "law_date": law_date,
                        "version": ({"status": info.get("status", ""), "ef": info.get("ef", ""),
                                     "mst": info.get("mst", ""), "id": info.get("id", "")}
                                    if "law:성공" in tried else {}),
                        "count": len(articles), "articles": articles})

    except req_lib.exceptions.ConnectTimeout:
        return jsonify({"error": "법제처 서버 연결 시간 초과 (5초). 잠시 후 다시 시도해주세요."}), 504
    except req_lib.exceptions.ReadTimeout:
        return jsonify({"error": "법제처 서버 응답 시간 초과. 법령 데이터가 클 수 있습니다. 잠시 후 다시 시도해주세요."}), 504
    except req_lib.exceptions.ConnectionError as e:
        return jsonify({"error": f"법제처 서버에 연결할 수 없습니다: {e}"}), 502
    except req_lib.exceptions.Timeout:
        return jsonify({"error": "법제처 API 응답 시간 초과"}), 504
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"오류: {e}"}), 500




# ── AI 모델 자동 현행화 ─────────────────────────────────────────────────────
# Gemini는 모델명이 자주 갱신되므로 하드코딩하지 않고 ListModels로 최신을 고른다.
_AI_MODEL_FALLBACK = {"gemini": "gemini-flash-latest",
                      "claude": "claude-haiku-4-5-20251001",
                      "gpt": "gpt-4.1-mini", "openai": "gpt-4.1-mini"}
# 콜드 스타트에서 시나리오/해석 핫패스가 ListModels 왕복을 동기로 기다리지 않도록
# 즉시 반환할 기본 모델(캐시가 비었을 때 사용).
GEMINI_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash"
_GEMINI_MODEL_CACHE: dict = {"model": None, "ts": 0.0}
_GEMINI_CACHE_TTL = 6 * 3600          # 6시간
# 선호 Gemini 버전. 기본은 비워 두고 ListModels 기준 '사용 가능한 최신'을 자동 선택한다
# (현재 최신 계열은 3.x). 특정 버전으로 묶고 싶을 때만 GEMINI_MODEL_PREF=3.0 처럼 지정.
_GEMINI_PREF_DEFAULT = ""


# 텍스트 생성용이 아닌 계열(이미지·음성·로보틱스 등)은 generateContent 를 지원해도 제외한다.
_GEMINI_SKIP = re.compile(
    r"(image|nano-banana|tts|audio|native-audio|live|robotics|computer-use|omni|"
    r"embedding|deep-research|antigravity|gemma|lyria|veo|imagen)")


def _gemini_model_score(name: str):
    """모델명에서 (버전, 등급, 안정성) 점수를 뽑아 최신·상위 모델을 고른다."""
    n = name.lower()
    if _GEMINI_SKIP.search(n):
        return None
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", n)
    if not m:
        return None
    ver = int(m.group(1)) * 100 + int(m.group(2) or 0)
    # 등급: pro > flash > flash-lite  (본 서비스는 응답속도 중요 → flash 우대)
    if "flash-lite" in n:
        tier = 1
    elif "flash" in n:
        tier = 3
    elif "pro" in n:
        tier = 2
    else:
        tier = 0
    # 실험/프리뷰 버전은 안정 버전보다 후순위
    stable = 0 if re.search(r"(exp|preview|thinking|-\d{3,})", n) else 1
    return (ver, stable, tier)


def _gemini_latest_model(api_key: str) -> str:
    """Gemini ListModels로 모델명을 결정(6시간 캐시).

    GEMINI_MODEL_PREF(예: "4.6")로 선호 버전을 지정할 수 있고, 계정에서 해당 버전을
    쓸 수 있으면 그 버전을 우선 사용한다. 없으면 사용 가능한 최신 버전으로 폴백한다.
    (모델명을 고정하면 미출시/미허용 버전일 때 AI 기능 전체가 실패하므로 검증 후 사용)
    """
    now = time.time()
    if _GEMINI_MODEL_CACHE["model"] and now - _GEMINI_MODEL_CACHE["ts"] < _GEMINI_CACHE_TTL:
        return _GEMINI_MODEL_CACHE["model"]
    fallback = _AI_MODEL_FALLBACK["gemini"]
    if not api_key:
        return fallback
    try:
        r = _SESSION.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 200}, timeout=8)
        if r.status_code != 200:
            print(f"[ai-model] ListModels 실패({r.status_code}) → 폴백 {fallback}")
            return fallback
        pref = (os.environ.get("GEMINI_MODEL_PREF") or _GEMINI_PREF_DEFAULT).strip()
        pref_ver = None
        if pref:
            pm = re.match(r"(\d+)(?:\.(\d+))?$", pref)
            if pm:
                pref_ver = int(pm.group(1)) * 100 + int(pm.group(2) or 0)
        best, best_score = None, None
        pbest, pbest_score = None, None      # 선호 버전 중 최적
        for m in (r.json().get("models") or []):
            name = (m.get("name") or "").split("/")[-1]
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            sc = _gemini_model_score(name)
            if not sc:
                continue
            if best_score is None or sc > best_score:
                best, best_score = name, sc
            if pref_ver is not None and sc[0] == pref_ver:
                if pbest_score is None or sc > pbest_score:
                    pbest, pbest_score = name, sc
            elif pref and not pref_ver and pref.lower() in name.lower():
                if pbest_score is None or sc > pbest_score:
                    pbest, pbest_score = name, sc
        if pbest:
            _GEMINI_MODEL_CACHE.update({"model": pbest, "ts": now})
            print(f"[ai-model] 선호 버전({pref}) 모델 사용: {pbest}")
            return pbest
        if pref:
            print(f"[ai-model] 선호 버전({pref}) 사용 불가 → 최신 버전으로 대체")
        if best:
            _GEMINI_MODEL_CACHE.update({"model": best, "ts": now})
            print(f"[ai-model] Gemini 최신 모델 선택: {best}")
            return best
    except Exception as e:
        print(f"[ai-model] 조회 오류: {e}")
    return fallback


def _default_model_for(provider: str, api_key: str = "") -> str:
    """프로바이더별 기본 모델.

    Gemini 는 캐시에 값이 있으면 그것을, 없으면 상수 기본값을 '즉시' 돌려준다.
    핫패스(시나리오/해석)에서 콜드 인스턴스가 ListModels 네트워크 왕복을 동기로
    기다려 플랫폼 504 로 죽는 것을 막기 위함이다. 동적 최신화는 캐시가 채워진
    뒤(또는 /api/ai/models 명시 호출 시)에만 반영된다.
    """
    if provider == "gemini":
        return _GEMINI_MODEL_CACHE.get("model") or GEMINI_DEFAULT_MODEL
    return _AI_MODEL_FALLBACK.get(provider, _AI_MODEL_FALLBACK["gemini"])


@app.route("/api/ai/models")
def ai_models():
    """현재 선택될 기본 모델 확인용(설정 화면 표시).

    이 엔드포인트는 명시 호출이므로 Gemini 는 실시간 ListModels 로 캐시를 채운다.
    """
    provider = (request.args.get("provider") or "gemini").lower()
    key = (request.args.get("api_key") or
           os.environ.get(f"{provider.upper()}_API_KEY", "")).strip()
    if provider == "gemini":
        mdl = _gemini_latest_model(key)
    else:
        mdl = _default_model_for(provider, key)
    return jsonify({"success": True, "provider": provider, "model": mdl,
                    "resolved": provider == "gemini" and bool(key),
                    "cached_at": _GEMINI_MODEL_CACHE["ts"] if provider == "gemini" else 0})


def _gemini_thinking_cfg(mdl: str):
    """모델 세대에 맞는 사고(thinking) 설정.

    Gemini 3.x 는 기본적으로 길게 '생각'하고, 그 토큰이 maxOutputTokens 를 함께 쓴다.
    설정하지 않으면 답변이 나오기도 전에 예산이 소진돼 본문이 잘린다(finishReason=MAX_TOKENS).
    """
    n = (mdl or "").lower()
    if "gemini-2.5" in n:
        return {"thinkingBudget": 0}          # 2.5 계열은 예산(int)만 받는다
    if re.search(r"gemini-(1\.5|2\.0)", n):
        return None                           # 사고 기능 없음
    return {"thinkingLevel": "low"}           # 3.x·'-latest' 별칭


def _ai_generate(provider: str, api_key: str, mdl: str, system: str, user: str,
                 max_tokens: int = 1800, temperature: float = 0.2,
                 json_mode: bool = False):
    """프로바이더 공통 텍스트 생성. 반환: (text, error_message). 실패 시 text=''."""
    try:
        if provider == "gemini":
            url = (f"https://generativelanguage.googleapis.com/v1beta/models"
                   f"/{mdl}:generateContent?key={api_key}")

            def call(limit, think):
                cfg = {"maxOutputTokens": limit, "temperature": temperature}
                if json_mode:
                    cfg["responseMimeType"] = "application/json"
                if think:
                    cfg["thinkingConfig"] = think
                return _ai_post_retry(lambda: req_lib.post(
                    url, timeout=60, headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
                          "generationConfig": cfg}))

            think = _gemini_thinking_cfg(mdl)
            # 사고 토큰까지 감안해 넉넉히 잡는다(본문이 잘리는 것보다 낫다)
            limit = max(max_tokens, 3000)
            r = call(limit, think)
            if r.status_code == 400 and think and "thinking" in (r.text or "").lower():
                r = call(limit, None)           # 사고 설정 미지원 모델 폴백
            if r.status_code != 200:
                return "", _ai_error(r)[0]
            data = r.json()
            cands = data.get("candidates") or []
            if not cands:
                return "", "AI 응답이 비어 있습니다."

            def text_of(d):
                cs = d.get("candidates") or [{}]
                ps = cs[0].get("content", {}).get("parts") or []
                return "".join(p.get("text", "") for p in ps)

            txt = text_of(data)
            # 사고에 예산을 다 써서 본문이 잘렸으면 한 번 더 크게 잡아 재시도
            if cands[0].get("finishReason") == "MAX_TOKENS":
                r2 = call(min(limit * 3, 12000), think or {"thinkingLevel": "low"})
                if r2.status_code == 200:
                    t2 = text_of(r2.json())
                    if len(t2) > len(txt):
                        txt = t2
            if not txt.strip():
                return "", "AI가 본문을 생성하지 못했습니다(사고 토큰 초과). 잠시 후 다시 시도하세요."
            return txt, ""
        if provider == "claude":
            r = _ai_post_retry(lambda: req_lib.post(
                "https://api.anthropic.com/v1/messages", timeout=40,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": mdl, "max_tokens": max_tokens, "temperature": temperature,
                      "system": system, "messages": [{"role": "user", "content": user}]}))
            if r.status_code != 200:
                return "", _ai_error(r)[0]
            return "".join(p.get("text", "") for p in r.json().get("content", [])), ""
        if provider in ("gpt", "openai"):
            r = _ai_post_retry(lambda: req_lib.post(
                "https://api.openai.com/v1/chat/completions", timeout=40,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={"model": mdl, "temperature": temperature,
                      "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]}))
            if r.status_code != 200:
                return "", _ai_error(r)[0]
            return r.json()["choices"][0]["message"]["content"], ""
        if provider == "ollama":
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            r = req_lib.post(f"{base}/api/chat", timeout=60,
                             json={"model": mdl or "gemma2", "stream": False,
                                   "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": user}]})
            if r.status_code != 200:
                return "", f"Ollama 오류({r.status_code})"
            return (r.json().get("message") or {}).get("content", ""), ""
    except Exception as e:
        return "", f"AI 호출 오류: {e}"
    return "", f"지원하지 않는 프로바이더: {provider}"


def _ai_post_retry(do_post, tries=3):
    """AI 프로바이더 호출 — 과부하/일시오류(429/500/502/503/504)는 백오프 재시도."""
    import time as _t
    resp = None
    for i in range(tries):
        resp = do_post()
        if resp.status_code not in (429, 500, 502, 503, 504):
            return resp
        if i < tries - 1:
            _t.sleep(0.8 * (i + 1))
    return resp


def _ai_error(resp):
    """AI 응답 에러를 (사용자 메시지, 분류) 로 정규화."""
    try:
        msg = resp.json().get("error", {})
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
    except Exception:
        msg = (resp.text or "")[:200]
    low = (msg or "").lower()
    code = resp.status_code
    if code in (429, 503) or "overload" in low or "high demand" in low or "unavailable" in low or "quota" in low or "rate" in low:
        kind = "overload"
        user = f"AI 모델이 일시적으로 과부하 상태입니다 (재시도 후에도 실패). 잠시 뒤 다시 시도하거나 다른 모델을 선택하세요. (원문: {msg})"
    elif code in (401, 403) or "api key" in low or "permission" in low or "invalid" in low or "unauthenticated" in low:
        kind = "auth"
        user = f"API 키가 올바르지 않거나 권한이 없습니다. 키를 확인하세요. (원문: {msg})"
    else:
        kind = "error"
        user = msg or f"AI API 오류 ({code})"
    return user, kind


def _ai_url_allowed(url: str) -> bool:
    """승인된 모델 서버 URL 검증(F01/SSRF 방어).

    · http/https 스킴과 호스트가 있어야 한다.
    · OLLAMA_ALLOWED_HOSTS(쉼표 구분)가 설정돼 있으면 그 호스트만 허용한다.
      미설정이면 OLLAMA_BASE_URL 자체가 관리자 승인값이므로 형식만 확인한다.
    """
    try:
        from urllib.parse import urlparse
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        allow = [h.strip().lower() for h in
                 (os.environ.get("OLLAMA_ALLOWED_HOSTS") or "").split(",") if h.strip()]
        if allow and u.hostname.lower() not in allow:
            return False
        return True
    except Exception:
        return False


# ── 내규 원문·매니페스트 ─────────────────────────────────────────────────────
# ── 내규 원본 PDF(Supabase Storage 등) ───────────────────────────────────────
# 원본 HWP/HWPX를 PDF로 변환해 올린 스토리지의 공개 URL 접두사.
#   예) https://xxxx.supabase.co/storage/v1/object/public/regulations/pdf
REG_PDF_BASE_URL = os.environ.get("REG_PDF_BASE_URL", "").strip().rstrip("/")
_REG_MANIFEST: list | None = None


def _load_reg_manifest() -> list:
    """규정명 → 원본 PDF 매핑(regulations_manifest.json). 없으면 빈 목록."""
    global _REG_MANIFEST
    if _REG_MANIFEST is not None:
        return _REG_MANIFEST
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "regulations_manifest.json")
        with open(p, encoding="utf-8") as f:
            _REG_MANIFEST = json.load(f)
    except Exception as e:
        print(f"[reg-manifest] 로드 실패: {e}")
        _REG_MANIFEST = []
    return _REG_MANIFEST


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def _save_reg_manifest(man: list) -> None:
    """manifest 저장 — 기존 파일과 같은 포맷(indent=1)으로 써서 diff 를 최소화한다."""
    tmp = REG_MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, REG_MANIFEST_PATH)


def _find_reg_exact(name: str) -> dict | None:
    """규정명 '정확 일치'만 반환(공백·대소문자 무시). 유사명 매칭을 하지 않는다."""
    man = _load_reg_manifest()
    key = _norm_key(name)
    if not man or not key:
        return None
    for m in man:
        if _norm_key(m.get("title", "")) == key:
            return m
    return None


def _find_reg_original(name: str) -> dict | None:
    """규정명으로 원본 항목을 찾는다(정확 일치 → 포함 관계).

    포함 관계 매칭은 '가장 가까운' 제목을 고른다. 예전에는 '가장 긴 제목'을
    골라 '감사규정' 조회가 '감사규정 시행세칙'으로 잘못 연결되는 문제가 있었다.
    이제 질의어와 길이 차가 가장 작은(=가장 근접한) 제목을 우선한다.
    """
    m = _find_reg_exact(name)                      # 1) 정확 일치
    if m:
        return m
    man = _load_reg_manifest()
    key = _norm_key(name)
    if not man or not key:
        return None
    cands = [m for m in man                        # 2) 포함 관계(가장 근접한 제목 우선)
             if _norm_key(m.get("title", "")) and
             (_norm_key(m["title"]) in key or key in _norm_key(m["title"]))]
    if cands:
        return min(cands, key=lambda m: (abs(len(_norm_key(m.get("title", ""))) - len(key)),
                                         len(m.get("title", ""))))
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  개정 내규 업로드 (HWPX·DOCX·HTML·TXT·PDF)
#    · 원본을 regulations/<슬러그>/ 에 보관하고 열람용 HTML 을 생성한다
#    · regulations_manifest.json 에 등록해 기존 내규 조회·전문 화면에서 바로 열린다
#    · 추출 본문(text.txt)은 내규 검색·전문 조회의 로컬 소스로 쓰인다
# ══════════════════════════════════════════════════════════════════════════════
import zipfile, io as _io, unicodedata
from datetime import datetime, timezone, timedelta

REG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regulations")
REG_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "regulations_manifest.json")
# 업로드 토큰(설정 시 업로드에 필수) — 공개 배포본에서 무단 업로드 방지
REG_UPLOAD_TOKEN = os.environ.get("REG_UPLOAD_TOKEN", "").strip()
REG_UPLOAD_MAX_MB = int(os.environ.get("REG_UPLOAD_MAX_MB", "40"))
REG_CATEGORIES = ["정관", "규정", "규칙", "세칙", "예규", "매뉴얼", "기타"]
_ALLOWED_EXT = {".hwpx", ".hwp", ".docx", ".pdf", ".html", ".htm", ".txt", ".md"}
_KST = timezone(timedelta(hours=9))

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


def _guess_reg_category(title: str) -> str:
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


def _now_kst() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d %H:%M")


def _reg_slug(title: str) -> str:
    """규정명 → 디렉터리 슬러그. 기존 manifest 규칙(공백→_)을 따른다."""
    s = unicodedata.normalize("NFC", (title or "").strip())
    s = re.sub(r"[\\/:*?\"<>|]+", "", s)          # 경로·윈도우 금지문자 제거
    s = re.sub(r"\s+", "_", s).strip("._")
    return s[:120]


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
_ON_ATTR_RE = re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
# srcdoc/formaction 은 스크립트 실행 경로가 되므로 속성째 제거
_DANGER_ATTR_RE = re.compile(
    r"\s(srcdoc|formaction)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL_RE = re.compile(
    r"(href|src)\s*=\s*(\"|')\s*(?:javascript|data|vbscript):[^\"']*(\2)", re.I)


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
    out = _JS_URL_RE.sub(r"\1=\2#\2", out)
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


# ── 업로드된 내규의 로컬 본문 (내규 검색·전문 조회에 사용) ────────────────────
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
        return (True, "")
    tok = (request.form.get("token") or request.headers.get("X-Upload-Token") or "").strip()
    if tok == REG_UPLOAD_TOKEN:
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
        d = _gh("GET", f"/contents/{path}", params={"ref": ref or GITHUB_BRANCH})
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _gh_file(path: str, ref: str = ""):
    """저장소 파일 내용(bytes). 없으면 None."""
    try:
        d = _gh("GET", f"/contents/{path}", params={"ref": ref or GITHUB_BRANCH})
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


@app.route("/regulations/<path:subpath>")
def serve_regulation_file(subpath):
    """내규 원본 서식·업로드 문서 서빙(로컬 실행용 — Vercel은 vercel.json이 정적 처리)."""
    from flask import send_from_directory
    # 보관용 백업 폴더(.backup)는 노출하지 않는다
    if any(part.startswith(".") for part in subpath.replace("\\", "/").split("/")):
        return Response("<h1>404</h1>", status=404, mimetype="text/html; charset=utf-8")
    try:
        return send_from_directory(REG_DIR, subpath)
    except Exception:
        return Response("<h1>404 — 규정 파일을 찾을 수 없습니다</h1>",
                        status=404, mimetype="text/html; charset=utf-8")


@app.route("/upload")
@app.route("/upload.html")
def upload_page():
    """개정 내규 업로드 페이지."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload.html")
        with open(p, encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    except FileNotFoundError:
        return Response("<h1>upload.html not found</h1>", status=404)


@app.route("/api/regs/upload/status")
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


@app.route("/api/regs/names")
def reg_names_for_upload():
    """등록된 규정명 목록 — 업로드 화면의 '기존 규정 개정' 자동완성용."""
    man = _load_reg_manifest()
    return jsonify({"success": True, "names": [
        {"title": m.get("title", ""), "category": m.get("category", ""),
         "revision": m.get("revision", ""), "uploaded_at": m.get("uploaded_at", "")}
        for m in man if m.get("title")]})


@app.route("/api/regs/upload", methods=["POST"])
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


@app.route("/api/regs/upload/delete", methods=["POST"])
def reg_upload_delete():
    """
    업로드한 개정 내규 되돌리기.
      · 이전 개정이 있으면 그 개정본(파일·manifest 항목)으로 복원한다
      · 이전 개정이 없으면(신규 등록) 등록을 해제하고 파일을 삭제한다
    """
    _ok, _why = _upload_authorized()
    if not _ok:
        return jsonify({"error": _why}), 401
    slug = (request.form.get("slug") or (request.json or {}).get("slug") or "").strip()
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



# ── 의미 검색(임베딩) + 키워드 하이브리드 ─────────────────────────────────────
# 벡터는 리포지토리에 함께 배포되는 int8 파일에서 읽는다(벡터DB 불필요).
_VEC_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "regulations_vectors.bin")
_VEC_META = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "regulations_vectors.json")
_VEC_CACHE: dict = {"loaded": False, "meta": None, "mat": None, "np": None}
# 코사인 하한. 관련 없는 조문은 대체로 0.5 아래에 몰려 있어 노이즈를 걸러낸다.
_SEM_MIN = float(os.environ.get("SEMANTIC_MIN_SCORE", "0.55"))


def _vec_load():
    """벡터 파일 로드(프로세스당 1회). numpy 가 없으면 의미 검색을 끈다."""
    if _VEC_CACHE["loaded"]:
        return _VEC_CACHE
    _VEC_CACHE["loaded"] = True
    try:
        import numpy as np
    except ImportError:
        print("[vec] numpy 미설치 — 의미 검색 비활성")
        return _VEC_CACHE
    try:
        with open(_VEC_META, encoding="utf-8") as f:
            meta = json.load(f)
        dim, cnt = meta["dim"], meta["count"]
        raw = np.fromfile(_VEC_BIN, dtype=np.int8)
        if raw.size != dim * cnt:
            print(f"[vec] 크기 불일치 {raw.size} != {dim*cnt} — 비활성")
            return _VEC_CACHE
        mat = raw.reshape(cnt, dim).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        _VEC_CACHE.update({"meta": meta, "mat": mat / norms, "np": np})
        print(f"[vec] 로드 {cnt:,}청크 × {dim}차원")
    except FileNotFoundError:
        pass                                   # 벡터 파일 없음 = 기능 미사용
    except Exception as e:
        print(f"[vec] 로드 실패: {e}")
    return _VEC_CACHE


def _embed_query(text: str, api_key: str, model: str, dim: int = 0):
    """질의 임베딩. 실패 시 None.

    문서 벡터를 MRL 로 축소해 저장했으면 질의도 같은 차원으로 뽑아야 한다.
    """
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models"
               f"/{model}:embedContent?key={api_key}")
        body = {"model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_QUERY"}
        if dim:
            body["outputDimensionality"] = dim
        r = _SESSION.post(url, timeout=15, json=body)
        if r.status_code != 200:
            print(f"[vec] 질의 임베딩 실패({r.status_code})")
            return None
        return r.json()["embedding"]["values"]
    except Exception as e:
        print(f"[vec] 질의 임베딩 오류: {e}")
        return None


def semantic_search(query: str, api_key: str, top_k: int = 20):
    """의미 검색. [{slug,title,no,art_title,preview,score}] 또는 []"""
    c = _vec_load()
    if c["mat"] is None or not api_key:
        return []
    np = c["np"]
    qv = _embed_query(query, api_key,
                      c["meta"].get("model", "gemini-embedding-001"),
                      dim=int(c["meta"].get("dim") or 0))
    if not qv or len(qv) != c["mat"].shape[1]:
        if qv:
            print(f"[vec] 질의 차원 불일치 {len(qv)} != {c['mat'].shape[1]}")
        return []
    q = np.asarray(qv, dtype=np.float32)
    n = float(np.linalg.norm(q)) or 1.0
    sims = c["mat"] @ (q / n)
    k = min(top_k, sims.shape[0])
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    chunks = c["meta"]["chunks"]
    return [{**chunks[int(i)], "score": float(sims[int(i)])} for i in idx]


def _user_gemini_key():
    """사용자 Gemini 키 — 헤더(X-Gemini-Key) 우선, 없으면 서버 키.

    F02: URL 쿼리로 키를 받지 않는다. 쿼리 파라미터는 접근 로그·관측 시스템에
    남을 수 있어, 사용자별 키는 요청 헤더로만 전달받는다.
    """
    return (request.headers.get("X-Gemini-Key")
            or os.environ.get("GEMINI_API_KEY", "")).strip()



@app.route("/api/ping")
def ping():
    """서버 생존 확인 - 빠른 응답 (법제처 API 호출 없음)"""
    return jsonify({"server": True, "ok": True})


# ══════════════════════════════════════════════════════════════════════════
# 한글(.hwpx) 서식 베이스 — 실제 내규 hwpx의 header/스타일을 재사용
# ══════════════════════════════════════════════════════════════════════════
def _hwpx_base_bytes():
    """HWPX 서식 베이스 바이트. 임베드 모듈 우선(서버리스 대응), 실패 시 내규 원본."""
    try:
        import base64 as _b64, hwpx_base
        return _b64.b64decode(hwpx_base.BASE_HWPX_B64)
    except Exception:
        pass
    import glob as _glob
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in ([os.path.join(here, "regulations", "보직관리기준", "original.hwpx")]
                 + sorted(_glob.glob(os.path.join(here, "regulations", "*", "original.hwpx")))):
        if os.path.exists(cand):
            with open(cand, "rb") as f:
                return f.read()
    return None

def _hwpx_full_border(header_xml):
    """4면 모두 선이 있는 borderFill id를 찾는다(표 테두리용). 없으면 '3'."""
    for blk in re.findall(r'<hh:borderFill\b.*?</hh:borderFill>', header_xml, re.S):
        idm = re.match(r'<hh:borderFill id="([0-9]+)"', blk)
        if not idm:
            continue
        ok = 0
        for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
            m = re.search(r'<hh:' + side + r'\b[^>]*type="([^"]+)"', blk)
            if m and m.group(1) != "NONE":
                ok += 1
        if ok == 4:
            return idm.group(1)
    return "3"


# ══════════════════════════════════════════════════════════════════════════
# 규정 제·개정 에이전트(reg_agent.py) — 공통 헬퍼를 넘겨 등록
# ══════════════════════════════════════════════════════════════════════════
@app.route("/assets/<path:subpath>")
def serve_asset_file(subpath):
    """정적 리소스(로컬 실행용 — Vercel은 vercel.json이 정적 처리)."""
    from flask import send_from_directory
    if any(part.startswith(".") for part in subpath.replace("\\", "/").split("/")):
        return Response("404", status=404)
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"), subpath)


import reg_agent as _reg_agent  # noqa: E402
_reg_agent.register(
    app,
    ai_generate=_ai_generate,
    default_model_for=_default_model_for,
    semantic_search=semantic_search,
    user_gemini_key=_user_gemini_key,
    vec_ready=lambda: _vec_load()["mat"] is not None,
    hwpx_base_bytes=_hwpx_base_bytes,
    hwpx_full_border=_hwpx_full_border,
)


# ── 실행 ─────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 5100))

if __name__ == "__main__":
    url = f"http://localhost:{PORT}"
    print("=" * 50)
    print("  🌾  KOAT 규정 제·개정 에이전트")
    print(f"  🔗  {url}")
    print("  종료: Ctrl+C")
    print("=" * 50)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
