# 생성: 2026-10-21 22:18 (KST)
"""저장소 인터페이스(Store)와 시험·로컬용 메모리 저장소(MemoryStore)."""
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import ContextManager, Protocol

from teamform.model import PENDING, REJECTED, Account, Application, Student

CLOSE_REASON = "모집 마감"


@dataclass
class Snapshot:
    """화면 한 번 그리는 데 필요한 현황. PgStore는 질의 한 번으로 읽는다."""

    students: dict[str, Student]
    team_ids: list[int]
    members: dict[int, list[str]]  # 팀 번호 → 학번(자리 순)
    pending: list[Application]
    votes: dict[int, dict[str, str]]  # 대기 지원과 rejected의 id → 투표자 학번 → 찬성/거부
    settings: dict[str, str]
    rejected: list[Application] = field(default_factory=list)  # 학생의 가장 최근 지원이 거절된 것(마감 거절 제외)


class Store(Protocol):
    def transaction(self) -> ContextManager[None]: ...
    def lock_team(self, team_id: int) -> None: ...
    def reset(self, students: list[Student], team_count: int) -> None: ...
    def upsert_admin(self, password_hash: str) -> None: ...
    def set_all_student_password_hash(self, password_hash: str) -> None: ...
    def get_login(self, student_no: str) -> tuple[Account, str] | None: ...
    def get_student(self, student_no: str) -> Student | None: ...
    def list_students(self) -> list[Student]: ...
    def team_ids(self) -> list[int]: ...
    def members(self, team_id: int) -> list[Student]: ...
    def team_of(self, student_no: str) -> int | None: ...
    def add_member(self, team_id: int, student_no: str) -> bool: ...
    def remove_member(self, student_no: str) -> None: ...
    def create_application(self, team_id: int, student_no: str) -> Application: ...
    def get_application(self, app_id: int) -> Application: ...
    def applications_of(self, student_no: str) -> list[Application]: ...
    def pending_application_of(self, student_no: str) -> Application | None: ...
    def pending_applications(self, team_id: int | None = None) -> list[Application]: ...
    def set_application_status(self, app_id: int, status: str, reason: str | None = None) -> None: ...
    def add_vote(self, app_id: int, voter_no: str, vote: str) -> bool: ...
    def votes(self, app_id: int) -> dict[str, str]: ...
    def get_setting(self, key: str) -> str | None: ...
    def set_setting(self, key: str, value: str | None) -> None: ...
    def log_ai(self, tier: int, model: str, outcome: str, detail: str, elapsed_ms: int) -> None: ...
    def snapshot(self) -> Snapshot: ...


ADMIN_NO = "admin"
MAX_SLOT = 4


