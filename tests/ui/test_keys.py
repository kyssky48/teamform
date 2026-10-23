# 생성: 2026-10-21 22:32 (KST)
"""채점 프로그램을 흉내 내 공고 2.7절의 key로만 화면을 조작한다."""
import csv
import os
import re

import pytest

from tests.scenarios import EASY, HARD, MEDIUM
from tests.ui.conftest import ADMIN_PW, ROOT, click, key, login, result, settle


def roster(name: str) -> dict[int, tuple[str, str]]:
    with open(ROOT / "tests" / "data" / f"{name}.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {int(re.match(r"학생(\d+)", r["name"]).group(1)): (r["student_no"].strip(), r["name"].strip()) for r in rows}


def start_as_admin(new_page, name: str, teams: int):
    admin = new_page()
    login(admin, "admin", ADMIN_PW)
    key(admin, "admin_roster_file").locator("input[type=file]").set_input_files(str(ROOT / "tests" / "data" / f"{name}.csv"))
    settle(admin)
    count = key(admin, "admin_team_count").locator("input")
    count.fill(str(teams))
    count.press("Enter")
    settle(admin)
    click(admin, "admin_start")
    assert result(admin).startswith("승인"), result(admin)
    return admin


def test_easy_scenario_by_keys(new_page):
    name, teams, steps = EASY
    people = roster(name)
    admin = start_as_admin(new_page, name, teams)
    pages = {}

    def page_of(n):
        if n not in pages:
            pages[n] = new_page()
            login(pages[n], people[n][0], "1234")
            assert people[n][1] in key(pages[n], "whoami").inner_text()
        return pages[n]

    for action, args, expected in steps:
        if action == "apply":
            p = page_of(args[0])
            click(p, f"apply_{args[1]}")
        elif action in ("yes", "no"):
            p = page_of(args[0])
            k = f"vote_{action}_{people[args[1]][0]}"
            key(p, k).wait_for(timeout=7000)  # 다른 사람의 지원이 자동으로 나타나야 함
            click(p, k)
        elif action == "close":
            p = admin
            click(admin, "admin_close")
        elif action == "assign_confirm":
            click(admin, "admin_assign", timeout_s=420)  # 실제 AI는 모델마다 최대 120초
            status = key(admin, "assign_status").inner_text()
            assert "1차 모델" in status, status  # 몇 차 모델을 기다리는지 보여 줌
            # 로컬 시험은 가짜 AI(늘 실패), 배포 앱은 실제 AI라 둘 중 하나
            assert re.match(r"^승인: (3차까지 실패해 앱이 배정안을 만듦|[123]차 모델\(.+\)의 배정안을 받음)$", result(admin)), result(admin)
            click(admin, "admin_confirm")
            assert result(admin) == "승인: 배정을 확정함", result(admin)
            continue
        else:
            continue
        assert result(p).split(":")[0].strip() == expected, f"{action}{args}: {result(p)}"

    fresh = new_page()
    login(fresh, people[8][0], "1234")
    text = " ".join(key(fresh, f"team_{t}").inner_text() for t in range(1, teams + 1))
    for no, nm in people.values():
        assert nm in text


def test_other_browser_sees_change(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    a, b = new_page(), new_page()
    login(a, people[1][0], "1234")
    login(b, people[4][0], "1234")
    click(a, "apply_1")
    click(b, "apply_1")
    assert result(b).startswith("대기")
    key(a, f"vote_yes_{people[4][0]}").wait_for(timeout=7000)


def test_disabled_apply_after_pending(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    a, b = new_page(), new_page()
    login(a, people[1][0], "1234")
    login(b, people[4][0], "1234")
    click(a, "apply_1")
    click(b, "apply_1")
    for t in (1, 2, 3):
        assert key(b, f"apply_{t}").locator("button").is_disabled()
        assert key(a, f"apply_{t}").locator("button").is_disabled()


def test_vote_buttons_disabled_after_vote(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    a, b, c = new_page(), new_page(), new_page()
    login(a, people[1][0], "1234")
    login(b, people[4][0], "1234")
    login(c, people[7][0], "1234")
    click(a, "apply_1")
    click(b, "apply_1")
    key(a, f"vote_yes_{people[4][0]}").wait_for(timeout=7000)
    click(a, f"vote_yes_{people[4][0]}")
    click(c, "apply_1")
    key(a, f"vote_yes_{people[7][0]}").wait_for(timeout=7000)
    click(a, f"vote_yes_{people[7][0]}")
    assert result(a).startswith("대기")
    assert key(a, f"vote_yes_{people[7][0]}").locator("button").is_disabled()
    assert key(a, f"vote_no_{people[7][0]}").locator("button").is_disabled()
    assert "내 투표: 찬성" in a.content()


def test_wrong_password_not_logged_in(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    p = new_page()
    key(p, "login_student_no").locator("input").fill(people[1][0])
    key(p, "login_password").locator("input").fill("9999")
    click(p, "login_submit")
    assert result(p).startswith("막힘")
    assert key(p, "whoami").count() == 0


def test_restart_logs_out_removed_student(new_page):
    people = roster("쉬움")
    admin = start_as_admin(new_page, "쉬움", 3)
    s = new_page()
    login(s, people[1][0], "1234")
    key(admin, "admin_roster_file").locator("input[type=file]").set_input_files(str(ROOT / "tests" / "data" / "중간.csv"))
    settle(admin)
    click(admin, "admin_start")
    assert result(admin).startswith("승인")
    key(s, "login_student_no").wait_for(timeout=7000)  # 자동 갱신 때 로그인 화면으로


def test_student_has_no_admin_controls(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    s = new_page()
    login(s, people[1][0], "1234")
    for k in ("admin_roster_file", "admin_start", "admin_close", "admin_assign", "admin_confirm"):
        assert key(s, k).count() == 0


def test_secrets_not_rendered(new_page):
    admin = start_as_admin(new_page, "쉬움", 3)
    html = admin.content()
    for bad in ("sk-or-", "postgres://", "postgresql://", ADMIN_PW):
        assert bad not in html


def test_vote_after_another_member_rejected(new_page):
    people = roster("쉬움")
    start_as_admin(new_page, "쉬움", 3)
    a, b, c = new_page(), new_page(), new_page()
    login(a, people[1][0], "1234")
    login(b, people[4][0], "1234")
    login(c, people[7][0], "1234")
    click(a, "apply_1")
    click(b, "apply_1")
    key(a, f"vote_yes_{people[4][0]}").wait_for(timeout=7000)
    click(a, f"vote_yes_{people[4][0]}")
    click(c, "apply_1")
    key(b, f"vote_no_{people[7][0]}").wait_for(timeout=7000)
    click(b, f"vote_no_{people[7][0]}")
    assert result(b).startswith("거절")
    key(a, f"vote_yes_{people[7][0]}").wait_for(timeout=7000)  # 거부가 먼저 나와도 단추가 남아 있음
    click(a, f"vote_yes_{people[7][0]}")
    assert result(a).startswith("거절"), result(a)


@pytest.mark.parametrize("scenario", [MEDIUM, HARD], ids=["medium", "hard"])
def test_practice_scenario_by_keys(new_page, scenario):
    """중간·어려움 시나리오를 key만 써서 끝까지 실행. TEAMFORM_SHOTS가 있으면 단계마다 화면을 저장."""
    name, teams, steps = scenario
    people = roster(name)
    shots = os.environ.get("TEAMFORM_SHOTS")
    admin = start_as_admin(new_page, name, teams)
    pages = {}

    def shot(p, label):
        if shots:
            p.page.screenshot(path=os.path.join(shots, f"{name}_{label}.png"), full_page=True)

    def page_of(n):
        if n not in pages:
            pages[n] = new_page()
            login(pages[n], people[n][0], "1234")
        return pages[n]

    for i, (action, args, expected) in enumerate(steps, 1):
        got = None
        if action == "apply":
            p = page_of(args[0])
            button = key(p, f"apply_{args[1]}").locator("button")
            if button.count() == 0 or button.is_disabled():  # 공고 2.7절: 없거나 비활성이면 막힘으로 봄
                got = "막힘(단추 비활성)"
            else:
                click(p, f"apply_{args[1]}")
        elif action in ("yes", "no"):
            p = page_of(args[0])
            k = f"vote_{action}_{people[args[1]][0]}"
            key(p, k).wait_for(timeout=7000)
            click(p, k)
        elif action == "close":
            p = admin
            click(admin, "admin_close")
        elif action == "unassigned_has":
            text = key(admin, "unassigned").inner_text()
            for n in args:
                assert people[n][1] in text, (i, text)
            shot(admin, f"{i:02d}_unassigned")
            continue
        elif action == "assign_confirm":
            key(admin, "admin_assign").locator("button").click()
            admin.wait_for_timeout(5000)
            shot(admin, f"{i:02d}_assign_waiting")
            settle(admin, 420)
            shot(admin, f"{i:02d}_assign_done")
            assert re.match(r"^승인: (3차까지 실패해 앱이 배정안을 만듦|[123]차 모델\(.+\)의 배정안을 받음)$", result(admin)), result(admin)
            click(admin, "admin_confirm")
            assert result(admin) == "승인: 배정을 확정함", result(admin)
            admin.locator("summary:has-text('AI 호출 기록')").click()
            admin.wait_for_timeout(1500)
            shot(admin, f"{i:02d}_confirmed_ai_logs")
            continue
        got = got or result(p)
        shot(p, f"{i:02d}_{action}_{'_'.join(map(str, args))}")
        assert re.split(r"[:(]", got)[0].strip() == expected, f"{i}번째 {action}{args}: {got}"

    fresh = new_page()
    login(fresh, people[1][0], "1234")
    for t in range(1, teams + 1):
        assert key(fresh, f"team_{t}").inner_text()


def test_assign_again_shows_only_new_progress(new_page):
    admin = start_as_admin(new_page, "쉬움", 3)
    click(admin, "admin_close")
    click(admin, "admin_assign", timeout_s=420)
    click(admin, "admin_assign", timeout_s=420)  # 다시 눌러도 이전 진행 안내와 섞이지 않아야 함
    status = key(admin, "assign_status").inner_text()
    assert status.count("1차 모델(") == 1, status
