# 생성: 2026-10-23 19:19 (KST)
"""저장소를 공개하기 전에, .env의 실제 비밀 값이 커밋 기록이나 지금 파일에 들어 있는지 검사한다.
값은 출력하지 않고 "있음/없음"만 보여 준다. 실행: .venv/Scripts/python scripts/check_secrets.py"""
import os
import subprocess
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")


def scan(text: str, secrets: dict[str, str]) -> dict[str, bool]:
    """text 안에 각 비밀 값이 있는지. DB 주소는 주소 전체와 그 안의 비밀번호를 따로 봄."""
    found = {}
    for name in NAMES:
        value = secrets.get(name) or ""
        found[name] = bool(value) and value in text
        if name == "DATABASE_URL" and value:
            password = unquote(urlsplit(value).password or "")
            found["DB 비밀번호"] = bool(password) and (password in text or (urlsplit(value).password or "") in text)
    return found


def report(found: dict[str, bool]) -> int:
    for name, hit in found.items():
        print(f"{name}: {'있음 ⚠' if hit else '없음'}")
    if any(found.values()):
        print("공개하면 안 됨: 위 값을 바꾸고(키 재발급, 비밀번호 변경) 기록에서 지워야 함")
        return 1
    print("통과: 커밋 기록과 파일에 실제 비밀 값이 없음")
    return 0


def main() -> int:
    from teamform import config

    secrets = {name: config.get_secret(name) or "" for name in NAMES}
    history = subprocess.run(["git", "log", "-p", "--all"], capture_output=True).stdout.decode("utf-8", "replace")
    files = subprocess.run(["git", "grep", "-I", "-h", "-e", ""], capture_output=True).stdout.decode("utf-8", "replace")
    return report(scan(history + files, secrets))


if __name__ == "__main__":
    sys.exit(main())