class MemoryStore:
    """한 프로세스 안에서만 사는 저장소. 시험과 로컬 화면 시험에 씀."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._admin_hash: str | None = None
        self._students: dict[str, Student] = {}
        self._student_hash: str | None = None
        self._teams: list[int] = []
        self._slots: dict[int, dict[int, str]] = {}
        self._apps: dict[int, Application] = {}
        self._next_app = 1
        self._votes: dict[int, dict[str, str]] = {}
        self._settings: dict[str, str] = {}
        self.ai_logs: list[tuple[int, str, str, str, int]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            yield

    def lock_team(self, team_id: int) -> None:
        pass  # transaction()의 잠금 하나로 모든 처리를 줄 세움

    def reset(self, students: list[Student], team_count: int) -> None:
        with self._lock:
            self._students = {s.student_no: s for s in students}
            self._student_hash = None
            self._teams = list(range(1, team_count + 1))
            self._slots = {t: {} for t in self._teams}
            self._apps, self._votes, self._settings = {}, {}, {}

    def upsert_admin(self, password_hash: str) -> None:
        self._admin_hash = password_hash

    def set_all_student_password_hash(self, password_hash: str) -> None:
        self._student_hash = password_hash

    def get_login(self, student_no: str) -> tuple[Account, str] | None:
        if student_no == ADMIN_NO and self._admin_hash:
            return Account(ADMIN_NO, "관리자", True), self._admin_hash
        s = self._students.get(student_no)
        if s is None or self._student_hash is None:
            return None
        return Account(s.student_no, s.name, False), self._student_hash

    def get_student(self, student_no: str) -> Student | None:
        return self._students.get(student_no)

    def list_students(self) -> list[Student]:
        return sorted(self._students.values(), key=lambda s: s.student_no)

    def team_ids(self) -> list[int]:
        return list(self._teams)

    def members(self, team_id: int) -> list[Student]:
        slots = self._slots.get(team_id, {})
        return [self._students[slots[k]] for k in sorted(slots)]

    def team_of(self, student_no: str) -> int | None:
        for t, slots in self._slots.items():
            if student_no in slots.values():
                return t
        return None

    def add_member(self, team_id: int, student_no: str) -> bool:
        with self._lock:
            slots = self._slots[team_id]
            free = [k for k in range(1, MAX_SLOT + 1) if k not in slots]
            if not free or self.team_of(student_no) is not None:
                return False
            slots[free[0]] = student_no
            return True

    def remove_member(self, student_no: str) -> None:
        for slots in self._slots.values():
            for k, no in list(slots.items()):
                if no == student_no:
                    del slots[k]

    def create_application(self, team_id: int, student_no: str) -> Application:
        with self._lock:
            if self.pending_application_of(student_no):
                raise ValueError("이미 대기 중인 지원이 있음")
            app = Application(self._next_app, team_id, student_no, PENDING)
            self._apps[app.id] = app
            self._next_app += 1
            return app

    def get_application(self, app_id: int) -> Application:
        return self._apps[app_id]

    def applications_of(self, student_no: str) -> list[Application]:
        return [a for a in self._apps.values() if a.student_no == student_no]

    def pending_application_of(self, student_no: str) -> Application | None:
        return next((a for a in self._apps.values() if a.student_no == student_no and a.status == PENDING), None)

    def pending_applications(self, team_id: int | None = None) -> list[Application]:
        return [a for a in sorted(self._apps.values(), key=lambda a: a.id)
                if a.status == PENDING and (team_id is None or a.team_id == team_id)]

    def set_application_status(self, app_id: int, status: str, reason: str | None = None) -> None:
        self._apps[app_id] = replace(self._apps[app_id], status=status, reason=reason)

    def add_vote(self, app_id: int, voter_no: str, vote: str) -> bool:
        with self._lock:
            votes = self._votes.setdefault(app_id, {})
            if voter_no in votes:
                return False
            votes[voter_no] = vote
            return True

    def votes(self, app_id: int) -> dict[str, str]:
        return dict(self._votes.get(app_id, {}))

    def get_setting(self, key: str) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: str, value: str | None) -> None:
        if value is None:
            self._settings.pop(key, None)
        else:
            self._settings[key] = value

    def log_ai(self, tier: int, model: str, outcome: str, detail: str, elapsed_ms: int) -> None:
        self.ai_logs.append((tier, model, outcome, detail, elapsed_ms))

    def snapshot(self) -> Snapshot:
        with self._lock:
            pending = self.pending_applications()
            latest: dict[str, Application] = {}
            for a in sorted(self._apps.values(), key=lambda a: a.id):
                latest[a.student_no] = a
            rejected = sorted((a for a in latest.values() if a.status == REJECTED and a.reason != CLOSE_REASON),
                              key=lambda a: a.id)
            return Snapshot(
                students={s.student_no: s for s in self.list_students()},
                team_ids=self.team_ids(),
                members={t: [self._slots[t][k] for k in sorted(self._slots[t])] for t in self._teams},
                pending=pending,
                votes={a.id: self.votes(a.id) for a in pending + rejected if self._votes.get(a.id)},
                settings=dict(self._settings),
                rejected=rejected,
            )
