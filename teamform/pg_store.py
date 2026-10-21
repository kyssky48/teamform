# 생성: 2026-10-21 22:27 (KST)
"""Supabase(Postgres)용 저장소.

연결은 하나만 만들어 다시 쓴다(공고 4.2절). Streamlit은 브라우저마다 다른 스레드에서 돌기 때문에,
한 연결 위에서 두 사람의 트랜잭션이 섞이지 않도록 모든 질의를 RLock 하나로 줄 세운다.
"""
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from teamform.model import PENDING, Account, Application, Student
from teamform.store import ADMIN_NO, Snapshot

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")

_STUDENT_SQL = """
select s.student_no, s.name, s.main_role,
       coalesce(array_agg(r.role order by r.position) filter (where r.role is not null), '{}')
from tf_students s left join tf_student_sub_roles r on r.student_id = s.id
where not s.is_admin {where}
group by s.id order by s.student_no
"""

_APP_SQL = """
select a.id, a.team_id, s.student_no, a.status, a.reason
from tf_applications a join tf_students s on s.id = a.student_id
where {where} order by a.id
"""

_SNAPSHOT_SQL = """
select json_build_object(
  'students', (select coalesce(json_agg(json_build_object(
        'no', s.student_no, 'name', s.name, 'main', s.main_role,
        'subs', (select coalesce(json_agg(r.role order by r.position), '[]')
                 from tf_student_sub_roles r where r.student_id = s.id)) order by s.student_no), '[]')
      from tf_students s where not s.is_admin),
  'teams', (select coalesce(json_agg(id order by id), '[]') from tf_teams),
  'members', (select coalesce(json_agg(json_build_object('team', m.team_id, 'no', s.student_no)
        order by m.team_id, m.slot_no), '[]')
      from tf_members m join tf_students s on s.id = m.student_id),
  'pending', (select coalesce(json_agg(json_build_object('id', a.id, 'team', a.team_id,
        'no', s.student_no, 'reason', a.reason) order by a.id), '[]')
      from tf_applications a join tf_students s on s.id = a.student_id where a.status = '대기'),
  'votes', (select coalesce(json_agg(json_build_object('app', v.application_id, 'voter', s.student_no,
        'vote', v.vote)), '[]')
      from tf_votes v join tf_students s on s.id = v.voter_id
      join tf_applications a on a.id = v.application_id where a.status = '대기'),
  'settings', (select coalesce(json_object_agg(key, value), '{}') from tf_settings)
)
"""


def _student(row) -> Student:
    return Student(row[0], row[1], row[2], tuple(row[3]))


def _app(row) -> Application:
    return Application(row[0], row[1], row[2], row[3], row[4])


class PgStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._lock = threading.RLock()
        self._conn: psycopg.Connection | None = None
        self._depth = 0

    # ---- 연결과 트랜잭션 ----

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed or (self._depth == 0 and self._conn.broken):
            # prepare_threshold=None: Supabase 연결 풀러에서 준비된 문장 충돌을 피함
            self._conn = psycopg.connect(self._url, autocommit=True, prepare_threshold=None, connect_timeout=10)
        return self._conn

    def _q(self, sql: str, params=()) -> list[tuple]:
        with self._lock:
            cur = self._connection().execute(sql, params)
            return cur.fetchall() if cur.description else []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            conn = self._connection()
            self._depth += 1
            try:
                with conn.transaction():
                    yield
            finally:
                self._depth -= 1

    def lock_team(self, team_id: int) -> None:
        self._q("select 1 from tf_teams where id = %s for update", (team_id,))

    def apply_schema(self) -> None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            sql = f.read()
        with self._lock:
            self._connection().execute(sql)

    def ping(self) -> int:
        return self._q("select count(*) from tf_settings")[0][0]

    # ---- 학생과 로그인 ----

    def reset(self, students: list[Student], team_count: int) -> None:
        with self.transaction():
            for sql in (
                "delete from tf_votes",
                "delete from tf_applications",
                "delete from tf_members",
                "delete from tf_settings",
                "delete from tf_teams",
                "delete from tf_students where not is_admin",
            ):
                self._q(sql)
            with self._lock:
                cur = self._connection().cursor()
                cur.executemany(
                    "insert into tf_teams (id, name) values (%s, %s)",
                    [(t, f"팀{t}") for t in range(1, team_count + 1)],
                )
                cur.executemany(
                    "insert into tf_students (student_no, name, main_role, password_hash) values (%s, %s, %s, '')",
                    [(s.student_no, s.name, s.main_role) for s in students],
                )
                cur.executemany(
                    "insert into tf_student_sub_roles (student_id, role, position) "
                    "select id, %s, %s from tf_students where student_no = %s",
                    [(r, i, s.student_no) for s in students for i, r in enumerate(s.sub_roles, 1)],
                )

    def upsert_admin(self, password_hash: str) -> None:
        self._q(
            "insert into tf_students (student_no, name, main_role, password_hash, is_admin) "
            "values (%s, '관리자', null, %s, true) "
            "on conflict (student_no) do update set password_hash = excluded.password_hash, is_admin = true",
            (ADMIN_NO, password_hash),
        )

    def set_all_student_password_hash(self, password_hash: str) -> None:
        self._q("update tf_students set password_hash = %s where not is_admin", (password_hash,))

    def get_login(self, student_no: str) -> tuple[Account, str] | None:
        rows = self._q(
            "select student_no, name, is_admin, password_hash from tf_students where student_no = %s",
            (student_no,),
        )
        if not rows or not rows[0][3]:
            return None
        no, name, is_admin, h = rows[0]
        return Account(no, name, is_admin), h

    def get_student(self, student_no: str) -> Student | None:
        rows = self._q(_STUDENT_SQL.format(where="and s.student_no = %s"), (student_no,))
        return _student(rows[0]) if rows else None

    def list_students(self) -> list[Student]:
        return [_student(r) for r in self._q(_STUDENT_SQL.format(where=""))]

    # ---- 팀과 팀원 ----

    def team_ids(self) -> list[int]:
        return [r[0] for r in self._q("select id from tf_teams order by id")]

    def members(self, team_id: int) -> list[Student]:
        nos = [r[0] for r in self._q(
            "select s.student_no from tf_members m join tf_students s on s.id = m.student_id "
            "where m.team_id = %s order by m.slot_no",
            (team_id,),
        )]
        by_no = {s.student_no: s for s in self.list_students()} if nos else {}
        return [by_no[n] for n in nos]

    def team_of(self, student_no: str) -> int | None:
        rows = self._q(
            "select m.team_id from tf_members m join tf_students s on s.id = m.student_id where s.student_no = %s",
            (student_no,),
        )
        return rows[0][0] if rows else None

    def add_member(self, team_id: int, student_no: str) -> bool:
        """빈 자리 중 가장 작은 번호에 넣음. 자리나 학생이 겹치면 DB 제약이 막고 False."""
        try:
            with self.transaction():  # 바깥 트랜잭션 안에서는 savepoint
                self._q(
                    "insert into tf_members (team_id, slot_no, student_id) "
                    "select %s, (select min(n) from generate_series(1, 4) n "
                    "            where n not in (select slot_no from tf_members where team_id = %s)), id "
                    "from tf_students where student_no = %s",
                    (team_id, team_id, student_no),
                )
        except psycopg.errors.IntegrityError:
            return False
        return True

    def remove_member(self, student_no: str) -> None:
        self._q(
            "delete from tf_members where student_id = (select id from tf_students where student_no = %s)",
            (student_no,),
        )

    # ---- 지원과 투표 ----

    def create_application(self, team_id: int, student_no: str) -> Application:
        rows = self._q(
            "insert into tf_applications (team_id, student_id) "
            "select %s, id from tf_students where student_no = %s returning id",
            (team_id, student_no),
        )
        return Application(rows[0][0], team_id, student_no, PENDING)

    def get_application(self, app_id: int) -> Application:
        return _app(self._q(_APP_SQL.format(where="a.id = %s"), (app_id,))[0])

    def applications_of(self, student_no: str) -> list[Application]:
        return [_app(r) for r in self._q(_APP_SQL.format(where="s.student_no = %s"), (student_no,))]

    def pending_application_of(self, student_no: str) -> Application | None:
        rows = self._q(_APP_SQL.format(where="s.student_no = %s and a.status = '대기'"), (student_no,))
        return _app(rows[0]) if rows else None

    def pending_applications(self, team_id: int | None = None) -> list[Application]:
        if team_id is None:
            return [_app(r) for r in self._q(_APP_SQL.format(where="a.status = '대기'"))]
        return [_app(r) for r in self._q(_APP_SQL.format(where="a.status = '대기' and a.team_id = %s"), (team_id,))]

    def set_application_status(self, app_id: int, status: str, reason: str | None = None) -> None:
        self._q(
            "update tf_applications set status = %s, reason = %s, "
            "decided_at = case when %s = '대기' then null else now() end where id = %s",
            (status, reason, status, app_id),
        )

    def add_vote(self, app_id: int, voter_no: str, vote: str) -> bool:
        rows = self._q(
            "insert into tf_votes (application_id, voter_id, vote) "
            "select %s, id, %s from tf_students where student_no = %s "
            "on conflict do nothing returning 1",
            (app_id, vote, voter_no),
        )
        return bool(rows)

    def votes(self, app_id: int) -> dict[str, str]:
        return dict(self._q(
            "select s.student_no, v.vote from tf_votes v join tf_students s on s.id = v.voter_id "
            "where v.application_id = %s",
            (app_id,),
        ))

    # ---- 설정, 기록, 현황 ----

    def get_setting(self, key: str) -> str | None:
        rows = self._q("select value from tf_settings where key = %s", (key,))
        return rows[0][0] if rows else None

    def set_setting(self, key: str, value: str | None) -> None:
        if value is None:
            self._q("delete from tf_settings where key = %s", (key,))
        else:
            self._q(
                "insert into tf_settings (key, value) values (%s, %s) "
                "on conflict (key) do update set value = excluded.value",
                (key, value),
            )

    def log_ai(self, tier: int, model: str, outcome: str, detail: str, elapsed_ms: int) -> None:
        self._q(
            "insert into tf_ai_logs (tier, model, outcome, detail, elapsed_ms) values (%s, %s, %s, %s, %s)",
            (tier, model, outcome, detail, elapsed_ms),
        )

    def snapshot(self) -> Snapshot:
        data = self._q(_SNAPSHOT_SQL)[0][0]
        if isinstance(data, str):
            data = json.loads(data)
        team_ids = list(data["teams"])
        members: dict[int, list[str]] = {t: [] for t in team_ids}
        for m in data["members"]:
            members[m["team"]].append(m["no"])
        votes: dict[int, dict[str, str]] = {}
        for v in data["votes"]:
            votes.setdefault(v["app"], {})[v["voter"]] = v["vote"]
        return Snapshot(
            students={s["no"]: Student(s["no"], s["name"], s["main"], tuple(s["subs"])) for s in data["students"]},
            team_ids=team_ids,
            members=members,
            pending=[Application(p["id"], p["team"], p["no"], PENDING, p["reason"]) for p in data["pending"]],
            votes=votes,
            settings=dict(data["settings"]),
        )
