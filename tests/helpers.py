# 생성: 2026-10-21 22:14 (KST)
"""시험용 학생 만들기 도우미. S("TT", "PL") → 주 역할 테스터, 보조 역할 기획자."""
import itertools

from teamform.model import Student

ABBR = {
    "PL": "기획자",
    "WP": "웹 프로그래머",
    "FD": "프론트엔드 디자이너",
    "TT": "테스터",
    "RW": "보고서 작성자",
    "PT": "발표자",
}
_seq = itertools.count(1)


def S(main: str, *subs: str, no: str | None = None) -> Student:
    n = no or f"9{next(_seq):05d}"
    return Student(n, f"학생{n}", ABBR[main], tuple(ABBR[s] for s in subs))
