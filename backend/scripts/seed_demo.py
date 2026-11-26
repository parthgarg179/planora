"""Create (or reset) the DEMO account for presentations.

*** Everything this script makes is DEMO DATA, not a real user. ***

Run from backend/ (the server can stay running):   python -m scripts.seed_demo

The demo login comes from settings, so it's never stored in the code. Set these in backend/.env
(or as environment variables, e.g. when seeding the hosted database):
    DEMO_EMAIL=...       the login email
    DEMO_PASSWORD=...    the login password
    DEMO_NAME=...        optional display name (default "Demo Student")
DATABASE_URL decides which database is seeded (local by default).
Running it again DELETES the account with DEMO_EMAIL (and everything in it) and builds it fresh,
with dates relative to today (in APP_TIMEZONE if set).

What you get:
  - An earlier goal (archived) with 25 finished tasks. These are hand-made demo history, so the
    personalised (ML) estimates switch on for the current goal. The ML model itself is still
    the one trained on SYNTHETIC data.
  - The current goal, started 10 days ago. Its task list is written by hand below (no Gemini
    call, so the demo is the same every time). Every day since then was reviewed through the
    app's own planner code, with "today" moved back one day at a time. That includes a partly
    done day and a fully missed day, so the backlog was really redistributed. The last working
    day is left unreviewed, so the review page and a "missed review" notification have something
    to show.
"""
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import today as app_today
from app.database import SessionLocal, init_db
from app.models import Goal, Notification, Task, TaskHistory, User
from app.security import hash_password
from app.services import planner
from app.services.validation import validate_plan

# The demo login is read from settings (backend/.env or environment variables), never stored here.
DEMO_NAME = os.getenv("DEMO_NAME", "").strip() or "Demo Student"
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "").strip().lower()
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
DAYS_IN = 10  # how long ago the current goal started
SEED = 7      # fixed, so the demo looks the same every time

# The current goal's tasks: (milestone, title, hours, category, complexity, priority, optional, depends on)
DEMO_TASKS = [
    ("Plan", "Collect projects and write a short bio", 2, "planning", "Low", "High", False, []),
    ("Plan", "Sketch the page layout on paper", 1.5, "planning", "Low", "Normal", False, [1]),
    ("Learn", "HTML basics: structure and semantic tags", 3, "learning", "Medium", "High", False, [2]),
    ("Learn", "CSS basics: box model, flexbox, grid", 4, "learning", "Medium", "High", False, [3]),
    ("Learn", "Responsive design with media queries", 2.5, "learning", "Medium", "Normal", False, [4]),
    ("Build", "Build the home and about sections", 4, "project", "Medium", "High", False, [5]),
    ("Build", "Build the projects gallery", 5, "project", "High", "High", False, [6]),
    ("Build", "Add a contact form", 2, "project", "Medium", "Normal", False, [6]),
    ("Build", "Add a dark-mode toggle", 2, "project", "Medium", "Low", True, [7]),
    ("Ship", "Test on phone and fix layout bugs", 2.5, "testing", "Medium", "Normal", False, [7, 8]),
    ("Ship", "Publish on GitHub Pages", 1.5, "setup", "Low", "High", False, [10]),
    ("Ship", "Ask two friends for feedback and polish", 2, "revision", "Low", "Normal", False, [11]),
]

# The earlier goal's finished tasks: (title, category, complexity, AI estimate)
PAST_TASKS = [
    ("Install Python and an editor", "setup", "Low", 1), ("Variables and types", "learning", "Low", 1.5),
    ("If statements and loops", "learning", "Medium", 2), ("Loop exercises", "practice", "Medium", 2),
    ("Functions", "learning", "Medium", 2), ("Function exercises", "practice", "Medium", 2.5),
    ("Lists and tuples", "learning", "Medium", 2), ("Dictionaries and sets", "learning", "Medium", 2),
    ("Collections exercises", "practice", "Medium", 3), ("Reading and writing files", "learning", "Medium", 2),
    ("Error handling", "learning", "Medium", 1.5), ("File exercises", "practice", "Medium", 2),
    ("Plan the mini project", "planning", "Low", 1), ("Modules and packages", "learning", "Medium", 2),
    ("Mini project: core logic", "project", "High", 4), ("Mini project: menu and input", "project", "Medium", 3),
    ("Classes and objects", "learning", "High", 3), ("OOP exercises", "practice", "High", 3),
    ("Mini project: refactor into classes", "project", "High", 4), ("Write tests with pytest", "testing", "Medium", 2.5),
    ("Fix bugs found by the tests", "testing", "Medium", 2), ("Read about virtual environments", "research", "Low", 1),
    ("Write a README for the project", "writing", "Low", 1.5), ("Revise weak topics", "revision", "Medium", 2),
    ("Final review quiz", "revision", "Medium", 1.5),
]


def quarter(h: float) -> float:
    return max(0.25, round(h * 4) / 4)


def demo_plan():
    """The hand-written task list in the same shape the AI returns, run through the same validation."""
    milestones = list(dict.fromkeys(m for m, *_ in DEMO_TASKS))
    return validate_plan({
        "milestones": [{"id": f"m{i + 1}", "name": n} for i, n in enumerate(milestones)],
        "tasks": [{"id": f"t{i + 1}", "title": title, "milestone_id": f"m{milestones.index(ms) + 1}",
                   "estimated_hours": hours, "category": cat, "complexity": cx, "priority": prio,
                   "optional": opt, "dependencies": [f"t{d}" for d in deps], "subtasks": []}
                  for i, (ms, title, hours, cat, cx, prio, opt, deps) in enumerate(DEMO_TASKS)],
    })


