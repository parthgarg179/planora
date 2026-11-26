"""Personalised task-duration estimate (the "how long" part of the planner).

predict_hours() returns the number of hours this user will probably need for a task,
or None, in which case the app keeps the AI's estimate. It returns None when:
  - the user has fewer than MIN_COMPLETED_TASKS (20) finished tasks with logged hours, or
  - there is no model file (or it can't be loaded).

NOTE: the current model (ml/models/duration_model_synthetic.joblib) was trained on
SYNTHETIC data, because there is no real history yet. Retrain it on real task_history
once there is enough (see backend/ml/train.py).

The features are built by app/ml/features.py, the same code used in training.
"""
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Goal, Task, TaskHistory
from .features import FEATURE_COLUMNS, PastTask, build_features

log = logging.getLogger("planora.ml")

MIN_COMPLETED_TASKS = 20  # same threshold the Progress page shows
MODEL_PATH = Path(__file__).resolve().parents[2] / "ml" / "models" / "duration_model_synthetic.joblib"
MIN_HOURS, MAX_HOURS = 0.25, 40.0  # same limits as the AI's estimates (services/validation.py)

_loaded: dict[str, object] = {}  # path → loaded model bundle (or None if loading failed)


def load_model(path: Path | None = None):
    """Load the saved model once and keep it in memory. Returns None if it isn't available."""
    path = Path(path or MODEL_PATH)
    key = str(path)
    if key not in _loaded:
        try:
            import joblib  # imported here so the app still starts if the ML packages are missing
            _loaded[key] = joblib.load(path)
            log.info("Loaded duration model from %s (%s)", path, _loaded[key].get("trained_on", ""))
        except FileNotFoundError:
            log.info("No duration model at %s, so AI estimates are used.", path)
            _loaded[key] = None
        except Exception as exc:  # broken file, version mismatch, missing package...
            log.warning("Couldn't load duration model (%s), so AI estimates are used.", exc)
            _loaded[key] = None
    return _loaded[key]


def completed_task_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(func.distinct(TaskHistory.task_id)))
        .join(Goal, Goal.id == TaskHistory.goal_id)
        .where(Goal.user_id == user_id, TaskHistory.status == "completed", TaskHistory.actual_hours_spent > 0)
    ) or 0


def user_history(db: Session, user_id: int, exclude_task_id: int | None = None) -> tuple[list[PastTask], int]:
    """The user's finished tasks (oldest first) and how many tasks they have worked on or reviewed.

    Finished = status "done" with actual hours logged. Attempted = any task with a task_history row.
    """
    last_entry = (select(TaskHistory.task_id, func.max(TaskHistory.entry_date).label("last_date"))
                  .group_by(TaskHistory.task_id).subquery())
    rows = db.execute(
        select(Task.category, Task.initial_estimated_hours, Task.actual_hours)
        .join(Goal, Goal.id == Task.goal_id)
        .join(last_entry, last_entry.c.task_id == Task.id)
        .where(Goal.user_id == user_id, Task.status == "done", Task.actual_hours > 0,
               Task.initial_estimated_hours > 0, Task.id != (exclude_task_id or -1))
        .order_by(last_entry.c.last_date, Task.id)
    ).all()
    past = [PastTask(r.category, r.initial_estimated_hours, r.actual_hours) for r in rows]

    attempted = db.scalar(
        select(func.count(func.distinct(TaskHistory.task_id)))
        .join(Goal, Goal.id == TaskHistory.goal_id)
        .where(Goal.user_id == user_id, TaskHistory.task_id != (exclude_task_id or -1))
    ) or 0
    return past, max(attempted, len(past))


def estimates_status(db: Session, user_id: int) -> dict:
    """What the Progress page needs to say whether estimates are AI or personalised."""
    past, _ = user_history(db, user_id)
    bundle = load_model()
    return {
        "finished_tasks": len(past),
        "threshold": MIN_COMPLETED_TASKS,
        "model_ready": bundle is not None,
        "model_synthetic": bundle is not None and "SYNTHETIC" in str(bundle.get("trained_on", "")).upper(),
    }


def predict_hours(db: Session, task: Task, model_path: Path | None = None) -> float | None:
    """Personalised estimate for `task` in hours (rounded to 0.25), or None to keep the AI estimate."""
    user_id = task.goal.user_id if task.goal else db.scalar(select(Goal.user_id).where(Goal.id == task.goal_id))
    past, attempted = user_history(db, user_id, exclude_task_id=task.id)
    if len(past) < MIN_COMPLETED_TASKS:
        return None

    bundle = load_model(model_path)
    if bundle is None:
        return None

    import pandas as pd
    row = build_features(task.category, task.complexity, task.priority, task.initial_estimated_hours, past, attempted)
    try:
        hours = float(bundle["model"].predict(pd.DataFrame([row], columns=FEATURE_COLUMNS))[0])
    except Exception as exc:
        log.warning("Duration model failed for task %s (%s), so the AI estimate is used.", task.id, exc)
        return None
    hours = min(MAX_HOURS, max(MIN_HOURS, hours))
    return round(hours * 4) / 4
