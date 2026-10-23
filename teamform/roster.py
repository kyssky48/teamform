# 생성: 2026-10-21 22:07 (KST)
"""명단 CSV 읽기 (공고 2.6절)."""
import csv
import io

from teamform.model import ROLES, Student

COLUMNS = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(Exception):
    pass


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_roster(data: bytes) -> list[Student]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("UTF-8 파일이 아님")
    reader = csv.reader(io.StringIO(text))
    # (파일의 줄 번호, 칸들). 빈 줄은 건너뛰되 줄 번호는 실제 파일 기준으로 셈
    rows = [(reader.line_num, r) for r in reader if any(c.strip() for c in r)]
    if not rows or [_clean(c) for c in rows[0][1]] != COLUMNS:
        raise RosterError("첫 줄은 student_no,name,main_role,sub_roles 이어야 함")
    if len(rows) == 1:
        raise RosterError("학생이 한 명도 없음")

    header_line = rows[0][0]
    students: list[Student] = []
    seen: set[str] = set()
    for file_line, row in rows[1:]:
        line = file_line - header_line  # 헤더 다음 줄이 1번째 줄
        where = f"{line}번째 줄"
        if len(row) != 4:
            raise RosterError(f"{where}: 열이 4개가 아님")
        no, name, main, subs = (_clean(c) for c in row)
        if not no or not name:
            raise RosterError(f"{where}: 학번이나 이름이 비어 있음")
        if no.lower() == "admin":
            raise RosterError(f"{where}: 학번 admin은 관리자용이라 쓸 수 없음")
        if no in seen:
            raise RosterError(f"{where}: 학번 {no}이(가) 겹침")
        if main not in ROLES:
            raise RosterError(f"{where}: 주 역할 '{main}'은(는) 6개 역할이 아님")
        sub_roles: list[str] = []
        for sub in (_clean(s) for s in subs.split(";")):
            if not sub:
                continue
            if sub not in ROLES:
                raise RosterError(f"{where}: 보조 역할 '{sub}'은(는) 6개 역할이 아님")
            if sub != main and sub not in sub_roles:
                sub_roles.append(sub)
        if len(sub_roles) > 2:
            raise RosterError(f"{where}: 보조 역할이 2개를 넘음")
        seen.add(no)
        students.append(Student(no, name, main, tuple(sub_roles)))
    return students
