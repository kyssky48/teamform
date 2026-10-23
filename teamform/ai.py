# 생성: 2026-10-21 22:24 (KST)
"""OpenRouter 호출, 모델마다 전체 대기 시간 제한, 응답 해석 (공고 2.5절, 4.3절)."""
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import TypeVar

import requests

from teamform.model import ROLES, Student

URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 16000

T = TypeVar("T")
ModelCaller = Callable[[str, str], str]


class AIError(Exception):
    pass


class AITimeout(AIError):
    pass


def with_deadline(fn: Callable[[], T], seconds: float) -> T:
    """fn을 따로 돈 스레드에서 실행하고, 부른 때부터 seconds가 지나면 기다리지 않고 AITimeout.
    응답이 천천히 흘러 들어와도 전체 시간으로 끊는다(3장 "AI 응답이 늦을 때"의 어려운 해결)."""
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        return future.result(timeout=seconds)
    except FutureTimeout:
        raise AITimeout(f"{seconds:g}초 안에 응답을 다 받지 못함") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _error_message(resp, api_key: str) -> str:
    """OpenRouter 오류 설명(예: 무료 제공 종료, 사용량 초과)을 짧게 붙임. 실패 기록과 README 근거용."""
    try:
        text = str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return ""
    text = " ".join(text.replace(api_key, "").split()) if api_key else " ".join(text.split())
    return f": {text[:140]}" if text else ""


def openrouter_caller(api_key: str) -> ModelCaller:
    def call(model: str, prompt: str) -> str:
        try:
            resp = requests.post(
                URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "reasoning": {"effort": "low"},
                    "max_tokens": MAX_TOKENS,
                },
                timeout=(10, 150),
            )
        except requests.RequestException as e:
            raise AIError(f"연결 오류({type(e).__name__})") from None
        if resp.status_code != 200:
            raise AIError(f"HTTP {resp.status_code}{_error_message(resp, api_key)}")
        try:
            body = resp.json()
            content = body["choices"][0]["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("응답 형식이 맞지 않음") from None
        if not content.strip():
            raise AIError("빈 응답")
        return content

    return call


def _describe(s: Student) -> str:
    subs = ", ".join(s.sub_roles) if s.sub_roles else "없음"
    return f"- 학번 {s.student_no}: 주 역할 {s.main_role}, 보조 역할 {subs}"


def build_prompt(teams: dict[int, list[Student]], unassigned: list[Student]) -> str:
    lines = [
        "당신은 팀 프로젝트의 팀 배정을 돕는다. 팀이 없는 학생을 팀에 넣는 배정안을 JSON으로만 답하라.",
        "",
        "규칙:",
        "1. 팀이 없는 학생은 빠짐없이 정확히 한 팀에 넣는다. 이미 팀에 있는 학생은 옮기지 않는다.",
        "2. 배정 뒤 모든 팀은 2~4명이어야 한다. 빈 팀이 있으면 안 된다.",
        "3. 한 팀 안에 주 역할이 같은 학생이 2명 이상이면 안 된다.",
        "4. 모든 팀에 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다.",
        "   주 역할이나 보조 역할로 맡을 수 있다. 한 학생이 두 역할을 동시에 맡을 수는 없다.",
        f"역할은 {', '.join(ROLES)} 6개다.",
        "",
        "지금의 팀:",
    ]
    for t in sorted(teams):
        lines.append(f"팀{t} (팀 번호 {t}, {len(teams[t])}명):")
        if teams[t]:
            lines.extend(_describe(m) for m in teams[t])
        else:
            lines.append("- (비어 있음)")
    lines += ["", "팀이 없는 학생:"]
    lines.extend(_describe(s) for s in unassigned)
    lines += [
        "",
        "답의 형식(다른 글 없이 이 JSON 하나만):",
        '{"assignments": [{"student_no": "학번", "team": 팀 번호}]}',
    ]
    return "\n".join(lines)


def parse_plan(text: str) -> dict[str, int]:
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "assignments" in obj:
            return _plan_from(obj["assignments"])
    raise AIError("응답에서 배정안 JSON을 찾지 못함")


def _plan_from(items) -> dict[str, int]:
    if not isinstance(items, list):
        raise AIError("assignments가 목록이 아님")
    plan: dict[str, int] = {}
    for item in items:
        try:
            no = str(item["student_no"]).strip()
            team = int(str(item["team"]).strip().removeprefix("팀"))
        except (KeyError, TypeError, ValueError):
            raise AIError("배정 항목의 형식이 맞지 않음") from None
        if no in plan:
            raise AIError(f"같은 학생이 두 번 배정됨: {no}")
        plan[no] = team
    return plan
