"""Everything that changes a goal's plan, using the database.

The scheduling decisions themselves live in scheduler.py (pure functions);
this module loads data, calls them, saves a new schedule version, and writes
plan updates and notifications.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now, settings, today
from ..ml.predictor import predict_hours
from ..models import DailyReview, Goal, Milestone, PlanUpdate, ScheduleAssignment, Task, TaskHistory, User
from . import llm
from . import scheduler as S
from .notifications import notify

DAY = timedelta(days=1)


def hrs(h: float) -> str:
    return f"{round(h, 2):g}h"


def short_day(d: date) -> str:
    return f"{d.strftime('%a')} {d.day}"


# ------------------------------------------------------------------ reading ----
MAX_HOURS_PER_DAY = 24.0  # all of a user's active goals together, on any one weekday


def hours_used_by_other_goals(user: User, goal_id: int | None) -> dict[int, float]:
    """Hours per weekday (0=Sun … 6=Sat) already promised to the user's other active goals."""
    used = {d: 0.0 for d in range(7)}
    for g in user.goals:
        if g.status == "active" and g.id != goal_id:
            for d in g.available_days:
                used[d] += g.daily_available_hours
    return used


def free_hours_per_day(user: User, goal_id: int | None) -> dict[int, float]:
    """How many hours a day this goal may use on each weekday without the user's total passing 24h."""
    used = hours_used_by_other_goals(user, goal_id)
    return {d: max(0.0, MAX_HOURS_PER_DAY - h) for d, h in used.items()}


def check_daily_limit(user: User, goal_id: int | None, hours: float, days) -> None:
    """Refuse a goal setting that would make any weekday add up to more than 24h across active goals."""
    free = free_hours_per_day(user, goal_id)
    for d in sorted(days, key=lambda d: (d or 7)):  # Monday first
        if hours > free[d] + S.EPS:
            used = MAX_HOURS_PER_DAY - free[d]
            raise HTTPException(400, f"{S.DAY_NAMES[d]} already has {hrs(used)} planned for your other goals, "
                                     f"so this goal can use at most {hrs(free[d])} that day.")


def plan_settings(goal: Goal, **override) -> S.PlanSettings:
    return S.PlanSettings(
        daily_hours=override.get("daily_hours", goal.daily_available_hours),
        working_days=frozenset(override.get("working_days", goal.available_days)),
        deadline=override.get("deadline", goal.deadline),
    )


def sched_tasks(goal: Goal) -> list[S.SchedTask]:
    return [S.SchedTask(id=t.id, remaining_hours=t.remaining_hours, priority=t.priority,
                        dependencies=tuple(p.id for p in t.prerequisites), position=t.position,
                        status=t.status, optional=t.optional, title=t.title) for t in goal.tasks]


def reviewed_dates(db: Session, goal: Goal) -> set[date]:
    return set(db.scalars(select(DailyReview.review_date).where(DailyReview.goal_id == goal.id)))


def plan_start(db: Session, goal: Goal) -> date:
    """Plans start today, or tomorrow once today's review is in."""
    t = today()
    return t + DAY if t in reviewed_dates(db, goal) else t


def current_assignments(db: Session, goal: Goal) -> list[ScheduleAssignment]:
    return list(db.scalars(select(ScheduleAssignment)
                           .where(ScheduleAssignment.goal_id == goal.id,
                                  ScheduleAssignment.schedule_version == goal.schedule_version)
                           .order_by(ScheduleAssignment.assigned_date, ScheduleAssignment.id)))


def _by_date(rows) -> dict[date, list[tuple[int, float]]]:
    out: dict[date, list[tuple[int, float]]] = {}
    for a in rows:
        out.setdefault(a.assigned_date, []).append((a.task_id, a.planned_hours))
    return out


def status(db: Session, goal: Goal) -> dict:
    return S.evaluate(plan_settings(goal), sched_tasks(goal), plan_start(db, goal))


