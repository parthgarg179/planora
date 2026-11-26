"""What happens when Gemini is busy: Planora cycles through the main model and its backups, with
short growing pauses, until about 45 of its 50 seconds are used, and only then uses the starter
plan. Gemini and the clock are simulated; nothing calls Google and nothing really waits."""
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
BUSY = llm.LLMBusy("503 high demand")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture()
def gemini(monkeypatch):
    """call_gemini follows `script` (then keeps saying busy); each call takes `call_seconds`."""
    monkeypatch.setattr(config, "settings", config.Settings(
        gemini_api_key="test-key", gemini_model="main", gemini_fallback_models=["lite-a", "lite-b"],
        llm_timeout_seconds=35, llm_total_seconds=50, today_override=""))
    monkeypatch.setattr(llm, "settings", config.settings)
    clock = FakeClock()
    monkeypatch.setattr(llm.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(llm.time, "sleep", clock.sleep)
    state = {"calls": [], "script": [], "call_seconds": 2.0}

    def fake_call(prompt, model=None, timeout=None):
        state["calls"].append(model)
        clock.now += state["call_seconds"]
        outcome = state["script"].pop(0) if state["script"] else BUSY
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(llm, "call_gemini", fake_call)
    state["clock"] = clock
    return state


def breakdown():
    return llm.decompose("Learn Python", "", date(2026, 12, 31), date(2026, 12, 1), 2, 20, 40)


def test_main_model_works_first_time(gemini):
    gemini["script"] = [VALID_REPLY]
    plan, used_fallback = breakdown()
    assert not used_fallback and gemini["calls"] == ["main"]
    assert plan.tasks[0].title == "Read the basics"


def test_main_busy_then_first_backup_works(gemini):
    gemini["script"] = [BUSY, VALID_REPLY]
    _, used_fallback = breakdown()
    assert not used_fallback and gemini["calls"] == ["main", "lite-a"]


def test_everything_busy_in_round_one_then_works_in_round_two(gemini):
    gemini["script"] = [BUSY, BUSY, BUSY, VALID_REPLY]
    _, used_fallback = breakdown()
    assert not used_fallback and gemini["calls"] == ["main", "lite-a", "lite-b", "main"]


def test_keeps_trying_until_about_45_seconds_then_starter_plan(gemini):
    plan, used_fallback = breakdown()  # every call says busy
    assert used_fallback and "generic template" in plan.checks[0]["label"]
    assert len(gemini["calls"]) > 6              # several rounds, not one pass
    assert 40 <= gemini["clock"].now <= 50       # used the budget, but stayed inside it


def test_slow_busy_answers_still_stop_inside_the_budget(gemini):
    gemini["call_seconds"] = 12.0  # like gemini-3.5-flash answering "busy" after 12 s
    _, used_fallback = breakdown()
    assert used_fallback and gemini["clock"].now <= 50


def test_bad_key_gives_starter_plan_without_retrying(gemini):
    gemini["script"] = [llm.LLMUnavailable("Gemini returned 400: API key not valid")]
    _, used_fallback = breakdown()
    assert used_fallback and gemini["calls"] == ["main"]


def test_unusable_reply_moves_on_to_the_next_model(gemini):
    gemini["script"] = ["not json", "still not json", VALID_REPLY]  # main fails twice, lite-a works
    _, used_fallback = breakdown()
    assert not used_fallback and gemini["calls"] == ["main", "main", "lite-a"]
