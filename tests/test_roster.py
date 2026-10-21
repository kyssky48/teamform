# 생성: 2026-10-21 22:07 (KST)
import pytest

from teamform.model import Student
from teamform.roster import RosterError, parse_roster

HEADER = "student_no,name,main_role,sub_roles\n"


def test_parse_basic():
    data = (HEADER + "2026101,학생1,기획자,보고서 작성자\n2026105,학생5,웹 프로그래머,\n").encode("utf-8-sig")
    s = parse_roster(data)
    assert s[0] == Student("2026101", "학생1", "기획자", ("보고서 작성자",))
    assert s[1].sub_roles == ()


def test_parse_messy_csv():
    data = (
        HEADER
        + "2026001, 가나다 , 기획자 , 보고서  작성자\n"
        + "2026002, 라마바 , 웹  프로그래머 ,\n"
        + "2026003, 사아자 , 테스터 , 기획자 ; 발표자\n"
    ).encode("utf-8-sig")
    s = parse_roster(data)
    assert s[0].sub_roles == ("보고서 작성자",)
    assert s[1] == Student("2026002", "라마바", "웹 프로그래머", ())
    assert s[2].sub_roles == ("기획자", "발표자")


def test_parse_without_bom():
    text = HEADER + "2026101,학생1,기획자,보고서 작성자\n"
    assert parse_roster(text.encode("utf-8")) == parse_roster(text.encode("utf-8-sig"))


def test_parse_handout_files():
    for name, count in [("쉬움", 8), ("중간", 12), ("어려움", 16)]:
        with open(f"tests/data/{name}.csv", "rb") as f:
            assert len(parse_roster(f.read())) == count


def test_student_can_uses_main_and_sub_roles():
    s = Student("1", "a", "테스터", ("기획자",))
    assert s.can("테스터") and s.can("기획자") and not s.can("웹 프로그래머")


@pytest.mark.parametrize(
    "body, line",
    [
        ("2026101,학생1,요리사,\n", 1),  # 역할 밖 값
        ("2026101,학생1,기획자,\n2026102,학생2,기획자\n", 2),  # 열이 3개
        ("2026101,학생1,기획자,\n2026101,학생2,테스터,\n", 2),  # 학번 중복
        ("2026101,학생1,기획자,테스터;발표자;보고서 작성자\n", 1),  # 보조 역할 3개
        ("2026101,학생1,기획자,요리사\n", 1),  # 보조 역할이 역할 밖
        (",학생1,기획자,\n", 1),  # 학번 빈칸
        ("admin,학생1,기획자,\n", 1),  # 관리자 학번과 겹침
    ],
)
def test_parse_errors(body, line):
    with pytest.raises(RosterError) as e:
        parse_roster((HEADER + body).encode("utf-8-sig"))
    assert f"{line}번째 줄" in str(e.value)


@pytest.mark.parametrize("data", [b"", HEADER.encode(), b"a,b,c,d\n1,x,\xea\xb8\xb0\xed\x9a\x8d\xec\x9e\x90,\n"])
def test_parse_empty_or_wrong_header(data):
    with pytest.raises(RosterError):
        parse_roster(data)
