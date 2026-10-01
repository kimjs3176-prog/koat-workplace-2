"""
KOAT 규정 제·개정 에이전트 — API 서버
배포: Vercel / Render / Railway
로컬: python run_local.py
"""

import os, json, re, time, threading, webbrowser
import xml.etree.ElementTree as ET
# 신뢰할 수 없는 XML(업로드 파일·외부 법령 XML)의 엔티티 폭탄(billion laughs) 방어.
# defusedxml 이 있으면 그 파서를 쓰고, 없으면 표준 파서로 폴백한다.
try:
    import defusedxml.ElementTree as _DET
    def _xml_fromstring(s): return _DET.fromstring(s)
except Exception:
    def _xml_fromstring(s): return ET.fromstring(s)
import urllib3
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


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


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


# ── 내규 원문 ────────────────────────────────────────────────────────────────
REG_DIR = os.environ.get("REG_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "regulations")


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




# ── 의미 검색(임베딩) + 키워드 하이브리드 ─────────────────────────────────────
# 벡터는 리포지토리에 함께 배포되는 int8 파일에서 읽는다(벡터DB 불필요).
# 다른 기관 데이터를 쓸 때는 REG_VECTORS(확장자 뺀 경로 접두어)로 색인 위치를 바꾼다
_VEC_PREFIX = os.environ.get("REG_VECTORS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "regulations_vectors")
_VEC_BIN = _VEC_PREFIX + ".bin"
_VEC_META = _VEC_PREFIX + ".json"
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


import reg_upload as _reg_upload  # noqa: E402
_reg_upload.register(app)            # 내규 원문 등록(/upload) + 저장소 자동 커밋

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
