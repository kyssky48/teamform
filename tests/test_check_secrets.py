# 생성: 2026-10-23 19:19 (KST)
from scripts import check_secrets

SECRETS = {
    "OPENROUTER_API_KEY": "sk-or-v1-realkey123",
    "DATABASE_URL": "postgresql://postgres.ref:pa%40ss@aws-0.pooler.supabase.com:5432/postgres",
    "ADMIN_PASSWORD": "adm1n!",
}


def test_scan_finds_each_secret_and_db_password():
    text = "commit ...\n+ password = 'pa@ss'\n+ key sk-or-v1-realkey123\n"
    found = check_secrets.scan(text, SECRETS)
    assert found == {"OPENROUTER_API_KEY": True, "DATABASE_URL": False, "DB 비밀번호": True, "ADMIN_PASSWORD": False}


def test_scan_ignores_fake_test_urls():
    text = "+ URL = 'postgresql://postgres.abc:secretpw@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres'"
    assert not any(check_secrets.scan(text, SECRETS).values())


def test_report_prints_only_yes_no(capsys):
    code = check_secrets.report({"OPENROUTER_API_KEY": True, "ADMIN_PASSWORD": False})
    out = capsys.readouterr().out
    assert code == 1 and "OPENROUTER_API_KEY: 있음" in out and "ADMIN_PASSWORD: 없음" in out
    assert "realkey" not in out
    assert check_secrets.report({"ADMIN_PASSWORD": False}) == 0
