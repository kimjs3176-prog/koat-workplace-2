"""기능완성도 검토에서 고친 부분의 회귀 테스트."""
import io
import struct
import zipfile
import zlib

import pytest

import hwp5
import notation as nt
import reg_agent as ra
import reg_import


def _zip(name, data, method=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        z.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


def test_safe_zip_read_ok():
    z = _zip("a.xml", "가나다" * 100)
    assert reg_import.safe_zip_read(z, "a.xml", 10_000).decode() == "가나다" * 100


def test_safe_zip_read_bomb_ratio():
    z = _zip("a.xml", b"\0" * 5_000_000)
    with pytest.raises(ValueError):
        reg_import.safe_zip_read(z, "a.xml", 50_000_000)


def test_safe_zip_read_limit():
    z = _zip("a.xml", b"x" * 2000, zipfile.ZIP_STORED)
    with pytest.raises(ValueError):
        reg_import.safe_zip_read(z, "a.xml", 1000)


def test_hwp_para_text_tab():
    data = "가".encode("utf-16le") + struct.pack("<8H", 9, 0, 0, 0, 0, 0, 0, 9) + "나".encode("utf-16le")
    assert hwp5._para_text(data) == "가\t나"


def test_hwp_records_level():
    rec = b"abcd"
    h = hwp5.HWPTAG_PARA_TEXT | (2 << 10) | (len(rec) << 20)
    assert list(hwp5._records(struct.pack("<I", h) + rec)) == [(hwp5.HWPTAG_PARA_TEXT, 2, rec)]


def test_hwp_corrupted_is_value_error():
    with pytest.raises(ValueError):
        hwp5.hwp_paragraphs(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    with pytest.raises(ValueError):
        hwp5.hwp_paragraphs(b"not an ole file")


@pytest.mark.parametrize("q,kw", [
    ("다른 공공기관들은 출장 규정을 어떻게 정했어?", "출장"),
    ("\"갑질\" 관련 타기관 사례", "갑질"),
    ("알리오에서 청렴 규정 찾아줘", "청렴"),
])
def test_compare_keyword(q, kw):
    assert ra.compare_keyword(q) == kw


def test_alio_rank_marks_relevant():
    arts = [
        {"no": "1", "title": "목적", "body": "이 규정은 출장에 관한 사항을 정한다.", "deleted": False},
        {"no": "2", "title": "출장비", "body": "출장비는 실비로 지급한다.", "deleted": False},
        {"no": "3", "title": "휴가", "body": "연차휴가는 15일로 한다.", "deleted": False},
    ]
    r = ra._alio_rank(arts, "출장비 지급", kw="출장")
    assert r[0]["no"] == "2" and r[0]["rel"]
    assert not next(a for a in r if a["no"] == "3")["rel"]


def test_term_uses_short_term_counts_spaced():
    assert ra._term_uses("보수 규정에 따른 보수", "보수") == 2


def test_tilde_suggest_keeps_context():
    f = next(f for f in nt.check("2026. 3. 5. ~ 2026. 3. 9.", "doc") if f["rule"] == "TILDE")
    assert "∼" in f["suggest"] and "~" not in f["suggest"]
    assert f["suggest"].replace("∼", "") == f["match"].replace("~", "").replace(" ", "")
