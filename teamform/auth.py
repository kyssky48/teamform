# 생성: 2026-10-21 22:21 (KST)
"""비밀번호 해시(bcrypt)와 로그인."""
import bcrypt

from teamform.model import Account
from teamform.store import ADMIN_NO, Store

ROUNDS = 10


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(ROUNDS)).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def ensure_admin(store: Store, admin_password: str) -> None:
    """앱이 시작할 때 관리자 계정을 만들거나 비밀번호를 갱신함(공고 2.1절)."""
    if not admin_password:
        raise ValueError("ADMIN_PASSWORD 없음")
    found = store.get_login(ADMIN_NO)
    if found and check_password(admin_password, found[1]):
        return
    store.upsert_admin(hash_password(admin_password))


def login(store: Store, student_no: str, password: str, admin_password: str | None = None) -> Account | None:
    """admin_password를 주면 관리자 로그인 때마다 관리자 계정을 그 값으로 맞춘 뒤 확인함
    (DB의 해시가 다른 이유로 바뀌어도 Secrets의 ADMIN_PASSWORD로 로그인되게)."""
    if not student_no or not password:
        return None
    student_no = student_no.strip()
    if student_no == ADMIN_NO and admin_password:
        ensure_admin(store, admin_password)
    found = store.get_login(student_no)
    if found is None:
        return None
    account, hashed = found
    return account if check_password(password, hashed) else None
