"""
Comprehensive tests for dayplan/planner.py.
Covers core scheduling constraints, priority, deadlines, dependencies, cycles, and edge cases.
"""

from datetime import date, datetime, time, timedelta
import pytest

from dayplan.models import (
    DayPlanConfig,
    FixedCommitment,
    Priority,
    Task,
    TaskStatus,
)
from dayplan.planner import (
    ScheduleGenerator,
    detect_dependency_cycles,
    generate_schedule,
    get_available_free_slots,
)


@pytest.fixture
def base_config():
    return DayPlanConfig(
        planning_date=date(2026, 10, 25),
        day_start=time(9, 0),
        day_end=time(17, 0),
        break_duration_minutes=15,
        break_frequency_minutes=90,
    )


def test_1_tasks_scheduled_within_available_hours(base_config):
    """1. Tasks are scheduled within available hours."""
    tasks = [
        Task(id="T-1", title="Task 1", duration_minutes=60),
        Task(id="T-2", title="Task 2", duration_minutes=120),
    ]
    result = generate_schedule(tasks, base_config)

    day_start_dt = datetime.combine(base_config.planning_date, base_config.day_start)
    day_end_dt = datetime.combine(base_config.planning_date, base_config.day_end)

    assert len(result.task_blocks) == 2
    for block in result.blocks:
        assert block.start_dt >= day_start_dt
        assert block.end_dt <= day_end_dt


def test_2_high_priority_tasks_handled_appropriately(base_config):
    """2. High-priority tasks are handled appropriately."""
    tasks = [
        Task(id="T-LOW", title="Low Priority Task", duration_minutes=60, priority=Priority.LOW),
        Task(id="T-CRIT", title="Critical Priority Task", duration_minutes=60, priority=Priority.CRITICAL),
        Task(id="T-MED", title="Medium Priority Task", duration_minutes=60, priority=Priority.MEDIUM),
    ]
    result = generate_schedule(tasks, base_config)

    task_blocks = result.task_blocks
    assert len(task_blocks) == 3
    # The first task scheduled should be the Critical one
    assert task_blocks[0].task_id == "T-CRIT"
    assert task_blocks[0].start_time_str == "09:00"


def test_3_earlier_deadlines_considered(base_config):
    """3. Earlier deadlines are considered."""
    tasks = [
        Task(id="T-LATER", title="Due at 15:00", duration_minutes=60, deadline=time(15, 0), priority=Priority.MEDIUM),
        Task(id="T-EARLY", title="Due at 10:30", duration_minutes=60, deadline=time(10, 30), priority=Priority.MEDIUM),
    ]
    result = generate_schedule(tasks, base_config)

    task_blocks = result.task_blocks
    assert len(task_blocks) == 2
    # T-EARLY has urgent deadline, so it should be scheduled first
    assert task_blocks[0].task_id == "T-EARLY"
    assert task_blocks[0].start_time_str == "09:00"
    assert task_blocks[1].task_id == "T-LATER"


def test_7_dependencies_are_respected(base_config):
    """7. Dependencies are respected."""
    tasks = [
        Task(id="T-DEP", title="Child Task", duration_minutes=60, dependencies=["T-PARENT"]),
        Task(id="T-PARENT", title="Parent Task", duration_minutes=60),
    ]
    result = generate_schedule(tasks, base_config)

    task_blocks = result.task_blocks
    assert len(task_blocks) == 2

    parent_block = next(b for b in task_blocks if b.task_id == "T-PARENT")
    child_block = next(b for b in task_blocks if b.task_id == "T-DEP")

    # Child must start at or after parent finishes
    assert child_block.start_dt >= parent_block.end_dt


def test_8_dependency_cycles_detected(base_config):
    """8. Dependency cycles are detected."""
    tasks = [
        Task(id="T-A", title="Task A", duration_minutes=30, dependencies=["T-B"]),
        Task(id="T-B", title="Task B", duration_minutes=30, dependencies=["T-C"]),
        Task(id="T-C", title="Task C", duration_minutes=30, dependencies=["T-A"]),
        Task(id="T-INDEP", title="Independent Task", duration_minutes=45),
    ]

    has_cycle, cycle_ids = detect_dependency_cycles(tasks)
    assert has_cycle is True
    assert set(cycle_ids) == {"T-A", "T-B", "T-C"}

    result = generate_schedule(tasks, base_config)
    # The independent task should schedule cleanly
    assert any(b.task_id == "T-INDEP" for b in result.task_blocks)
    # The cyclic tasks must NOT be scheduled and flagged in warnings / unscheduled
    assert any("Dependency cycle detected" in w for w in result.warnings)
    unscheduled_ids = [t.id for t, _ in result.unscheduled_tasks]
    assert "T-A" in unscheduled_ids
    assert "T-B" in unscheduled_ids
    assert "T-C" in unscheduled_ids


