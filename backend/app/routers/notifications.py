from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import Notification, User
from ..schemas import NotificationsOut
from ..serializers import notification_out
from ..services import planner

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationsOut)
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for goal in user.goals:  # create any reminders that are now due
        planner.sync(db, goal)
    db.commit()
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id.desc()).limit(30))
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                                  Notification.read_at.is_(None))) or 0
    return {"unread": unread, "items": [notification_out(n) for n in rows]}


@router.post("/read-all", status_code=204)
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(timezone.utc)))
    db.commit()


@router.post("/{notification_id}/read", status_code=204)
def read_one(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found.")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
