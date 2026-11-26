"""Check and repair the AI's goal breakdown before anything is saved or scheduled.

Pure Python (no database). Returns clean milestones/tasks plus a list of checks
that the frontend shows to the user.

Expected AI output:
{
  "milestones": [{"id": "m1", "name": "..."}],
  "tasks": [{"id": "t1", "title": "...", "description": "...", "milestone_id": "m1",
             "category": "learning", "complexity": "Medium", "estimated_hours": 2.5,
             "priority": "High", "dependencies": ["t0"], "optional": false,
             "subtasks": ["...", "..."]}]
}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

COLORS = ["#6b86e8", "#f2c94c", "#5ad19a", "#e58bb6", "#9b8cf5", "#5cc3d9", "#f29b6b"]
CATEGORIES = {"learning", "practice", "project", "planning", "testing", "revision", "setup", "research", "writing", "other"}
DEFAULT_HOURS = {"Low": 1.0, "Medium": 2.0, "High": 4.0}
MIN_HOURS, MAX_HOURS = 0.25, 40.0
MAX_TASKS = 60


class ValidationFailed(Exception):
    """The output can't be repaired into a usable plan."""


@dataclass
class CleanMilestone:
    key: str
    name: str
    color: str


@dataclass
class CleanTask:
    key: str
    title: str
    description: str
    milestone_key: str
    category: str
    complexity: str
    hours: float
    priority: str
    dependencies: list[str]
    optional: bool
    subtasks: list[str]


@dataclass
class CleanPlan:
    milestones: list[CleanMilestone]
    tasks: list[CleanTask]
    checks: list[dict] = field(default_factory=list)  # [{"ok": bool, "label": str}]


