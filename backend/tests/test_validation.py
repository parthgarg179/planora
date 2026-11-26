"""Unit tests for checking/repairing the AI breakdown."""
import pytest

from app.services.llm import fallback_plan
from app.services.validation import ValidationFailed, extract_json, topological_order, validate_plan


def plan(**overrides):
    data = {
        "milestones": [{"id": "m1", "name": "Basics"}],
        "tasks": [
            {"id": "t1", "title": "A", "milestone_id": "m1", "estimated_hours": 2, "priority": "high"},
            {"id": "t2", "title": "B", "milestone_id": "m1", "estimated_hours": 1, "dependencies": ["t1"]},
        ],
    }
    data.update(overrides)
    return data


def test_extract_json_from_fenced_reply():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```')["a"] == 1


def test_extract_json_rejects_garbage():
    with pytest.raises(ValidationFailed):
        extract_json("no json here")


def test_valid_plan_passes_and_normalises():
    p = validate_plan(plan())
    assert [t.key for t in p.tasks] == ["t1", "t2"]
    assert p.tasks[0].priority == "High"
    assert all(c["ok"] for c in p.checks)


def test_no_tasks_fails():
    with pytest.raises(ValidationFailed):
        validate_plan({"milestones": [], "tasks": []})


def test_unknown_and_self_dependencies_removed():
    data = plan()
    data["tasks"][1]["dependencies"] = ["t1", "t9", "t2"]
    p = validate_plan(data)
    assert p.tasks[1].dependencies == ["t1"]
    assert any("invalid dependency" in c["label"] for c in p.checks)


def test_cycles_are_broken():
    data = plan()
    data["tasks"][0]["dependencies"] = ["t2"]  # t1 -> t2 -> t1
    p = validate_plan(data)
    order = topological_order(p.tasks)
    for t in p.tasks:
        for d in t.dependencies:
            assert order.index(d) < order.index(t.key)
    assert any("cycle" in c["label"] for c in p.checks)


def test_bad_durations_get_defaults():
    data = plan()
    data["tasks"][0]["estimated_hours"] = -3
    data["tasks"][1]["estimated_hours"] = "lots"
    p = validate_plan(data)
    assert all(t.hours > 0 for t in p.tasks)
    assert any("default duration" in c["label"] for c in p.checks)


def test_huge_duration_is_capped():
    data = plan()
    data["tasks"][0]["estimated_hours"] = 999
    assert validate_plan(data).tasks[0].hours == 40


def test_unknown_milestone_goes_to_general():
    data = plan()
    data["tasks"][0]["milestone_id"] = "nope"
    p = validate_plan(data)
    assert any(m.name == "General" for m in p.milestones)


def test_duplicate_ids_renamed():
    data = plan()
    data["tasks"][1]["id"] = "t1"
    p = validate_plan(data)
    assert len({t.key for t in p.tasks}) == 2


def test_fallback_plan_is_valid_and_scaled():
    p = fallback_plan("Learn guitar", 40)
    assert len(p.tasks) == 10 and len(p.milestones) == 5
    assert 30 <= sum(t.hours for t in p.tasks) <= 36
    assert any(t.optional for t in p.tasks)