def pending_review_dates(db: Session, goal: Goal) -> list[date]:
    """Days with planned work that can still be reviewed (look-back window + today)."""
    if goal.status != "active":
        return []
    t = today()
    first = max(goal.start_date or t, t - timedelta(days=settings.review_lookback_days))
    done = reviewed_dates(db, goal)
    days = {a.assigned_date for a in current_assignments(db, goal)}
    return sorted(d for d in days if first <= d <= t and d not in done)


# ------------------------------------------------------------------ replanning ----
def replan(db: Session, goal: Goal, title: str | None = None, text: str = "",
           start: date | None = None, notify_change: bool = True) -> tuple[int, dict, list[date]]:
    """Save a new schedule version. Days before `start` are copied unchanged (history is kept)."""
    start = start or plan_start(db, goal)
    old = current_assignments(db, goal)
    old_map = _by_date(old)
    version = goal.schedule_version + 1
    ps, tasks = plan_settings(goal), sched_tasks(goal)

    for a in old:
        if a.assigned_date < start:
            db.add(ScheduleAssignment(goal_id=goal.id, task_id=a.task_id, assigned_date=a.assigned_date,
                                      planned_hours=a.planned_hours, schedule_version=version))
    result = S.build_schedule(ps, tasks, start)
    for d, items in result.plan.items():
        for task_id, h in items:
            db.add(ScheduleAssignment(goal_id=goal.id, task_id=task_id, assigned_date=d,
                                      planned_hours=h, schedule_version=version))
    goal.schedule_version = version
    goal.planned_from = start
    db.flush()

    st = S.evaluate(ps, tasks, start)
    changed = sorted(d for d in set(old_map) | set(result.plan)
                     if d >= start and sorted(old_map.get(d, [])) != sorted(result.plan.get(d, [])))

    if title:
        full_title = title.format(v=version)
        full_text = text + ("" if st["feasible"] else " Doesn’t fit before the deadline.")
        db.add(PlanUpdate(goal_id=goal.id, version=version, update_date=today(), title=full_title,
                          text=full_text.strip(), bad=not st["feasible"]))
        if notify_change and version > 1:
            notify(db, goal, "schedule_changed", full_title, f"{goal.title}: {full_text.strip()}", "schedule.html",
                   dedupe_key=f"changed:{goal.id}:{version}")
    _check_health(db, goal, st, version)
    db.flush()
    return version, st, changed


def _check_health(db: Session, goal: Goal, st: dict, version: int) -> None:
    new = S.health(st)
    if new != goal.health and new in ("tight", "late"):
        if new == "late":
            title = f"“{goal.title}” no longer fits before its deadline"
            body = f"{hrs(st['remaining_hours'])} of work left, {hrs(st['capacity_hours'])} available. Open the plan to choose what to change."
        else:
            title = f"“{goal.title}” is getting tight"
            body = f"Only {hrs(max(st['slack_hours'], 0))} of spare time left before {short_day(goal.deadline)}."
        notify(db, goal, "deadline_risk", title, body, "home.html", dedupe_key=f"risk:{goal.id}:{version}")
    goal.health = new


# ------------------------------------------------------------------ time-based sync ----
def sync(db: Session, goal: Goal) -> None:
    """Run whenever the app is opened: close expired reviews, then add reminders. Caller commits."""
    if goal.status != "active":
        return
    _close_expired_reviews(db, goal)
    t = today()
    for d in pending_review_dates(db, goal):
        if d < t:
            last_day = d + timedelta(days=settings.review_lookback_days)
            notify(db, goal, "missed_review", f"You haven’t reviewed {d.strftime('%A')} yet",
                   f"You can still fill it in until {last_day.strftime('%A')}, {short_day(last_day)}. "
                   "After that, its work counts as not done and is rescheduled.",
                   "review.html", dedupe_key=f"missed:{d.isoformat()}")  # one per day, covers every goal
        elif _past_reminder_time(goal):
            notify(db, goal, "review_reminder", "Time for today’s review",
                   "Tell Planora what you finished today so it can plan the days ahead.",
                   "review.html", dedupe_key=f"reminder:{t.isoformat()}")  # one per day, covers every goal


