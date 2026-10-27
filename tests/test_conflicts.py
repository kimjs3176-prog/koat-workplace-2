"""같은 문장, 다른 수치: 내규 사이·본문과 별표 사이 불일치, 개정안이 바꾸는 수치 문장이 다른 곳에 있는지."""
import reg_agent as ra


def _reg(slug, title, arts, appendix=""):
    return {"slug": slug, "title": title, "category": "규칙", "revision": "2024년 1월 개정", "addenda": "", "appendix": appendix,
            "chapters": [], "articles": [{"no": n, "title": t, "body": b, "deleted": False} for n, t, b in arts]}


def _use(monkeypatch, regs):
    monkeypatch.setattr(ra, "all_regs", lambda: regs)
    ra._CF.clear(); ra._CF.update(key=None, v=None)
    monkeypatch.setattr(ra, "dup_regs", lambda: {})
    monkeypatch.setattr(ra, "citation_graph", lambda: {"nodes": [{"slug": r["slug"]} for r in regs], "edges": [], "broken": [], "stats": {}})


def test_cf_values_normalize():
    cl = ra._cf_clauses(_reg("a", "가", [("1", "", "숙박비는 1일 2만원으로 하고 숙박비 상한액의 10분의 3을 더 지급할 수 있다.")]))
    assert cl[0]["vals"] == ["1일", "20000원", "3/10"]
    assert not ra._cf_clauses(_reg("a", "가", [("1", "시행일", "이 규칙은 2025년 5월 1일부터 시행한다.")]))   # 날짜·시행일은 비교하지 않는다


def test_conflicts_mismatch_and_differ(monkeypatch):
    s = "회의소집은 간사를 통해 개최 {}일 전까지 개최일시 및 장소, 의제 등을 서면으로 통보하여야 한다."
    regs = [_reg("p", "여비규정", [("15", "숙박비", "국내여행자의 숙박비는 1박당 10만원 범위에서 실비로 지급하되 상한액을 넘을 수 없다.")]),
            _reg("p2", "여비규정 시행세칙", [("3", "숙박비", "국내여행자의 숙박비는 1박당 8만원 범위에서 실비로 지급하되 상한액을 넘을 수 없다.")]),
            _reg("c1", "가위원회 운영규칙", [("9", "회의", s.format(7))]),
            _reg("c2", "나위원회 운영규칙", [("9", "회의", s.format(10))]),
            _reg("c3", "다위원회 운영규칙", [("9", "회의", s.format(7))])]
    _use(monkeypatch, regs)
    v = ra.conflicts()
    assert [(c["a"]["slug"], c["b"]["slug"]) for c in v["mismatch"]] in ([("p", "p2")], [("p2", "p")])   # 규정↔시행세칙
    assert {frozenset((c["a"]["slug"], c["b"]["slug"])) for c in v["differ"]} == {frozenset(("c1", "c2")), frozenset(("c2", "c3"))}


def test_conflicts_skip_when_counterpart_has_same_value(monkeypatch):
    """별표가 두 경우를 함께 적은 경우(본문 35시간·30시간 ↔ 별표 35시간·30시간)는 불일치가 아니다."""
    b = "단축 후 근무시간이 주당 15시간 이상 {}시간 이하가 되어야 하며 단축한 시간은 무급으로 한다."
    regs = [_reg("s", "복무규정 시행세칙", [("7", "단축", "육아기 직원 : " + b.format(35) + "\n가족 돌봄 직원 : " + b.format(30))],
                 appendix="※ " + b.format(30) + "\n※ " + b.format(35))]
    _use(monkeypatch, regs)
    assert ra.conflicts()["mismatch"] == []


def test_conflict_check_for_amendment(monkeypatch, client):
    s = "회의소집은 간사를 통해 개최 {}일 전까지 개최일시 및 장소, 의제 등을 서면으로 통보하여야 한다."
    regs = [_reg("c1", "가위원회 운영규칙", [("9", "회의", s.format(10)), ("10", "의결", "회의는 재적위원 과반수의 출석으로 개의한다.")]),
            _reg("c1x", "가위원회 운영규칙 시행세칙", [("2", "회의", s.format(10))]),
            _reg("c2", "나위원회 운영규칙", [("9", "회의", s.format(7))])]
    _use(monkeypatch, regs)
    out = ra.conflict_check("c1", [{"no": "9", "old": s.format(10), "body": s.format(14)}])
    assert out[0]["old_vals"] == ["10일"] and out[0]["new_vals"] == ["14일"]
    pl = out[0]["places"]
    assert [p["slug"] for p in pl] == ["c1x", "c2"] and pl[0]["related"] and pl[0]["same_as_old"]   # 시행세칙이 먼저
    assert ra.conflict_check("c1", [{"no": "9", "old": s.format(10), "body": s.format(10) + " 끝."}]) == []   # 수치를 안 바꾸면 없음
    d = client.post("/api/regagent/conflicts/check", json={"slug": "c1", "changes": [{"no": "9", "old": s.format(10), "body": s.format(14)}, "x"]}).get_json()
    assert d["success"] and d["items"][0]["no"] == "9"
    d = client.get("/api/regagent/conflicts").get_json()
    assert d["success"] and d["counts"] == {"mismatch": 0, "differ": 2}   # 가위원회 규칙·세칙은 같은 10일


def test_health_counts_mismatch(monkeypatch):
    regs = [_reg("p", "여비규정", [("15", "숙박비", "국내여행자의 숙박비는 1박당 10만원 범위에서 실비로 지급하되 상한액을 넘을 수 없다.")]),
            _reg("p2", "여비규정 시행세칙", [("3", "숙박비", "국내여행자의 숙박비는 1박당 8만원 범위에서 실비로 지급하되 상한액을 넘을 수 없다.")])]
    _use(monkeypatch, regs)
    row = ra.health_row(regs[0], {}, "20261027")
    c = [i for i in row["issues"] if i["code"] == "conflict"]
    assert c and "100000원" in c[0]["msg"] and c[0]["other"] == "p2" and row["counts"]["conflict"] == 1
