"""Turn database rows into API response dicts (ids as strings for tasks/milestones)."""
from .models import Goal, Notification, Task, User


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "photo_url": u.photo_url}


def goal_out(g: Goal) -> dict:
    return {
        "id": g.id, "title": g.title, "status": g.status, "start_date": g.start_date, "deadline": g.deadline,
        "daily_available_hours": g.daily_available_hours, "available_days": sorted(g.available_days),
        "start_time": g.start_time, "reminder_time": g.reminder_time,
        "milestones": [{"id": str(m.id), "name": m.name, "color": m.color} for m in g.milestones],
    }


def task_out(t: Task) -> dict:
    return {
        "id": str(t.id), "goal_id": t.goal_id, "order": t.position, "title": t.title, "description": t.description,
        "milestone_id": str(t.milestone_id) if t.milestone_id else None, "category": t.category,
        "complexity": t.complexity, "initial_estimated_hours": t.initial_estimated_hours,
        "predicted_hours": t.predicted_hours, "remaining_hours": t.remaining_hours, "actual_hours": t.actual_hours,
        "priority": t.priority, "status": t.status, "optional": t.optional,
        "dependencies": [str(p.id) for p in t.prerequisites], "subtasks": t.subtasks or [],
    }


def notification_out(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "created_at": n.created_at, "read": n.read_at is not None}
