# 생성: 2026-10-21 22:51 (KST)
from scripts import db_ping

URL = "postgresql://postgres.abc:secretpw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"


class FakeConn:
    def __init__(self, fail=False):
        self.fail, self.sql = fail, None

    def execute(self, sql):
        if self.fail:
            raise RuntimeError(f"could not connect to {URL}")
        self.sql = sql
        return self

    def fetchone(self):
        return (3,)

    def close(self):
        pass


def test_ping_ok(capsys):
    conn = FakeConn()
    assert db_ping.main(URL, connect=lambda url: conn) == 0
    assert "tf_settings" in conn.sql
    out = capsys.readouterr().out
    assert "성공" in out and "secretpw" not in out and URL not in out


def test_ping_error_hides_url(capsys):
    assert db_ping.main(URL, connect=lambda url: FakeConn(fail=True)) == 1
    out = capsys.readouterr()
    assert "실패" in out.out
    assert "secretpw" not in out.out + out.err and "pooler" not in out.out + out.err


def test_ping_without_url(capsys):
    assert db_ping.main(None) == 1
    assert "DATABASE_URL 없음" in capsys.readouterr().out
