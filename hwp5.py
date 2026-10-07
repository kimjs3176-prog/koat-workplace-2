"""한/글 HWP 5.0(바이너리)·PDF 본문 추출 — 외부 변환 엔진 없이.

HWP 5.0 은 OLE 복합 문서다. BodyText/Section{n} 스트림(대개 zlib raw deflate 압축) 안의
레코드 가운데 HWPTAG_PARA_TEXT(67)가 문단 글자(UTF-16LE)를 담는다. 표 셀의 문단도 같은
레코드로 차례대로 나오므로 문단 단위 줄 목록이면 조문 파싱에 충분하다.
참고: 한글과컴퓨터 「한글 문서 파일 형식 5.0」 공개 문서.
"""
from __future__ import annotations

import io
import re
import struct
import zlib

HWPTAG_PARA_TEXT = 16 + 51
_MAX_SECTIONS = 200
_MAX_STREAM = 64 * 1024 * 1024          # 압축 해제 후 섹션 하나 상한

# 글자 컨트롤: 1 WCHAR 로 끝나는 것(그 밖의 0~31 은 8 WCHAR 확장·인라인 컨트롤)
_CHAR_CTRL = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}


def _para_text(data: bytes) -> str:
    out, i, n = [], 0, len(data) // 2
    while i < n:
        c = struct.unpack_from("<H", data, i * 2)[0]
        if c >= 32:
            out.append(chr(c))
            i += 1
        elif c in _CHAR_CTRL:
            if c in (10,):
                out.append("\n")
            elif c in (24, 30, 31):           # 하이픈·묶음 빈칸·고정폭 빈칸
                out.append("-" if c == 24 else " ")
            i += 1
        else:
            i += 8                            # 인라인·확장 컨트롤(표·그림·각주 등 자리표시)
    return "".join(out).replace("\r", "")


def _records(buf: bytes):
    pos, n = 0, len(buf)
    while pos + 4 <= n:
        h = struct.unpack_from("<I", buf, pos)[0]
        pos += 4
        tag, size = h & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > n:
                break
            size = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        if pos + size > n:
            break
        yield tag, buf[pos:pos + size]
        pos += size


def hwp_paragraphs(raw: bytes) -> list:
    """HWP 5.0 바이트 → 문단 글자 목록. 암호·배포용 문서나 HWP 3.x 는 ValueError."""
    try:
        import olefile
    except ImportError as e:                  # requirements.txt 의 olefile
        raise ValueError("HWP 변환 모듈(olefile)이 설치되어 있지 않습니다.") from e
    if not olefile.isOleFile(io.BytesIO(raw)):
        if raw[:17] == b"HWP Document File":
            raise ValueError("HWP 3.x 문서는 본문 변환을 지원하지 않습니다. 한/글에서 HWPX로 저장해 주세요.")
        raise ValueError("HWP 5.0 문서가 아닙니다.")
    ole = olefile.OleFileIO(io.BytesIO(raw))
    try:
        if not ole.exists("FileHeader"):
            raise ValueError("HWP 파일 헤더가 없습니다.")
        head = ole.openstream("FileHeader").read(256)
        if head[:17] != b"HWP Document File":
            raise ValueError("HWP 5.0 문서가 아닙니다.")
        flags = struct.unpack_from("<I", head, 36)[0]
        if flags & 0x2:
            raise ValueError("암호가 걸린 HWP 문서입니다.")
        if flags & 0x4:
            raise ValueError("배포용 HWP 문서라 본문을 읽을 수 없습니다.")
        compressed = bool(flags & 0x1)
        secs = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and re.fullmatch(r"Section\d+", e[1])),
                      key=lambda e: int(e[1][7:]))[:_MAX_SECTIONS]
        if not secs:
            raise ValueError("HWP 본문(BodyText)을 찾지 못했습니다.")
        paras = []
        for e in secs:
            data = ole.openstream(e).read()
            if compressed:
                d = zlib.decompressobj(-15)
                data = d.decompress(data, _MAX_STREAM)
                if d.unconsumed_tail:
                    raise ValueError("HWP 본문이 너무 큽니다.")
            for tag, rec in _records(data):
                if tag == HWPTAG_PARA_TEXT:
                    paras.extend(_para_text(rec).split("\n"))
        return paras
    finally:
        ole.close()


def hwp_text(raw: bytes) -> str:
    lines = [re.sub(r"[ \t ]+", " ", p).strip() for p in hwp_paragraphs(raw)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pdf_text(raw: bytes, max_pages: int = 300) -> str:
    """PDF 글자 추출(글자 층이 있는 PDF만, 스캔 이미지는 빈 문자열)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        r = PdfReader(io.BytesIO(raw))
        if r.is_encrypted:
            return ""
        parts = [(p.extract_text() or "") for p in r.pages[:max_pages]]
    except Exception:
        return ""
    t = "\n".join(parts)
    t = "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()
