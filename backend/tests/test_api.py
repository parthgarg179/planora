"""End-to-end API tests. Run from backend/:  python -m pytest -q

Needs the packages in requirements.txt (FastAPI's TestClient uses httpx).
"""
from datetime import date, datetime, timedelta

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.routers import goals as goals_router  # noqa: E402
from app.services import planner  # noqa: E402

MON = date(2026, 11, 16)


@pytest.fixture()
def clock(monkeypatch):
    """Control 'today' and the time of day."""
    state = {"today": MON, "time": (9, 0)}

    def fake_today():
        return state["today"]

    def fake_now():
        h, m = state["time"]
        d = state["today"]
        return datetime(d.year, d.month, d.day, h, m)

    for module in (planner, goals_router):
        monkeypatch.setattr(module, "today", fake_today)
    monkeypatch.setattr(planner, "now", fake_now)
    return state


@pytest.fixture()
def client(clock):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(main.app) as c:
        yield c


def signup(client, email="a@example.com"):
    r = client.post("/auth/signup", json={"name": "Asha", "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_goal(client, h, days=(1, 2, 3, 4, 5, 6), hours=2.0, deadline=MON + timedelta(days=27)):
    r = client.post("/goals", headers=h, json={"title": "Learn guitar", "deadline": deadline.isoformat(),
                                               "daily_available_hours": hours, "available_days": list(days)})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    d = client.post(f"/goals/{gid}/decompose", headers=h)
    assert d.status_code == 200, d.text
    body = d.json()
    assert all(c["ok"] for c in body["checks"])
    assert "generic template" in body["checks"][0]["label"]  # no API key in tests → fallback
    assert body["used_fallback"] is True
    return gid, body


def activate(client, h, gid, excluded=()):
    r = client.post(f"/goals/{gid}/schedule", headers=h, json={"excluded_task_ids": list(excluded)})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- auth ----
def test_signup_login_and_me(client):
    h = signup(client)
    assert client.get("/users/me", headers=h).json()["email"] == "a@example.com"
    assert client.post("/auth/login", json={"email": "A@example.com", "password": "password123"}).status_code == 200
    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Incorrect email or password."


def test_duplicate_signup_and_short_password(client):
    signup(client)
    assert client.post("/auth/signup", json={"name": "B", "email": "a@example.com", "password": "password123"}).status_code == 409
    r = client.post("/auth/signup", json={"name": "B", "email": "b@example.com", "password": "short"})
    assert r.status_code == 422 and "password" in r.json()["detail"]


def test_requires_login(client):
    assert client.get("/users/me").status_code == 401
    assert client.get("/goals").status_code == 401


def test_profile_and_password(client):
    h = signup(client)
    r = client.patch("/users/me", headers=h, json={"name": "Asha K", "photo_url": "data:image/png;base64,AAAA"})
    assert r.json()["name"] == "Asha K" and r.json()["photo_url"].startswith("data:image/")
    assert client.patch("/users/me", headers=h, json={"photo_url": None}).json()["photo_url"] is None
    assert client.post("/users/me/password", headers=h, json={"current_password": "wrong", "new_password": "newpassword1"}).status_code == 400
    assert client.post("/users/me/password", headers=h, json={"current_password": "password123", "new_password": "newpassword1"}).status_code == 204
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "newpassword1"}).status_code == 200


def test_users_cannot_see_each_others_goals(client):
    h1 = signup(client, "one@example.com")
    gid, _ = make_goal(client, h1)
    h2 = signup(client, "two@example.com")
    assert client.get(f"/goals/{gid}", headers=h2).status_code == 404
    assert client.get(f"/goals/{gid}/tasks", headers=h2).status_code == 404


# ---------------------------------------------------------------- planning ----
def test_create_goal_and_schedule(client):
    h = signup(client)
    gid, body = make_goal(client, h)
    optional = [t["id"] for t in body["tasks"] if t["optional"]]
    res = activate(client, h, gid, optional)
    assert res["goal"]["status"] == "active" and res["status"]["feasible"]

    sched = client.get(f"/goals/{gid}/schedule", headers=h).json()
    per_day = {}
    for a in sched["assignments"]:
        per_day[a["date"]] = per_day.get(a["date"], 0) + a["planned_hours"]
        assert date.fromisoformat(a["date"]).isoweekday() != 7  # never on Sunday
    assert max(per_day.values()) <= 2
    tasks = {t["id"]: t for t in client.get(f"/goals/{gid}/tasks", headers=h).json()}
    assert all(tasks[i]["status"] == "dropped" for i in optional)
    assert client.get("/goals?status=active", headers=h).json()[0]["id"] == gid


def test_non_optional_task_cannot_be_excluded(client):
    h = signup(client)
    gid, body = make_goal(client, h)
    core = next(t["id"] for t in body["tasks"] if not t["optional"])
    assert client.post(f"/goals/{gid}/schedule", headers=h, json={"excluded_task_ids": [core]}).status_code == 400


def test_new_goal_archives_old_one(client):
    h = signup(client)
    g1, _ = make_goal(client, h)
    activate(client, h, g1)
    g2, _ = make_goal(client, h)
    activate(client, h, g2)
    active = client.get("/goals?status=active", headers=h).json()
    assert [g["id"] for g in active] == [g2]


