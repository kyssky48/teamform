# 생성: 2026-10-21 22:32 (KST)
"""연습용과 다른 무작위 명단으로 solve를 확인 (학생 8~16명, 팀 3~4개)."""
import itertools
import random

from teamform.model import ROLES, Student
from teamform.rules import block_reason, solve, validate_plan


def _random_case(rng: random.Random):
    n_students, n_teams = rng.randint(8, 16), rng.randint(3, 4)
    students = []
    for i in range(n_students):
        main = rng.choice(ROLES)
        subs = tuple(rng.sample([r for r in ROLES if r != main], rng.randint(0, 2)))
        students.append(Student(f"{i:03d}", f"s{i}", main, subs))
    teams: dict[int, list[Student]] = {t: [] for t in range(1, n_teams + 1)}
    rng.shuffle(students)
    for s in students:  # 지원을 흉내: 막히지 않는 팀에 들어가거나 팀 없이 남음
        if rng.random() < 0.6:
            t = rng.randint(1, n_teams)
            if block_reason(teams[t], s) is None:
                teams[t].append(s)
    for t, ms in teams.items():  # 마감: 1명뿐인 팀은 비움
        if len(ms) == 1:
            teams[t] = []
    placed = {m.student_no for ms in teams.values() for m in ms}
    return teams, [s for s in students if s.student_no not in placed]


def _brute_force_exists(teams, unassigned) -> bool:
    for choice in itertools.product(sorted(teams), repeat=len(unassigned)):
        plan = {s.student_no: t for s, t in zip(unassigned, choice)}
        if not validate_plan(teams, unassigned, plan):
            return True
    return False


def test_solve_random_cases():
    rng = random.Random(20261021)
    checked_none = solved = 0
    for _ in range(200):
        teams, unassigned = _random_case(rng)
        plan = solve(teams, unassigned)
        if plan is not None:
            assert validate_plan(teams, unassigned, plan) == []
            solved += 1
        elif len(unassigned) <= 6:
            assert not _brute_force_exists(teams, unassigned)
            checked_none += 1
    assert solved > 20 and checked_none > 5


def test_solve_worst_case_is_fast():
    import time

    rng = random.Random(7)
    worst = 0.0
    for _ in range(300):
        teams, unassigned = _random_case(rng)
        t0 = time.perf_counter()
        solve(teams, unassigned[:8])
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 1.0
