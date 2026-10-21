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


def login(store: Store, student_no: str, password: str) -> Account | None:
    if not student_no or not password:
        return None
    found = store.get_login(student_no.strip())
    if found is None:
        return None
    account, hashed = found
    return account if check_password(password, hashed) else None
