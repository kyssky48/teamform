# 생성: 2026-10-21 22:50 (KST)
"""앱의 동작. 결과는 "승인", "대기", "거절", "막힘"으로 시작하는 문구로 돌려준다."""
from teamform.model import APPROVED, NO, PENDING, REJECTED, YES, Account, Application
from teamform.rules import block_reason
from teamform.store import Store

CLOSED_KEY = "closed"
SEAT_TAKEN = "자리가 이미 찼음"


def is_closed(store: Store) -> bool:
    return store.get_setting(CLOSED_KEY) == "1"


def status_text(app: Application) -> str:
    if app.status == REJECTED and app.reason:
        return f"{REJECTED}: {app.reason}"
    return app.status


def _decide(store: Store, app: Application, status: str, reason: str | None = None) -> str:
    store.set_application_status(app.id, status, reason)
    return status_text(store.get_application(app.id))


def _admit(store: Store, app: Application) -> str:
    if store.add_member(app.team_id, app.student_no):
        return _decide(store, app, APPROVED)
    return _decide(store, app, REJECTED, SEAT_TAKEN)


def apply(store: Store, actor: Account, team_id: int) -> str:
    if actor.is_admin:
        return "막힘: 관리자는 지원할 수 없음"
    with store.transaction():
        if team_id not in store.team_ids():
            return "막힘: 없는 팀"
        if is_closed(store):
            return "막힘: 모집이 마감됨"
        if store.team_of(actor.student_no) is not None:
            return "막힘: 이미 팀이 있음"
        if store.pending_application_of(actor.student_no):
            return "막힘: 결과를 기다리는 지원이 있음"
        store.lock_team(team_id)
        applicant = store.get_student(actor.student_no)
        if applicant is None:
            return "막힘: 명단에 없는 학생"
        members = store.members(team_id)
        reason = block_reason(members, applicant)
        if reason:
            return f"막힘: {reason}"
        app = store.create_application(team_id, actor.student_no)
        if not members:
            return _admit(store, app)
        return PENDING


def vote(store: Store, actor: Account, applicant_no: str, yes: bool) -> str:
    if actor.is_admin:
        return "막힘: 관리자는 투표할 수 없음"
    with store.transaction():
        team_id = store.team_of(actor.student_no)
        apps = [a for a in store.applications_of(applicant_no) if a.team_id == team_id]
        if team_id is None or not apps:
            return "막힘: 이 팀의 팀원이 아님"
        if is_closed(store):
            return "막힘: 모집이 마감됨"
        store.lock_team(team_id)
        app = store.get_application(max(a.id for a in apps))
        if app.status != PENDING:
            return status_text(app)
        if not store.add_vote(app.id, actor.student_no, YES if yes else NO):
            return "막힘: 이미 투표함"
        if not yes:
            return _decide(store, app, REJECTED, "팀원이 거부함")
        members = store.members(team_id)
        votes = store.votes(app.id)
        if any(votes.get(m.student_no) != YES for m in members):
            return PENDING
        applicant = store.get_student(applicant_no)
        reason = block_reason(members, applicant) if applicant else "명단에 없는 학생"
        if reason:
            return _decide(store, app, REJECTED, f"승인 직전 검사: {reason}")
        return _admit(store, app)
