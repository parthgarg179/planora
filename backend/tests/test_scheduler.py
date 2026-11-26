"""Unit tests for the pure scheduler (no database needed)."""
from datetime import date, timedelta

from app.services.scheduler import PlanSettings, SchedTask, build_schedule, evaluate, fix_options, js_weekday

MON = date(2026, 11, 16)  # a Monday
WEEKDAYS = frozenset({1, 2, 3, 4, 5})


def settings(hours=2.0, days=WEEKDAYS, deadline=MON + timedelta(days=11)):
    return PlanSettings(hours, frozenset(days), deadline)


def day_totals(plan):
    return {d: sum(h for _, h in items) for d, items in plan.items()}


def test_js_weekday():
    assert js_weekday(MON) == 1
    assert js_weekday(MON + timedelta(days=6)) == 0  # Sunday


def test_never_exceeds_daily_hours():
    tasks = [SchedTask(i, 3.5) for i in range(1, 6)]
    res = build_schedule(settings(2), tasks, MON)
    assert all(total <= 2 + 1e-9 for total in day_totals(res.plan).values())


def test_only_working_days_used():
    res = build_schedule(settings(2), [SchedTask(1, 12)], MON)
    assert all(js_weekday(d) in WEEKDAYS for d in res.plan)


def test_prerequisites_come_first():
    tasks = [SchedTask(1, 2, priority="Low"), SchedTask(2, 2, priority="High", dependencies=(1,))]
    res = build_schedule(settings(2), tasks, MON)
    first_day_of = {}
    for d in sorted(res.plan):
        for tid, _ in res.plan[d]:
            first_day_of.setdefault(tid, d)
    assert first_day_of[1] < first_day_of[2]


def test_higher_priority_first_when_both_ready():
    tasks = [SchedTask(1, 2, priority="Low", position=0), SchedTask(2, 2, priority="High", position=1)]
    res = build_schedule(settings(2), tasks, MON)
    assert res.plan[MON] == [(2, 2.0)]


def test_in_progress_task_is_continued_first():
    tasks = [SchedTask(1, 2, priority="High"), SchedTask(2, 1, priority="Low", status="in_progress")]
    res = build_schedule(settings(2), tasks, MON)
    assert res.plan[MON][0][0] == 2


def test_done_and_dropped_tasks_are_not_scheduled():
    tasks = [SchedTask(1, 2, status="done"), SchedTask(2, 2, status="dropped"), SchedTask(3, 2, dependencies=(1,))]
    res = build_schedule(settings(2), tasks, MON)
    scheduled = {tid for items in res.plan.values() for tid, _ in items}
    assert scheduled == {3}


def test_backlog_is_spread_not_dumped_on_one_day():
    # 10h of work, 2h/day: needs 5 working days, never more than 2h on any day
    res = build_schedule(settings(2), [SchedTask(1, 6), SchedTask(2, 4)], MON)
    assert len(res.plan) == 5
    assert max(day_totals(res.plan).values()) == 2


def test_feasible_plan():
    st = evaluate(settings(2), [SchedTask(1, 10)], MON)  # 10 working days * 2h = 20h available
    assert st["feasible"] and st["capacity_days"] == 10 and st["capacity_hours"] == 20
    assert st["shortfall_hours"] == 0


def test_infeasible_plan_reports_shortfall_and_projection():
    st = evaluate(settings(2), [SchedTask(1, 25)], MON)
    assert not st["feasible"]
    assert st["shortfall_hours"] == 5
    assert st["projected_finish"] > settings().deadline


def test_dependencies_can_make_plan_late_even_with_enough_hours():
    # 2h/day: the chain needs 3 sequential days, deadline allows only 2 working days
    s = settings(2, deadline=MON + timedelta(days=1))
    tasks = [SchedTask(1, 2), SchedTask(2, 2, dependencies=(1,))]
    st = evaluate(s, tasks, MON)
    assert st["capacity_hours"] == 4 and st["remaining_hours"] == 4
    assert st["feasible"]  # exactly fits
    st2 = evaluate(s, tasks + [SchedTask(3, 0.5, dependencies=(2,))], MON)
    assert not st2["feasible"]


def test_no_working_days_is_unschedulable():
    st = evaluate(settings(2, days=frozenset()), [SchedTask(1, 2)], MON)
    assert not st["feasible"] and st["projected_finish"] is None


def test_fix_options_each_make_sense():
    tasks = [SchedTask(1, 21), SchedTask(2, 3, optional=True, title="Extra")]
    opts = {o["kind"]: o for o in fix_options(settings(2), tasks, MON)}
    assert opts["extend_deadline"]["result"]["feasible"]
    assert opts["increase_hours"]["needs_consent"] and opts["increase_hours"]["result"]["feasible"]
    assert opts["drop_optional"]["value"] == ["2"]
    assert "add_day" in opts


def test_fix_options_respect_hours_left_by_other_goals():
    tasks = [SchedTask(1, 21)]
    # other goals leave only 2.5h free on weekdays and nothing at the weekend
    room = {0: 0, 1: 2.5, 2: 2.5, 3: 2.5, 4: 2.5, 5: 2.5, 6: 0}
    opts = {o["kind"]: o for o in fix_options(settings(2), tasks, MON, room)}
    assert "add_day" not in opts  # Sat and Sun are full
    if "increase_hours" in opts:
        assert opts["increase_hours"]["value"] <= 2.5


def test_deterministic():
    tasks = [SchedTask(i, 1.5, priority=["High", "Low", "Normal"][i % 3], position=i) for i in range(10)]
    assert build_schedule(settings(2), tasks, MON).plan == build_schedule(settings(2), tasks, MON).plan
