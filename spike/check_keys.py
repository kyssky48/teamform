# 생성: 2026-10-21 22:13 (KST)
import subprocess, sys, time, re
from playwright.sync_api import sync_playwright, expect

proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "spike/fragment_spike.py", "--server.port", "8599", "--server.headless", "true"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(6)
    with sync_playwright() as p:
        b = p.chromium.launch()
        a = b.new_context().new_page(); a.goto("http://localhost:8599/?me=A")
        c = b.new_context().new_page(); c.goto("http://localhost:8599/?me=B")
        a.locator(".st-key-login_student_no input").fill("2026101"); print("text_input key 찾음")
        c.locator(".st-key-apply_1 button").click()
        expect(c.locator(".st-key-result")).to_contain_text(re.compile("^대기"), timeout=7000); print("result 갱신(누른 사람 화면) OK")
        t = time.time()
        a.locator(".st-key-vote_yes_B button").wait_for(timeout=7000); print(f"다른 사람 화면에 vote_yes_B 나타남 {time.time()-t:.1f}s")
        a.locator(".st-key-vote_yes_B button").click()
        expect(a.locator(".st-key-result")).to_contain_text(re.compile("^승인"), timeout=7000); print("찬성 결과 OK")
        print("result text:", repr(a.locator(".st-key-result").inner_text()))
        b.close()
finally:
    proc.terminate()
