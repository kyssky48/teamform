# 생성: 2026-10-21 22:32 (KST)
"""화면 시험: 앱을 메모리 저장소로 띄우고, 채점 프로그램처럼 Streamlit key로 화면을 조작한다.
TEAMFORM_URL이 있으면 그 주소(배포한 앱)를 쓴다. 이때 관리자 비밀번호는 TEAMFORM_ADMIN_PW."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW = os.environ.get("TEAMFORM_ADMIN_PW", "ui-test-admin")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def app_url():
    if os.environ.get("TEAMFORM_URL"):
        yield os.environ["TEAMFORM_URL"].rstrip("/")
        return
    port = _free_port()
    env = dict(os.environ, TEAMFORM_STORE="memory", TEAMFORM_FAKE_AI="fail", ADMIN_PASSWORD=ADMIN_PW)
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), 1).close()
            break
        except OSError:
            time.sleep(0.3)
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def new_page(browser, app_url):
    """학생마다 새 브라우저 문맥(쿠키, 세션 따로)을 연다."""
    contexts = []

    def _open() -> "AppView":
        ctx = browser.new_context()
        contexts.append(ctx)
        page = ctx.new_page()
        for attempt in range(3):  # Streamlit Cloud가 가끔 앱 iframe을 숨긴 채 멈춤: 다시 열어 봄
            try:
                page.goto(app_url, timeout=60000)
                frame = page.main_frame
                if "streamlit.app" in app_url:  # Streamlit Cloud는 앱을 iframe 안에 띄움
                    frame = page.wait_for_selector('iframe[title="streamlitApp"]', timeout=60000).content_frame()
                view = AppView(page, frame)
                view.locator(".st-key-login_student_no input").wait_for(timeout=60000)
                return view
            except PlaywrightTimeout:
                if attempt == 2:
                    raise

    yield _open
    for c in contexts:
        c.close()


class AppView:
    """앱이 그려진 frame(로컬은 페이지 자체, 배포 앱은 iframe)을 페이지처럼 다루게 함."""

    def __init__(self, page: Page, frame):
        self.page, self.frame = page, frame

    def locator(self, selector: str):
        return self.frame.locator(selector)

    def wait_for_selector(self, selector: str, **kw):
        return self.frame.wait_for_selector(selector, **kw)

    def wait_for_timeout(self, ms: float) -> None:
        self.page.wait_for_timeout(ms)

    def content(self) -> str:
        return self.frame.content()


def settle(page: Page, timeout_s: float = 60) -> None:
    """Streamlit이 다시 그리기를 마칠 때까지 기다림(stApp의 data-test-script-state)."""
    try:
        page.wait_for_selector('[data-testid="stApp"][data-test-script-state="running"]', timeout=2000)
    except PlaywrightTimeout:
        pass  # 이미 끝났거나 아주 빨리 끝남
    # 3초 자동 갱신(fragment)의 실행 끝을 클릭 실행의 끝으로 잘못 보지 않도록, 0.8초 동안 조용할 때까지 기다림
    quiet, deadline = 0, time.time() + timeout_s
    while quiet < 8 and time.time() < deadline:
        state = page.locator('[data-testid="stApp"]').get_attribute("data-test-script-state")
        quiet = 0 if state == "running" else quiet + 1
        page.wait_for_timeout(100)


def key(page: Page, k: str):
    return page.locator(f".st-key-{k}")


def click(page: Page, k: str, timeout_s: float = 60) -> None:
    key(page, k).locator("button").click()
    settle(page, timeout_s)


def result(page: Page) -> str:
    return key(page, "result").inner_text().strip()


def login(page: Page, student_no: str, password: str) -> None:
    key(page, "login_student_no").locator("input").fill(student_no)
    key(page, "login_password").locator("input").fill(password)
    click(page, "login_submit")
    key(page, "whoami").wait_for(timeout=10000)
