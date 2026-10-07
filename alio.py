"""알리오(ALIO, 공공기관 경영정보 공개시스템) 내부규정 조회 — 다른 기관 사규를 제·개정 참고 자료로.

알리오 사이트 화면이 쓰는 내부 JSON 주소를 그대로 쓴다(공식 문서가 없는 주소라 사이트가 바뀌면 SCHEMA 오류로 알린다).
요청 방식은 MIT 라이선스 오픈소스 alio-mcp(https://github.com/chromehearts79/alio-mcp)를 참고했다.
  ① 기관 목록   POST /item/itemOrganListSusi.json
  ② 규정 검색   POST /item/itemReportListSusi.json  (기관별, 한 쪽 10건)
  ③ 첨부 목록   GET  /item/itemBoard21110.do?…      (상세 HTML 의 rulefiledown 링크)
  ④ 파일 받기   GET  /download/rulefiledown.json?fileNo=…
알리오 서버에 부담을 주지 않도록 한 번에 조회하는 기관 수·동시 요청 수를 제한하고 결과를 캐시한다.
"""
from __future__ import annotations

import concurrent.futures as cf
import html as _html
import io
import os
import re
import threading
import time
import zipfile

import requests

BASE = "https://www.alio.go.kr"
REPORT_FORM = "21110"                 # 내부규정
CATEGORIES = {"K1100": "인사·복무·징계", "K1200": "보수", "K1300": "직제", "K1400": "기타", "K1500": "정관"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RegAgent/1.0; +https://www.alio.go.kr)",
    "Referer": f"{BASE}/item/itemOrganList.do?reportFormRootNo={REPORT_FORM}",
    "Origin": BASE,
}
TIMEOUT = float(os.environ.get("ALIO_TIMEOUT", "12"))
MAX_ORGS_PER_CALL = 12                # 한 요청에서 조회할 기관 수(화면이 나눠 부른다)
CONCURRENCY = 4
MAX_PAGES = 30
MAX_FILE = 25 * 1024 * 1024

_lock = threading.Lock()
_cache = {"orgs": None, "orgs_at": 0.0, "search": {}, "files": {}, "text": {}}


class AlioError(Exception):
    """kind: HTTP | NETWORK | SCHEMA(응답 구조가 다름 — 사이트 개편 의심) | NO_FILE | PARSE"""

    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind = kind


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


_S = _session()


def _request(method: str, path: str, *, json_body=None, binary=False, retries=2):
    last = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(0.5 * 2 ** (attempt - 1))
        try:
            r = _S.request(method, BASE + path, json=json_body, timeout=TIMEOUT, stream=binary)
        except requests.RequestException as e:
            last = AlioError("NETWORK", f"알리오 연결 실패: {type(e).__name__}")
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = AlioError("NETWORK", f"알리오 응답 오류(HTTP {r.status_code})")
            continue
        if r.status_code != 200:
            raise AlioError("HTTP", f"알리오 응답 오류(HTTP {r.status_code})")
        if binary:
            buf = io.BytesIO()
            for chunk in r.iter_content(65536):
                buf.write(chunk)
                if buf.tell() > MAX_FILE:
                    raise AlioError("HTTP", "규정 파일이 너무 큽니다.")
            return r, buf.getvalue()
        return r, r.text
    raise last


def _json(method: str, path: str, body=None):
    _, txt = _request(method, path, json_body=body)
    try:
        import json
        return json.loads(txt)
    except ValueError:
        raise AlioError("SCHEMA", "알리오 응답이 JSON이 아닙니다(차단 페이지 또는 사이트 개편 의심).")


# ── ① 기관 목록 ─────────────────────────────────────────────────────────────
def list_orgs() -> list:
    with _lock:
        if _cache["orgs"] and time.time() - _cache["orgs_at"] < 6 * 3600:
            return _cache["orgs"]
    j = _json("POST", "/item/itemOrganListSusi.json",
              {"apbaType": [], "jidtDptm": [], "area": [], "apbaId": "", "reportFormRootNo": REPORT_FORM})
    arr = (j.get("data") or {}).get("organList") if isinstance(j, dict) else None
    if not isinstance(arr, list) or not arr:
        raise AlioError("SCHEMA", "알리오 기관 목록이 비어 있습니다(사이트 개편 의심).")
    orgs = [{"id": o.get("apbaId"), "name": (o.get("apbaNa") or "").strip(), "type": o.get("typeNa") or "",
             "dept": o.get("jidtNa") or "", "apbaType": o.get("apbaType") or ""} for o in arr if o.get("apbaId")]
    with _lock:
        _cache["orgs"], _cache["orgs_at"] = orgs, time.time()
    return orgs


