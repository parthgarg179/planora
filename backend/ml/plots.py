"""Plots for the report, made from the SYNTHETIC model run.

*** Every plot here is from SYNTHETIC data. It shows how well the model recovers
the patterns put into the generator, NOT accuracy on real users. ***

Uses the saved model (ml/models/duration_model_synthetic.joblib) and the same
by-user split as train.py (same seed), so "test" means the same held-out
synthetic users. Run `python -m ml.train` first.

Run from backend/:   python -m ml.plots
Outputs (ml/results/):
  synthetic_model_comparison.png     CV MAE (± std) and test MAE for every model
  synthetic_predicted_vs_actual.png  AI estimate vs saved model, against actual hours (test users)
  synthetic_feature_importance.png   feature importance of the best tree model
"""
import joblib
import matplotlib

matplotlib.use("Agg")  # write files only, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit  # noqa: E402

from app.ml.features import FEATURE_COLUMNS, TARGET  # noqa: E402
from app.ml.predictor import MIN_COMPLETED_TASKS  # noqa: E402
from ml.train import DATA_FILE, IMPORTANCE_FILE, MODEL_FILE, RESULTS_FILE, SEED  # noqa: E402

OUT = RESULTS_FILE.parent
NOTE = "SYNTHETIC data — not real users"

BLUE, GRAY, INK, MUTED = "#2a78d6", "#a9a8a2", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": "#d6d5d0", "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False, "axes.titlecolor": INK,
    "axes.titlesize": 11, "figure.dpi": 150,
})


def model_comparison(saved_name: str):
    res = pd.read_csv(RESULTS_FILE).iloc[::-1]  # first model at the top
    y = np.arange(len(res))
    colors = [BLUE if m == saved_name else GRAY for m in res.model]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(y, res.cv_mae_mean, xerr=res.cv_mae_std, color=colors, height=0.6,
            error_kw={"ecolor": MUTED, "elinewidth": 1, "capsize": 3}, label="CV MAE (± std), training users")
    ax.scatter(res.test_mae, y, color=INK, marker="D", s=22, zorder=3, label="Test MAE, held-out users")
    x_num = max(res.cv_mae_mean.max() + res.cv_mae_std.max(), res.test_mae.max()) + 0.05
    for yi, v in zip(y, res.test_mae):
        ax.text(x_num, yi, f"{v:.2f}", va="center", fontsize=8.5, color=MUTED)
    ax.text(x_num, len(res) - 0.4, "test MAE", fontsize=8, color=MUTED)
    ax.set_yticks(y, [f"{m}  (saved)" if m == saved_name else m for m in res.model])
    ax.set_xlabel("Mean absolute error (hours) — lower is better")
    ax.set_title(f"Task-duration models compared\n{NOTE}", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False, fontsize=8.5)
    ax.grid(axis="x", color="#ecebe7")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "synthetic_model_comparison.png")
    plt.close(fig)


def predicted_vs_actual(model, model_name: str):
    df = pd.read_csv(DATA_FILE)
    df = df[df.n_prior_completed >= MIN_COMPLETED_TASKS].reset_index(drop=True)
    X, y, users = df[FEATURE_COLUMNS], df[TARGET], df["synthetic_user_id"]
    _, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, users))
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx].to_numpy()

    panels = [("AI estimate (what the app uses today)", X_test["initial_estimated_hours"].to_numpy()),
              (f"Saved model: {model_name}", model.predict(X_test))]
    top = float(np.percentile(np.r_[y_test, panels[0][1], panels[1][1]], 99.5))  # cut off the few largest outliers
    hidden = int(np.sum((y_test > top) | (panels[1][1] > top)))
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4), sharex=True, sharey=True)
    for ax, (title, pred) in zip(axes, panels):
        mae = np.mean(np.abs(pred - y_test))
        ax.scatter(pred, y_test, s=8, alpha=0.25, color=BLUE, edgecolors="none")
        ax.plot([0, top], [0, top], color=INK, lw=1, ls="--", label="perfect prediction")
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_title(f"{title}\nMAE {mae:.2f} h", loc="left", fontsize=10)
        ax.set_xlabel("Predicted hours")
        ax.grid(color="#ecebe7")
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Actual hours")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.suptitle(f"Predicted vs actual on {len(y_test)} tasks from held-out users — {NOTE}\n"
                 f"({hidden} points above {top:.0f} h are outside the axes; MAE uses all points)", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "synthetic_predicted_vs_actual.png")
    plt.close(fig)


def feature_importance():
    imp = pd.read_csv(IMPORTANCE_FILE).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(imp.feature, imp.importance, color=BLUE, height=0.6)
    for yi, v in enumerate(imp.importance):
        ax.text(v + 0.005, yi, f"{v:.3f}", va="center", fontsize=8.5, color=MUTED)
    ax.set_xlabel("Importance (share of error reduction, sums to 1)")
    ax.set_title(f"What the Gradient Boosting (ratio) model relies on\n{NOTE}", loc="left")
    ax.grid(axis="x", color="#ecebe7")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(OUT / "synthetic_feature_importance.png")
    plt.close(fig)


def main():
    bundle = joblib.load(MODEL_FILE)
    model_comparison(bundle["model_name"])
    predicted_vs_actual(bundle["model"], bundle["model_name"])
    feature_importance()
    print(f"SYNTHETIC-data plots written to {OUT}")


if __name__ == "__main__":
    main()