def test_review_partial_redistributes_and_keeps_history(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    today_items = [a for a in client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"] if a["date"] == MON.isoformat()]
    assert today_items
    items = [{"task_id": a["task_id"], "status": "partial", "actual_hours_spent": 0.5, "remaining_hours": 3} for a in today_items]
    r = client.post(f"/goals/{gid}/daily-review", headers=h, json={"date": MON.isoformat(), "items": items})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2

    sched = client.get(f"/goals/{gid}/schedule", headers=h).json()
    kept = [a for a in sched["assignments"] if a["date"] == MON.isoformat()]
    assert kept == today_items  # today's plan is kept as history
    task = next(t for t in client.get(f"/goals/{gid}/tasks", headers=h).json() if t["id"] == today_items[0]["task_id"])
    assert task["status"] == "in_progress" and task["remaining_hours"] == 3 and task["actual_hours"] == 0.5
    # second review for the same day is refused
    assert client.post(f"/goals/{gid}/daily-review", headers=h, json={"date": MON.isoformat(), "items": items}).status_code == 409


def test_review_must_cover_every_planned_task(client):
    h = signup(client)
    gid, _ = make_goal(client, h, hours=4)
    activate(client, h, gid)
    today_items = [a for a in client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"] if a["date"] == MON.isoformat()]
    if len(today_items) < 2:
        pytest.skip("needs two tasks on day one")
    one = [{"task_id": today_items[0]["task_id"], "status": "completed", "actual_hours_spent": 1}]
    assert client.post(f"/goals/{gid}/daily-review", headers=h, json={"date": MON.isoformat(), "items": one}).status_code == 400


def test_missed_days_can_be_reviewed_then_expire(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)

    clock["today"] = MON + timedelta(days=2)  # Wednesday: Mon and Tue were never reviewed
    pending = client.get(f"/goals/{gid}/pending-reviews", headers=h).json()["dates"]
    assert pending[:2] == [MON.isoformat(), (MON + timedelta(days=1)).isoformat()]
    kinds = [n["kind"] for n in client.get("/notifications", headers=h).json()["items"]]
    assert kinds.count("missed_review") == 2

    clock["today"] = MON + timedelta(days=5)  # Saturday: Monday is now past the 3-day window
    client.get("/goals?status=active", headers=h)
    pending = client.get(f"/goals/{gid}/pending-reviews", headers=h).json()["dates"]
    assert MON.isoformat() not in pending
    reviews = client.get(f"/goals/{gid}/daily-reviews", headers=h).json()
    assert reviews[0]["date"] == MON.isoformat() and reviews[0]["items"][0]["status"] == "not_completed"
    titles = [u["title"] for u in client.get(f"/goals/{gid}/updates", headers=h).json()]
    assert any("missed reviews closed" in t for t in titles)


def test_review_reminder_after_reminder_time(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    clock["time"] = (21, 0)
    assert "review_reminder" not in [n["kind"] for n in client.get("/notifications", headers=h).json()["items"]]
    clock["time"] = (21, 31)
    data = client.get("/notifications", headers=h).json()
    assert [n["kind"] for n in data["items"]].count("review_reminder") == 1
    client.get("/notifications", headers=h)  # not duplicated
    assert [n["kind"] for n in client.get("/notifications", headers=h).json()["items"]].count("review_reminder") == 1
    assert client.post("/notifications/read-all", headers=h).status_code == 204
    assert client.get("/notifications", headers=h).json()["unread"] == 0


def test_infeasible_plan_fix_options_and_consent(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h, hours=0.5, deadline=MON + timedelta(days=2))  # 1.5h available, 5h of work
    st = activate(client, h, gid)["status"]
    assert not st["feasible"] and st["shortfall_hours"] > 0
    opts = client.get(f"/goals/{gid}/fix-options", headers=h).json()["options"]
    kinds = {o["kind"]: o for o in opts}
    assert "extend_deadline" in kinds
    kinds_notes = [n["kind"] for n in client.get("/notifications", headers=h).json()["items"]]
    assert "deadline_risk" in kinds_notes

    if "increase_hours" in kinds:
        no = client.post(f"/goals/{gid}/adjust", headers=h, json={"kind": "increase_hours", "value": kinds["increase_hours"]["value"], "consent": False})
        assert no.status_code == 400
    ok = client.post(f"/goals/{gid}/adjust", headers=h, json={"kind": "extend_deadline", "value": kinds["extend_deadline"]["value"]})
    assert ok.status_code == 200 and ok.json()["status"]["feasible"]


def test_preferences_replan(client):
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    r = client.patch(f"/goals/{gid}", headers=h, json={"daily_available_hours": 3, "available_days": [1, 3, 5], "reminder_time": "20:00"})
    assert r.status_code == 200, r.text
    assert r.json()["goal"]["available_days"] == [1, 3, 5] and r.json()["version"] == 2
    for a in client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"]:
        if a["date"] >= MON.isoformat():
            assert date.fromisoformat(a["date"]).isoweekday() in (1, 3, 5)


def test_task_progress_and_subtasks(client):
    h = signup(client)
    gid, body = make_goal(client, h)
    activate(client, h, gid)
    tid = body["tasks"][0]["id"]
    subs = [{"title": s["title"], "done": True} for s in body["tasks"][0]["subtasks"]]
    assert client.patch(f"/tasks/{tid}", headers=h, json={"subtasks": subs}).json()["subtasks"][0]["done"]
    r = client.post(f"/tasks/{tid}/progress", headers=h, json={"actual_hours_spent": 1, "remaining_hours": 0})
    assert r.status_code == 200 and r.json()["task"]["status"] == "done"
    sched = client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"]
    assert all(a["task_id"] != tid for a in sched if a["date"] > MON.isoformat())


def test_frontend_is_served(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    page = client.get("/app/index.html")
    assert page.status_code == 200 and page.headers["cache-control"] == "no-cache"  # never a stale copy
