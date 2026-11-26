"""Generate a SYNTHETIC task-history dataset for the duration model.

*** SYNTHETIC DATA. These are made-up users, not real Planora history. ***
Planora has no real completion history yet, so this dataset lets us build and
compare models. The columns match what app/ml/features.py builds from the real
task_history table, so the same pipeline can be retrained on real data later.

Every number below is a modelling ASSUMPTION (agreed with Parth on 21 Nov 2026),
not a value taken from a study:
  - Each user has a speed factor: lognormal, median 1.15 (most people slightly
    underestimate, the "planning fallacy"), sigma 0.3 → roughly 0.6x to 2.2x.
  - Each user has a multiplier per category: lognormal, sigma 0.15 (about ±15%).
  - Complexity: High tasks overrun ~15% more, Low ~5% less.
  - Priority: High tasks ~5% faster (deliberately a weak effect).
  - Completion rate per user ~ Beta(8, 2) (≈80%), a bit lower for slower users.
  - Per-task noise: lognormal, sigma 0.25 (≈ ±25%). 3% outliers take 2–3x longer.
  - Initial estimates are drawn like the AI's: Low 0.5–2h, Medium 1.5–4h, High 3–8h.
  - 300 users, each finishing 40–80 tasks. Fixed seed 42.

Run from backend/:   python -m ml.generate_synthetic_data
Output:              ml/data/synthetic_task_history.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.features import PastTask, build_features

SEED = 42
N_USERS = 300
COMPLETED_PER_USER = (40, 80)

CATEGORIES = ["learning", "practice", "project", "planning", "testing",
              "revision", "setup", "research", "writing", "other"]
COMPLEXITIES = ["Low", "Medium", "High"]
COMPLEXITY_PROBS = [0.30, 0.45, 0.25]
ESTIMATE_RANGE = {"Low": (0.5, 2.0), "Medium": (1.5, 4.0), "High": (3.0, 8.0)}
COMPLEXITY_EFFECT = {"Low": 0.95, "Medium": 1.00, "High": 1.15}
PRIORITIES = ["High", "Normal", "Low"]
PRIORITY_PROBS = [0.30, 0.50, 0.20]
PRIORITY_EFFECT = {"High": 0.95, "Normal": 1.00, "Low": 1.00}

SPEED_MEDIAN, SPEED_SIGMA = 1.15, 0.30
CATEGORY_SIGMA = 0.15
NOISE_SIGMA = 0.25
OUTLIER_RATE, OUTLIER_RANGE = 0.03, (2.0, 3.0)

OUT_FILE = Path(__file__).resolve().parent / "data" / "synthetic_task_history.csv"


def round_quarter(x: float) -> float:
    """Round to the nearest 0.25h, at least 0.25h (same granularity as the app)."""
    return max(0.25, round(x * 4) / 4)


def generate(seed: int = SEED, n_users: int = N_USERS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for user in range(n_users):
        # --- hidden traits of this synthetic user (never given to the model directly) ---
        speed = rng.lognormal(np.log(SPEED_MEDIAN), SPEED_SIGMA)
        category_mult = {c: rng.lognormal(0.0, CATEGORY_SIGMA) for c in CATEGORIES}
        completion = rng.beta(8, 2) - 0.15 * (speed - SPEED_MEDIAN)  # slower users finish a bit less
        completion = float(np.clip(completion, 0.40, 0.99))
        target_completed = int(rng.integers(COMPLETED_PER_USER[0], COMPLETED_PER_USER[1] + 1))

        past: list[PastTask] = []
        attempted = 0
        while len(past) < target_completed:
            category = str(rng.choice(CATEGORIES))
            complexity = str(rng.choice(COMPLEXITIES, p=COMPLEXITY_PROBS))
            priority = str(rng.choice(PRIORITIES, p=PRIORITY_PROBS))
            estimate = round_quarter(rng.uniform(*ESTIMATE_RANGE[complexity]))

            # Features use only what happened BEFORE this task.
            features = build_features(category, complexity, priority, estimate, past, attempted)
            attempted += 1
            if rng.random() > completion:
                continue  # started/scheduled but never finished: counts for the completion rate only

            actual = (estimate * speed * category_mult[category] * COMPLEXITY_EFFECT[complexity]
                      * PRIORITY_EFFECT[priority] * rng.lognormal(0.0, NOISE_SIGMA))
            if rng.random() < OUTLIER_RATE:
                actual *= rng.uniform(*OUTLIER_RANGE)
            actual = round_quarter(actual)

            rows.append({"synthetic_user_id": user, "task_seq": attempted,
                         "n_prior_completed": len(past), **features, "actual_hours": actual})
            past.append(PastTask(category, estimate, actual))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)
    print(f"SYNTHETIC dataset written to {OUT_FILE}")
    print(f"{len(df)} completed tasks from {df.synthetic_user_id.nunique()} synthetic users")
    print(f"rows with >= 20 earlier finished tasks: {(df.n_prior_completed >= 20).sum()}")
    print(df[["initial_estimated_hours", "actual_hours", "user_ratio", "user_completion_rate"]].describe().round(2))