def _past_reminder_time(goal: Goal) -> bool:
    try:
        h, m = (int(x) for x in goal.reminder_time.split(":"))
    except ValueError:
        return False
    current = now()
    return (current.hour, current.minute) >= (h, m)


def _close_expired_reviews(db: Session, goal: Goal) -> None:
    t = today()
    cutoff = t - timedelta(days=settings.review_lookback_days)
    done = reviewed_dates(db, goal)
    by_day = _by_date(current_assignments(db, goal))
    expired = sorted(d for d in by_day if d < cutoff and d not in done and d >= (goal.start_date or d))
    if not expired:
        return
    for d in expired:
        review = DailyReview(goal_id=goal.id, review_date=d)
        db.add(review)
        db.flush()
        for task_id, planned in by_day[d]:
            task = db.get(Task, task_id)
            db.add(TaskHistory(goal_id=goal.id, task_id=task_id, review_id=review.id, entry_date=d, source="auto",
                               status="not_completed", planned_hours=planned, actual_hours_spent=0,
                               remaining_hours=task.remaining_hours if task else 0,
                               notes="No review within the look-back window"))
    names = ", ".join(short_day(d) for d in expired)
    replan(db, goal, "Schedule v{v} · missed reviews closed",
           f"{names} wasn’t reviewed within {settings.review_lookback_days} days, so that work was counted as not done and rescheduled.")


# ------------------------------------------------------------------ goal creation ----
def decompose(db: Session, goal: Goal) -> tuple[list[dict], bool]:
    """Ask the AI for tasks, validate them, and save them on the draft goal.
    Returns (checks, used_fallback). used_fallback is True when the AI failed and the generic plan was used."""
    start = today()
    cap_hours, cap_days = S.capacity(plan_settings(goal), start)
    plan, used_fallback = llm.decompose(goal.title, goal.description, goal.deadline, start,
                                         goal.daily_available_hours, cap_days, cap_hours)
    # replace any earlier breakdown of this draft
    for t in list(goal.tasks):
        t.prerequisites = []
    db.flush()
    goal.tasks.clear()
    goal.milestones.clear()
    db.flush()

    ms_by_key: dict[str, Milestone] = {}
    for i, m in enumerate(plan.milestones):
        ms_by_key[m.key] = Milestone(goal_id=goal.id, name=m.name, color=m.color, position=i)
        goal.milestones.append(ms_by_key[m.key])
    db.flush()
    by_key: dict[str, Task] = {}
    for i, t in enumerate(plan.tasks):
        by_key[t.key] = Task(goal_id=goal.id, milestone_id=ms_by_key[t.milestone_key].id, title=t.title,
                             description=t.description, category=t.category, complexity=t.complexity,
                             initial_estimated_hours=t.hours, remaining_hours=t.hours, actual_hours=0,
                             priority=t.priority, status="todo", optional=t.optional, position=i,
                             subtasks=[{"title": s, "done": False} for s in t.subtasks])
        goal.tasks.append(by_key[t.key])
    db.flush()
    for t in plan.tasks:
        by_key[t.key].prerequisites = [by_key[d] for d in t.dependencies]
    db.flush()
    return plan.checks, used_fallback


