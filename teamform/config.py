# 생성: 2026-10-21 22:24 (KST)
"""비밀 값과 모델 목록. 비밀 값은 절대 출력하지 않고, 확인할 때는 "있음/없음"만 보여 준다."""
import os
from urllib.parse import quote, unquote

from dotenv import load_dotenv

SECRET_NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")

# 1차, 2차, 3차 모델 (공고 4.3절). openrouter/free 라우터는 쓰지 않는다.
# 무료 모델은 수시로 없어지거나 바뀜(10/22 minimax 무료 종료). 10/23 실제 호출로 응답을 확인한 모델로 고름.
MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
    "google/gemma-4-31b-it:free",
]

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def _from_streamlit(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # secrets.toml이 없으면 Streamlit이 예외를 냄
        return None
    return str(value) if value else None


def normalize_db_url(url: str) -> str:
    """비밀번호에 @ : / # 같은 글자가 있어도 연결되도록 비밀번호 부분만 URL 인코딩한다.
    마지막 @ 뒤를 호스트로 본다. 이미 %40처럼 바꿔 둔 비밀번호는 그대로 둔다."""
    url = url.strip()
    scheme, sep, rest = url.partition("://")
    if not sep or "@" not in rest:
        return url
    userinfo, host = rest.rsplit("@", 1)
    user, colon, password = userinfo.partition(":")
    if not colon:
        return url
    return f"{scheme}://{user}:{quote(unquote(password), safe='')}@{host}"


def get_secret(name: str) -> str | None:
    value = _from_streamlit(name) or os.environ.get(name) or None
    if value and name == "DATABASE_URL":
        value = normalize_db_url(value)
    return value


def secret_status() -> dict[str, str]:
    return {name: "있음" if get_secret(name) else "없음" for name in SECRET_NAMES}
