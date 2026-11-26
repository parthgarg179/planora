"""Features for the task-duration model.

This one file is used by BOTH:
  - the training scripts in backend/ml/ (on the synthetic dataset), and
  - app/ml/predictor.py (on a real user's task history),
so the model always sees features built in exactly the same way.

History features only look at tasks the user finished BEFORE the task being
predicted, so the model never sees the answer it is trying to predict.
"""
from dataclasses import dataclass

# Columns the model is trained on, in order.
CATEGORICAL_FEATURES = ["category", "complexity", "priority"]
NUMERIC_FEATURES = ["initial_estimated_hours", "user_ratio", "user_cat_avg_actual", "user_completion_rate"]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "actual_hours"


@dataclass
class PastTask:
    """A task the user already finished."""
    category: str
    estimated_hours: float  # the initial (AI) estimate
    actual_hours: float     # total time the user really spent


def build_features(category: str, complexity: str, priority: str, estimated_hours: float,
                   past: list[PastTask], attempted_count: int) -> dict:
    """One row of model input for a task, from the user's earlier finished tasks.

    attempted_count: how many tasks the user has worked on or been scheduled for so far
    (finished or not). Used for the completion rate.
    """
    if past:
        user_ratio = sum(p.actual_hours / p.estimated_hours for p in past) / len(past)
        same_category = [p.actual_hours for p in past if p.category == category]
        pool = same_category or [p.actual_hours for p in past]  # no history in this category → overall average
        user_cat_avg_actual = sum(pool) / len(pool)
    else:  # no history: neutral values (the app never calls the model in this case anyway)
        user_ratio = 1.0
        user_cat_avg_actual = estimated_hours
    completion_rate = len(past) / attempted_count if attempted_count else 1.0

    return {
        "category": category,
        "complexity": complexity,
        "priority": priority,
        "initial_estimated_hours": float(estimated_hours),
        "user_ratio": user_ratio,
        "user_cat_avg_actual": user_cat_avg_actual,
        "user_completion_rate": min(1.0, completion_rate),
    }
