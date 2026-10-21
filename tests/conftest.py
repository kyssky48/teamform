# 생성: 2026-10-21 22:17 (KST)
import pytest

from teamform.model import Account, Student
from teamform.store import MemoryStore


def acct(s: Student) -> Account:
    return Account(s.student_no, s.name, False)


ADMIN = Account("admin", "관리자", True)


@pytest.fixture
def make_store():
    """make_store(students, team_count) → 학생과 빈 팀이 든 MemoryStore."""

    def _make(students: list[Student], team_count: int = 4) -> MemoryStore:
        st = MemoryStore()
        st.upsert_admin("x")
        st.reset(students, team_count)
        return st

    return _make
