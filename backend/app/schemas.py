"""Request and response shapes. Field names match frontend/assets/js/services/api.js.

Task and milestone ids are sent as strings so the frontend can compare them
directly with values read from HTML attributes.
"""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
Priority = Literal["High", "Normal", "Low"]


def _check_days(days: list[int]) -> list[int]:
    if not days:
        raise ValueError("Pick at least one working day.")
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("Working days must be numbers from 0 (Sunday) to 6 (Saturday).")
    return sorted(set(days))


# ---------- auth & users ----------
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    photo_url: str | None = None


class TokenOut(BaseModel):
    token: str
    user: UserOut


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    photo_url: str | None = Field(default=None, max_length=3_000_000)  # data URL or https URL; null removes it

    @field_validator("photo_url")
    @classmethod
    def _photo(cls, v):
        if v is not None and not (v.startswith("data:image/") or v.startswith("https://") or v.startswith("http://")):
            raise ValueError("Photo must be an image.")
        return v


class EstimatesOut(BaseModel):
    """Whether personalised (ML) estimates are switched on for this user. Shown on the Progress page."""
    finished_tasks: int      # finished tasks with logged hours (same count the model uses)
    threshold: int           # needed before personalised estimates start (MIN_COMPLETED_TASKS)
    model_ready: bool        # a trained model file is installed and loads
    model_synthetic: bool    # that model was trained on synthetic data (must be shown in the UI)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=200)


# ---------- goals ----------
class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    deadline: date
    daily_available_hours: float = Field(gt=0, le=16)
    available_days: list[int]

    @field_validator("available_days")
    @classmethod
    def _valid_days(cls, v):
        return _check_days(v)


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    deadline: date | None = None
    daily_available_hours: float | None = Field(default=None, gt=0, le=16)
    available_days: list[int] | None = None
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    reminder_time: str | None = Field(default=None, pattern=TIME_PATTERN)

    @field_validator("available_days")
    @classmethod
    def _valid_days(cls, v):
        return None if v is None else _check_days(v)


class MilestoneOut(BaseModel):
    id: str
    name: str
    color: str


class GoalOut(BaseModel):
    id: int
    title: str
    status: str
    start_date: date | None
    deadline: date
    daily_available_hours: float
    available_days: list[int]
    start_time: str
    reminder_time: str
    milestones: list[MilestoneOut]


# ---------- tasks ----------
class Subtask(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    done: bool = False


class TaskOut(BaseModel):
    id: str
    goal_id: int
    order: int
    title: str
    description: str
    milestone_id: str | None
    category: str
    complexity: str
    initial_estimated_hours: float
    predicted_hours: float | None
    remaining_hours: float
    actual_hours: float
    priority: str
    status: str
    optional: bool
    dependencies: list[str]
    subtasks: list[Subtask]


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    priority: Priority | None = None
    subtasks: list[Subtask] | None = None


class ProgressIn(BaseModel):
    actual_hours_spent: float = Field(default=0, ge=0, le=24)
    remaining_hours: float = Field(default=0, ge=0, le=500)


# ---------- decomposition & schedule ----------
class Check(BaseModel):
    ok: bool
    label: str


class DecomposeOut(BaseModel):
    milestones: list[MilestoneOut]
    tasks: list[TaskOut]
    checks: list[Check]
    used_fallback: bool  # True → the AI failed and this is the generic starter plan


class ScheduleCreate(BaseModel):
    excluded_task_ids: list[str] = []


class AssignmentOut(BaseModel):
    date: date
    task_id: str
    planned_hours: float


class ScheduleOut(BaseModel):
    version: int
    today: date
    assignments: list[AssignmentOut]


class StatusOut(BaseModel):
    deadline: date
    remaining_hours: float
    capacity_hours: float
    capacity_days: int
    feasible: bool
    shortfall_hours: float
    slack_hours: float
    projected_finish: date | None
    at_risk: bool


class GoalWithStatus(BaseModel):
    goal: GoalOut
    status: StatusOut


class PreferencesOut(GoalWithStatus):
    version: int


class FixResult(BaseModel):
    feasible: bool
    finish: date | None = None
    shortfall_hours: float = 0


class FixOption(BaseModel):
    kind: Literal["extend_deadline", "increase_hours", "add_day", "drop_optional"]
    value: Any
    title: str
    detail: str = ""
    result: FixResult
    needs_consent: bool = False


class FixOptionsOut(BaseModel):
    status: StatusOut
    options: list[FixOption]


class AdjustIn(BaseModel):
    kind: Literal["extend_deadline", "increase_hours", "add_day", "drop_optional"]
    value: Any
    consent: bool = False


class AdjustOut(BaseModel):
    message: str
    status: StatusOut
    version: int


class ProgressOut(BaseModel):
    task: TaskOut
    status: StatusOut
    version: int


# ---------- reviews & updates ----------
class ReviewItemIn(BaseModel):
    task_id: str
    status: Literal["completed", "partial", "not_completed"]
    actual_hours_spent: float = Field(default=0, ge=0, le=24)
    remaining_hours: float = Field(default=0, ge=0, le=500)


class ReviewIn(BaseModel):
    date: date
    items: list[ReviewItemIn] = Field(min_length=1)


class ReviewOut(BaseModel):
    version: int
    today: date
    backlog_hours: float
    changed_dates: list[date]
    summary: str
    status: StatusOut


class ReviewItemOut(BaseModel):
    task_id: str
    planned_hours: float
    status: str
    actual_hours_spent: float
    remaining_hours: float


class DailyReviewOut(BaseModel):
    date: date
    items: list[ReviewItemOut]


class UpdateOut(BaseModel):
    version: int
    date: date
    title: str
    text: str
    bad: bool


class PendingReviewsOut(BaseModel):
    dates: list[date]  # oldest first; can include today


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]
