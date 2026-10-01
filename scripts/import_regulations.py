"""기관 내규 일괄 등록 — 다른 기관이 자기 내규로 에이전트를 쓰도록 데이터를 만든다.

사용법
    python scripts/import_regulations.py <내규 파일 폴더> [--reset] [--dry-run]

    · 폴더 안의 .hwpx .docx .html .htm .txt .md (.pdf .hwp 는 원본 보관만) 를 읽어
      regulations/<규정명>/index.html·text.txt 와 regulations_manifest.json 을 만든다.
    · 파일명이 규정명이 된다. "인사규정(2025년도 1월 일부개정).hwpx" 처럼 괄호 안은 개정 정보로 쓴다.
    · --reset 을 주면 기존 regulations/ 와 매니페스트를 비우고 새로 만든다(다른 기관 최초 설정).
    · 등록 후 의미 검색을 쓰려면 scripts/build_embeddings.py 로 색인을 다시 만든다(선택).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reg_import as ri  # noqa: E402


def split_name(fname: str):
    stem = os.path.splitext(os.path.basename(fname))[0]
    m = re.match(r"^(.*?)\s*[(（]([^)）]*)[)）]\s*$", stem)
    title, rev = (m.group(1), m.group(2)) if m else (stem, "")
    return re.sub(r"[_\s]+", " ", title).strip(), rev.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="기관 내규 일괄 등록")
    ap.add_argument("folder", help="내규 파일이 있는 폴더")
    ap.add_argument("--reset", action="store_true", help="기존 내규 데이터를 지우고 새로 만든다")
    ap.add_argument("--dry-run", action="store_true", help="변환만 시험하고 저장하지 않는다")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.folder):
        ap.error(f"폴더가 없습니다: {a.folder}")
    files = sorted(f for f in os.listdir(a.folder)
                   if os.path.splitext(f)[1].lower() in ri.ALLOWED_EXT)
    if not files:
        print("등록할 파일이 없습니다(지원 형식: " + ", ".join(sorted(ri.ALLOWED_EXT)) + ")")
        return 1
    if a.reset and not a.dry_run:
        shutil.rmtree(ri.REG_DIR, ignore_errors=True)
        os.makedirs(ri.REG_DIR, exist_ok=True)
        man = []
    else:
        man = ri.load_manifest()
    ok = warn = fail = 0
    for f in files:
        title, rev = split_name(f)
        with open(os.path.join(a.folder, f), "rb") as fh:
            raw = fh.read()
        try:
            res = ri.convert(f, raw, title, {"revision": rev})
        except Exception as e:
            print(f"  ✗ {f}: {e}")
            fail += 1
            continue
        slug = ri.reg_slug(title)
        if not a.dry_run:
            ri.write_reg(slug, res["view_html"], res["text"], f, raw)
            man = ri.upsert(man, {"title": title, "revision": rev,
                                  "category": ri.guess_category(title), "slug": slug,
                                  "src": f, "html": f"/regulations/{slug}/index.html",
                                  "uploaded_at": ri.now_kst()})
        mark = "⚠" if res.get("warning") else "✓"
        warn += bool(res.get("warning"))
        ok += 1
        print(f"  {mark} {title}{(' · ' + rev) if rev else ''}{(' — ' + res['warning']) if res.get('warning') else ''}")
    if not a.dry_run:
        ri.save_manifest(man)
    print(f"\n완료: {ok}건 등록(주의 {warn}건), 실패 {fail}건 → {ri.REG_DIR}"
          + (" (시험 실행 — 저장 안 함)" if a.dry_run else ""))
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
