"""
End-to-end tests for all 7 reproducible demonstration scenarios.
"""

from datetime import date, datetime
import pytest

from dayplan.explanations import ExplanationEngine
from dayplan.planner import generate_schedule
from dayplan.presets import get_all_scenarios
from dayplan.replanner import replan_schedule


def test_scenario_1_normal_day():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["normal_day"]
    result = generate_schedule(sc.tasks, sc.config)

    assert len(result.task_blocks) == 5
    assert len(result.unscheduled_tasks) == 0
    assert any(b.block_type == "commitment" for b in result.blocks)
    assert any(b.block_type == "break" for b in result.blocks)


def test_scenario_2_missed_morning():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["missed_morning"]
    sim_dt = datetime.combine(sc.config.planning_date, sc.simulated_current_time)

    result = generate_schedule(sc.tasks, sc.config, effective_start_dt=sim_dt)

    # First task scheduled must be at or after 11:00
    first_task = result.task_blocks[0]
    assert first_task.start_dt >= sim_dt

    # The Critical demo prep task must be scheduled
    crit_block = next(b for b in result.task_blocks if b.task_id == "T-202")
    assert crit_block is not None


def test_scenario_3_task_overrun():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["task_overrun"]
    sim_dt = datetime.combine(sc.config.planning_date, sc.simulated_current_time)

    # Replan after T-301 took 120m instead of 60m
    result, diff = replan_schedule(
        tasks=sc.tasks,
        config=sc.config,
        current_time=sim_dt,
        disruption_note=sc.disruption_note,
    )

    # T-301 must be preserved and locked
    t301_block = next(b for b in result.blocks if b.task_id == "T-301")
    assert t301_block.is_locked is True
    assert t301_block.duration_minutes == 120

    # Downstream T-302 must start at or after 11:00
    t302_block = next(b for b in result.task_blocks if b.task_id == "T-302")
    assert t302_block.start_dt >= sim_dt


def test_scenario_4_urgent_addition():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["urgent_addition"]
    sim_dt = datetime.combine(sc.config.planning_date, sc.simulated_current_time)

    result, diff = replan_schedule(
        tasks=sc.tasks,
        config=sc.config,
        current_time=sim_dt,
        disruption_note=sc.disruption_note,
    )

    # T-403 (Critical) should be scheduled at 13:00
    t403_block = next(b for b in result.task_blocks if b.task_id == "T-403")
    assert t403_block.start_time_str == "13:00"
    assert "T-401" in diff.completed_preserved
    assert "T-402" in diff.completed_preserved


def test_scenario_5_blocked_prerequisite():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["blocked_prerequisite"]
    result = generate_schedule(sc.tasks, sc.config)

    unscheduled_ids = [t.id for t, _ in result.unscheduled_tasks]
    # Blocked task T-501 and dependent task T-502 must be unscheduled
    assert "T-501" in unscheduled_ids
    assert "T-502" in unscheduled_ids

    # Independent tasks T-503 and T-504 must be scheduled
    scheduled_ids = result.scheduled_task_ids
    assert "T-503" in scheduled_ids
    assert "T-504" in scheduled_ids


def test_scenario_6_impossible_deadline():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["impossible_deadline"]
    result = generate_schedule(sc.tasks, sc.config)

    t601_block = next(b for b in result.task_blocks if b.task_id == "T-601")
    assert t601_block.deadline_missed is True
    assert any("missing its deadline" in w for w in result.warnings)


def test_scenario_7_insufficient_time():
    scenarios = get_all_scenarios(date(2026, 10, 25))
    sc = scenarios["insufficient_time"]
    result = generate_schedule(sc.tasks, sc.config)

    # Total window is 14:00 to 17:00 (180 mins).
    # Critical T-701 (60m) and High T-702 (60m) should be scheduled.
    scheduled_ids = result.scheduled_task_ids
    assert "T-701" in scheduled_ids
    assert "T-702" in scheduled_ids

    # Medium T-703 (120m) cannot fit in remaining 60m
    unscheduled_ids = [t.id for t, _ in result.unscheduled_tasks]
    assert "T-703" in unscheduled_ids
    assert "T-704" in unscheduled_ids
