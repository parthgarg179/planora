from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import owned_task
from ..models import Task
from ..schemas import ProgressIn, ProgressOut, TaskOut, TaskUpdate
from ..serializers import task_out
from ..services import planner

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(body: TaskUpdate, task: Task = Depends(owned_task), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "subtasks" in changes:
        task.subtasks = [dict(s) for s in changes.pop("subtasks")]
    for field, value in changes.items():
        setattr(task, field, value)
    if body.priority is not None and task.goal.status == "active":
        planner.replan(db, task.goal, "Schedule v{v} · priority changed", f"{task.title} is now {task.priority} priority.")
    db.commit()
    return task_out(task)


@router.post("/{task_id}/progress", response_model=ProgressOut)
def progress(body: ProgressIn, task: Task = Depends(owned_task), db: Session = Depends(get_db)):
    version, st = planner.record_progress(db, task, body.actual_hours_spent, body.remaining_hours)
    db.commit()
    return {"task": task_out(task), "status": st, "version": version}
