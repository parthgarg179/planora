"""Wrapper that makes a regression model predict the RATIO actual ÷ estimate.

Why: how long a task takes is roughly  estimate × (how fast this user is) × noise.
Those effects multiply. Tree models are bad at learning a multiplication from raw
hours, so instead we let them predict the ratio (e.g. 1.3 = "takes 30% longer than
estimated") and multiply by the estimate afterwards.

It lives inside app/ so the app can load a saved model (joblib needs this class).
"""
import numpy as np

ESTIMATE_COLUMN = "initial_estimated_hours"


class RatioTargetModel:
    def __init__(self, model):
        self.model = model  # any scikit-learn regressor / pipeline

    def fit(self, X, y):
        ratio = np.asarray(y) / X[ESTIMATE_COLUMN].to_numpy()
        self.model.fit(X, ratio)
        return self

    def predict(self, X):
        return self.model.predict(X) * X[ESTIMATE_COLUMN].to_numpy()
