# 생성: 2026-10-21 22:19 (KST)
"""앱의 동작. 결과는 "승인", "대기", "거절", "막힘"으로 시작하는 문구로 돌려준다."""
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from teamform.ai import AIError, ModelCaller, build_prompt, parse_plan, with_deadline
from teamform.auth import hash_password
from teamform.model import APPROVED, NO, PENDING, REJECTED, YES, Account, Application, Student
from teamform.roster import RosterError, parse_roster
from teamform.rules import block_reason, infeasible_reason, solve, validate_plan
from teamform.store import CLOSE_REASON, Store

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


# ---- 관리자 동작 (공고 2.5절, 2.6절) ----

PLAN_KEY = "pending_plan"
ADMIN_ONLY = "막힘: 관리자만 할 수 있음"


class _Abort(Exception):
    pass


def start(store: Store, actor: Account, csv_bytes: bytes | None, team_count: int) -> str:
    if not actor.is_admin:
        return ADMIN_ONLY
    if not csv_bytes:
        return "막힘: 명단 파일을 올려야 함"
    if team_count < 1:
        return "막힘: 팀 수는 1 이상"
    try:
        students = parse_roster(csv_bytes)
    except RosterError as e:
        return f"막힘: {e}"
    student_hash = hash_password("1234")
    with store.transaction():
        store.reset(students, team_count)
        store.set_all_student_password_hash(student_hash)
    return f"승인: 학생 {len(students)}명, 팀 {team_count}개로 시작함"


def close(store: Store, actor: Account) -> str:
    if not actor.is_admin:
        return ADMIN_ONLY
    with store.transaction():
        if is_closed(store):
            return "막힘: 이미 마감함"
        store.set_setting(CLOSED_KEY, "1")
        for app in store.pending_applications():
            store.set_application_status(app.id, REJECTED, CLOSE_REASON)
        for t in store.team_ids():
            members = store.members(t)
            if len(members) == 1:
                store.remove_member(members[0].student_no)
    return "승인: 모집을 마감함"


def current_teams(store: Store) -> dict[int, list[Student]]:
    return {t: store.members(t) for t in store.team_ids()}


def unassigned(store: Store) -> list[Student]:
    return [s for s in store.list_students() if store.team_of(s.student_no) is None]


def save_plan(store: Store, plan: dict[str, int], source: str) -> None:
    store.set_setting(PLAN_KEY, json.dumps({"plan": plan, "source": source}, ensure_ascii=False))


def load_plan(store: Store) -> tuple[dict[str, int], str] | None:
    raw = store.get_setting(PLAN_KEY)
    if not raw:
        return None
    data = json.loads(raw)
    return {str(k): int(v) for k, v in data["plan"].items()}, data["source"]


def confirm(store: Store, actor: Account) -> str:
    if not actor.is_admin:
        return ADMIN_ONLY
    if not is_closed(store):
        return "막힘: 아직 마감하지 않음"
    try:
        with store.transaction():
            loaded = load_plan(store)
            if loaded is None:
                return "막힘: 배정안이 없음"
            plan = loaded[0]
            errs = validate_plan(current_teams(store), unassigned(store), plan)
            if errs:
                return "막힘: " + "; ".join(errs)
            for no, t in sorted(plan.items()):
                if not store.add_member(t, no):
                    raise _Abort
            store.set_setting(PLAN_KEY, None)
    except _Abort:
        return "막힘: 확정하는 중에 자리가 겹침"
    return "승인: 배정을 확정함"


# ---- 화면용 현황 ----


@dataclass
class PendingView:
    applicant: Student
    my_vote: str | None
    can_vote: bool
    status: str = PENDING  # 거절이면 다른 팀원이 거부한 뒤에도 단추를 남겨 결과(거절)를 보여 줌


@dataclass
class TeamView:
    team_id: int
    members: list[Student]
    pending: list[PendingView]


