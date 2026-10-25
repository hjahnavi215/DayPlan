"""
Tests for dayplan/models.py
"""

from datetime import date, datetime, time
import pytest

from dayplan.models import (
    DayPlanConfig,
    EnergyLevel,
    FixedCommitment,
    Priority,
    ScheduledBlock,
    Task,
    TaskStatus,
)


def test_task_validations():
    # Valid task
    t = Task(id="T-1", title="Write tests", duration_minutes=30)
    assert t.validate() == []
    assert not t.is_completed

    # Empty ID and title
    invalid_t = Task(id="", title="  ", duration_minutes=-10)
    errs = invalid_t.validate()
    assert any("ID cannot be empty" in e for e in errs)
    assert any("title cannot be empty" in e for e in errs)
    assert any("positive integer" in e for e in errs)

    # Self-dependency
    self_dep = Task(id="T-2", title="Circular", duration_minutes=30, dependencies=["T-2"])
    assert any("cannot depend on itself" in e for e in self_dep.validate())

    # Invalid earliest start after deadline
    bad_times = Task(
        id="T-3",
        title="Bad times",
        duration_minutes=30,
        earliest_start=time(16, 0),
        deadline=time(14, 0),
    )
    assert any("must be before deadline" in e for e in bad_times.validate())


def test_task_dict_roundtrip():
    t = Task(
        id="T-100",
        title="Review Code",
        description="PR #42 review",
        duration_minutes=45,
        priority=Priority.HIGH,
        deadline=time(17, 0),
        earliest_start=time(10, 0),
        dependencies=["T-99"],
        status=TaskStatus.IN_PROGRESS,
        actual_duration_minutes=50,
        category="Engineering",
    )
    d = t.to_dict()
    restored = Task.from_dict(d)

    assert restored.id == t.id
    assert restored.title == t.title
    assert restored.description == t.description
    assert restored.duration_minutes == t.duration_minutes
    assert restored.priority == t.priority
    assert restored.deadline == t.deadline
    assert restored.earliest_start == t.earliest_start
    assert restored.dependencies == t.dependencies
    assert restored.status == t.status
    assert restored.actual_duration_minutes == t.actual_duration_minutes
    assert restored.category == t.category


def test_fixed_commitment_validation():
    # Valid
    c = FixedCommitment(id="C-1", title="Lunch", start_time=time(12, 0), end_time=time(13, 0))
    assert c.validate() == []

    # Invalid start >= end
    bad_c = FixedCommitment(id="C-2", title="Impossible", start_time=time(14, 0), end_time=time(13, 0))
    assert any("must be earlier than end time" in e for e in bad_c.validate())


def test_config_validation():
    config = DayPlanConfig(
        day_start=time(9, 0),
        day_end=time(17, 0),
        break_duration_minutes=15,
        break_frequency_minutes=90,
    )
    assert config.validate() == []

    # Inverted day hours (overnight unsupported)
    bad_config = DayPlanConfig(day_start=time(20, 0), day_end=time(8, 0))
    assert any("earlier than day end" in e for e in bad_config.validate())
