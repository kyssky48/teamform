# 생성: 2026-10-23 11:21 (KST)
"""끊긴 DB 연결을 다시 잇는지 (실제 DB 없이 가짜 연결로)."""
import psycopg
import pytest

from teamform.pg_store import PgStore


class FakeCursor:
    description = [("x",)]

    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, dead=False):
        self.dead, self.closed, self.broken, self.sqls = dead, False, False, []

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        if self.dead and not sql.startswith("set "):
            self.broken = True
            raise psycopg.OperationalError("server closed the connection unexpectedly")
        return FakeCursor([(1,)])


def test_query_retries_once_on_dropped_connection():
    made = []

    def connect(url, **kw):
        made.append(kw)
        return FakeConn(dead=len(made) == 1)

    store = PgStore("postgresql://u:p@h/db", connect=connect)
    assert store.team_ids() == [1]
    assert len(made) == 2


def test_connection_has_keepalive_and_statement_timeout():
    made, conns = [], []

    def connect(url, **kw):
        made.append(kw)
        conns.append(FakeConn())
        return conns[-1]

    store = PgStore("postgresql://u:p@h/db", connect=connect)
    store.team_ids()
    kw = made[0]
    assert kw["keepalives"] == 1 and kw["keepalives_idle"] <= 60 and kw["connect_timeout"] <= 15
    assert conns[0].sqls[0].startswith("set statement_timeout")


def test_no_retry_inside_transaction():
    made = []

    def connect(url, **kw):
        made.append(kw)
        return FakeConn(dead=True)

    store = PgStore("postgresql://u:p@h/db", connect=connect)
    store._conn = FakeConn(dead=True)
    store._depth = 1  # 트랜잭션 안에서는 다시 시도하면 앞의 작업이 사라지므로 하지 않음
    with pytest.raises(psycopg.OperationalError):
        store._q("select 1")
    assert made == []
