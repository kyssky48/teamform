# 생성: 2026-10-21 23:20 (KST)
import json
import time

from teamform import ai, rules, service
from tests.conftest import ADMIN, acct
from tests.helpers import S

MODELS = ["a/one:free", "b/two:free", "c/three:free"]


def closed_store(make_store):
    ppl = [S("PL"), S("WP"), S("FD"), S("TT", "PL"), S("RW", "WP")]
    st = make_store(ppl, 2)
    service.apply(st, acct(ppl[0]), 1)
    service.apply(st, acct(ppl[1]), 1)
    service.vote(st, acct(ppl[0]), ppl[1].student_no, True)
    service.close(st, ADMIN)
    return st


def as_json(plan):
    return json.dumps({"assignments": [{"student_no": k, "team": v} for k, v in plan.items()]})


def good_answer(st):
    return as_json(rules.solve(service.current_teams(st), service.unassigned(st)))


def test_assign_first_model_ok(make_store):
    st = closed_store(make_store)
    status = []
    msg = service.assign(st, ADMIN, lambda m, p: good_answer(st), MODELS, status.append)
    assert msg == "승인: 1차 모델(a/one:free)의 배정안을 받음"
    assert status[0] == "1차 모델(a/one:free) 응답을 기다리는 중 (최대 120초)"
    plan, source = service.load_plan(st)
    assert source == "1차 모델(a/one:free)"
    assert rules.validate_plan(service.current_teams(st), service.unassigned(st), plan) == []
    assert [x[2] for x in st.ai_logs] == ["성공"]


def test_assign_falls_through(make_store):
    st = closed_store(make_store)
    un = service.unassigned(st)
    calls = []

    def caller(model, prompt):
        calls.append(model)
        if model == MODELS[0]:
            time.sleep(1)
        if model == MODELS[1]:
            raise ai.AIError("HTTP 429")
        return as_json({s.student_no: 1 for s in un})  # 규칙 위반: 팀1 정원 초과, 팀2 빔

    status = []
    t0 = time.perf_counter()
    msg = service.assign(st, ADMIN, caller, MODELS, status.append, deadline_s=0.2)
    assert time.perf_counter() - t0 < 1.0
    assert msg == "승인: 3차까지 실패해 앱이 배정안을 만듦"
    assert calls == MODELS
    joined = "\n".join(status)
    assert joined.index("1차 모델") < joined.index("2차 모델") < joined.index("3차 모델")
    assert "1차 모델 실패: 0.2초 안에 응답을 다 받지 못함" in status
    assert "2차 모델 실패: HTTP 429" in status
    assert any(s.startswith("3차 모델 실패: 배정안 검사 실패") for s in status)
    assert [x[2] for x in st.ai_logs] == ["실패", "실패", "실패"]
    plan, source = service.load_plan(st)
    assert source == "앱"
    assert rules.validate_plan(service.current_teams(st), service.unassigned(st), plan) == []
    assert service.confirm(st, ADMIN) == "승인: 배정을 확정함"


def test_assign_unexpected_error_falls_through(make_store):
    st = closed_store(make_store)

    def caller(model, prompt):
        raise RuntimeError("secret-ish detail")

    status = []
    assert service.assign(st, ADMIN, caller, MODELS, status.append).startswith("승인: 3차까지")
    assert all("secret-ish" not in s for s in status)


def test_assign_infeasible_skips_ai(make_store):
    ppl = [S("PL"), S("FD"), S("TT"), S("RW"), S("PT"), S("PL", no="x2"), S("WP", no="x3")]
    st = make_store(ppl, 2)
    service.apply(st, acct(ppl[0]), 1)
    for i in range(1, 4):
        service.apply(st, acct(ppl[i]), 1)
        for j in range(i):
            service.vote(st, acct(ppl[j]), ppl[i].student_no, True)
    service.apply(st, acct(ppl[5]), 2)
    service.apply(st, acct(ppl[6]), 2)
    service.vote(st, acct(ppl[5]), ppl[6].student_no, True)
    service.close(st, ADMIN)
    called, status = [], []
    msg = service.assign(st, ADMIN, lambda m, p: called.append(m), MODELS, status.append)
    assert called == []
    assert msg == "막힘: 규칙을 지키는 배정이 없음 - 팀1에 웹 프로그래머를 맡을 학생이 없음"
    assert status == ["규칙을 지키는 배정이 없음: 팀1에 웹 프로그래머를 맡을 학생이 없음"]
    assert service.load_plan(st) is None


def test_assign_before_close_blocked(make_store):
    st = make_store([S("PL")], 2)
    assert service.assign(st, ADMIN, lambda m, p: "", MODELS, lambda s: None) == "막힘: 아직 마감하지 않음"


def test_assign_by_student_blocked(make_store):
    a = S("PL")
    st = make_store([a], 2)
    assert service.assign(st, acct(a), lambda m, p: "", MODELS, lambda s: None) == "막힘: 관리자만 할 수 있음"


def test_assign_nobody_left(make_store):
    a, b = S("PL"), S("WP")
    st = make_store([a, b], 1)
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)
    service.close(st, ADMIN)
    assert service.assign(st, ADMIN, lambda m, p: "", MODELS, lambda s: None) == "승인: 배정할 학생이 없음"
    assert service.confirm(st, ADMIN) == "승인: 배정을 확정함"
