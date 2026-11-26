"""Spec test scenarios (SPEC step 3) that test_api.py didn't cover yet:
every task completed, a full day missed, backlog that fits vs exceeds, the daily cap
across many replans, completed tasks stay completed, and user A can't touch user B's data.

Same setup as test_api.py: fixed date, test DB, fallback plan (never calls Gemini).
"""
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
from tests.test_api import MON, activate, client, clock, make_goal, signup  # noqa: E402,F401  (fixtures)


# ---------------------------------------------------------------- helpers ----
def schedule(client, h, gid):
    return client.get(f"/goals/{gid}/schedule", headers=h).json()["assignments"]


def tasks(client, h, gid):
    return {t["id"]: t for t in client.get(f"/goals/{gid}/tasks", headers=h).json()}


def day_items(client, h, gid, d: date):
    return [a for a in schedule(client, h, gid) if a["date"] == d.isoformat()]


def review(client, h, gid, d: date, items):
    r = client.post(f"/goals/{gid}/daily-review", headers=h, json={"date": d.isoformat(), "items": items})
    assert r.status_code == 200, r.text
    return r.json()


def complete_all(items):
    return [{"task_id": a["task_id"], "status": "completed", "actual_hours_spent": a["planned_hours"]} for a in items]


def assert_plan_respects_limits(client, h, gid, from_day: date, hours: float, days: set[int]):
    """From `from_day` on: never more than `hours` a day, and only on working days (0=Sun … 6=Sat)."""
    per_day = {}
    for a in schedule(client, h, gid):
        if a["date"] >= from_day.isoformat():
            per_day[a["date"]] = per_day.get(a["date"], 0) + a["planned_hours"]
    for d, total in per_day.items():
        assert total <= hours + 1e-9, f"{d}: {total}h planned, limit {hours}h"
        assert date.fromisoformat(d).isoweekday() % 7 in days, f"{d} is not a working day"


def notification_kinds(client, h):
    return [n["kind"] for n in client.get("/notifications", headers=h).json()["items"]]


# ---------------------------------------------------------------- every task completed ----
def test_every_task_completed(client, clock):
    """Do exactly what's planned every day until nothing is left."""
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    deadline = MON + timedelta(days=27)

    for _ in range(40):
        items = day_items(client, h, gid, clock["today"])
        if items:
            review(client, h, gid, clock["today"], complete_all(items))
        if all(t["status"] in ("done", "dropped") for t in tasks(client, h, gid).values()):
            break
        clock["today"] += timedelta(days=1)
    else:
        pytest.fail("plan never finished")

    assert clock["today"] <= deadline  # done on time
    assert all(t["remaining_hours"] == 0 for t in tasks(client, h, gid).values())
    st = client.get(f"/goals/{gid}/status", headers=h).json()
    assert st["remaining_hours"] == 0 and st["feasible"]
    assert not [a for a in schedule(client, h, gid) if a["date"] > clock["today"].isoformat()]  # nothing left planned
    assert client.get(f"/goals/{gid}/pending-reviews", headers=h).json()["dates"] == []
    assert "deadline_risk" not in notification_kinds(client, h)


