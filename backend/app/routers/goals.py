from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import today
from ..database import get_db
from ..deps import current_user, owned_goal
from ..models import DailyReview, Goal, PlanUpdate, User
from ..schemas import (AdjustIn, AdjustOut, DailyReviewOut, DecomposeOut, FixOptionsOut, GoalCreate, GoalOut,
                       GoalUpdate, GoalWithStatus, PendingReviewsOut, PreferencesOut, ReviewIn, ReviewOut,
                       ScheduleCreate, ScheduleOut, StatusOut, TaskOut, UpdateOut)
from ..serializers import goal_out, task_out
from ..services import planner

router = APIRouter(prefix="/goals", tags=["goals"])


def _active(goal: Goal) -> None:
    if goal.status != "active":
        raise HTTPException(400, "This goal isn’t active.")


@router.get("", response_model=list[GoalOut])
def list_goals(status: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    goals = [g for g in user.goals if status is None or g.status == status]
    for g in goals:
        planner.sync(db, g)
    db.commit()
    return [goal_out(g) for g in sorted(goals, key=lambda g: g.id, reverse=True)]


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.deadline <= today():
        raise HTTPException(400, "The deadline must be after today.")
    goal = Goal(user_id=user.id, title=body.title.strip(), description=body.description.strip(), status="draft",
                deadline=body.deadline, daily_available_hours=body.daily_available_hours,
                available_days=body.available_days, start_date=today())
    db.add(goal)
    db.commit()
    return goal_out(goal)


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal: Goal = Depends(owned_goal)):
    return goal_out(goal)


@router.patch("/{goal_id}", response_model=PreferencesOut)
def update_preferences(body: GoalUpdate, goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "deadline" in changes and changes["deadline"] < today():
        raise HTTPException(400, "The deadline can’t be in the past.")
    plan_fields = {"deadline", "daily_available_hours", "available_days"}
    plan_changed = any(getattr(goal, f) != v for f, v in changes.items() if f in plan_fields)
    for field, value in changes.items():
        setattr(goal, field, value)
    version = goal.schedule_version
    if goal.status == "active" and plan_changed:
        version, _, _ = planner.replan(db, goal, "Schedule v{v} · preferences changed",
                                       f"{goal.daily_available_hours:g}h a day, due {goal.deadline.strftime('%b')} {goal.deadline.day}.")
    db.commit()
    return {"goal": goal_out(goal), "status": planner.status(db, goal), "version": version}


@router.post("/{goal_id}/decompose", response_model=DecomposeOut)
def decompose(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    if goal.status != "draft":
        raise HTTPException(400, "Only a new goal can be broken down.")
    checks, used_fallback = planner.decompose(db, goal)
    db.commit()
    db.refresh(goal)
    return {"milestones": goal_out(goal)["milestones"], "tasks": [task_out(t) for t in goal.tasks], "checks": checks,
            "used_fallback": used_fallback}


@router.post("/{goal_id}/schedule", response_model=GoalWithStatus)
def create_schedule(body: ScheduleCreate, goal: Goal = Depends(owned_goal), user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    try:
        excluded = [int(i) for i in body.excluded_task_ids]
    except ValueError:
        raise HTTPException(400, "Unknown task id.")
    st = planner.activate(db, user, goal, excluded)
    db.commit()
    return {"goal": goal_out(goal), "status": st}


@router.get("/{goal_id}/tasks", response_model=list[TaskOut])
def tasks(goal: Goal = Depends(owned_goal)):
    return [task_out(t) for t in goal.tasks]


@router.get("/{goal_id}/schedule", response_model=ScheduleOut)
def schedule(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    rows = planner.current_assignments(db, goal)
    return {"version": goal.schedule_version, "today": today(),
            "assignments": [{"date": a.assigned_date, "task_id": str(a.task_id), "planned_hours": a.planned_hours} for a in rows]}


@router.get("/{goal_id}/status", response_model=StatusOut)
def status(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    return planner.status(db, goal)


@router.get("/{goal_id}/fix-options", response_model=FixOptionsOut)
def fix_options(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    _active(goal)
    return planner.fix_options(db, goal)


@router.post("/{goal_id}/adjust", response_model=AdjustOut)
def adjust(body: AdjustIn, goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    _active(goal)
    message, version, st = planner.apply_fix(db, goal, body.kind, body.value, body.consent)
    db.commit()
    return {"message": message, "status": st, "version": version}


@router.get("/{goal_id}/updates", response_model=list[UpdateOut])
def updates(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    rows = db.scalars(select(PlanUpdate).where(PlanUpdate.goal_id == goal.id).order_by(PlanUpdate.id.desc()).limit(50))
    return [{"version": u.version, "date": u.update_date, "title": u.title, "text": u.text, "bad": u.bad} for u in rows]


@router.get("/{goal_id}/pending-reviews", response_model=PendingReviewsOut)
def pending_reviews(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    return {"dates": planner.pending_review_dates(db, goal)}


@router.post("/{goal_id}/daily-review", response_model=ReviewOut)
def daily_review(body: ReviewIn, goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    _active(goal)
    result = planner.submit_review(db, goal, body.date, [i.model_dump() for i in body.items])
    db.commit()
    return result


@router.get("/{goal_id}/daily-reviews", response_model=list[DailyReviewOut])
def daily_reviews(goal: Goal = Depends(owned_goal), db: Session = Depends(get_db)):
    rows = db.scalars(select(DailyReview).where(DailyReview.goal_id == goal.id).order_by(DailyReview.review_date))
    return [{"date": r.review_date,
             "items": [{"task_id": str(i.task_id), "planned_hours": i.planned_hours, "status": i.status,
                        "actual_hours_spent": i.actual_hours_spent, "remaining_hours": i.remaining_hours} for i in r.items]}
            for r in rows]
