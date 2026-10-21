# 생성: 2026-10-21 22:18 (KST)
from teamform import service
from teamform.model import APPROVED, PENDING, REJECTED
from tests.conftest import ADMIN, acct
from tests.helpers import S


def setup(make_store, *roles):
    people = [S(*r) for r in roles]
    return make_store(people), people


def test_apply_empty_team_approved(make_store):
    st, (a,) = setup(make_store, ("PL",))
    assert service.apply(st, acct(a), 1) == "승인"
    assert st.team_of(a.student_no) == 1


def test_apply_occupied_team_pending(make_store):
    st, (a, b) = setup(make_store, ("PL",), ("WP",))
    service.apply(st, acct(a), 1)
    assert service.apply(st, acct(b), 1) == "대기"
    assert st.pending_application_of(b.student_no).status == PENDING


def test_apply_blocked_reasons(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("PL", "TT"), ("RW",))
    service.apply(st, acct(a), 1)
    assert service.apply(st, acct(b), 1) == "막힘: 같은 주 역할의 팀원이 있음"
    assert st.pending_application_of(b.student_no) is None


def test_apply_blocked_required_slot(make_store):
    st, (t, p, w, r) = setup(make_store, ("TT",), ("PT",), ("WP",), ("RW",))
    service.apply(st, acct(t), 1)
    service.apply(st, acct(p), 1)
    service.vote(st, acct(t), p.student_no, True)
    assert service.apply(st, acct(r), 1) == "막힘: 필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_apply_blocked_full(make_store):
    st, ppl = setup(make_store, ("PL",), ("WP",), ("FD",), ("TT",), ("RW",))
    service.apply(st, acct(ppl[0]), 1)
    for i in range(1, 4):
        service.apply(st, acct(ppl[i]), 1)
        for j in range(i):
            service.vote(st, acct(ppl[j]), ppl[i].student_no, True)
    assert len(st.members(1)) == 4
    assert service.apply(st, acct(ppl[4]), 1) == "막힘: 팀이 꽉 참"


def test_apply_blocked_when_pending(make_store):
    st, (a, b) = setup(make_store, ("PL",), ("WP",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    assert service.apply(st, acct(b), 2) == "막힘: 결과를 기다리는 지원이 있음"


def test_apply_blocked_when_has_team(make_store):
    st, (a,) = setup(make_store, ("PL",))
    service.apply(st, acct(a), 1)
    assert service.apply(st, acct(a), 2) == "막힘: 이미 팀이 있음"


def test_apply_blocked_when_closed(make_store):
    st, (a,) = setup(make_store, ("PL",))
    st.set_setting("closed", "1")
    assert service.apply(st, acct(a), 1) == "막힘: 모집이 마감됨"


def test_apply_by_admin_blocked(make_store):
    st, _ = setup(make_store, ("PL",))
    assert service.apply(st, ADMIN, 1) == "막힘: 관리자는 지원할 수 없음"


def test_apply_unknown_team_blocked(make_store):
    st, (a,) = setup(make_store, ("PL",))
    assert service.apply(st, acct(a), 9) == "막힘: 없는 팀"


def test_reject_is_immediate(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("WP",), ("FD",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)
    service.apply(st, acct(c), 1)
    assert service.vote(st, acct(a), c.student_no, False) == "거절: 팀원이 거부함"
    app = st.get_application(st_last_app_id(st, c.student_no))
    assert app.status == REJECTED
    assert service.vote(st, acct(b), c.student_no, True) == "거절: 팀원이 거부함"  # 이미 끝난 지원은 지금 상태를 보여 줌
    assert st.votes(st_last_app_id(st, c.student_no)) == {a.student_no: "거부"}
    assert service.apply(st, acct(c), 2) == "승인"  # 결과가 나온 뒤 다른 팀에 지원 가능


def st_last_app_id(st, student_no):
    return max(a.id for a in st.applications_of(student_no))


def test_all_yes_approves(make_store):
    st, (a, b) = setup(make_store, ("PL",), ("WP",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    assert service.vote(st, acct(a), b.student_no, True) == "승인"
    assert st.team_of(b.student_no) == 1


def test_partial_yes_pending(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("WP",), ("FD",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)
    service.apply(st, acct(c), 1)
    assert service.vote(st, acct(a), c.student_no, True) == "대기"


def test_new_member_must_also_vote(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("WP",), ("FD",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.apply(st, acct(c), 1)
    assert service.vote(st, acct(a), b.student_no, True) == "승인"
    assert service.vote(st, acct(a), c.student_no, True) == "대기"
    assert service.vote(st, acct(b), c.student_no, True) == "승인"


def test_recheck_before_approval(make_store):
    # 어려움 6~8단계와 같은 꼴
    st, (pl, fd, wp1, wp2) = setup(make_store, ("PL", "PT"), ("FD", "TT"), ("WP", "FD"), ("WP", "RW"))
    service.apply(st, acct(pl), 2)
    service.apply(st, acct(fd), 2)
    service.vote(st, acct(pl), fd.student_no, True)
    assert service.apply(st, acct(wp1), 2) == "대기"
    assert service.apply(st, acct(wp2), 2) == "대기"
    service.vote(st, acct(pl), wp1.student_no, True)
    assert service.vote(st, acct(fd), wp1.student_no, True) == "승인"
    service.vote(st, acct(pl), wp2.student_no, True)
    service.vote(st, acct(fd), wp2.student_no, True)
    assert service.vote(st, acct(wp1), wp2.student_no, True) == "거절: 승인 직전 검사: 같은 주 역할의 팀원이 있음"
    assert st.team_of(wp2.student_no) is None


def test_vote_twice_blocked(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("WP",), ("FD",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    service.vote(st, acct(a), b.student_no, True)
    service.apply(st, acct(c), 1)
    service.vote(st, acct(a), c.student_no, True)
    assert service.vote(st, acct(a), c.student_no, False) == "막힘: 이미 투표함"


def test_vote_by_non_member_blocked(make_store):
    st, (a, b, c) = setup(make_store, ("PL",), ("WP",), ("FD",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    assert service.vote(st, acct(c), b.student_no, True) == "막힘: 이 팀의 팀원이 아님"


def test_vote_after_close_blocked(make_store):
    st, (a, b) = setup(make_store, ("PL",), ("WP",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    st.set_setting("closed", "1")
    assert service.vote(st, acct(a), b.student_no, True) == "막힘: 모집이 마감됨"


def test_add_member_conflict_rejects(make_store):
    st, (a, b) = setup(make_store, ("PL",), ("WP",))
    service.apply(st, acct(a), 1)
    service.apply(st, acct(b), 1)
    st.add_member = lambda team_id, student_no: False  # 먼저 도착한 다른 학생이 자리를 가져간 상황
    assert service.vote(st, acct(a), b.student_no, True) == "거절: 자리가 이미 찼음"
    assert st.pending_application_of(b.student_no) is None


def test_add_member_conflict_on_empty_team(make_store):
    st, (a,) = setup(make_store, ("PL",))
    st.add_member = lambda team_id, student_no: False
    assert service.apply(st, acct(a), 1) == "거절: 자리가 이미 찼음"
    assert st.pending_application_of(a.student_no) is None
    assert service.apply(st, acct(a), 1) != "막힘: 결과를 기다리는 지원이 있음"


def test_approved_status_recorded(make_store):
    st, (a,) = setup(make_store, ("PL",))
    service.apply(st, acct(a), 1)
    assert [x.status for x in st.applications_of(a.student_no)] == [APPROVED]
