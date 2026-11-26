"""Deterministic scheduler — pure Python, no database, fully unit-testable.

Rules (from the project spec):
  * prerequisites are scheduled before the tasks that depend on them
  * then higher priority first, then the original task order
  * a task already in progress is continued before starting something new
  * a day never gets more than the user's daily hours
  * only the user's working days are used
  * work that doesn't fit before the deadline keeps being projected past it,
    so the app can show the shortfall instead of hiding it (never squeezed in)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

PRIORITY_RANK = {"High": 0, "Normal": 1, "Low": 2}
EPS = 1e-9
MAX_DAYS_PAST_DEADLINE = 500


def js_weekday(d: date) -> int:
    """0 = Sunday ... 6 = Saturday (the convention used by the API and frontend)."""
    return (d.weekday() + 1) % 7


def quarter(hours: float) -> float:
    return round(hours * 4) / 4


@dataclass(frozen=True)
class PlanSettings:
    daily_hours: float
    working_days: frozenset[int]
    deadline: date

    def is_working_day(self, d: date) -> bool:
        return js_weekday(d) in self.working_days


@dataclass
class SchedTask:
    id: int
    remaining_hours: float
    priority: str = "Normal"
    dependencies: tuple[int, ...] = ()
    position: int = 0
    status: str = "todo"  # todo | in_progress | done | dropped
    optional: bool = False
    title: str = ""

    @property
    def open(self) -> bool:
        return self.status not in ("done", "dropped")


@dataclass
class ScheduleResult:
    plan: dict[date, list[tuple[int, float]]] = field(default_factory=dict)
    last_day: date | None = None
    unschedulable: list[int] = field(default_factory=list)  # blocked forever (e.g. no working days)


def build_schedule(settings: PlanSettings, tasks: list[SchedTask], start: date) -> ScheduleResult:
    by_id = {t.id: t for t in tasks}
    finished = {t.id for t in tasks if not t.open}
    left = {t.id: t.remaining_hours for t in tasks if t.open and t.remaining_hours > EPS}
    result = ScheduleResult()

    if settings.daily_hours <= EPS or not settings.working_days:
        result.unschedulable = sorted(left)
        return result

    def ready(task_id: int) -> bool:
        return all(d in finished or d not in by_id for d in by_id[task_id].dependencies)

    started: int | None = None
    day = start
    limit = settings.deadline + timedelta(days=MAX_DAYS_PAST_DEADLINE)

    while any(v > EPS for v in left.values()) and day <= limit:
        if settings.is_working_day(day):
            cap = settings.daily_hours
            first_pass = True
            while cap > EPS:
                candidates = [by_id[i] for i, v in left.items() if v > EPS and ready(i)]
                if not candidates:
                    break
                candidates.sort(key=lambda t: (
                    t.id != started,
                    t.status != "in_progress",
                    PRIORITY_RANK.get(t.priority, 1),
                    t.position,
                    t.id,
                ))
                task = candidates[0]
                hours = min(cap, left[task.id])
                planned = quarter(hours)
                if planned > 0:
                    result.plan.setdefault(day, []).append((task.id, planned))
                    result.last_day = day
                left[task.id] -= hours
                cap -= hours
                if left[task.id] <= EPS:
                    finished.add(task.id)
                    started = None
                else:
                    started = task.id
                first_pass = False
            if first_pass and not any(ready(i) for i, v in left.items() if v > EPS):
                break  # nothing can ever start (shouldn't happen after validation)
        day += timedelta(days=1)

    result.unschedulable = sorted(i for i, v in left.items() if v > EPS)
    return result


def capacity(settings: PlanSettings, start: date) -> tuple[float, int]:
    hours, days = 0.0, 0
    d = start
    while d <= settings.deadline:
        if settings.is_working_day(d):
            hours += settings.daily_hours
            days += 1
        d += timedelta(days=1)
    return hours, days


def evaluate(settings: PlanSettings, tasks: list[SchedTask], start: date) -> dict:
    """Feasibility numbers shown on the dashboard and in the warning."""
    res = build_schedule(settings, tasks, start)
    remaining = sum(t.remaining_hours for t in tasks if t.open)
    cap_hours, cap_days = capacity(settings, start)
    feasible = not res.unschedulable and (res.last_day is None or res.last_day <= settings.deadline)
    slack = cap_hours - remaining
    return {
        "deadline": settings.deadline,
        "remaining_hours": round(remaining, 2),
        "capacity_hours": round(cap_hours, 2),
        "capacity_days": cap_days,
        "feasible": feasible,
        "shortfall_hours": round(max(0.0, remaining - cap_hours), 2),
        "slack_hours": round(slack, 2),
        "projected_finish": None if res.unschedulable else res.last_day,
        "at_risk": feasible and slack < settings.daily_hours * 1.5,
    }


def health(status: dict) -> str:
    """ok | tight | late — used to decide when to send a 'deadline at risk' notification."""
    if not status["feasible"]:
        return "late"
    return "tight" if status["at_risk"] else "ok"


DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def fix_options(settings: PlanSettings, tasks: list[SchedTask], start: date,
                room: dict[int, float] | None = None) -> list[dict]:
    """Ways to make an infeasible plan fit. Nothing is applied here; the user chooses.
    `room` = most hours this goal may use on each weekday (0=Sun … 6=Sat), because the user's
    other goals share the same 24-hour days. None means no other goals."""
    base = evaluate(settings, tasks, start)
    room = room or {d: 24.0 for d in range(7)}

    def result(st: dict) -> dict:
        return {"feasible": st["feasible"], "finish": st["projected_finish"],
                "shortfall_hours": 0 if st["feasible"] else max(st["shortfall_hours"], 0.25)}

    options: list[dict] = []
    finish = base["projected_finish"]
    if finish and finish > settings.deadline:
        options.append({"kind": "extend_deadline", "value": finish.isoformat(),
                        "title": f"Extend the deadline to {finish.strftime('%b')} {finish.day}",
                        "detail": "Keeps your hours and scope as they are",
                        "result": {"feasible": True, "finish": finish, "shortfall_hours": 0}, "needs_consent": False})

    max_h = min([16, settings.daily_hours + 4] + [room[d] for d in settings.working_days])
    h = settings.daily_hours + 0.5
    while h <= max_h + EPS:
        st = evaluate(PlanSettings(h, settings.working_days, settings.deadline), tasks, start)
        if st["feasible"]:
            options.append({"kind": "increase_hours", "value": h,
                            "title": f"Work {h:g}h a day instead of {settings.daily_hours:g}h", "detail": "",
                            "result": result(st), "needs_consent": True})
            break
        h += 0.5

    missing = [d for d in (0, 1, 2, 3, 4, 5, 6)
               if d not in settings.working_days and room[d] + EPS >= settings.daily_hours]
    if missing:
        d = missing[0]
        st = evaluate(PlanSettings(settings.daily_hours, settings.working_days | {d}, settings.deadline), tasks, start)
        options.append({"kind": "add_day", "value": d, "title": f"Add {DAY_NAMES[d]} as a working day", "detail": "",
                        "result": result(st), "needs_consent": False})

    optional = [t for t in tasks if t.optional and t.open]
    if optional:
        ids = {t.id for t in optional}
        trimmed = [SchedTask(**{**t.__dict__, "status": "dropped"}) if t.id in ids else t for t in tasks]
        st = evaluate(settings, trimmed, start)
        options.append({"kind": "drop_optional", "value": [str(t.id) for t in optional], "title": "Drop optional tasks",
                        "detail": ", ".join(f"{t.title} ({t.remaining_hours:g}h)" for t in optional),
                        "result": result(st), "needs_consent": False})
    return options
