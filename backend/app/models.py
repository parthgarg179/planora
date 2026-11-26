"""Database tables (SQLAlchemy 2.0).

Days of the week are stored the JavaScript way: 0 = Sunday ... 6 = Saturday,
so the frontend and backend agree without conversion.
"""
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | archived
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date] = mapped_column(Date)
    daily_available_hours: Mapped[float] = mapped_column(Float)
    available_days: Mapped[list[int]] = mapped_column(JSON)  # 0=Sun .. 6=Sat
    start_time: Mapped[str] = mapped_column(String(5), default="19:00")
    reminder_time: Mapped[str] = mapped_column(String(5), default="21:30")
    schedule_version: Mapped[int] = mapped_column(Integer, default=0)
    planned_from: Mapped[date | None] = mapped_column(Date, nullable=True)  # first day of the current schedule version
    health: Mapped[str] = mapped_column(String(10), default="ok")  # ok | tight | late (last known)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="goals")
    milestones: Mapped[list["Milestone"]] = relationship(back_populates="goal", cascade="all, delete-orphan", order_by="Milestone.position")
    tasks: Mapped[list["Task"]] = relationship(back_populates="goal", cascade="all, delete-orphan", order_by="Task.position")


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(9), default="#6b86e8")
    position: Mapped[int] = mapped_column(Integer, default=0)

    goal: Mapped[Goal] = relationship(back_populates="milestones")


# Prerequisites: (task_id) can only start after (depends_on_id) is finished.
task_dependencies = Table(
    "task_dependencies",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("depends_on_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="other")
    complexity: Mapped[str] = mapped_column(String(10), default="Medium")  # Low | Medium | High
    initial_estimated_hours: Mapped[float] = mapped_column(Float)
    predicted_hours: Mapped[float | None] = mapped_column(Float, nullable=True)  # ML estimate, when available
    remaining_hours: Mapped[float] = mapped_column(Float)
    actual_hours: Mapped[float] = mapped_column(Float, default=0)
    priority: Mapped[str] = mapped_column(String(10), default="Normal")  # High | Normal | Low
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo | in_progress | done | dropped
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    subtasks: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{"title": str, "done": bool}]

    goal: Mapped[Goal] = relationship(back_populates="tasks")
    prerequisites: Mapped[list["Task"]] = relationship(
        secondary=task_dependencies,
        primaryjoin=lambda: Task.id == task_dependencies.c.task_id,
        secondaryjoin=lambda: Task.id == task_dependencies.c.depends_on_id,
    )


class ScheduleAssignment(Base):
    """One block of planned work. Every schedule version keeps a full copy, so revisions can be compared."""
    __tablename__ = "schedule_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    assigned_date: Mapped[date] = mapped_column(Date, index=True)
    planned_hours: Mapped[float] = mapped_column(Float)
    schedule_version: Mapped[int] = mapped_column(Integer, index=True)


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (UniqueConstraint("goal_id", "review_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    review_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["TaskHistory"]] = relationship(back_populates="review", order_by="TaskHistory.id")


class TaskHistory(Base):
    """Every reported piece of work: from an end-of-day review or a manual update. Future ML training data."""
    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[int | None] = mapped_column(ForeignKey("daily_reviews.id", ondelete="CASCADE"), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(10), default="review")  # review | manual
    status: Mapped[str] = mapped_column(String(20))  # completed | partial | not_completed
    planned_hours: Mapped[float] = mapped_column(Float, default=0)
    actual_hours_spent: Mapped[float] = mapped_column(Float, default=0)
    remaining_hours: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[DailyReview | None] = relationship(back_populates="items")


class PlanUpdate(Base):
    """Human-readable log of schedule changes, shown on the dashboard."""
    __tablename__ = "plan_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    update_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    bad: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """In-app notifications shown under the bell in the sidebar.

    kind: review_reminder | missed_review | schedule_changed | deadline_risk
    dedupe_key stops the same reminder being created twice (e.g. "reminder:2026-11-16").
    """
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(100), default="home.html")  # frontend page to open
    dedupe_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
