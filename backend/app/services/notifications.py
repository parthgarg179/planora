"""Create in-app notifications (shown under the bell in the sidebar)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Goal, Notification

KINDS = ("review_reminder", "missed_review", "schedule_changed", "deadline_risk")


def notify(db: Session, goal: Goal, kind: str, title: str, body: str = "", link: str = "home.html",
           dedupe_key: str | None = None) -> None:
    assert kind in KINDS
    if dedupe_key and db.scalar(select(Notification.id).where(
            Notification.user_id == goal.user_id, Notification.dedupe_key == dedupe_key)):
        return
    db.add(Notification(user_id=goal.user_id, goal_id=goal.id, kind=kind, title=title, body=body,
                        link=link, dedupe_key=dedupe_key))
    db.flush()