# ---------------------------------------------------------------- full day missed ----
def test_full_day_missed_moves_all_its_work_later(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    before = sum(t["remaining_hours"] for t in tasks(client, h, gid).values() if t["status"] != "dropped")
    monday = day_items(client, h, gid, MON)
    planned = sum(a["planned_hours"] for a in monday)

    res = review(client, h, gid, MON, [{"task_id": a["task_id"], "status": "not_completed"} for a in monday])
    assert res["backlog_hours"] == planned  # the whole day becomes backlog
    after = tasks(client, h, gid)
    assert sum(t["remaining_hours"] for t in after.values() if t["status"] != "dropped") == before  # nothing lost
    assert all(after[a["task_id"]]["actual_hours"] == 0 for a in monday)

    assert day_items(client, h, gid, MON) == monday  # Monday's plan is kept as history
    later = [a for a in schedule(client, h, gid) if a["date"] > MON.isoformat()]
    assert sum(a["planned_hours"] for a in later) == pytest.approx(before)  # all open work is planned again
    assert_plan_respects_limits(client, h, gid, MON + timedelta(days=1), 2.0, {1, 2, 3, 4, 5, 6})


def test_full_day_never_reviewed_is_closed_as_missed(client, clock):
    """No review at all for Monday: after the 3-day window it counts as not done and moves later."""
    h = signup(client)
    gid, _ = make_goal(client, h)
    activate(client, h, gid)
    monday = day_items(client, h, gid, MON)
    clock["today"] = MON + timedelta(days=4)  # Friday: Monday is past the window
    client.get("/notifications", headers=h)  # opening the app runs the time-based checks
    hist = client.get(f"/goals/{gid}/daily-reviews", headers=h).json()
    closed = next(r for r in hist if r["date"] == MON.isoformat())
    assert {i["task_id"] for i in closed["items"]} == {a["task_id"] for a in monday}
    assert all(i["status"] == "not_completed" for i in closed["items"])
    # Monday's work is planned again from today, inside the limits
    later_ids = {a["task_id"] for a in schedule(client, h, gid) if a["date"] >= clock["today"].isoformat()}
    assert {a["task_id"] for a in monday} <= later_ids
    assert_plan_respects_limits(client, h, gid, clock["today"], 2.0, {1, 2, 3, 4, 5, 6})


# ---------------------------------------------------------------- backlog fits vs exceeds ----
def test_backlog_that_fits_keeps_plan_on_time(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h, deadline=MON + timedelta(days=60))  # lots of spare time
    activate(client, h, gid)
    monday = day_items(client, h, gid, MON)
    items = [{"task_id": a["task_id"], "status": "partial", "actual_hours_spent": 0.5,
              "remaining_hours": tasks(client, h, gid)[a["task_id"]]["remaining_hours"] + 1} for a in monday]
    res = review(client, h, gid, MON, items)
    assert res["backlog_hours"] > 0
    assert res["status"]["feasible"]
    assert date.fromisoformat(res["status"]["projected_finish"]) <= MON + timedelta(days=60)
    assert "deadline_risk" not in notification_kinds(client, h)
    updates = client.get(f"/goals/{gid}/updates", headers=h).json()
    assert not updates[0]["bad"]


def test_backlog_that_exceeds_is_flagged_not_squeezed(client, clock):
    h = signup(client)
    deadline = MON + timedelta(days=13)
    gid, _ = make_goal(client, h, deadline=deadline)
    assert activate(client, h, gid)["status"]["feasible"]  # fits at the start
    monday = day_items(client, h, gid, MON)
    items = [{"task_id": a["task_id"], "status": "partial", "actual_hours_spent": 0.5,
              "remaining_hours": tasks(client, h, gid)[a["task_id"]]["remaining_hours"] + 20} for a in monday]
    res = review(client, h, gid, MON, items)

    st = res["status"]
    assert not st["feasible"] and st["shortfall_hours"] > 0
    assert date.fromisoformat(st["projected_finish"]) > deadline  # overflow is projected past the deadline
    # never squeezed in: still at most 2h a day on working days, including the days after the deadline
    assert_plan_respects_limits(client, h, gid, MON + timedelta(days=1), 2.0, {1, 2, 3, 4, 5, 6})
    assert any(a["date"] > deadline.isoformat() for a in schedule(client, h, gid))
    assert "deadline_risk" in notification_kinds(client, h)
    assert client.get(f"/goals/{gid}/updates", headers=h).json()[0]["bad"]
    # deadline and hours are unchanged until the user picks a fix
    goal = client.get(f"/goals/{gid}", headers=h).json()
    assert goal["deadline"] == deadline.isoformat() and goal["daily_available_hours"] == 2.0
    assert client.get(f"/goals/{gid}/fix-options", headers=h).json()["options"]


# ---------------------------------------------------------------- daily cap across replans ----
def test_daily_cap_never_exceeded_across_many_replans(client, clock):
    """Two weeks of mixed reviews (done / partly done with extra work / not done) plus a preference change."""
    h = signup(client)
    hours, days = 3.0, {1, 2, 3, 4, 5}
    gid, _ = make_goal(client, h, days=sorted(days), hours=hours, deadline=MON + timedelta(days=40))
    activate(client, h, gid)
    for i in range(14):
        today = clock["today"]
        items = day_items(client, h, gid, today)
        if items:
            out = []
            for j, a in enumerate(items):
                kind = ("completed", "partial", "not_completed")[(i + j) % 3]
                rem = tasks(client, h, gid)[a["task_id"]]["remaining_hours"] + 1.5
                out.append({"task_id": a["task_id"], "status": kind, "actual_hours_spent": 1.0, "remaining_hours": rem})
            review(client, h, gid, today, out)
            assert_plan_respects_limits(client, h, gid, today + timedelta(days=1), hours, days)
        if i == 6:  # change preferences mid-way
            hours, days = 2.5, {1, 3, 5, 6}
            r = client.patch(f"/goals/{gid}", headers=h, json={"daily_available_hours": hours, "available_days": sorted(days)})
            assert r.status_code == 200, r.text
            start = today + timedelta(days=1) if items else today
            assert_plan_respects_limits(client, h, gid, start, hours, days)
        clock["today"] += timedelta(days=1)


# ---------------------------------------------------------------- completed stays completed ----
def test_completed_tasks_stay_completed(client, clock):
    h = signup(client)
    gid, _ = make_goal(client, h, hours=4)
    activate(client, h, gid)
    monday = day_items(client, h, gid, MON)
    first = monday[0]["task_id"]
    items = complete_all(monday[:1]) + [{"task_id": a["task_id"], "status": "not_completed"} for a in monday[1:]]
    review(client, h, gid, MON, items)
    done = tasks(client, h, gid)[first]
    assert done["status"] == "done" and done["remaining_hours"] == 0

    def still_done():
        t = tasks(client, h, gid)[first]
        assert t["status"] == "done" and t["remaining_hours"] == 0 and t["actual_hours"] == done["actual_hours"]
        assert all(a["task_id"] != first for a in schedule(client, h, gid) if a["date"] > MON.isoformat())

    # replans of every kind: preferences, priority change, a later review, an expired review, a fix
    assert client.patch(f"/goals/{gid}", headers=h, json={"daily_available_hours": 3}).status_code == 200
    still_done()
    other = next(i for i in tasks(client, h, gid) if i != first)
    assert client.patch(f"/tasks/{other}", headers=h, json={"priority": "High"}).status_code == 200
    still_done()
    clock["today"] = MON + timedelta(days=1)
    tue = day_items(client, h, gid, clock["today"])
    review(client, h, gid, clock["today"], [{"task_id": a["task_id"], "status": "not_completed"} for a in tue])
    still_done()
    clock["today"] = MON + timedelta(days=6)  # Tuesday's follow-ups pass the window unreviewed
    client.get("/notifications", headers=h)
    still_done()
    opts = client.get(f"/goals/{gid}/fix-options", headers=h).json()["options"]
    ext = next((o for o in opts if o["kind"] == "extend_deadline"), None)
    if ext:
        assert client.post(f"/goals/{gid}/adjust", headers=h, json={"kind": "extend_deadline", "value": ext["value"]}).status_code == 200
        still_done()
    # Monday's history still says it was completed
    hist = client.get(f"/goals/{gid}/daily-reviews", headers=h).json()
    mon = next(r for r in hist if r["date"] == MON.isoformat())
    assert next(i for i in mon["items"] if i["task_id"] == first)["status"] == "completed"


# ---------------------------------------------------------------- users can't see each other's data ----
def test_user_b_cannot_read_or_change_user_a_data(client, clock):
    ha = signup(client, "a@example.com")
    gid, body = make_goal(client, ha)
    activate(client, ha, gid)
    tid = body["tasks"][0]["id"]
    clock["time"] = (22, 0)
    a_notes = client.get("/notifications", headers=ha).json()["items"]
    assert a_notes  # A has at least a review reminder
    a_task_before = tasks(client, ha, gid)[tid]

    hb = signup(client, "b@example.com")
    reads = ["", "/tasks", "/schedule", "/status", "/fix-options", "/updates", "/pending-reviews", "/daily-reviews"]
    for path in reads:
        assert client.get(f"/goals/{gid}{path}", headers=hb).status_code == 404, path
    writes = [
        ("patch", f"/goals/{gid}", {"daily_available_hours": 8}),
        ("post", f"/goals/{gid}/decompose", None),
        ("post", f"/goals/{gid}/schedule", {"excluded_task_ids": []}),
        ("post", f"/goals/{gid}/adjust", {"kind": "extend_deadline", "value": "2027-01-01"}),
        ("post", f"/goals/{gid}/daily-review", {"date": MON.isoformat(), "items": []}),
        ("patch", f"/tasks/{tid}", {"title": "hacked"}),
        ("post", f"/tasks/{tid}/progress", {"actual_hours_spent": 1, "remaining_hours": 0}),
        ("post", f"/notifications/{a_notes[0]['id']}/read", None),
    ]
    for method, url, payload in writes:
        r = client.request(method.upper(), url, headers=hb, json=payload)
        assert r.status_code == 404, f"{method} {url} → {r.status_code}"

    # B's own lists don't include A's things
    assert client.get("/goals", headers=hb).json() == []
    assert client.get("/notifications", headers=hb).json()["items"] == []
    assert client.get("/users/me/estimates", headers=hb).json()["finished_tasks"] == 0
    # and A's data is untouched
    assert tasks(client, ha, gid)[tid] == a_task_before
    assert client.get(f"/goals/{gid}", headers=ha).json()["daily_available_hours"] == 2.0
    assert client.get("/notifications", headers=ha).json()["unread"] == len([n for n in a_notes if not n["read"]])
