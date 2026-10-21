# 생성: 2026-10-21 22:24 (KST)
"""비밀 값과 모델 목록. 비밀 값은 절대 출력하지 않고, 확인할 때는 "있음/없음"만 보여 준다."""
import os

from dotenv import load_dotenv

SECRET_NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")

# 1차, 2차, 3차 모델 (공고 4.3절). openrouter/free 라우터는 쓰지 않는다.
MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "minimax/minimax-m3.1-flash:free",
]

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def _from_streamlit(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # secrets.toml이 없으면 Streamlit이 예외를 냄
        return None
    return str(value) if value else None


def get_secret(name: str) -> str | None:
    return _from_streamlit(name) or os.environ.get(name) or None


def secret_status() -> dict[str, str]:
    return {name: "있음" if get_secret(name) else "없음" for name in SECRET_NAMES}
