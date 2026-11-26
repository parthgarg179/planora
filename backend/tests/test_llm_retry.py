"""What happens when Gemini is busy: retry the main model, then the backup model, then the
starter plan, always within the time budget. Gemini is simulated; nothing calls Google."""
import json
from datetime import date

import pytest

from app import config
from app.services import llm

VALID_REPLY = json.dumps({
    "milestones": [{"id": "m1", "name": "Learn"}],
    "tasks": [{"id": "t1", "title": "Read the basics", "milestone_id": "m1", "estimated_hours": 2,
               "category": "learning", "complexity": "Low", "priority": "High",
               "dependencies": [], "optional": False, "subtasks": []}],
})


@pytest.fixture()
def gemini(monkeypatch):
    """Replace call_gemini with a script of replies; record which model was asked each time."""
    monkeypatch.setattr(config, "settings", config.Settings(
        gemini_api_key="test-key", gemini_model="main-model", gemini_fallback_model="backup-model",
        llm_timeout_seconds=35, llm_total_seconds=50, today_override=""))
    monkeypatch.setattr(llm, "settings", config.settings)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # no real waiting in tests
    calls, script = [], []

    def fake_call(prompt, model=None, timeout=None):
        calls.append(model)
        outcome = script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(llm, "call_gemini", fake_call)
    return calls, script


def breakdown():
    return llm.decompose("Learn Python", "", date(2026, 12, 31), date(2026, 12, 1), 2, 20, 40)


def test_main_model_works_first_time(gemini):
    calls, script = gemini
    script[:] = [VALID_REPLY]
    plan, used_fallback = breakdown()
    assert not used_fallback and calls == ["main-model"]
    assert plan.tasks[0].title == "Read the basics"


def test_busy_once_then_main_model_works(gemini):
    calls, script = gemini
    script[:] = [llm.LLMBusy("503"), VALID_REPLY]
    _, used_fallback = breakdown()
    assert not used_fallback and calls == ["main-model", "main-model"]


def test_main_busy_twice_then_backup_model_works(gemini):
    calls, script = gemini
    script[:] = [llm.LLMBusy("503"), llm.LLMBusy("429"), VALID_REPLY]
    _, used_fallback = breakdown()
    assert not used_fallback and calls == ["main-model", "main-model", "backup-model"]


def test_everything_busy_gives_starter_plan(gemini):
    calls, script = gemini
    script[:] = [llm.LLMBusy("503")] * 3
    plan, used_fallback = breakdown()
    assert used_fallback and calls == ["main-model", "main-model", "backup-model"]
    assert "generic template" in plan.checks[0]["label"]


def test_bad_key_gives_starter_plan_without_retrying(gemini):
    calls, script = gemini
    script[:] = [llm.LLMUnavailable("Gemini returned 400: API key not valid")]
    _, used_fallback = breakdown()
    assert used_fallback and calls == ["main-model"]


def test_no_retry_once_the_time_budget_is_used_up(gemini, monkeypatch):
    calls, script = gemini
    clock = iter([0, 0, 49, 49, 49, 49])  # start, first call, then the budget is nearly gone
    monkeypatch.setattr(llm.time, "monotonic", lambda: next(clock))
    script[:] = [llm.LLMBusy("503"), VALID_REPLY, VALID_REPLY]
    _, used_fallback = breakdown()
    assert used_fallback and calls == ["main-model"]