def activate(db: Session, user: User, goal: Goal, excluded_ids: list[int]) -> dict:
    if goal.status != "draft":
        raise HTTPException(400, "This goal already has a schedule.")
    if not goal.tasks:
        raise HTTPException(400, "Break the goal down into tasks first.")
    by_id = {t.id: t for t in goal.tasks}
    for tid in excluded_ids:
        task = by_id.get(tid)
        if not task:
            raise HTTPException(400, "One of the removed tasks doesn’t belong to this goal.")
        if not task.optional:
            raise HTTPException(400, f"“{task.title}” isn’t optional, so it can’t be removed.")
        task.status = "dropped"

    # several goals can be active at once, as long as no weekday adds up to more than 24h
    check_daily_limit(user, goal.id, goal.daily_available_hours, goal.available_days)
    goal.status = "active"
    goal.start_date = today()
    for t in goal.tasks:
        t.predicted_hours = predict_hours(db, t)
        if t.predicted_hours:  # schedule with the personalised estimate when there is one
            t.remaining_hours = t.predicted_hours

    st = S.evaluate(plan_settings(goal), sched_tasks(goal), goal.start_date)
    n = sum(1 for t in goal.tasks if t.status != "dropped")
    replan(db, goal, "Plan created",
           f"{n} tasks · {hrs(st['remaining_hours'])} estimated · {hrs(st['capacity_hours'])} available across {st['capacity_days']} working days.",
           start=goal.start_date)
    return status(db, goal)


# ------------------------------------------------------------------ progress & reviews ----
def record_progress(db: Session, task: Task, spent: float, remaining: float) -> tuple[int, dict]:
    goal = task.goal
    if task.status in ("done", "dropped"):
        raise HTTPException(400, "This task is already closed.")
    task.actual_hours += spent
    task.remaining_hours = remaining
    task.status = "done" if remaining <= 0 else "in_progress"
    if task.status == "done":
        task.subtasks = [{**s, "done": True} for s in (task.subtasks or [])]
    db.add(TaskHistory(goal_id=goal.id, task_id=task.id, entry_date=today(), source="manual",
                       status="completed" if remaining <= 0 else "partial", planned_hours=0,
                       actual_hours_spent=spent, remaining_hours=remaining))
    version, st, _ = replan(db, goal, "Schedule v{v} · task updated",
                            f"{task.title}: {'completed' if task.status == 'done' else hrs(remaining) + ' left'}.")
    return version, st


def submit_review(db: Session, goal: Goal, review_date: date, items: list[dict]) -> dict:
    if review_date not in pending_review_dates(db, goal):
        if review_date in reviewed_dates(db, goal):
            raise HTTPException(409, "That day’s review is already saved.")
        raise HTTPException(400, f"That day can’t be reviewed. Reviews are open for today and the last {settings.review_lookback_days} days.")

    planned = dict(_by_date(current_assignments(db, goal)).get(review_date, []))
    by_task = {}
    for it in items:
        try:
            by_task[int(it["task_id"])] = it
        except ValueError:
            raise HTTPException(400, "Unknown task in the review.")
    missing = set(planned) - set(by_task)
    if missing:
        raise HTTPException(400, "Give a status for every task planned that day.")
    tasks = {t.id: t for t in goal.tasks}
    if any(tid not in tasks for tid in by_task):
        raise HTTPException(400, "Unknown task in the review.")

    review = DailyReview(goal_id=goal.id, review_date=review_date)
    db.add(review)
    db.flush()
    backlog = 0.0
    counts = {"completed": 0, "partial": 0, "not_completed": 0}
    for tid, it in by_task.items():
        task, p, kind = tasks[tid], planned.get(tid, 0.0), it["status"]
        spent = float(it.get("actual_hours_spent") or 0)
        counts[kind] += 1
        if task.status in ("done", "dropped"):
            pass  # closed from the task panel in the meantime; just record what was reported
        elif kind == "completed":
            task.actual_hours += spent
            task.remaining_hours = 0
            task.status = "done"
            task.subtasks = [{**s, "done": True} for s in (task.subtasks or [])]
        elif kind == "partial":
            rem = max(0.0, float(it.get("remaining_hours") or 0))
            task.actual_hours += spent
            backlog += max(0.0, rem - (task.remaining_hours - p))
            task.remaining_hours = rem
            task.status = "in_progress" if rem > 0 else "done"
        else:
            spent = 0.0
            backlog += p
        db.add(TaskHistory(goal_id=goal.id, task_id=tid, review_id=review.id, entry_date=review_date, source="review",
                           status=kind, planned_hours=p, actual_hours_spent=spent, remaining_hours=task.remaining_hours))
    db.flush()

    backlog = S.quarter(backlog)
    version, st, changed = replan(db, goal, f"Schedule v{{v}} · {review_date.strftime('%a')} review", "")
    spread = ", ".join(short_day(d) for d in changed[:4]) + (f" +{len(changed) - 4} more" if len(changed) > 4 else "")
    summary = (f"{counts['completed']} done, {counts['partial']} partly done, {counts['not_completed']} not done. "
               + (f"{hrs(backlog)} of backlog spread across {spread or 'later days'}." if backlog > 0 else "No backlog."))
    # put the summary on the update/notification written by replan()
    upd = db.scalar(select(PlanUpdate).where(PlanUpdate.goal_id == goal.id, PlanUpdate.version == version))
    if upd:
        upd.text = (summary + " " + upd.text).strip()
    from ..models import Notification  # local import keeps the top of the file short
    note = db.scalar(select(Notification).where(Notification.dedupe_key == f"changed:{goal.id}:{version}"))
    if note:
        note.body = f"{goal.title}: {upd.text if upd else summary}"
    return {"version": version, "today": today(), "backlog_hours": backlog, "changed_dates": changed,
            "summary": summary, "status": st}


