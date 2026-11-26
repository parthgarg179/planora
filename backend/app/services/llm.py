"""Goal breakdown with Google Gemini, plus a clearly-labelled fallback plan.

The AI only decides WHAT work is needed. It never assigns dates; the scheduler does that.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from ..config import settings
from .validation import CleanPlan, ValidationFailed, extract_json, validate_plan

log = logging.getLogger("planora.llm")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ATTEMPTS = 2           # tries per model when the reply isn't usable JSON
BUSY_PAUSE_SECONDS = 2  # wait before asking an overloaded model again


class LLMUnavailable(Exception):
    """Gemini can't help (no key, bad key, network down, blocked reply)."""


class LLMBusy(LLMUnavailable):
    """Gemini is temporarily overloaded or rate-limited (503 / 429) or too slow: worth another try."""


def build_prompt(title: str, description: str, deadline: date, today: date,
                 daily_hours: float, working_days: int, capacity_hours: float) -> str:
    return f"""You are a planning assistant. Break the user's goal into milestones and tasks.

Goal: {title}
{f"Details: {description}" if description else ""}
Time available: {daily_hours:g} hours per working day, {working_days} working days until {deadline.isoformat()} (today is {today.isoformat()}), about {capacity_hours:g} hours in total.

Rules:
- 3 to 6 milestones, 8 to 25 tasks in total.
- Each task takes between 0.5 and 8 hours. Split anything bigger.
- estimated_hours is an honest estimate for a typical person. Do not shrink it to fit the time available.
- Mark nice-to-have tasks "optional": true. Core tasks are false.
- dependencies lists the ids of tasks that must be finished first. Only use ids that exist. No cycles.
- priority is one of High, Normal, Low. complexity is one of Low, Medium, High.
- category is one of learning, practice, project, planning, testing, revision, setup, research, writing, other.
- Do NOT include dates or a schedule.

Reply with JSON only, in exactly this shape:
{{
  "milestones": [{{"id": "m1", "name": "Milestone name"}}],
  "tasks": [{{
    "id": "t1", "title": "Short task title", "description": "One sentence.",
    "milestone_id": "m1", "category": "learning", "complexity": "Medium",
    "estimated_hours": 2, "priority": "High", "dependencies": [],
    "optional": false, "subtasks": ["Step one", "Step two"]
  }}]
}}"""