# ── ② 기관별 규정 검색 ──────────────────────────────────────────────────────
def _search_org(org: dict, keyword: str, category: str) -> list:
    ck = (org["id"], keyword, category)
    with _lock:
        hit = _cache["search"].get(ck)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
    rows, total_page, total = [], 1, None
    page = 1
    while page <= total_page:
        j = _json("POST", "/item/itemReportListSusi.json", {
            "pageNo": page, "apbaId": org["id"], "apbaType": org.get("apbaType", ""),
            "reportFormRootNo": REPORT_FORM, "search_word": keyword, "search_flag": "title",
            "bid_type": category, "enfc_istt": ""})
        data = j.get("data") if isinstance(j, dict) else None
        res, meta = (data or {}).get("result"), (data or {}).get("page")
        if not isinstance(res, list) or not isinstance(meta, dict):
            raise AlioError("SCHEMA", f"{org['name']} 검색 응답 구조가 다릅니다(사이트 개편 의심).")
        if page == 1:
            total_page = min(int(meta.get("totalPage") or 1), MAX_PAGES)
            total = int(meta.get("totalCount") or 0)
        rows += res
        page += 1
    out = [{"org": org["name"], "orgId": org["id"], "title": (r.get("title") or "").strip(),
            "category": r.get("bidType") or "", "categoryName": CATEGORIES.get(r.get("bidType"), r.get("bidType") or ""),
            "enf": r.get("stDate") or "", "mod": r.get("idate") or "", "idx": str(r.get("idx") or ""),
            "table": r.get("tableName") or "COMM_RULE", "idxName": r.get("idxName") or "RULE_NO"}
           for r in rows if r.get("idx")]
    with _lock:
        _cache["search"][ck] = (time.time(), out)
        if len(_cache["search"]) > 2000:
            _cache["search"].clear()
    return out


def base_title(t: str) -> str:
    """규정명 비교용: 제·개정일 괄호, 앞머리 연도·분류번호를 뗀다."""
    t = re.sub(r"[(（\[]\s*(?:제정|개정|시행|전부개정|일부개정)?\s*[`'’]?[\d.\s년월일~-]{4,}\s*(?:제정|개정|시행)?\s*[)）\]]", "", t or "")
    t = re.sub(r"^\s*(?:19|20)\d{2}\s*년도?\s*", "", t)
    t = re.sub(r"^\s*(?:[가-힣]{1,2}-)?\d+(?:[-.]\d+)*(?:\.?\s+|[-.](?=[가-힣]))", "", t)
    return re.sub(r"\s+", "", t)


def _mark_superseded(hits: list) -> list:
    """같은 기관·같은 이름이 여러 건이면(옛 판을 따로 올린 경우) 시행일이 가장 늦은 것만 현행으로 본다."""
    latest = {}
    for h in hits:
        k = (h["orgId"], base_title(h["title"]))
        cur = latest.get(k)
        if not cur or (h["enf"], int(h["idx"] or 0)) > (cur["enf"], int(cur["idx"] or 0)):
            latest[k] = h
    for h in hits:
        h["superseded"] = latest[(h["orgId"], base_title(h["title"]))] is not h
    return hits


def search(keyword: str, org_ids: list, category: str = "", budget: float = 8.0) -> dict:
    """여러 기관을 동시에 조회. 실패(failed)·시간 초과(timedOut)한 기관도 빠짐없이 알린다."""
    orgs = {o["id"]: o for o in list_orgs()}
    pick = [orgs[i] for i in org_ids if i in orgs][:MAX_ORGS_PER_CALL]
    hits, failed = [], []
    ex = cf.ThreadPoolExecutor(max_workers=CONCURRENCY)
    futs = {ex.submit(_search_org, o, keyword, category): o for o in pick}
    done, pending = cf.wait(futs, timeout=budget)
    for f in done:
        o = futs[f]
        try:
            hits += f.result()
        except AlioError as e:
            failed.append({"org": o["name"], "orgId": o["id"], "kind": e.kind, "error": str(e)})
        except Exception as e:                               # noqa: BLE001 — 기관 하나의 실패가 전체를 멈추지 않게
            failed.append({"org": o["name"], "orgId": o["id"], "kind": "UNKNOWN", "error": type(e).__name__})
    ex.shutdown(wait=False, cancel_futures=True)
    timed = [{"org": futs[f]["name"], "orgId": futs[f]["id"], "kind": "TIMEOUT", "error": "시간 제한"} for f in pending]
    order = {o["id"]: i for i, o in enumerate(pick)}
    hits.sort(key=lambda h: (order.get(h["orgId"], 0), h["title"]))
    return {"hits": _mark_superseded(hits), "failed": failed, "timedOut": timed, "searched": len(done)}


