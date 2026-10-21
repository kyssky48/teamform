# 생성: 2026-10-21 22:07 (KST)
"""역할 상수와 데이터 클래스."""
from dataclasses import dataclass

ROLES = ("기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자")
PL = "기획자"
WP = "웹 프로그래머"

PENDING, APPROVED, REJECTED = "대기", "승인", "거절"
YES, NO = "찬성", "거부"


@dataclass(frozen=True)
class Student:
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...] = ()

    def can(self, role: str) -> bool:
        return role == self.main_role or role in self.sub_roles


@dataclass(frozen=True)
class Application:
    id: int
    team_id: int
    student_no: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class Account:
    student_no: str
    name: str
    is_admin: bool