# ------------------------------------------------------------------ fixing an infeasible plan ----
def fix_options(db: Session, goal: Goal) -> dict:
    start = plan_start(db, goal)
    room = free_hours_per_day(goal.user, goal.id)  # options must respect the 24h-a-day total too
    return {"status": status(db, goal), "options": S.fix_options(plan_settings(goal), sched_tasks(goal), start, room)}


def apply_fix(db: Session, goal: Goal, kind: str, value, consent: bool) -> tuple[str, int, dict]:
    if kind == "extend_deadline":
        try:
            new = date.fromisoformat(str(value))
        except ValueError:
            raise HTTPException(400, "That isn’t a valid date.")
        if new < today():
            raise HTTPException(400, "The new deadline can’t be in the past.")
        goal.deadline = new
        message = f"Deadline moved to {new.strftime('%b')} {new.day}"
    elif kind == "increase_hours":
        if not consent:
            raise HTTPException(400, "Planora needs your agreement before raising your daily hours.")
        try:
            h = float(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "That isn’t a valid number of hours.")
        if not 0 < h <= 16:
            raise HTTPException(400, "Daily hours must be between 0 and 16.")
        check_daily_limit(goal.user, goal.id, h, goal.available_days)
        goal.daily_available_hours = h
        message = f"Daily time raised to {h:g}h"
    elif kind == "add_day":
        try:
            d = int(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "That isn’t a valid day.")
        if not 0 <= d <= 6:
            raise HTTPException(400, "That isn’t a valid day.")
        check_daily_limit(goal.user, goal.id, goal.daily_available_hours, [d])
        goal.available_days = sorted(set(goal.available_days) | {d})
        message = f"{S.DAY_NAMES[d]} added as a working day"
    elif kind == "drop_optional":
        ids = {int(v) for v in (value or [])}
        for t in goal.tasks:
            if t.id in ids:
                if not t.optional:
                    raise HTTPException(400, f"“{t.title}” isn’t optional.")
                if t.status != "done":
                    t.status = "dropped"
        message = "Optional tasks dropped"
    else:
        raise HTTPException(400, "Unknown option.")
    version, st, _ = replan(db, goal, "Schedule v{v} · plan adjusted", message + ".")
    return message, version, st
