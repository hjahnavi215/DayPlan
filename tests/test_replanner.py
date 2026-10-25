"""
Tests for dayplan/replanner.py.
Covers completed task preservation, overruns/delays, unscheduled flagging, and diff comparisons.
"""

from datetime import date, datetime, time, timedelta
import pytest

from dayplan.models import (
    DayPlanConfig,
    Priority,
    Task,
    TaskStatus,
)
from dayplan.planner import generate_schedule
from dayplan.replanner import replan_schedule


@pytest.fixture
def plan_env():
    planning_date = date(2026, 10, 25)
    config = DayPlanConfig(
        planning_date=planning_date,
        day_start=time(9, 0),
        day_end=time(17, 0),
        break_duration_minutes=15,
        break_frequency_minutes=90,
    )
    return config, planning_date


def test_4_completed_tasks_preserved_after_replanning(plan_env):
    """4. Completed tasks remain completed after replanning."""
    config, p_date = plan_env

    tasks = [
        Task(id="T-1", title="First Task", duration_minutes=60, status=TaskStatus.COMPLETED, actual_duration_minutes=60),
        Task(id="T-2", title="Second Task", duration_minutes=60, status=TaskStatus.PENDING),
    ]

    initial_res = generate_schedule(tasks, config)
    # Replan at 10:30
    current_time = datetime.combine(p_date, time(10, 30))

    new_res, change_summary = replan_schedule(
        tasks=tasks,
        config=config,
        current_time=current_time,
        previous_result=initial_res,
        disruption_note="Periodic check-in",
    )

    # T-1 must be preserved and locked
    t1_block = next(b for b in new_res.blocks if b.task_id == "T-1")
    assert t1_block.is_locked is True
    assert t1_block.status == TaskStatus.COMPLETED
    assert "T-1" in change_summary.completed_preserved

    # T-2 scheduled from 10:30 onwards
    t2_block = next(b for b in new_res.blocks if b.task_id == "T-2")
    assert t2_block.start_dt >= current_time


def test_5_delayed_tasks_cause_recalculation(plan_env):
    """5. Delayed tasks cause remaining work to be recalculated."""
    config, p_date = plan_env

    t1 = Task(id="T-1", title="Task 1", duration_minutes=60)
    t2 = Task(id="T-2", title="Task 2", duration_minutes=60)
    initial_res = generate_schedule([t1, t2], config)

    # T-1 actually took 90 mins (overran by 30 mins) and completed at 10:30
    t1.status = TaskStatus.COMPLETED
    t1.actual_duration_minutes = 90

    current_time = datetime.combine(p_date, time(10, 30))
    new_res, change_summary = replan_schedule(
        tasks=[t1, t2],
        config=config,
        current_time=current_time,
        previous_result=initial_res,
        disruption_note="T-1 took 30m longer than estimated",
    )

    # T-2 was originally at 10:00, now should be moved to 10:30
    t2_block = next(b for b in new_res.blocks if b.task_id == "T-2")
    assert t2_block.start_time_str == "10:30"
    assert len(change_summary.moved_tasks) >= 1
    moved = next(m for m in change_summary.moved_tasks if m["task_id"] == "T-2")
    assert moved["shift_minutes"] == 30


def test_6_tasks_that_no_longer_fit_are_explicitly_flagged(plan_env):
    """6. Tasks that no longer fit are explicitly flagged."""
    config, p_date = plan_env
    # Day ends at 12:00 (only 3 hours total)
    config.day_end = time(12, 0)

    t1 = Task(id="T-1", title="High Priority", duration_minutes=120, priority=Priority.HIGH)
    t2 = Task(id="T-2", title="Low Priority", duration_minutes=120, priority=Priority.LOW)

    initial_res = generate_schedule([t1, t2], config)
    # T1 fits (09:00-11:00), T2 cannot fit before 12:00
    assert any(b.task_id == "T-1" for b in initial_res.task_blocks)
    unscheduled_ids = [t.id for t, _ in initial_res.unscheduled_tasks]
    assert "T-2" in unscheduled_ids


def test_16_schedule_comparisons_identify_added_removed_moved_completed(plan_env):
    """16. Schedule comparisons correctly identify added, removed, moved, and completed tasks."""
    config, p_date = plan_env

    t1 = Task(id="T-1", title="Completed Task", duration_minutes=60, status=TaskStatus.COMPLETED, actual_duration_minutes=60)
    t2 = Task(id="T-2", title="Moved Task", duration_minutes=60)
    t3 = Task(id="T-3", title="Removed Task", duration_minutes=60)

    initial_res = generate_schedule([t1, t2, t3], config)

    # In replan: T3 removed, T4 added, T2 moved due to delay
    t4 = Task(id="T-4", title="Newly Added Task", duration_minutes=30, priority=Priority.CRITICAL)
    current_time = datetime.combine(p_date, time(10, 30))

    new_res, change_summary = replan_schedule(
        tasks=[t1, t2, t4],
        config=config,
        current_time=current_time,
        previous_result=initial_res,
        disruption_note="Urgent task T-4 injected",
    )

    assert "T-1" in change_summary.completed_preserved
    assert "T-4" in change_summary.added_tasks
    assert "T-3" in change_summary.removed_tasks
    assert any(m["task_id"] == "T-2" for m in change_summary.moved_tasks)
