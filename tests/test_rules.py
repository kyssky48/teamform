# 생성: 2026-10-21 22:14 (KST)
from teamform.rules import (
    block_reason,
    infeasible_reason,
    missing_required,
    solve,
    team_errors,
    validate_plan,
)
from tests.helpers import S


def test_missing_required_counts_distinct_people():
    assert missing_required([S("PL", "WP")]) == 1  # 공고 3장 예: 혼자서 둘 다 못 함
    assert missing_required([S("PL", "WP"), S("TT", "PL")]) == 0
    assert missing_required([S("TT"), S("PT")]) == 2
    assert missing_required([]) == 2


def test_block_full():
    assert block_reason([S("PL"), S("WP"), S("FD"), S("TT")], S("RW")) == "팀이 꽉 참"


def test_block_same_main():
    assert block_reason([S("PL"), S("WP")], S("PL", "TT")) == "같은 주 역할의 팀원이 있음"


def test_block_required_slot():
    # 공고 3장 예: 테스터와 발표자만 있는 팀(2명)에 보고서 작성자가 지원
    assert block_reason([S("TT"), S("PT")], S("RW")) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_allow_sub_role_fill():
    assert block_reason([S("TT", "RW"), S("PT")], S("PL", "WP")) is None


def test_allow_empty_team():
    assert block_reason([], S("RW")) is None


def test_block_required_slot_full_after_join():
    # 3명 + 지원자 = 4명, 남는 자리 0, 웹 프로그래머 못 채움
    assert block_reason([S("PL"), S("FD"), S("TT")], S("RW")) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_team_errors():
    assert team_errors(2, [S("PL"), S("FD")]) == ["팀2에 웹 프로그래머를 맡을 학생이 없음"]
    assert team_errors(1, [S("PL", "WP")]) == [
        "팀1의 인원이 2~4명이 아님",
        "팀1에 기획자와 웹 프로그래머를 서로 다른 학생이 맡지 못함",
    ]
    assert team_errors(3, []) == [
        "팀3의 인원이 2~4명이 아님",
        "팀3에 기획자를 맡을 학생이 없음",
        "팀3에 웹 프로그래머를 맡을 학생이 없음",
    ]
    assert team_errors(4, [S("PL"), S("WP"), S("PL", "WP")]) == ["팀4에 같은 주 역할의 학생이 있음: 기획자"]
    assert team_errors(1, [S("PL"), S("WP")]) == []


def _fixture():
    a, b = S("PL"), S("WP")
    c, d = S("TT", "PL"), S("FD", "WP")
    teams = {1: [a, b], 2: []}
    return teams, [c, d], {c.student_no: 2, d.student_no: 2}


def test_validate_plan_ok():
    teams, un, plan = _fixture()
    assert validate_plan(teams, un, plan) == []


def test_validate_plan_missing_student():
    teams, un, plan = _fixture()
    del plan[un[0].student_no]
    errs = validate_plan(teams, un, plan)
    assert f"{un[0].name}이(가) 배정되지 않음" in errs


def test_validate_plan_rejects_moves_and_unknowns():
    teams, un, plan = _fixture()
    plan[teams[1][0].student_no] = 2  # 이미 팀에 있는 학생을 옮김
    plan["0000000"] = 1  # 명단에 없는 학번
    errs = validate_plan(teams, un, plan)
    assert f"팀이 없는 학생이 아님: {teams[1][0].student_no}" in errs
    assert "팀이 없는 학생이 아님: 0000000" in errs
    teams, un, plan = _fixture()
    plan[un[0].student_no] = 9
    assert "없는 팀: 9" in validate_plan(teams, un, plan)


def test_validate_plan_reports_rule_breaks():
    teams, un, plan = _fixture()
    plan[un[1].student_no] = 1  # 팀2는 1명, 팀1은 WP 주 역할 겹치지 않지만 팀2에 WP 없음
    errs = validate_plan(teams, un, plan)
    assert "팀2의 인원이 2~4명이 아님" in errs
    assert "팀2에 웹 프로그래머를 맡을 학생이 없음" in errs


def test_solve_uses_sub_role():
    pl = S("PL")
    fdwp, tt = S("FD", "WP"), S("TT")
    teams = {1: [pl], 2: [S("PL"), S("WP")]}
    plan = solve(teams, [fdwp, tt])
    assert plan is not None and plan[fdwp.student_no] == 1
    assert validate_plan(teams, [fdwp, tt], plan) == []


def test_solve_none_when_full_team_lacks_wp():
    teams = {1: [S("PL"), S("FD"), S("TT"), S("RW")], 2: [S("PL"), S("WP")]}
    pt = S("PT")
    assert solve(teams, [pt]) is None
    assert infeasible_reason(teams, [pt]) == "팀1에 웹 프로그래머를 맡을 학생이 없음"


def test_infeasible_too_many_students():
    teams = {1: [S("PL"), S("WP"), S("FD"), S("TT")]}
    un = [S("RW")]
    assert solve(teams, un) is None
    assert infeasible_reason(teams, un) == "팀이 없는 학생 수가 남은 자리보다 많음"


def test_infeasible_empty_team_short():
    teams = {1: [S("PL"), S("WP")], 2: [], 3: []}
    un = [S("PL"), S("WP"), S("FD")]
    assert solve(teams, un) is None
    assert infeasible_reason(teams, un) == "빈 팀을 2명 이상으로 채울 학생이 모자람"


def test_infeasible_cross_team():
    # 팀1, 팀2 모두 웹 프로그래머가 필요하지만 맡을 학생은 1명뿐
    teams = {1: [S("PL"), S("FD")], 2: [S("PL"), S("TT")]}
    un = [S("WP")]
    assert solve(teams, un) is None
    assert infeasible_reason(teams, un) == "팀 사이에 학생을 나눌 방법이 없음"


def test_solve_no_unassigned_valid_teams():
    teams = {1: [S("PL"), S("WP")]}
    assert solve(teams, []) == {}


def test_solve_is_deterministic():
    teams = {1: [S("PL")], 2: [S("PL")], 3: []}
    un = [S("WP"), S("WP", "PL"), S("TT", "PL"), S("FD", "WP"), S("RW")]
    assert solve(teams, un) == solve(teams, un)
    assert validate_plan(teams, un, solve(teams, un)) == []


def test_infeasible_reason_names_the_role_the_pool_lacks():
    teams = {1: [S("PL"), S("WP")], 2: []}
    un = [S("PL"), S("FD"), S("TT")]
    assert solve(teams, un) is None
    assert infeasible_reason(teams, un) == "팀2에 웹 프로그래머를 맡을 학생이 없음"
