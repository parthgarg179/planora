"""Tests for the personalised duration model hook (app/ml/predictor.py).

A tiny model is trained on a small SYNTHETIC dataset into a temp folder, so these
tests don't depend on the saved model in ml/models/.
"""
from datetime import date, timedelta

import pytest

pytest.importorskip("sklearn")
import joblib  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.ml import predictor  # noqa: E402
from app.ml.features import FEATURE_COLUMNS, TARGET  # noqa: E402
from app.ml.ratio_model import RatioTargetModel  # noqa: E402
from app.models import Goal, Task, TaskHistory, User  # noqa: E402
from ml.generate_synthetic_data import generate  # noqa: E402
from ml.train import with_preprocessing  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402

START = date(2026, 1, 5)


@pytest.fixture(scope="module")
def model_path(tmp_path_factory):
    """Train a small model on 20 synthetic users and save it like train.py does."""
    df = generate(seed=1, n_users=20)
    model = RatioTargetModel(with_preprocessing(LinearRegression())).fit(df[FEATURE_COLUMNS], df[TARGET])
    path = tmp_path_factory.mktemp("model") / "tiny_synthetic.joblib"
    joblib.dump({"model": model, "trained_on": "SYNTHETIC test data"}, path)
    return path


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()


def add_user(db, email="u@example.com") -> User:
    user = User(name="Test", email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def add_finished_tasks(db, user_id: int, n: int, ratio: float = 1.5) -> None:
    """n finished tasks on an old goal, each taking `ratio` × its estimate."""
    goal = Goal(user_id=user_id, title="Old goal", deadline=START + timedelta(days=90), daily_available_hours=2,
                available_days=[1, 2, 3, 4, 5], status="archived")
    db.add(goal)
    db.flush()
    for i in range(n):
        est = 1.0 + (i % 4)
        t = Task(goal_id=goal.id, title=f"Old task {i}", category="learning" if i % 2 else "practice",
                 complexity="Medium", initial_estimated_hours=est, remaining_hours=0, actual_hours=est * ratio,
                 priority="Normal", status="done", position=i)
        db.add(t)
        db.flush()
        db.add(TaskHistory(goal_id=goal.id, task_id=t.id, entry_date=START + timedelta(days=i), status="completed",
                           planned_hours=est, actual_hours_spent=est * ratio, remaining_hours=0))
    db.flush()


def add_new_task(db, user_id: int) -> Task:
    goal = Goal(user_id=user_id, title="New goal", deadline=START + timedelta(days=200), daily_available_hours=2,
                available_days=[1, 2, 3, 4, 5], status="draft")
    db.add(goal)
    db.flush()
    t = Task(goal_id=goal.id, title="New task", category="learning", complexity="Medium",
             initial_estimated_hours=2.0, remaining_hours=2.0, priority="Normal", position=0)
    db.add(t)
    db.flush()
    return t


def test_new_user_gets_none(db, model_path):
    user = add_user(db)
    assert predictor.predict_hours(db, add_new_task(db, user.id), model_path) is None


def test_user_below_threshold_gets_none(db, model_path):
    user = add_user(db)
    add_finished_tasks(db, user.id, predictor.MIN_COMPLETED_TASKS - 1)
    assert predictor.predict_hours(db, add_new_task(db, user.id), model_path) is None


def test_returns_positive_hours_with_model_and_history(db, model_path):
    user = add_user(db)
    add_finished_tasks(db, user.id, 25, ratio=1.5)
    hours = predictor.predict_hours(db, add_new_task(db, user.id), model_path)
    assert hours is not None and hours > 0
    assert hours * 4 == int(hours * 4)  # rounded to 0.25h
    assert hours > 2.0  # this user always takes 1.5× the estimate, so expect more than the 2h estimate


def test_history_only_counts_this_users_tasks(db, model_path):
    me, other = add_user(db, "me@example.com"), add_user(db, "other@example.com")
    add_finished_tasks(db, other.id, 30)
    assert predictor.predict_hours(db, add_new_task(db, me.id), model_path) is None


def test_missing_model_file_gives_none(db, tmp_path):
    user = add_user(db)
    add_finished_tasks(db, user.id, 25)
    assert predictor.predict_hours(db, add_new_task(db, user.id), tmp_path / "no_model.joblib") is None


def test_broken_model_file_gives_none(db, tmp_path):
    bad = tmp_path / "broken.joblib"
    bad.write_bytes(b"not a model")
    user = add_user(db)
    add_finished_tasks(db, user.id, 25)
    assert predictor.predict_hours(db, add_new_task(db, user.id), bad) is None


def _signup_and_plan(client):
    r = client.post("/auth/signup", json={"name": "Asha", "email": "asha@example.com", "password": "password123"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    deadline = (date.today() + timedelta(days=200)).isoformat()
    gid = client.post("/goals", headers=h, json={"title": "Learn guitar", "deadline": deadline,
                                                 "daily_available_hours": 2, "available_days": [1, 2, 3, 4, 5]}).json()["id"]
    assert client.post(f"/goals/{gid}/decompose", headers=h).status_code == 200
    return h, gid, r.json()["user"]["id"]


def test_app_works_when_model_file_is_missing(db, monkeypatch, tmp_path):
    monkeypatch.setattr(predictor, "MODEL_PATH", tmp_path / "missing.joblib")
    with TestClient(main.app) as client:
        h, gid, user_id = _signup_and_plan(client)
        with SessionLocal() as s:
            add_finished_tasks(s, user_id, 25)
            s.commit()
        assert client.post(f"/goals/{gid}/schedule", headers=h, json={"excluded_task_ids": []}).status_code == 200
        tasks = client.get(f"/goals/{gid}/tasks", headers=h).json()
        assert all(t["predicted_hours"] is None for t in tasks)  # fell back to the AI estimate
        assert all(t["remaining_hours"] == t["initial_estimated_hours"] for t in tasks)


def test_schedule_uses_predicted_hours_when_available(db, monkeypatch, model_path):
    monkeypatch.setattr(predictor, "MODEL_PATH", model_path)
    with TestClient(main.app) as client:
        h, gid, user_id = _signup_and_plan(client)
        with SessionLocal() as s:
            add_finished_tasks(s, user_id, 25)
            s.commit()
        assert client.post(f"/goals/{gid}/schedule", headers=h, json={"excluded_task_ids": []}).status_code == 200
        tasks = client.get(f"/goals/{gid}/tasks", headers=h).json()
        assert all(t["predicted_hours"] and t["predicted_hours"] > 0 for t in tasks)
        assert all(t["remaining_hours"] == t["predicted_hours"] for t in tasks)  # scheduler works from the prediction
        # the initial AI estimate is kept separately
        assert any(t["initial_estimated_hours"] != t["predicted_hours"] for t in tasks)
        planned = sum(a["planned_hours"] for a in client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"])
        assert planned == pytest.approx(sum(t["predicted_hours"] for t in tasks))


def test_estimates_endpoint_counts_only_my_finished_tasks(db, monkeypatch, model_path):
    monkeypatch.setattr(predictor, "MODEL_PATH", model_path)
    with TestClient(main.app) as client:
        h, _, user_id = _signup_and_plan(client)
        assert client.get("/users/me/estimates", headers=h).json() == {
            "finished_tasks": 0, "threshold": 20, "model_ready": True, "model_synthetic": True}
        with SessionLocal() as s:
            add_finished_tasks(s, user_id, 23)
            add_finished_tasks(s, add_user(s, "someone@example.com").id, 30)  # another user's tasks don't count
            s.commit()
        assert client.get("/users/me/estimates", headers=h).json()["finished_tasks"] == 23
        assert client.get("/users/me/estimates").status_code == 401  # needs login


def test_estimates_endpoint_without_model(db, monkeypatch, tmp_path):
    monkeypatch.setattr(predictor, "MODEL_PATH", tmp_path / "missing.joblib")
    with TestClient(main.app) as client:
        h, _, _ = _signup_and_plan(client)
        body = client.get("/users/me/estimates", headers=h).json()
        assert body["model_ready"] is False and body["model_synthetic"] is False