# ── ③ 첨부 목록 ─────────────────────────────────────────────────────────────
def parse_rule_files(page: str) -> list:
    files, seen = [], set()

    def add(no, name):
        if no not in seen:
            seen.add(no)
            files.append({"fileNo": no, "fileName": _html.unescape(name.strip())})

    for m in re.finditer(r'<a\b[^>]*href="[^"]*rulefiledown\.json\?fileNo=(\d+)"[^>]*>([^<]*)</a>', page, re.I):
        add(m.group(1), m.group(2))
    for m in re.finditer(r"previewAjax\(\s*'(\d+)'\s*,\s*'([^']*)'", page):
        add(m.group(1), m.group(2))
    if not files and re.search(r"fileNo=\d+|downRuleFile\(", page):
        raise AlioError("SCHEMA", "상세 페이지의 첨부 목록을 해석하지 못했습니다(사이트 개편 의심).")
    return files


def detail_url(rule: dict) -> str:
    from urllib.parse import urlencode
    qs = urlencode({"disclosureNo": "null", "apbaId": rule["orgId"], "nowcode": REPORT_FORM, "reportFormNo": REPORT_FORM,
                    "table_name": rule.get("table") or "COMM_RULE", "idx_name": rule.get("idxName") or "RULE_NO",
                    "idx": rule["idx"], "reportGbn": "N", "bid_type": rule.get("category") or ""})
    return f"/item/itemBoard{REPORT_FORM}.do?{qs}"


def rule_files(rule: dict) -> list:
    ck = (rule["orgId"], rule["idx"], rule.get("mod", ""))
    with _lock:
        hit = _cache["files"].get(ck)
    if hit is not None:
        return hit
    _, page = _request("GET", detail_url(rule))
    files = parse_rule_files(page)
    with _lock:
        _cache["files"][ck] = files
        if len(_cache["files"]) > 2000:
            _cache["files"].clear()
    return files


def pick_latest(files: list):
    """현행본 = 가장 나중에 올린 파일(fileNo 최댓값). 파일명의 연도 표기는 제각각이라 쓰지 않는다."""
    return max(files, key=lambda f: int(f["fileNo"])) if files else None


# ── ④ 파일 → 본문 ───────────────────────────────────────────────────────────
def _kind(name: str, raw: bytes) -> str:
    """파일 종류 — 확장자보다 내용(머리 바이트)을 믿는다(알리오 첨부는 확장자와 실제 형식이 다른 경우가 있다)."""
    if raw[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return "bad"
        if any(n.lower().startswith("contents/section") for n in names):
            return "hwpx"
        if "word/document.xml" in names:
            return "docx"
        return "zip"
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or raw[:17] == b"HWP Document File":
        return "hwp"
    if raw[:5] == b"%PDF-":
        return "pdf"
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def file_text(name: str, raw: bytes, depth: int = 0) -> str:
    import hwp5
    import reg_import
    k = _kind(name, raw)
    try:
        if k == "zip" and depth == 0:              # 묶음(zip): 안의 한/글·Word·PDF 파일 가운데 가장 큰 것
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                inner = [i for i in z.infolist() if os.path.splitext(i.filename)[1].lower() in (".hwpx", ".hwp", ".docx", ".pdf")
                         and 0 < i.file_size < MAX_FILE]
                if not inner:
                    raise AlioError("PARSE", "묶음 파일 안에 읽을 수 있는 규정 파일이 없습니다.")
                f = max(inner, key=lambda i: i.file_size)
                return file_text(f.filename, z.read(f), depth + 1)
        if k == "hwpx":
            return reg_import._blocks_to_text(reg_import._hwpx_blocks(raw))
        if k == "docx":
            return reg_import._blocks_to_text(reg_import._docx_blocks(raw))
        if k == "hwp":
            return hwp5.hwp_text(raw)
        if k == "pdf":
            t = hwp5.pdf_text(raw)
            if not t:
                raise AlioError("PARSE", "PDF에서 글자를 뽑지 못했습니다(스캔 이미지 PDF일 수 있습니다).")
            return t
    except (ValueError, zipfile.BadZipFile) as e:
        raise AlioError("PARSE", str(e) or "파일을 읽지 못했습니다.")
    raise AlioError("PARSE", f"읽을 수 없는 형식입니다: {k or '알 수 없음'}")


def rule_text(rule: dict) -> dict:
    """규정 현행본 파일을 받아 본문을 돌려준다 → {text, file, files}. 본문은 fileNo 로 캐시한다."""
    files = rule_files(rule)
    pick = pick_latest(files)
    if not pick:
        raise AlioError("NO_FILE", "이 규정에는 첨부 파일이 없습니다.")
    with _lock:
        t = _cache["text"].get(pick["fileNo"])
    if t is None:
        r, raw = _request("GET", f"/download/rulefiledown.json?fileNo={pick['fileNo']}", binary=True)
        ct = r.headers.get("content-type", "")
        if re.search(r"text/html|application/json", ct, re.I):
            raise AlioError("SCHEMA", "알리오가 파일 대신 안내 페이지를 돌려주었습니다.")
        t = file_text(pick["fileName"], raw)
        with _lock:
            _cache["text"][pick["fileNo"]] = t
            if len(_cache["text"]) > 200:
                _cache["text"].pop(next(iter(_cache["text"])))
    return {"text": t, "file": pick, "files": files}
