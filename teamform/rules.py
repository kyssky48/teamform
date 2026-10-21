# 생성: 2026-10-21 22:25 (KST)
"""팀 규칙 (공고 2.3절, 2.5절, 3장). Streamlit과 DB를 모르는 순수 함수."""
from collections import Counter
from collections.abc import Sequence
from itertools import combinations

from teamform.model import PL, ROLES, WP, Student

MAX_TEAM = 4
MIN_TEAM = 2

FULL = "팀이 꽉 참"
SAME_MAIN = "같은 주 역할의 팀원이 있음"
NO_SLOT = "필수 포함 역할을 맡을 학생의 자리가 모자람"
NO_ASSIGNMENT_TOO_MANY = "팀이 없는 학생 수가 남은 자리보다 많음"
NO_ASSIGNMENT_EMPTY = "빈 팀을 2명 이상으로 채울 학생이 모자람"
NO_ASSIGNMENT_CROSS = "팀 사이에 학생을 나눌 방법이 없음"


def missing_required(members: Sequence[Student]) -> int:
    """기획자와 웹 프로그래머를 서로 다른 학생에게 짝지은 뒤 못 채운 수(0~2)."""
    pls = [m for m in members if m.can(PL)]
    wps = [m for m in members if m.can(WP)]
    if any(p is not w for p in pls for w in wps):
        return 0
    return 1 if pls or wps else 2


def _has_same_main(members: Sequence[Student]) -> bool:
    return len({m.main_role for m in members}) < len(members)


def block_reason(members: Sequence[Student], applicant: Student) -> str | None:
    if len(members) >= MAX_TEAM:
        return FULL
    if any(m.main_role == applicant.main_role for m in members):
        return SAME_MAIN
    after = list(members) + [applicant]
    if MAX_TEAM - len(after) < missing_required(after):
        return NO_SLOT
    return None


def _required_errors(team_id: int, members: Sequence[Student]) -> list[str]:
    errs = []
    if not any(m.can(PL) for m in members):
        errs.append(f"팀{team_id}에 기획자를 맡을 학생이 없음")
    if not any(m.can(WP) for m in members):
        errs.append(f"팀{team_id}에 웹 프로그래머를 맡을 학생이 없음")
    if not errs and missing_required(members):
        errs.append(f"팀{team_id}에 기획자와 웹 프로그래머를 서로 다른 학생이 맡지 못함")
    return errs


def team_errors(team_id: int, members: Sequence[Student]) -> list[str]:
    errs = []
    if not MIN_TEAM <= len(members) <= MAX_TEAM:
        errs.append(f"팀{team_id}의 인원이 2~4명이 아님")
    counts = Counter(m.main_role for m in members)
    for role in ROLES:
        if counts[role] > 1:
            errs.append(f"팀{team_id}에 같은 주 역할의 학생이 있음: {role}")
    return errs + _required_errors(team_id, members)


def validate_plan(
    teams: dict[int, list[Student]], unassigned: list[Student], plan: dict[str, int]
) -> list[str]:
    """공고 2.5절 4항의 다섯 가지 검사. 빈 목록이면 통과."""
    errs = []
    by_no = {s.student_no: s for s in unassigned}
    for s in unassigned:
        if s.student_no not in plan:
            errs.append(f"{s.name}이(가) 배정되지 않음")
    for no in plan:
        if no not in by_no:
            errs.append(f"팀이 없는 학생이 아님: {no}")
    for t in sorted({t for t in plan.values() if t not in teams}, key=str):
        errs.append(f"없는 팀: {t}")
    final = {t: list(ms) for t, ms in teams.items()}
    for no, t in plan.items():
        if no in by_no and t in final:
            final[t].append(by_no[no])
    for t in sorted(final):
        errs.extend(team_errors(t, final[t]))
    return errs


def solve(teams: dict[int, list[Student]], unassigned: list[Student]) -> dict[str, int] | None:
    """규칙을 모두 지키는 배정을 모든 경우를 따져 찾음. 없으면 None."""
    team_ids = sorted(teams)
    current = {t: list(teams[t]) for t in team_ids}

    def fits(s: Student, t: int) -> bool:
        ms = current[t]
        return len(ms) < MAX_TEAM and all(m.main_role != s.main_role for m in ms)

    order = sorted(unassigned, key=lambda s: (sum(fits(s, t) for t in team_ids), s.student_no))
    plan: dict[str, int] = {}

    def hopeless(remaining: int) -> bool:
        short = sum(max(0, MIN_TEAM - len(current[t])) for t in team_ids)
        if short > remaining:
            return True
        return any(missing_required(current[t]) > MAX_TEAM - len(current[t]) for t in team_ids)

    def dfs(i: int) -> bool:
        if hopeless(len(order) - i):
            return False
        if i == len(order):
            return all(not team_errors(t, current[t]) for t in team_ids)
        s = order[i]
        for t in team_ids:
            if fits(s, t):
                current[t].append(s)
                plan[s.student_no] = t
                if dfs(i + 1):
                    return True
                current[t].pop()
                del plan[s.student_no]
        return False

    return dict(plan) if dfs(0) else None


def _team_alone_possible(members: list[Student], pool: list[Student]) -> bool:
    free = MAX_TEAM - len(members)
    for k in range(0, min(free, len(pool)) + 1):
        for extra in combinations(pool, k):
            if not team_errors(0, members + list(extra)):
                return True
    return False


def infeasible_reason(teams: dict[int, list[Student]], unassigned: list[Student]) -> str:
    """solve가 None일 때 관리자에게 보여 줄 이유."""
    free = sum(max(0, MAX_TEAM - len(ms)) for ms in teams.values())
    if free < len(unassigned):
        return NO_ASSIGNMENT_TOO_MANY
    for t in sorted(teams):
        members = list(teams[t])
        if not _team_alone_possible(members, unassigned):
            mains = {m.main_role for m in members}
            reachable = members + [s for s in unassigned if s.main_role not in mains]
            errs = _required_errors(t, reachable) or _required_errors(t, members) or team_errors(t, members)
            return errs[0] if errs else NO_ASSIGNMENT_CROSS
    empty = sum(1 for ms in teams.values() if not ms)
    if empty * MIN_TEAM > len(unassigned):
        return NO_ASSIGNMENT_EMPTY
    return NO_ASSIGNMENT_CROSS
