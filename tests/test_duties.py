"""권한·절차(규정 온톨로지 3단계): 조문 문장의 주체·행위·상대·기한, 위임전결 별표, 자문 연계."""
import pytest

import reg_agent as R


@pytest.fixture()
def client():
    import api_server
    api_server.app.config["TESTING"] = True
    return api_server.app.test_client()


def _find(pred):
    return [x for x in R.duties()["rels"] if pred(x)]


def test_approver_and_subject():
    # “인사위원회의 심의를 거쳐” → 인사위원회가 심의권자
    assert _find(lambda x: x["actor"] == "인사위원회" and x["kind"] == "approve" and x["act"].startswith("심의"))
    # “이사회는 … 원장이 소집한다” — 주제(이사회)가 아니라 주어(원장)가 소집
    assert _find(lambda x: x["actor"] == "원장" and x["act"] == "소집" and x["reg"] == "한국농업기술진흥원 정관")
    assert not _find(lambda x: x["actor"] == "이사회" and x["act"] == "소집" and "원장이 소집" in x["sent"])
    # 종속절의 주어(“직원이 휴직을 신청하면 이를 허가”)는 허가 주체가 아니다
    assert not _find(lambda x: x["actor"] == "직원" and x["act"] == "허가")
    # 기한·의무
    x = _find(lambda x: x["act"] == "통보" and "60일 이내" in x["when"] and x["actor"] == "감사")
    assert x and x[0]["target"] == "원장" and x[0]["modal"] == "의무"


def test_delegation_table():
    D = R.delegations()
    assert len(D) > 500
    rows = [x for x in D if x["group"] == "업무추진비"]
    assert {x["who"] for x in rows} >= {"원장", "부원장", "본부장", "부서장"}
    assert any(x["note"] == "센터장" for x in rows)


def test_advise_uses_delegations():
    S = R.advise_sources("업무추진비 1건당 70만원이면 누가 결재하나요?")
    assert any(x["task"] == "1건당 5십만 원 이상" and x["who"] == "본부장" for x in S["delegations"])
    assert not R.advise_sources("연차휴가 이월이 되나요?")["delegations"]          # 권한을 묻지 않으면 붙이지 않는다
    ans = R._adv_rule_answer("업무추진비 결재권자", S)
    assert any("전결" in c for c in ans["caveats"])


def test_duties_api(client):
    d = client.post("/api/regagent/duties", json={"actor": "인사위원회"}).get_json()
    assert d["success"] and d["count"] and all(x["actor"] == "인사위원회" or x["target"] == "인사위원회" for x in d["rels"])
    d = client.post("/api/regagent/duties", json={"q": "국외출장"}).get_json()
    assert d["delegations"] and any("국외출장" in x["group"] for x in d["delegations"])
    st = client.get("/api/regagent/org").get_json()["stats"]
    assert st["duties"] > 500 and st["delegations"] > 500
