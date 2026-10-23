# 생성: 2026-10-21 22:20 (KST)
"""부록 연습용 시나리오를 동작 함수로 처음부터 끝까지 실행."""
import re

import pytest

from teamform import auth, rules, service
from teamform.ai import AIError
from teamform.store import MemoryStore
from tests.conftest import ADMIN
from tests.scenarios import ALL


def failing_ai(model, prompt):
    raise AIError("HTTP 429")


def assign_and_confirm(st) -> None:
    msg = service.assign(st, ADMIN, failing_ai, ["a:free", "b:free", "c:free"], lambda s: None)
    assert msg == "승인: 3차까지 실패해 앱이 배정안을 만듦"
    assert service.confirm(st, ADMIN).startswith("승인")


def run_scenario(st, name, team_count, steps, assign=assign_and_confirm):
    auth.ensure_admin(st, "pw")
    with open(f"tests/data/{name}.csv", "rb") as f:
        assert service.start(st, ADMIN, f.read(), team_count).startswith("승인")
    by_n = {int(re.match(r"학생(\d+)", s.name).group(1)): s for s in st.list_students()}

    def login(n):
        s = by_n[n]
        acc = auth.login(st, s.student_no, "1234")
        assert acc is not None
        return acc

    for i, (action, args, expected) in enumerate(steps, 1):
        where = f"{name} {i}번째 동작 {action}{args}"
        if action == "apply":
            got = service.apply(st, login(args[0]), args[1])
        elif action in ("yes", "no"):
            got = service.vote(st, login(args[0]), by_n[args[1]].student_no, action == "yes")
        elif action == "close":
            got = service.close(st, ADMIN)
        elif action == "unassigned_has":
            names = {s.name for s in service.unassigned(st)}
            assert {by_n[n].name for n in args} <= names, where
            continue
        elif action == "assign_confirm":
            assign(st)
            assert service.unassigned(st) == [], where
            for t, ms in service.current_teams(st).items():
                assert rules.team_errors(t, ms) == [], where
            continue
        assert got.split(":")[0] == expected, f"{where}: {got}"


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s[0])
def test_practice_scenario(scenario):
    run_scenario(MemoryStore(), *scenario)


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s[0])
def test_practice_scenario_on_real_db(scenario):
    """TEAMFORM_PG_TESTS=1 일 때만 실제 DB(PgStore)로 같은 시나리오를 돌림."""
    from tests.test_store_contract import _pg_store

    run_scenario(_pg_store(), *scenario)
