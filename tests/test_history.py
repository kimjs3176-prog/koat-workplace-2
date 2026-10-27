"""조문 연혁: 보관본·이력에서 과거 판을 모아 조문별 변경을 보여 준다."""
import os

import reg_agent as ra
import reg_chunks

OLD = "제1조(목적) 이 규정은 여비에 관한 사항을 정한다.\n제15조(일비) 일비는 1일 2만원으로 한다.\n제16조(식비) 식비는 실비로 한다."
NEW = "제1조(목적) 이 규정은 여비에 관한 사항을 정한다.\n제15조(일비) 일비는 1일 2만5천원으로 한다.\n제17조(숙박비) 숙박비는 실비로 한다."


def _setup(tmp_path, monkeypatch):
    d = tmp_path / "여비규정"
    d.mkdir()
    (d / "text.txt").write_text(NEW, encoding="utf-8")
    b = tmp_path / ".backup" / "여비규정__20260101-120000-123"
    b.mkdir(parents=True)
    (b / "text.txt").write_text(OLD, encoding="utf-8")
    same = tmp_path / ".backup" / "여비규정__20260201-120000"
    same.mkdir()
    (same / "text.txt").write_text(NEW + "\n", encoding="utf-8")          # 현행과 같은 본문은 판으로 치지 않는다
    monkeypatch.setattr(reg_chunks, "REG_DIR", str(tmp_path))
    monkeypatch.setattr(ra, "_hist_git", lambda slug: [])
    monkeypatch.setattr(ra, "_hist_github", lambda slug: [])
    ra._HIST_CACHE.clear()
    reg = {"slug": "여비규정", "title": "여비규정", "revision": "2026년 3월 개정", **ra.parse_text(NEW)}
    monkeypatch.setattr(ra, "find_reg", lambda slug="", title="": reg if slug == "여비규정" else None)


def test_reg_versions_from_backups(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    v = ra.reg_versions("여비규정")
    assert [(x["date"], x["src"]) for x in v] == [("2026-01-01", "backup")]


def test_history_endpoint(tmp_path, monkeypatch, client):
    _setup(tmp_path, monkeypatch)
    d = client.get("/api/regagent/history?slug=여비규정&no=15").get_json()
    assert [(r["label"][:2], r["changed"]) for r in d["rows"]] == [("현행", True), ("개정", False)]
    assert "2만5천원" in d["rows"][0]["body"] and "2만원" in d["rows"][1]["body"]
    d = client.get("/api/regagent/history?slug=여비규정").get_json()
    assert d["versions"] == [{"date": "", "label": "현행 2026년 3월 개정", "changed": ["15"], "added": ["17"], "removed": ["16"]}]
    assert client.get("/api/regagent/history?slug=없음").status_code == 404
    ra._HIST_CACHE.clear()