def extract_json(text: str) -> dict:
    """Parse JSON from a model reply, tolerating ```json fences or text around it."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValidationFailed("The AI reply wasn't valid JSON.")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationFailed("The AI reply wasn't valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValidationFailed("The AI reply wasn't a JSON object.")
    return data


def _norm(value, allowed: dict[str, str], default: str) -> str:
    return allowed.get(str(value or "").strip().lower(), default)


def _hours(value) -> float | None:
    try:
        h = float(value)
    except (TypeError, ValueError):
        return None
    if h != h or h <= 0:  # NaN or non-positive
        return None
    return round(min(max(h, MIN_HOURS), MAX_HOURS) * 4) / 4


def validate_plan(data: dict) -> CleanPlan:
    checks: list[dict] = []
    raw_ms = data.get("milestones") if isinstance(data.get("milestones"), list) else []
    raw_tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else None
    if not raw_tasks:
        raise ValidationFailed("The AI reply had no tasks.")
    checks.append({"ok": True, "label": "Valid JSON matching the schema"})

    # ---- milestones ----
    milestones: list[CleanMilestone] = []
    seen_ms: set[str] = set()
    for i, m in enumerate(raw_ms):
        if not isinstance(m, dict):
            continue
        key = str(m.get("id") or f"m{i + 1}").strip()
        name = str(m.get("name") or m.get("title") or "").strip()[:200]
        if not name or key in seen_ms:
            continue
        seen_ms.add(key)
        milestones.append(CleanMilestone(key, name, COLORS[len(milestones) % len(COLORS)]))

    # ---- tasks ----
    priorities = {"high": "High", "normal": "Normal", "medium": "Normal", "low": "Low"}
    complexities = {"low": "Low", "easy": "Low", "medium": "Medium", "moderate": "Medium", "high": "High", "hard": "High"}
    tasks: list[CleanTask] = []
    keys: set[str] = set()
    fixed_hours = renamed = dropped = 0
    for i, t in enumerate(raw_tasks[:MAX_TASKS]):
        if not isinstance(t, dict):
            dropped += 1
            continue
        title = str(t.get("title") or t.get("name") or "").strip()[:300]
        if not title:
            dropped += 1
            continue
        key = str(t.get("id") or f"t{i + 1}").strip()
        if key in keys:
            key, renamed = f"{key}_{i + 1}", renamed + 1
        keys.add(key)
        complexity = _norm(t.get("complexity"), complexities, "Medium")
        hours = _hours(t.get("estimated_hours", t.get("hours")))
        if hours is None:
            hours, fixed_hours = DEFAULT_HOURS[complexity], fixed_hours + 1
        category = str(t.get("category") or "other").strip().lower()
        deps = t.get("dependencies") if isinstance(t.get("dependencies"), list) else []
        subtasks = [str(s.get("title") if isinstance(s, dict) else s).strip()[:300]
                    for s in (t.get("subtasks") if isinstance(t.get("subtasks"), list) else [])]
        tasks.append(CleanTask(
            key=key, title=title, description=str(t.get("description") or "").strip(),
            milestone_key=str(t.get("milestone_id") or "").strip(),
            category=category if category in CATEGORIES else "other", complexity=complexity, hours=hours,
            priority=_norm(t.get("priority"), priorities, "Normal"),
            dependencies=[str(d).strip() for d in deps if str(d).strip()],
            optional=bool(t.get("optional", False)), subtasks=[s for s in subtasks if s][:12],
        ))
    if not tasks:
        raise ValidationFailed("None of the AI's tasks had a title.")

    # tasks pointing at unknown milestones go into a "General" milestone
    ms_keys = {m.key for m in milestones}
    orphans = [t for t in tasks if t.milestone_key not in ms_keys]
    if orphans:
        general = CleanMilestone("general", "General", COLORS[len(milestones) % len(COLORS)])
        milestones.append(general)
        for t in orphans:
            t.milestone_key = general.key
    milestones = [m for m in milestones if any(t.milestone_key == m.key for t in tasks)]

    count_label = f"{len(tasks)} tasks across {len(milestones)} milestone{'s' if len(milestones) != 1 else ''}"
    if dropped:
        count_label += f" ({dropped} unusable task{'s' if dropped != 1 else ''} removed)"
    checks.append({"ok": True, "label": count_label})

    # ---- dependencies ----
    bad_refs = 0
    for t in tasks:
        clean = []
        for d in t.dependencies:
            if d in keys and d != t.key and d not in clean:
                clean.append(d)
            else:
                bad_refs += 1
        t.dependencies = clean
    checks.append({"ok": True, "label": "Every dependency exists" if not bad_refs
                   else f"Removed {bad_refs} invalid dependency reference{'s' if bad_refs != 1 else ''}"})

    broken = break_cycles(tasks)
    checks.append({"ok": True, "label": "No dependency cycles" if not broken
                   else f"Broke {broken} dependency cycle{'s' if broken != 1 else ''}"})

    checks.append({"ok": True, "label": "All durations are positive" if not fixed_hours
                   else f"Gave {fixed_hours} task{'s' if fixed_hours != 1 else ''} a default duration"})
    if renamed:
        checks.append({"ok": True, "label": f"Fixed {renamed} duplicate task id{'s' if renamed != 1 else ''}"})
    return CleanPlan(milestones, tasks, checks)


def break_cycles(tasks: list[CleanTask]) -> int:
    """Remove dependency edges that close a cycle (depth-first search). Returns how many were removed."""
    by_key = {t.key: t for t in tasks}
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    removed = 0

    def visit(key: str) -> None:
        nonlocal removed
        state[key] = 1
        task = by_key[key]
        for dep in list(task.dependencies):
            if state.get(dep) == 1:  # back edge → cycle
                task.dependencies.remove(dep)
                removed += 1
            elif state.get(dep) is None:
                visit(dep)
        state[key] = 2

    for t in tasks:
        if t.key not in state:
            visit(t.key)
    return removed


def topological_order(tasks: list[CleanTask]) -> list[str]:
    """Keys in an order where every prerequisite comes first (used by tests)."""
    by_key = {t.key: t for t in tasks}
    out: list[str] = []
    seen: set[str] = set()

    def visit(k: str) -> None:
        if k in seen:
            return
        seen.add(k)
        for d in by_key[k].dependencies:
            visit(d)
        out.append(k)

    for t in tasks:
        visit(t.key)
    return out
