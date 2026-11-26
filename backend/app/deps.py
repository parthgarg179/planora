"""Shared FastAPI dependencies: the logged-in user and ownership checks."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Goal, Task, User
from .security import read_token

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    user_id = read_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in again.")
    return user


def owned_goal(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Goal:
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:  # same answer either way, so ids can't be probed
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found.")
    return goal


def owned_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task or task.goal.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    return task
