"""
Tests for dayplan/history.py.
Validates historical task duration tracking, sample thresholds, and calibration advice.
"""

import pytest
from dayplan.history import DurationHistoryTracker, TaskHistoryRecord


def test_17_historical_duration_estimates_with_insufficient_and_sufficient_data():
    """17. Historical duration estimates behave correctly with insufficient and sufficient data."""
    tracker = DurationHistoryTracker()

    # Case A: 0 samples
    stats = tracker.get_category_stats("Coding")
    assert stats["has_sufficient_history"] is False
    assert stats["sample_count"] == 0
    suggested, reason = tracker.suggest_duration("Coding", 60)
    assert suggested == 60
    assert "insufficient" in reason.lower()

    # Case B: 2 samples (< MIN_SAMPLE_SIZE = 3)
    tracker.record_completion(task_id="T-1", title="Task 1", category="Coding", planned_minutes=60, actual_minutes=90)
    tracker.record_completion(task_id="T-2", title="Task 2", category="Coding", planned_minutes=30, actual_minutes=45)

    stats = tracker.get_category_stats("Coding")
    assert stats["has_sufficient_history"] is False
    assert stats["sample_count"] == 2
    suggested, reason = tracker.suggest_duration("Coding", 60)
    assert suggested == 60  # Still uses original estimate

    # Case C: 3rd sample added (>= MIN_SAMPLE_SIZE = 3)
    # Total planned: 60 + 30 + 60 = 150m. Total actual: 90 + 45 + 90 = 225m.
    # Multiplier: 225 / 150 = 1.5x (50% overrun)
    tracker.record_completion(task_id="T-3", title="Task 3", category="Coding", planned_minutes=60, actual_minutes=90)

    stats = tracker.get_category_stats("Coding")
    assert stats["has_sufficient_history"] is True
    assert stats["sample_count"] == 3
    assert stats["avg_multiplier"] == 1.5
    assert "50% longer" in stats["message"]

    suggested, reason = tracker.suggest_duration("Coding", 60)
    assert suggested == 90  # 60 * 1.5 = 90
    assert "Adjusted from 60m to 90m" in reason
    assert "1.5x factor" in reason


def test_history_serialization_roundtrip():
    tracker = DurationHistoryTracker()
    tracker.record_completion("T-1", "Task 1", "Design", 40, 50)
    tracker.record_completion("T-2", "Task 2", "Design", 60, 60)

    data = tracker.to_dict_list()
    restored = DurationHistoryTracker.from_dict_list(data)

    assert len(restored.records) == 2
    assert restored.records[0].task_id == "T-1"
    assert restored.records[0].category == "Design"
    assert restored.records[0].variance_minutes == 10