@dataclass
class Board:
    teams: list[TeamView]
    closed: bool
    my_team: int | None
    my_pending: Application | None
    can_apply: bool
    unassigned: list[Student]
    viewer_exists: bool  # 명단을 다시 올려 로그인한 학생이 사라졌으면 False


def board(store: Store, viewer: Account) -> Board:
    snap = store.snapshot()  # 화면을 3초마다 다시 그리므로 질의 한 번으로 읽음
    closed = snap.settings.get(CLOSED_KEY) == "1"
    me = viewer.student_no
    team_of = {no: t for t, nos in snap.members.items() for no in nos}
    my_team = None if viewer.is_admin else team_of.get(me)
    my_pending = None if viewer.is_admin else next((a for a in snap.pending if a.student_no == me), None)
    teams = []
    for t in snap.team_ids:
        pending = []
        for app in snap.pending + snap.rejected:
            applicant = snap.students.get(app.student_no)
            if app.team_id != t or applicant is None:
                continue
            my_vote = snap.votes.get(app.id, {}).get(me)
            can_vote = not closed and my_team == t and my_vote is None and app.student_no != me
            pending.append(PendingView(applicant, my_vote, can_vote, app.status))
        members = [snap.students[no] for no in snap.members.get(t, []) if no in snap.students]
        teams.append(TeamView(t, members, pending))
    can_apply = not viewer.is_admin and not closed and my_team is None and my_pending is None
    unassigned = [s for no, s in sorted(snap.students.items()) if no not in team_of]
    viewer_exists = viewer.is_admin or me in snap.students
    return Board(teams, closed, my_team, my_pending, can_apply, unassigned, viewer_exists)

# ---- AI 배정 (공고 2.5절 3~8항) ----

APP_SOURCE = "앱"


def assign(
    store: Store,
    actor: Account,
    caller: ModelCaller,
    models: list[str],
    on_status: Callable[[str], None],
    deadline_s: float = 120,
) -> str:
    if not actor.is_admin:
        return ADMIN_ONLY
    if not is_closed(store):
        return "막힘: 아직 마감하지 않음"
    teams, left = current_teams(store), unassigned(store)
    fallback = solve(teams, left)
    if fallback is None:
        reason = infeasible_reason(teams, left)
        on_status(f"규칙을 지키는 배정이 없음: {reason}")
        return f"막힘: 규칙을 지키는 배정이 없음 - {reason}"
    if not left:
        save_plan(store, {}, APP_SOURCE)
        return "승인: 배정할 학생이 없음"

    prompt = build_prompt(teams, left)
    for tier, model in enumerate(models, 1):
        on_status(f"{tier}차 모델({model}) 응답을 기다리는 중 (최대 {deadline_s:g}초)")
        t0 = time.monotonic()
        try:
            plan = parse_plan(with_deadline(lambda: caller(model, prompt), deadline_s))
            errs = validate_plan(teams, left, plan)
            if errs:
                raise AIError("배정안 검사 실패: " + "; ".join(errs[:3]))
        except AIError as e:
            detail = str(e)
        except Exception as e:  # 예상 못 한 오류도 실패로 보고 다음 모델로 (내용은 화면에 쓰지 않음)
            detail = f"예상 못 한 오류({type(e).__name__})"
        else:
            store.log_ai(tier, model, "성공", "", _ms(t0))
            source = f"{tier}차 모델({model})"
            save_plan(store, plan, source)
            on_status(f"{tier}차 모델의 배정안이 검사를 통과함")
            return f"승인: {source}의 배정안을 받음"
        store.log_ai(tier, model, "실패", detail, _ms(t0))
        on_status(f"{tier}차 모델 실패: {detail}")

    save_plan(store, fallback, APP_SOURCE)
    on_status("3차까지 실패해 앱이 배정안을 만듦")
    return "승인: 3차까지 실패해 앱이 배정안을 만듦"


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
