# 생성: 2026-10-21 22:20 (KST)
from teamform import auth, service
from tests.conftest import ADMIN
from tests.helpers import S

CSV = "student_no,name,main_role,sub_roles\n2026101,학생1,기획자,\n2026102,학생2,웹 프로그래머,\n".encode("utf-8-sig")


def started(make_store):
    st = make_store([])
    auth.ensure_admin(st, "adminpw")
    assert service.start(st, ADMIN, CSV, 3).startswith("승인")
    return st


def test_login_ok_and_wrong_password(make_store):
    st = started(make_store)
    acc = auth.login(st, "2026101", "1234")
    assert acc is not None and acc.name == "학생1" and not acc.is_admin
    assert auth.login(st, "2026101", "4321") is None
    assert auth.login(st, "2026101", "") is None
    assert auth.login(st, "9999999", "1234") is None


def test_admin_login(make_store):
    st = started(make_store)
    assert auth.login(st, "admin", "adminpw").is_admin
    assert auth.login(st, "admin", "1234") is None


def test_password_stored_hashed(make_store):
    st = started(make_store)
    _, hashed = st.get_login("2026101")
    assert hashed != "1234" and hashed.startswith("$2")
    _, admin_hashed = st.get_login("admin")
    assert "adminpw" not in admin_hashed


def test_ensure_admin_updates_password(make_store):
    st = started(make_store)
    auth.ensure_admin(st, "newpw")
    assert auth.login(st, "admin", "adminpw") is None
    assert auth.login(st, "admin", "newpw").is_admin


def test_ensure_admin_skips_when_unchanged(make_store):
    st = started(make_store)
    _, before = st.get_login("admin")
    auth.ensure_admin(st, "adminpw")
    assert st.get_login("admin")[1] == before  # 같은 비밀번호면 해시를 다시 만들지 않음


def test_hash_roundtrip():
    h = auth.hash_password("1234")
    assert auth.check_password("1234", h) and not auth.check_password("1235", h)
    assert not auth.check_password("1234", "not-a-hash")


def test_student_named_admin_cannot_be_admin(make_store):
    st = make_store([S("PL", no="admin2")])
    assert auth.login(st, "admin", "x") is None  # 관리자 비밀번호가 없으면 로그인 불가


def test_admin_login_repairs_overwritten_admin_hash(make_store):
    # 배포 앱은 관리자 계정을 앱이 켜질 때 한 번 맞추므로, 그 뒤 DB의 해시가 바뀌면 로그인이 막혔음
    st = started(make_store)
    st.upsert_admin("not-a-bcrypt-hash")
    assert auth.login(st, "admin", "adminpw") is None
    assert auth.login(st, "admin", "adminpw", admin_password="adminpw").is_admin
    assert auth.login(st, "admin", "wrong", admin_password="adminpw") is None
    assert auth.login(st, "2026101", "1234", admin_password="adminpw").name == "학생1"