def test_9_fixed_commitments_and_breaks_not_overlapped(base_config):
    """9. Fixed commitments and breaks are not overlapped."""
    base_config.fixed_commitments = [
        FixedCommitment(id="C-1", title="Lunch", start_time=time(12, 0), end_time=time(13, 0))
    ]
    tasks = [
        Task(id="T-1", title="Morning Work", duration_minutes=90),
        Task(id="T-2", title="Afternoon Work", duration_minutes=90),
    ]
    result = generate_schedule(tasks, base_config)

    # Check that commitment block exists
    comm_block = next(b for b in result.blocks if b.block_type == "commitment")
    assert comm_block.start_time_str == "12:00"
    assert comm_block.end_time_str == "13:00"

    # Ensure no other block overlaps with commitment
    for block in result.blocks:
        if block is not comm_block:
            assert block.end_dt <= comm_block.start_dt or block.start_dt >= comm_block.end_dt


def test_10_no_overlapping_blocks(base_config):
    """10. Overlapping tasks never appear in the final schedule."""
    tasks = [
        Task(id=f"T-{i}", title=f"Task {i}", duration_minutes=45)
        for i in range(1, 8)
    ]
    result = generate_schedule(tasks, base_config)

    sorted_blocks = sorted(result.blocks, key=lambda b: b.start_dt)
    for i in range(len(sorted_blocks) - 1):
        curr_b = sorted_blocks[i]
        next_b = sorted_blocks[i + 1]
        assert curr_b.end_dt <= next_b.start_dt, f"Overlap between {curr_b.title} and {next_b.title}"


def test_11_impossible_deadlines_reported_honestly(base_config):
    """11. Impossible deadlines are reported honestly."""
    tasks = [
        Task(id="T-IMPOSSIBLE", title="Impossible Task", duration_minutes=120, deadline=time(9, 30)),
    ]
    result = generate_schedule(tasks, base_config)

    # The task will be scheduled at 09:00-11:00, but flagged with warning and deadline_missed
    assert len(result.task_blocks) == 1
    block = result.task_blocks[0]
    assert block.deadline_missed is True
    assert any("missing its deadline" in w for w in result.warnings)


def test_12_empty_task_lists_work(base_config):
    """12. Empty task lists work without crashing."""
    result = generate_schedule([], base_config)
    assert result.task_blocks == []
    assert result.unscheduled_tasks == []
    assert result.warnings == []


def test_13_invalid_inputs_handled_safely(base_config):
    """13. Invalid inputs are handled safely."""
    tasks = [
        Task(id="", title="Empty ID", duration_minutes=30),
        Task(id="T-NEG", title="Negative duration", duration_minutes=-20),
        Task(id="T-VALID", title="Valid task", duration_minutes=45),
    ]
    result = generate_schedule(tasks, base_config)

    # Valid task is scheduled
    assert any(b.task_id == "T-VALID" for b in result.task_blocks)
    # Invalid tasks appear in unscheduled with validation failure
    unscheduled_reasons = {t.title: reason for t, reason in result.unscheduled_tasks}
    assert "Empty ID" in unscheduled_reasons
    assert "Negative duration" in unscheduled_reasons
    assert "Validation failure" in unscheduled_reasons["Empty ID"]


def test_18_day_with_no_remaining_available_time(base_config):
    """18. A day with no remaining available time is handled correctly."""
    # Effective start is at 18:00, but day ends at 17:00
    effective_start = datetime.combine(base_config.planning_date, time(18, 0))
    tasks = [
        Task(id="T-1", title="Too Late", duration_minutes=30),
    ]
    result = generate_schedule(tasks, base_config, effective_start_dt=effective_start)

    assert result.task_blocks == []
    assert len(result.unscheduled_tasks) == 1
    assert any("No remaining" in w for w in result.warnings)
