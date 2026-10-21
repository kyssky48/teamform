# 생성: 2026-10-21 22:26 (KST)
"""MemoryStore와 PgStore가 똑같이 동작하는지 확인.
PgStore 쪽은 DATABASE_URL이 있고 TEAMFORM_PG_TESTS=1일 때만 돈다(실제 DB의 tf_ 데이터를 지우므로)."""
import os

import pytest

from teamform.model import APPROVED, PENDING, REJECTED, Student
from teamform.store import MemoryStore
from tests.helpers import S


def _pg_store():
    from teamform import config, pg_store

    url = config.get_secret("DATABASE_URL")
    if not url or os.environ.get("TEAMFORM_PG_TESTS") != "1":
        pytest.skip("실제 DB 시험은 TEAMFORM_PG_TESTS=1 일 때만")
    store = pg_store.PgStore(url)
    store.apply_schema()
    return store


@pytest.fixture(params=["memory", "pg"])
def store(request):
    st = MemoryStore() if request.param == "memory" else _pg_store()
    st.upsert_admin("hash-admin")
    return st


def two(store):
    a = Student("t001", "가", "기획자", ("발표자", "테스터"))
    b = Student("t002", "나", "웹 프로그래머", ())
    store.reset([a, b], 3)
    store.set_all_student_password_hash("hash-student")
    return a, b


def test_students_roundtrip(store):
    a, b = two(store)
    assert store.get_student("t001") == a
    assert store.list_students() == [a, b]
    assert store.get_student("admin") is None
    assert store.get_student("nope") is None
    acc, h = store.get_login("t001")
    assert (acc.name, acc.is_admin, h) == ("가", False, "hash-student")
    acc, h = store.get_login("admin")
    assert acc.is_admin and h == "hash-admin"
    assert store.get_login("nope") is None


def test_teams_and_slots(store):
    a, b = two(store)
    assert store.team_ids() == [1, 2, 3]
    assert store.add_member(2, "t002") and store.add_member(2, "t001")
    assert store.members(2) == [b, a]
    assert store.team_of("t001") == 2 and store.team_of("t002") == 2
    assert not store.add_member(1, "t001")  # 한 학생은 한 팀
    store.remove_member("t002")
    assert store.members(2) == [a]
    assert store.add_member(2, "t002")
    assert store.members(2) == [b, a]  # 빈 1번 자리에 들어감


def test_fifth_slot_rejected(store):
    ppl = [S(r) for r in ("PL", "WP", "FD", "TT", "RW")]
    store.reset(ppl, 1)
    assert [store.add_member(1, p.student_no) for p in ppl] == [True] * 4 + [False]


def test_applications_and_votes(store):
    a, b = two(store)
    app = store.create_application(1, "t002")
    assert (app.team_id, app.student_no, app.status) == (1, "t002", PENDING)
    with pytest.raises(Exception):
        store.create_application(2, "t002")  # 대기 지원은 하나만
    assert store.pending_application_of("t002") == app
    assert store.pending_applications(1) == [app] and store.pending_applications(2) == []
    assert store.add_vote(app.id, "t001", "찬성") and not store.add_vote(app.id, "t001", "거부")
    assert store.votes(app.id) == {"t001": "찬성"}
    store.set_application_status(app.id, REJECTED, "팀원이 거부함")
    assert store.get_application(app.id).reason == "팀원이 거부함"
    assert store.pending_application_of("t002") is None
    app2 = store.create_application(2, "t002")
    store.set_application_status(app2.id, APPROVED)
    assert [x.status for x in store.applications_of("t002")] == [REJECTED, APPROVED]


def test_reset_keeps_admin_and_clears(store):
    a, b = two(store)
    store.add_member(1, "t001")
    store.create_application(1, "t002")
    store.set_setting("closed", "1")
    c = Student("t003", "다", "테스터", ())
    store.reset([c], 2)
    assert store.list_students() == [c]
    assert store.team_ids() == [1, 2] and store.members(1) == []
    assert store.pending_applications() == [] and store.get_setting("closed") is None
    assert store.get_login("admin")[0].is_admin


def test_settings(store):
    two(store)
    store.set_setting("k", "v1")
    store.set_setting("k", "v2")
    assert store.get_setting("k") == "v2"
    store.set_setting("k", None)
    assert store.get_setting("k") is None


def test_transaction_rolls_back_on_error(store):
    two(store)
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.set_setting("k", "v")
            raise RuntimeError
    if isinstance(store, MemoryStore):
        pytest.skip("MemoryStore는 되돌리기를 하지 않음(시험용)")
    assert store.get_setting("k") is None


def test_snapshot(store):
    a, b = two(store)
    store.add_member(1, "t001")
    app = store.create_application(1, "t002")
    store.add_vote(app.id, "t001", "찬성")
    store.set_setting("closed", "1")
    snap = store.snapshot()
    assert snap.students == {"t001": a, "t002": b}
    assert snap.team_ids == [1, 2, 3]
    assert snap.members == {1: ["t001"], 2: [], 3: []}
    assert snap.pending == [app]
    assert snap.votes == {app.id: {"t001": "찬성"}}
    assert snap.settings == {"closed": "1"}


def test_log_ai(store):
    two(store)
    store.log_ai(1, "m:free", "실패", "HTTP 429", 1200)
