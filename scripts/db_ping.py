# 생성: 2026-10-21 22:51 (KST)
"""Supabase 무료 프로젝트가 일시정지되지 않도록 DB에 질의 한 번을 보낸다(공고 3장, 4.4절).
GitHub Actions가 매일 실행한다. DB 주소나 오류 내용은 출력하지 않는다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from teamform.dburl import normalize_db_url  # noqa: E402


def _connect(url: str):
    import psycopg

    return psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=15)


def main(database_url: str | None, connect=_connect) -> int:
    if not database_url:
        print("실패: DATABASE_URL 없음")
        return 1
    try:
        conn = connect(normalize_db_url(database_url))
        try:
            count = conn.execute("select count(*) from tf_settings").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:  # 오류 글에 주소가 섞일 수 있어 종류만 출력
        print(f"실패: {type(e).__name__}")
        return 1
    print(f"성공: tf_settings 행 {count}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(os.environ.get("DATABASE_URL")))
