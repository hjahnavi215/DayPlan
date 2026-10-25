"""
Tests for dayplan/storage.py.
Validates JSON export/import round-tripping and graceful error handling on malformed files.
"""

from datetime import date, time
import json
import pytest

from dayplan.history import DurationHistoryTracker
from dayplan.models import DayPlanConfig, FixedCommitment, Priority, Task, TaskStatus
from dayplan.storage import StorageManager


def test_14_json_export_import_roundtrip():
    """14. JSON export/import round-trips correctly."""
    config = DayPlanConfig(
        planning_date=date(2026, 10, 25),
        day_start=time(8, 30),
        day_end=time(17, 0),
        break_duration_minutes=20,
        break_frequency_minutes=60,
        fixed_commitments=[
            FixedCommitment(id="FC-1", title="Team Meeting", start_time=time(11, 0), end_time=time(12, 0))
        ],
    )
    tasks = [
        Task(
            id="T-1",
            title="Design Schema",
            description="DB schema design",
            duration_minutes=75,
            priority=Priority.CRITICAL,
            deadline=time(16, 0),
            category="Engineering",
        ),
        Task(
            id="T-2",
            title="Implement Migration",
            duration_minutes=45,
            priority=Priority.HIGH,
            dependencies=["T-1"],
            status=TaskStatus.PENDING,
        ),
    ]
    history = DurationHistoryTracker()
    history.record_completion("T-0", "Prior task", "Engineering", 30, 40)

    # Export
    json_text = StorageManager.export_to_json(config, tasks, history)
    assert isinstance(json_text, str)
    assert "Design Schema" in json_text

    # Import
    success, res_config, res_tasks, res_history, errors = StorageManager.import_from_json(json_text)
    assert success is True
    assert errors == []
    assert res_config is not None
    assert res_config.day_start == time(8, 30)
    assert len(res_config.fixed_commitments) == 1

    assert res_tasks is not None
    assert len(res_tasks) == 2
    assert res_tasks[0].id == "T-1"
    assert res_tasks[0].priority == Priority.CRITICAL

    assert res_history is not None
    assert len(res_history.records) == 1


def test_15_malformed_imports_rejected_without_crashing():
    """15. Malformed imports are rejected without crashing the application."""
    # 1. Empty string
    success, config, tasks, history, errors = StorageManager.import_from_json("")
    assert success is False
    assert any("empty" in e.lower() for e in errors)

    # 2. Syntax error / corrupted JSON
    corrupted_json = '{"version": "1.0", "tasks": [ {"id": "1", "title": incomplete'
    success, config, tasks, history, errors = StorageManager.import_from_json(corrupted_json)
    assert success is False
    assert any("invalid json format" in e.lower() for e in errors)

    # 3. Non-dict root
    array_json = '[1, 2, 3]'
    success, config, tasks, history, errors = StorageManager.import_from_json(array_json)
    assert success is False
    assert any("root element" in e.lower() for e in errors)

    # 4. Invalid task objects inside tasks array
    malformed_tasks_json = json.dumps({
        "config": {"day_start": "09:00:00", "day_end": "17:00:00"},
        "tasks": [
            "not a dictionary",
            {"id": "T-1", "title": "", "duration_minutes": -50},  # Invalid task values
        ]
    })
    success, config, tasks, history, errors = StorageManager.import_from_json(malformed_tasks_json)
    assert success is False
    assert len(errors) >= 2
