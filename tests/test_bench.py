"""유관기관 수치 비교: 다른 기관 사규에서 같은 항목의 수치를 뽑는다."""
import alio
import reg_agent as ra

RULE = """여비규정
제1조(목적) 이 규정은 여비 지급에 관한 사항을 정한다.
제15조(일비) ① 국내여행자의 일비는 1일 2만5천원으로 한다. 다만, 공용차량을 이용하는 경우에는 일비의 2분의 1을 지급한다.
② 숙박비는 1박당 7만원 이내에서 실비로 지급한다.
제16조(근무지내 출장) 근무지내 출장의 일비는 4시간 이상인 경우 2만원을 지급한다.
부칙
이 규정은 2024년 1월 1일부터 시행한다."""


def test_bench_extract_values():
    m = ra.bench_extract(RULE.replace("2만5천원", "25,000원"), "일비", "원")
    assert [(x["no"], x["first"]) for x in m] == [("15", 25000.0), ("16", 20000.0)]
    assert ra.bench_extract(RULE, "숙박비", "원")[0]["first"] == 70000.0
    assert ra.bench_extract(RULE, "일비", "년") == []              # 그 단위의 수치가 없으면 없음
    assert ra.bench_extract(RULE, "일", "원") == []                # 항목은 두 글자 이상
    assert ra.bench_extract("제3조(경조휴가) 본인 결혼 시 경조휴가는 5일로 한다.", "경조휴가", "일")[0]["first"] == 5.0


def test_bench_rule_endpoint(client, monkeypatch):
    monkeypatch.setattr(alio, "rule_text", lambda rule: {"text": RULE.replace("2만5천원", "25,000원"), "file": {"fileName": "여비규정.hwp"}, "files": []})
    body = {"orgId": "C0105", "idx": "21892", "item": "일비", "unit": "원"}
    d = client.post("/api/regagent/bench/rule", json=body).get_json()
    assert d["success"] and d["matches"][0]["first"] == 25000.0 and d["url"].startswith("https://www.alio.go.kr")
    assert client.post("/api/regagent/bench/rule", json={**body, "item": "일"}).status_code == 400
    assert client.post("/api/regagent/bench/rule", json={**body, "unit": "kg"}).status_code == 400
    assert client.post("/api/regagent/bench/rule", json={**body, "orgId": "../x"}).status_code == 400

    def boom(rule):
        raise alio.AlioError("NETWORK", "알리오 연결 실패")
    monkeypatch.setattr(alio, "rule_text", boom)
    r = client.post("/api/regagent/bench/rule", json=body)
    assert r.status_code == 502 and r.get_json()["success"] is False
