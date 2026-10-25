"""
Predefined Scenario Presets for DayPlan Demonstrations and Benchmarks.

Provides realistic, deterministic demonstration datasets for all key scenarios:
- Normal productive day
- Missed morning start
- Overrunning task (actual > planned)
- Urgent critical task added mid-day
- Blocked prerequisite dependency
- Impossible / infeasible deadline
- Insufficient remaining working time
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, NamedTuple

from dayplan.models import (
    DayPlanConfig,
    EnergyLevel,
    FixedCommitment,
    Priority,
    Task,
    TaskStatus,
)


class DemoScenario(NamedTuple):
    key: str
    name: str
    description: str
    config: DayPlanConfig
    tasks: List[Task]
    simulated_current_time: time
    disruption_note: str


def get_all_scenarios(target_date: date = date.today()) -> Dict[str, DemoScenario]:
    """Return dictionary of all standard demonstration scenarios."""
    return {
        "normal_day": DemoScenario(
            key="normal_day",
            name="1. Normal Productive Day",
            description="A balanced day where tasks, dependencies, a lunch commitment, and breaks fit smoothly within working hours.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 30),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                energy_level=EnergyLevel.NORMAL,
                fixed_commitments=[
                    FixedCommitment(id="FC-1", title="Team Lunch", start_time=time(12, 30), end_time=time(13, 30))
                ],
            ),
            tasks=[
                Task(id="T-101", title="Review Code & Pull Requests", duration_minutes=45, priority=Priority.HIGH, category="Engineering"),
                Task(id="T-102", title="Implement Authentication Endpoint", duration_minutes=90, priority=Priority.HIGH, dependencies=["T-101"], category="Engineering"),
                Task(id="T-103", title="Prepare Weekly Status Report", duration_minutes=45, priority=Priority.MEDIUM, deadline=time(15, 0), category="Admin"),
                Task(id="T-104", title="Write Integration Tests", duration_minutes=60, priority=Priority.HIGH, dependencies=["T-102"], category="Engineering"),
                Task(id="T-105", title="Inbox Zero & Documentation", duration_minutes=45, priority=Priority.LOW, category="Admin"),
            ],
            simulated_current_time=time(9, 0),
            disruption_note="Baseline schedule generated at start of morning.",
        ),

        "missed_morning": DemoScenario(
            key="missed_morning",
            name="2. Missed Morning Task (Late Start)",
            description="The user started working at 11:00 AM instead of 09:00 AM. Remaining work must be compacted or lower priorities deferred.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 0),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[
                    FixedCommitment(id="FC-1", title="Department Meeting", start_time=time(14, 0), end_time=time(15, 0))
                ],
            ),
            tasks=[
                Task(id="T-201", title="Morning Standup Async Update", duration_minutes=30, priority=Priority.MEDIUM, category="Admin"),
                Task(id="T-202", title="Client Demo Preparation", duration_minutes=90, priority=Priority.CRITICAL, deadline=time(16, 0), category="Sales"),
                Task(id="T-203", title="Refactor Database Queries", duration_minutes=90, priority=Priority.HIGH, category="Engineering"),
                Task(id="T-204", title="Draft Newsletter", duration_minutes=60, priority=Priority.LOW, category="Marketing"),
                Task(id="T-205", title="Clean Desktop Workspace", duration_minutes=45, priority=Priority.LOW, category="Admin"),
            ],
            simulated_current_time=time(11, 0),
            disruption_note="Late start: replanning starting at 11:00 AM after 2-hour morning delay.",
        ),

        "task_overrun": DemoScenario(
            key="task_overrun",
            name="3. Task Taking Longer Than Expected",
            description="A morning task planned for 60 minutes took 120 minutes. Completed task is locked, and afternoon tasks automatically shift.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 30),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[],
            ),
            tasks=[
                Task(id="T-301", title="Debug Payment Gateway Timeout", duration_minutes=60, actual_duration_minutes=120, status=TaskStatus.COMPLETED, priority=Priority.HIGH, category="Engineering"),
                Task(id="T-302", title="Deploy Patch to Production", duration_minutes=45, priority=Priority.HIGH, dependencies=["T-301"], category="DevOps"),
                Task(id="T-303", title="Customer Support Escalations", duration_minutes=60, priority=Priority.MEDIUM, category="Support"),
                Task(id="T-304", title="Sprint Retrospective Prep", duration_minutes=60, priority=Priority.MEDIUM, category="Admin"),
                Task(id="T-305", title="Update Knowledge Base", duration_minutes=60, priority=Priority.LOW, category="Support"),
            ],
            simulated_current_time=time(11, 0),
            disruption_note="T-301 ran 60 minutes over its original estimate; downstream schedule pushed back.",
        ),

        "urgent_addition": DemoScenario(
            key="urgent_addition",
            name="4. Urgent Critical Task Added Mid-Day",
            description="At 13:00, a high-severity production outage strikes. It must be inserted immediately ahead of non-critical tasks without losing progress.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 30),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[],
            ),
            tasks=[
                Task(id="T-401", title="Morning Design Review", duration_minutes=90, actual_duration_minutes=90, status=TaskStatus.COMPLETED, priority=Priority.HIGH, category="Design", scheduled_start=datetime.combine(target_date, time(9, 0)), scheduled_end=datetime.combine(target_date, time(10, 30))),
                Task(id="T-402", title="Weekly 1-on-1 Prep", duration_minutes=45, actual_duration_minutes=45, status=TaskStatus.COMPLETED, priority=Priority.MEDIUM, category="Management", scheduled_start=datetime.combine(target_date, time(10, 30)), scheduled_end=datetime.combine(target_date, time(11, 15))),
                Task(id="T-403", title="EMERGENCY: Mitigate Security CVE", duration_minutes=75, priority=Priority.CRITICAL, deadline=time(15, 30), category="Security"),
                Task(id="T-404", title="Build Dashboard Prototype", duration_minutes=90, priority=Priority.MEDIUM, category="Engineering"),
                Task(id="T-405", title="Write User Documentation", duration_minutes=60, priority=Priority.LOW, category="Docs"),
            ],
            simulated_current_time=time(13, 0),
            disruption_note="Emergency Security CVE injected at 13:00; prioritized immediately.",
        ),

        "blocked_prerequisite": DemoScenario(
            key="blocked_prerequisite",
            name="5. Blocked Prerequisite Dependency",
            description="Task 'Deploy Feature' depends on 'Client Sign-off', which is currently Blocked. The agent halts the dependent task while keeping independent tasks moving.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 0),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[],
            ),
            tasks=[
                Task(id="T-501", title="Waiting on Client Sign-off", duration_minutes=45, status=TaskStatus.BLOCKED, priority=Priority.HIGH, category="Sales"),
                Task(id="T-502", title="Deploy Staging Build", duration_minutes=60, priority=Priority.HIGH, dependencies=["T-501"], category="Engineering"),
                Task(id="T-503", title="Refactor Test Helpers", duration_minutes=75, priority=Priority.MEDIUM, category="Engineering"),
                Task(id="T-504", title="Update API Documentation", duration_minutes=45, priority=Priority.LOW, category="Docs"),
            ],
            simulated_current_time=time(9, 0),
            disruption_note="Prerequisite T-501 is Blocked; dependent T-502 is unscheduled with transparent explanation.",
        ),

        "impossible_deadline": DemoScenario(
            key="impossible_deadline",
            name="6. Impossible Deadline (Honest Warning)",
            description="A task requiring 120 minutes is due at 10:00 AM, but planning starts at 09:00 AM. The agent flags the shortfall honestly rather than claiming feasibility.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(9, 0),
                day_end=time(17, 0),
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[],
            ),
            tasks=[
                Task(id="T-601", title="Complete Regulatory Compliance Filing", duration_minutes=120, priority=Priority.CRITICAL, deadline=time(10, 0), category="Legal"),
                Task(id="T-602", title="General Team Sync", duration_minutes=30, priority=Priority.MEDIUM, category="Management"),
            ],
            simulated_current_time=time(9, 0),
            disruption_note="Task requires 120m starting at 09:00, making a 10:00 deadline mathematically impossible.",
        ),

        "insufficient_time": DemoScenario(
            key="insufficient_time",
            name="7. Insufficient Remaining Time",
            description="A heavy workload (7+ hours) attempted in a tight afternoon window (3 hours). High-priority tasks fit, lower priorities are explicitly postponed.",
            config=DayPlanConfig(
                planning_date=target_date,
                day_start=time(14, 0),
                day_end=time(17, 0),  # Only 3 hours available
                break_duration_minutes=15,
                break_frequency_minutes=90,
                fixed_commitments=[],
            ),
            tasks=[
                Task(id="T-701", title="Critical System Patch", duration_minutes=60, priority=Priority.CRITICAL, category="Engineering"),
                Task(id="T-702", title="Executive Summary Presentation", duration_minutes=60, priority=Priority.HIGH, category="Management"),
                Task(id="T-703", title="Deep Architecture Refactoring", duration_minutes=120, priority=Priority.MEDIUM, category="Engineering"),
                Task(id="T-704", title="Organize File Storage", duration_minutes=60, priority=Priority.LOW, category="Admin"),
            ],
            simulated_current_time=time(14, 0),
            disruption_note="Only 180 minutes available; lower priority tasks cannot fit and are honestly unscheduled.",
        ),
    }
