# 생성: 2026-10-21 22:23 (KST)
import time

import pytest

from teamform import ai, config
from tests.helpers import S


def test_with_deadline_cuts_slow_call():
    t0 = time.perf_counter()
    with pytest.raises(ai.AITimeout):
        ai.with_deadline(lambda: time.sleep(1), 0.2)
    assert time.perf_counter() - t0 < 0.5


def test_with_deadline_returns_and_raises():
    assert ai.with_deadline(lambda: 7, 1) == 7
    with pytest.raises(ai.AIError):
        ai.with_deadline(lambda: (_ for _ in ()).throw(ai.AIError("x")), 1)


def test_parse_plan_plain_and_fenced():
    assert ai.parse_plan('{"assignments":[{"student_no":"2026107","team":1}]}') == {"2026107": 1}
    text = '생각: ...\n```json\n{"assignments": [{"student_no": 2026108, "team": "2"}]}\n```\n끝'
    assert ai.parse_plan(text) == {"2026108": 2}


@pytest.mark.parametrize("text", ["", "   ", "배정할 수 없습니다", '{"foo": 1}', '{"assignments": "x"}',
                                  '{"assignments":[{"student_no":"1"}]}'])
def test_parse_plan_bad(text):
    with pytest.raises(ai.AIError):
        ai.parse_plan(text)


def test_parse_plan_duplicate_student():
    with pytest.raises(ai.AIError, match="두 번"):
        ai.parse_plan('{"assignments":[{"student_no":"1","team":1},{"student_no":"1","team":2}]}')


def test_prompt_mentions_rules_and_students():
    a, b = S("PL", no="2026001"), S("TT", "WP", no="2026002")
    p = ai.build_prompt({1: [a], 2: []}, [b])
    for word in ["2026001", "2026002", "기획자", "웹 프로그래머", "2~4명", "assignments", "팀1", "팀2", "테스터"]:
        assert word in p
    assert "sk-or-" not in p


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_openrouter_caller_sends_options(monkeypatch):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, json=json)
        return FakeResp(200, {"choices": [{"message": {"content": "답"}}]})

    monkeypatch.setattr(ai.requests, "post", fake_post)
    assert ai.openrouter_caller("sk-or-v1-test")("m:free", "p") == "답"
    assert sent["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert sent["json"]["reasoning"] == {"effort": "low"}
    assert sent["json"]["max_tokens"] >= 8000
    assert sent["json"]["model"] == "m:free"


def test_openrouter_caller_empty_content(monkeypatch):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": ""}}]}))
    with pytest.raises(ai.AIError, match="빈 응답"):
        ai.openrouter_caller("k")("m", "p")


def test_openrouter_caller_429(monkeypatch):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: FakeResp(429, {"error": {"message": "rate"}}))
    with pytest.raises(ai.AIError, match="429"):
        ai.openrouter_caller("k")("m", "p")


def test_openrouter_caller_error_body(monkeypatch):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: FakeResp(200, {"error": {"code": 502}}))
    with pytest.raises(ai.AIError):
        ai.openrouter_caller("k")("m", "p")


def test_models_are_three_distinct_free_models():
    assert len(config.MODELS) == 3 and len(set(config.MODELS)) == 3
    assert all(m.endswith(":free") for m in config.MODELS)
    assert "openrouter/free" not in config.MODELS


def test_secret_status_never_returns_values(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-abc")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(config, "_from_streamlit", lambda name: None)
    status = config.secret_status()
    assert status["OPENROUTER_API_KEY"] == "있음"
    assert "sk-or-v1-abc" not in repr(status)
    assert config.get_secret("OPENROUTER_API_KEY") == "sk-or-v1-abc"
