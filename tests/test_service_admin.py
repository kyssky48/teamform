# 생성: 2026-10-21 22:58 (KST)
from teamform import auth, rules, service
from teamform.model import REJECTED
from tests.conftest import ADMIN, acct
from tests.helpers import S

HEADER = "student_no,name,main_role,sub_roles\n"


def csv_of(students) -> bytes:
    rows = [f"{s.student_no},{s.name},{s.main_role},{';'.join(s.sub_roles)}" for s in students]
    return (HEADER + "\n".join(rows) + "\n").encode("utf-8-sig")


def started(make_store, roles, teams=4):
    people = [S(*r) for r in roles]
    st = make_store([])
    auth.ensure_admin(st, "pw")
    assert service.start(st, ADMIN, csv_of(people), teams) == f"승인: 학생 {len(people)}명, 팀 {teams}개로 시작함"
    return st, people


def test_restart_clears_everything_but_admin(make_store):
    st, (a, b) = started(make_store, [("PL",), ("WP",)])
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)
    service.close(st, ADMIN)
    service.save_plan(st, {}, "앱")
    c = S("FD")
    assert service.start(st, ADMIN, csv_of([c]), 3).startswith("승인")
    assert st.team_ids() == [1, 2, 3]
    assert all(st.members(t) == [] for t in st.team_ids())
    assert st.pending_applications() == []
    assert not service.is_closed(st)
    assert service.load_plan(st) is None
    assert st.get_student(a.student_no) is None
    assert auth.login(st, "admin", "pw").is_admin
    assert auth.login(st, c.student_no, "1234") is not None


def test_start_bad_csv_changes_nothing(make_store):
    st, (a,) = started(make_store, [("PL",)])
    bad = (HEADER + "1,x,기획자,\n2,y,요리사,\n").encode("utf-8-sig")
    assert service.start(st, ADMIN, bad, 3) == "막힘: 2번째 줄: 주 역할 '요리사'은(는) 6개 역할이 아님"
    assert st.get_student(a.student_no) is not None
    assert st.team_ids() == [1, 2, 3, 4]


def test_start_team_count_zero_blocked(make_store):
    st, _ = started(make_store, [("PL",)])
    assert service.start(st, ADMIN, csv_of([S("PL")]), 0) == "막힘: 팀 수는 1 이상"


def test_start_without_file_blocked(make_store):
    st, _ = started(make_store, [("PL",)])
    assert service.start(st, ADMIN, None, 3) == "막힘: 명단 파일을 올려야 함"


def test_close_rejects_pending_and_removes_singletons(make_store):
    st, (a, b, c, d) = started(make_store, [("PL",), ("WP",), ("FD",), ("TT",)])
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)  # 팀1: a, b
    service.apply(st, acct(c), 2)  # 팀2: c 혼자
    service.apply(st, acct(d), 1)  # 대기
    assert service.close(st, ADMIN) == "승인: 모집을 마감함"
    assert service.is_closed(st)
    assert st.applications_of(d.student_no)[-1].status == REJECTED
    assert st.applications_of(d.student_no)[-1].reason == "모집 마감"
    assert st.members(2) == []
    assert [s.name for s in service.unassigned(st)] == [c.name, d.name]
    assert service.apply(st, acct(c), 3) == "막힘: 모집이 마감됨"


def test_close_twice_blocked(make_store):
    st, _ = started(make_store, [("PL",)])
    service.close(st, ADMIN)
    assert service.close(st, ADMIN) == "막힘: 이미 마감함"


def _close_and_plan(make_store):
    st, ppl = started(make_store, [("PL",), ("WP",), ("FD",), ("TT", "PL"), ("RW", "WP")], teams=2)
    service.apply(st, acct(ppl[0]), 1)
    service.apply(st, acct(ppl[1]), 1)
    service.vote(st, acct(ppl[0]), ppl[1].student_no, True)
    service.close(st, ADMIN)
    teams, un = service.current_teams(st), service.unassigned(st)
    plan = rules.solve(teams, un)
    service.save_plan(st, plan, "앱")
    return st, ppl, plan


def test_confirm_writes_members(make_store):
    st, ppl, plan = _close_and_plan(make_store)
    assert service.load_plan(st) == (plan, "앱")
    assert service.confirm(st, ADMIN) == "승인: 배정을 확정함"
    assert service.unassigned(st) == []
    assert all(rules.team_errors(t, ms) == [] for t, ms in service.current_teams(st).items())


def test_confirm_without_plan_blocked(make_store):
    st, _ = started(make_store, [("PL",)])
    service.close(st, ADMIN)
    assert service.confirm(st, ADMIN) == "막힘: 배정안이 없음"


def test_confirm_before_close_blocked(make_store):
    st, _ = started(make_store, [("PL",)])
    assert service.confirm(st, ADMIN) == "막힘: 아직 마감하지 않음"


def test_confirm_revalidates(make_store):
    st, ppl, plan = _close_and_plan(make_store)
    bad = dict(plan)
    bad[next(iter(bad))] = 9
    service.save_plan(st, bad, "앱")
    assert service.confirm(st, ADMIN).startswith("막힘: 없는 팀: 9")
    assert len(service.unassigned(st)) == 3


def test_confirm_twice_blocked(make_store):
    st, _, _ = _close_and_plan(make_store)
    service.confirm(st, ADMIN)
    assert service.confirm(st, ADMIN) == "막힘: 배정안이 없음"


def test_student_cannot_use_admin_actions(make_store):
    st, (a,) = started(make_store, [("PL",)])
    me = acct(a)
    assert service.start(st, me, csv_of([a]), 3) == "막힘: 관리자만 할 수 있음"
    assert service.close(st, me) == "막힘: 관리자만 할 수 있음"
    assert service.confirm(st, me) == "막힘: 관리자만 할 수 있음"
    assert not service.is_closed(st)


def test_board_flags(make_store):
    st, (a, b, c) = started(make_store, [("PL",), ("WP",), ("FD",)])
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    bb = service.board(st, acct(b))
    assert not bb.can_apply and bb.my_pending.team_id == 1 and bb.my_team is None
    ba = service.board(st, acct(a))
    assert ba.my_team == 1 and not ba.can_apply
    pv = ba.teams[0].pending[0]
    assert pv.applicant == b and pv.my_vote is None and pv.can_vote
    service.vote(st, acct(a), b.student_no, True)
    service.apply(st, acct(c), 1)
    pv = service.board(st, acct(a)).teams[0].pending[0]
    assert pv.my_vote is None and pv.can_vote
    service.vote(st, acct(a), c.student_no, True)
    pv = service.board(st, acct(a)).teams[0].pending[0]
    assert pv.my_vote == "찬성" and not pv.can_vote
    assert service.board(st, acct(c)).teams[0].pending[0].can_vote is False  # 지원자 본인은 투표 못 함
    assert [t.team_id for t in service.board(st, ADMIN).teams] == [1, 2, 3, 4]


def test_board_can_apply_and_closed(make_store):
    st, (a,) = started(make_store, [("PL",)])
    assert service.board(st, acct(a)).can_apply
    service.close(st, ADMIN)
    b = service.board(st, acct(a))
    assert b.closed and not b.can_apply
