"""Train and compare task-duration models on the SYNTHETIC dataset.

*** Trained and evaluated on SYNTHETIC data (ml/data/synthetic_task_history.csv). ***
The numbers this prints say how well each model recovers the patterns we put into
the synthetic generator. They are NOT evidence of accuracy on real users.

How it avoids leakage:
  - Split BY USER: 20% of synthetic users are held out completely (GroupShuffleSplit).
  - Model choice uses 5-fold GroupKFold on the training users only.
  - The held-out users are used once, at the end, to report final numbers.
  - History features only use tasks finished before the one being predicted.

Each ML model is trained two ways: predicting hours directly, and predicting the
ratio actual ÷ estimate (then × estimate). The first run only had the hours version,
and the ratio baseline beat it; the ratio version was added after that (Parth's call).

Only rows where the user already has >= MIN_COMPLETED_TASKS (20) finished tasks
are used, because that's the only case where the app calls the model.

Run from backend/:   python -m ml.train
Outputs:
  ml/results/synthetic_model_comparison.csv   metrics table
  ml/results/synthetic_feature_importance.csv importance of each feature (best tree model)
  ml/models/duration_model_synthetic.joblib   best model (only if it beats both baselines)
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES, TARGET
from app.ml.predictor import MIN_COMPLETED_TASKS
from app.ml.ratio_model import RatioTargetModel

SEED = 42
ML_DIR = Path(__file__).resolve().parent
DATA_FILE = ML_DIR / "data" / "synthetic_task_history.csv"
RESULTS_FILE = ML_DIR / "results" / "synthetic_model_comparison.csv"
IMPORTANCE_FILE = ML_DIR / "results" / "synthetic_feature_importance.csv"
MODEL_FILE = ML_DIR / "models" / "duration_model_synthetic.joblib"


# ---------- baselines: simple rules, no training ----------
class EstimateBaseline:
    """Predict the AI's initial estimate (what the app does today)."""
    def fit(self, X, y):
        return self

    def predict(self, X):
        return X["initial_estimated_hours"].to_numpy()


class RatioBaseline:
    """Predict estimate × the user's own average actual/estimate ratio."""
    def fit(self, X, y):
        return self

    def predict(self, X):
        return (X["initial_estimated_hours"] * X["user_ratio"]).to_numpy()


def with_preprocessing(model) -> Pipeline:
    """One-hot encode the text columns, scale the numbers, then fit `model`."""
    prep = ColumnTransformer([
        ("categories", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("numbers", StandardScaler(), NUMERIC_FEATURES),
    ])
    return Pipeline([("prep", prep), ("model", model)])


def ml_models() -> dict:
    return {
        "Linear Regression": with_preprocessing(LinearRegression()),
        "Random Forest": with_preprocessing(RandomForestRegressor(
            n_estimators=300, min_samples_leaf=5, random_state=SEED, n_jobs=-1)),
        "Gradient Boosting": with_preprocessing(GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=3, random_state=SEED)),
    }


def make_models() -> dict:
    """Baselines, then each ML model twice:
    (hours)  predicts actual hours directly            (first run, kept for comparison)
    (ratio)  predicts actual ÷ estimate, × estimate    (added after the first run, see ratio_model.py)
    """
    models = {
        "Baseline: initial estimate": EstimateBaseline(),
        "Baseline: estimate x user ratio": RatioBaseline(),
    }
    for name, m in ml_models().items():
        models[f"{name} (hours)"] = m
    for name, m in ml_models().items():
        models[f"{name} (ratio)"] = RatioTargetModel(m)
    return models


def scores(y_true, y_pred) -> dict:
    return {"mae": mean_absolute_error(y_true, y_pred),
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "r2": r2_score(y_true, y_pred)}


def main():
    df = pd.read_csv(DATA_FILE)
    df = df[df.n_prior_completed >= MIN_COMPLETED_TASKS].reset_index(drop=True)
    X, y, users = df[FEATURE_COLUMNS], df[TARGET], df["synthetic_user_id"]

    # Hold out 20% of users for the final test.
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, users))
    X_train, y_train, g_train = X.iloc[train_idx], y.iloc[train_idx], users.iloc[train_idx]
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
    print("SYNTHETIC data only. Results do not describe real users.")
    print(f"rows: {len(df)} | train: {len(X_train)} rows / {g_train.nunique()} users"
          f" | test: {len(X_test)} rows / {users.iloc[test_idx].nunique()} users\n")

    rows, fitted = [], {}
    for name, model in make_models().items():
        # 5-fold cross-validation on training users only (grouped by user)
        cv_mae = []
        for fold_train, fold_val in GroupKFold(n_splits=5).split(X_train, y_train, g_train):
            m = make_models()[name].fit(X_train.iloc[fold_train], y_train.iloc[fold_train])
            cv_mae.append(mean_absolute_error(y_train.iloc[fold_val], m.predict(X_train.iloc[fold_val])))
        # Fit on all training users, score once on the held-out users
        model.fit(X_train, y_train)
        fitted[name] = model
        test = scores(y_test, model.predict(X_test))
        rows.append({"model": name, "cv_mae_mean": np.mean(cv_mae), "cv_mae_std": np.std(cv_mae),
                     "test_mae": test["mae"], "test_rmse": test["rmse"], "test_r2": test["r2"]})
        print(f"{name:34} CV MAE {np.mean(cv_mae):.3f} ± {np.std(cv_mae):.3f} | "
              f"test MAE {test['mae']:.3f}  RMSE {test['rmse']:.3f}  R² {test['r2']:.3f}")

    results = pd.DataFrame(rows).round(4)
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_FILE, index=False)
    print(f"\nResults table → {RESULTS_FILE}")

    # Pick the best ML model by cross-validation MAE (NOT by the test set).
    ml_rows = results[~results.model.str.startswith("Baseline")]
    best = ml_rows.sort_values("cv_mae_mean").iloc[0]
    best_baseline_cv = results[results.model.str.startswith("Baseline")].cv_mae_mean.min()
    print(f"Best ML model by CV MAE: {best.model} ({best.cv_mae_mean:.3f}); best baseline CV MAE: {best_baseline_cv:.3f}")

    # Feature importance of the best tree model (for the report)
    tree_name = best.model if not best.model.startswith("Linear") else "Gradient Boosting (ratio)"
    pipe = fitted[tree_name]
    pipe = pipe.model if isinstance(pipe, RatioTargetModel) else pipe
    names = pipe.named_steps["prep"].get_feature_names_out()
    imp = pd.DataFrame({"feature": names, "importance": pipe.named_steps["model"].feature_importances_})
    imp["feature"] = imp.feature.str.replace("categories__", "").str.replace("numbers__", "")
    imp.sort_values("importance", ascending=False).round(4).to_csv(IMPORTANCE_FILE, index=False)
    print(f"Feature importance ({tree_name}) → {IMPORTANCE_FILE}")

    if best.cv_mae_mean >= best_baseline_cv:
        print("The best ML model does NOT beat the baselines, so no model was saved. The app keeps using AI estimates.")
        MODEL_FILE.unlink(missing_ok=True)
        return

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": fitted[best.model],
        "model_name": best.model,
        "feature_columns": FEATURE_COLUMNS,
        "trained_on": "SYNTHETIC data (ml/data/synthetic_task_history.csv). Not real user history.",
        "min_completed_tasks": MIN_COMPLETED_TASKS,
        "metrics": json.loads(best.to_json()),
        "sklearn_version": sklearn.__version__,
    }, MODEL_FILE, compress=3)
    print(f"Saved {best.model} → {MODEL_FILE} ({MODEL_FILE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