def add_past_goal(db, user: User, start: date, rng: random.Random) -> None:
    """Archived earlier goal with finished tasks. This demo user takes about 1.3× the AI's estimates."""
    goal = Goal(user_id=user.id, title="Learn Python basics", status="archived", start_date=start,
                description="DEMO DATA: earlier goal made by scripts/seed_demo.py",
                deadline=start + timedelta(days=45), daily_available_hours=2, available_days=[1, 2, 3, 4, 5, 6],
                schedule_version=1)
    db.add(goal)
    db.flush()
    day = start
    for i, (title, cat, cx, est) in enumerate(PAST_TASKS):
        actual = quarter(est * rng.gauss(1.3, 0.15))
        task = Task(goal_id=goal.id, title=title, category=cat, complexity=cx, initial_estimated_hours=est,
                    remaining_hours=0, actual_hours=actual, priority="Normal", status="done", position=i)
        db.add(task)
        db.flush()
        db.add(TaskHistory(goal_id=goal.id, task_id=task.id, entry_date=day, source="review", status="completed",
                           planned_hours=est, actual_hours_spent=actual, remaining_hours=0,
                           notes="DEMO DATA"))
        day += timedelta(days=1 if day.isoweekday() != 6 else 2)  # skip Sundays
    db.flush()


def review_items(db, goal: Goal, day: date, n: int, rng: random.Random) -> list[dict]:
    """What the demo user reports for `day`. n counts reviewed days, so the story is fixed:
    day 3 → first task only partly done (needs more time), day 5 → nothing done (a missed day),
    otherwise the planned work is done, taking a bit longer than planned."""
    planned = planner._by_date(planner.current_assignments(db, goal)).get(day, [])
    tasks = {t.id: t for t in goal.tasks}
    items = []
    for j, (task_id, hours) in enumerate(planned):
        task = tasks[task_id]
        spent = quarter(hours * rng.uniform(1.0, 1.4))
        if n == 5:
            items.append({"task_id": task_id, "status": "not_completed"})
        elif n == 3 and j == 0:
            items.append({"task_id": task_id, "status": "partial", "actual_hours_spent": spent,
                          "remaining_hours": task.remaining_hours - hours + 1.5})
        elif hours < task.remaining_hours:  # worked as planned, task continues tomorrow
            items.append({"task_id": task_id, "status": "partial", "actual_hours_spent": spent,
                          "remaining_hours": task.remaining_hours - hours})
        else:
            items.append({"task_id": task_id, "status": "completed", "actual_hours_spent": spent})
    return items


def main():
    if not DEMO_EMAIL or not DEMO_PASSWORD:
        sys.exit("Set DEMO_EMAIL and DEMO_PASSWORD (in backend/.env or as environment variables) first.")
    rng = random.Random(SEED)
    real_today = app_today()  # the app's today (APP_TIMEZONE), not the computer's
    start = real_today - timedelta(days=DAYS_IN)
    clock = {"today": start}
    planner.today = lambda: clock["today"]  # same trick as the tests: move the app's "today"
    planner.llm.decompose = lambda *a, **k: (demo_plan(), False)  # hand-written tasks, no Gemini call

    init_db()
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == DEMO_EMAIL))  # reset: the DB cascades to all their data
        user = User(name=DEMO_NAME, email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
        add_past_goal(db, user, start - timedelta(days=70), rng)

        goal = Goal(user_id=user.id, title="Build a personal portfolio website",
                    description="DEMO DATA: made by scripts/seed_demo.py",
                    deadline=start + timedelta(days=38), daily_available_hours=2, available_days=[1, 2, 3, 4, 5, 6])
        db.add(goal)
        db.flush()
        planner.decompose(db, goal)
        planner.activate(db, user, goal, excluded_ids=[])

        # Review each day up to the last working day before today, which is left for the demo.
        days = sorted({a.assigned_date for a in planner.current_assignments(db, goal) if a.assigned_date < real_today})
        n = 0
        for day in days[:-1]:
            clock["today"] = day
            items = review_items(db, goal, day, n, rng)
            if items:
                planner.submit_review(db, goal, day, items)
                n += 1
        # A real user would have seen last week's notifications: keep only the latest one unread.
        notes = db.scalars(select(Notification).where(Notification.user_id == user.id)
                           .order_by(Notification.id)).all()
        for note in notes[:-1]:
            note.read_at = datetime.now(timezone.utc)
        clock["today"] = real_today
        planner.sync(db, goal)  # adds the "missed review" notification for the unreviewed day
        db.commit()

        predicted = sum(1 for t in goal.tasks if t.predicted_hours)
        print("DEMO account ready (all data is demo data).")
        print(f"  login: {DEMO_EMAIL}  (password: the DEMO_PASSWORD you set)")
        print(f"  current goal: '{goal.title}', started {start}, schedule v{goal.schedule_version}, "
              f"{n} days reviewed, health '{goal.health}'")
        print(f"  personalised estimates on {predicted} of {len(goal.tasks)} tasks; "
              f"waiting for review: {[d.isoformat() for d in planner.pending_review_dates(db, goal)]}")


if __name__ == "__main__":
    main()