def call_gemini(prompt: str, model: str | None = None, timeout: float | None = None) -> str:
    if not settings.gemini_api_key:
        raise LLMUnavailable("GEMINI_API_KEY is not set in backend/.env")
    import httpx  # imported here so the rest of the app (and tests) don't need it
    model = model or settings.gemini_model
    timeout = timeout or settings.llm_timeout_seconds

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
    }
    try:
        res = httpx.post(GEMINI_URL.format(model=model), json=body,
                         headers={"x-goog-api-key": settings.gemini_api_key}, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise LLMBusy(f"{model} took longer than {timeout:.0f}s") from exc
    except httpx.HTTPError as exc:
        raise LLMUnavailable(f"Couldn't reach Gemini: {exc}") from exc
    if res.status_code in (429, 503):
        raise LLMBusy(f"{model} returned {res.status_code}: {res.text[:200]}")
    if res.status_code != 200:
        raise LLMUnavailable(f"Gemini returned {res.status_code}: {res.text[:300]}")
    try:
        parts = res.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable("Gemini's reply had no text (it may have been blocked).") from exc


def _ask(model: str, prompt: str, deadline_at: float) -> CleanPlan:
    """One model: up to ATTEMPTS tries when its reply isn't usable JSON, within the overall time budget."""
    last: ValidationFailed | None = None
    for attempt in range(ATTEMPTS):
        remaining = deadline_at - time.monotonic()
        if remaining < 3:
            raise LLMBusy("no time left for another Gemini call")
        retry_note = "\n\nYour previous reply was not usable. Reply with valid JSON only."
        text = call_gemini(prompt if attempt == 0 else prompt + retry_note,
                           model=model, timeout=min(settings.llm_timeout_seconds, remaining))
        try:
            return validate_plan(extract_json(text))
        except ValidationFailed as exc:
            last = exc
    raise last


def decompose(title: str, description: str, deadline: date, today: date,
              daily_hours: float, working_days: int, capacity_hours: float) -> tuple[CleanPlan, bool]:
    """Returns (plan, used_fallback)."""
    prompt = build_prompt(title, description, deadline, today, daily_hours, working_days, capacity_hours)
    deadline_at = time.monotonic() + settings.llm_total_seconds
    # When the main model is busy: ask it once more after a short pause, then the backup model.
    models = [settings.gemini_model, settings.gemini_model]
    if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
        models.append(settings.gemini_fallback_model)

    last_error = "unknown error"
    for i, model in enumerate(models):
        if i > 0 and model == models[i - 1]:
            time.sleep(BUSY_PAUSE_SECONDS)
        try:
            plan = _ask(model, prompt, deadline_at)
            log.info("AI breakdown made by %s", model)
            return plan, False
        except LLMBusy as exc:
            last_error = str(exc)
            log.info("Gemini busy (%s); trying the next option", exc)
            if time.monotonic() >= deadline_at - 3:
                break  # no time left within the request limit
        except LLMUnavailable as exc:
            last_error = str(exc)
            break  # no key, bad key, network down: retrying won't help
        except ValidationFailed as exc:
            last_error = str(exc)
            break  # unusable JSON twice from this model; the starter plan is the safer choice
    log.warning("AI breakdown failed (%s); using the fallback plan", last_error)
    plan = fallback_plan(title, capacity_hours)
    plan.checks.insert(0, {"ok": True, "label": "AI unavailable, so a generic template plan was used. Edit or regenerate it later."})
    return plan, True


# ---------------------------------------------------------------- fallback ----
_FALLBACK = [  # (milestone, title, share of total time, priority, optional, subtasks)
    ("Plan", "Define what “done” looks like", 0.03, "High", False, ["Write the end result in one sentence", "List what's in and out of scope"]),
    ("Plan", "Research resources and approach", 0.07, "High", False, ["Find 2–3 good resources", "Pick one to follow"]),
    ("Learn", "Learn the fundamentals (part 1)", 0.12, "High", False, ["Study", "Take notes"]),
    ("Learn", "Learn the fundamentals (part 2)", 0.12, "High", False, ["Study", "Take notes"]),
    ("Practice", "Practice with small exercises", 0.12, "Normal", False, ["Do the exercises", "Check answers"]),
    ("Build", "Start the main piece of work", 0.16, "High", False, ["Set up", "First working version"]),
    ("Build", "Finish the main piece of work", 0.16, "High", False, ["Complete the remaining parts"]),
    ("Build", "Extra polish", 0.06, "Low", True, ["Small improvements"]),
    ("Review", "Review and fix gaps", 0.10, "Normal", False, ["Check against the goal", "Fix what's missing"]),
    ("Review", "Wrap up and reflect", 0.06, "Normal", False, ["Summarise what you learned"]),
]


def fallback_plan(goal_title: str, capacity_hours: float) -> CleanPlan:
    total = min(max(capacity_hours * 0.85, 5.0), 80.0)
    names = list(dict.fromkeys(m for m, *_ in _FALLBACK))
    data = {
        "milestones": [{"id": f"m{i + 1}", "name": n} for i, n in enumerate(names)],
        "tasks": [],
    }
    for i, (ms, title, share, prio, optional, subs) in enumerate(_FALLBACK):
        deps = [f"t{i}"] if i > 0 else []
        if title == "Review and fix gaps":
            deps = ["t7"]  # doesn't wait for the optional polish task
        data["tasks"].append({
            "id": f"t{i + 1}", "title": title, "milestone_id": f"m{names.index(ms) + 1}",
            "estimated_hours": max(0.5, round(total * share * 4) / 4), "priority": prio,
            "optional": optional, "dependencies": deps, "subtasks": subs,
            "category": {"Plan": "planning", "Learn": "learning", "Practice": "practice", "Build": "project", "Review": "revision"}[ms],
            "complexity": "Medium",
        })
    return validate_plan(data)
