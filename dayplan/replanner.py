"""
Adaptive Replanning Engine for DayPlan.

Handles real-world disruptions (delays, overrunning tasks, interruptions,
completed tasks, and emergency additions) with minimal schedule volatility
and explainable change reasoning.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from dayplan.models import (
    ChangeSummary,
    DayPlanConfig,
    ScheduledBlock,
    ScheduleResult,
    Task,
    TaskStatus,
)
from dayplan.planner import ScheduleGenerator


class AdaptiveReplanner:
    """
    Adaptive engine that adjusts an existing schedule when the real day deviates.

    Key Principles:
    1. Preservation of History: Completed work is never moved, modified, or re-run.
    2. Minimizing Volatility: Changes are localized to what is necessary.
    3. Explicit Trade-offs: When time is lost, low-priority tasks are dropped with honest reasons.
    4. Deterministic Explanations: Every movement or unscheduling is explained with causal evidence.
    """

    def __init__(self, config: DayPlanConfig):
        self.config = config
        self.planner = ScheduleGenerator(config)

    def replan(
        self,
        tasks: List[Task],
        current_time: datetime,
        previous_result: Optional[ScheduleResult] = None,
        disruption_note: str = "",
    ) -> Tuple[ScheduleResult, ChangeSummary]:
        """
        Replan the day from current_time forward.

        Args:
            tasks: Current state of all tasks (with updated status & actual durations).
            current_time: Current real-world timestamp.
            previous_result: The prior schedule result to diff against.
            disruption_note: Optional human note explaining the replan trigger.
        """
        day_start_dt = datetime.combine(self.config.planning_date, self.config.day_start)
        effective_start = max(current_time, day_start_dt)

        # Build previous schedule index
        prev_blocks_by_task: Dict[str, ScheduledBlock] = {}
        if previous_result:
            for b in previous_result.blocks:
                if b.task_id:
                    prev_blocks_by_task[b.task_id] = b

        # 1. Lock completed tasks
        locked_blocks: List[ScheduledBlock] = []
        completed_preserved_ids: List[str] = []
        cursor_completed = day_start_dt

        for task in tasks:
            if task.is_completed:
                # If we have a previous block for this task, anchor it
                prev_block = prev_blocks_by_task.get(task.id)
                actual_dur = task.actual_duration_minutes or task.duration_minutes

                if prev_block:
                    start_dt = prev_block.start_dt
                    end_dt = start_dt + timedelta(minutes=actual_dur)
                elif task.scheduled_start:
                    start_dt = task.scheduled_start
                    end_dt = task.scheduled_end or (start_dt + timedelta(minutes=actual_dur))
                else:
                    # Completed earlier: place chronologically after previous completed task
                    start_dt = cursor_completed
                    end_dt = start_dt + timedelta(minutes=actual_dur)

                cursor_completed = max(cursor_completed, end_dt)

                locked_blocks.append(
                    ScheduledBlock(
                        title=f"✓ {task.title}",
                        block_type="task",
                        start_dt=start_dt,
                        end_dt=end_dt,
                        duration_minutes=actual_dur,
                        task_id=task.id,
                        priority=task.priority,
                        status=TaskStatus.COMPLETED,
                        category=task.category,
                        notes="Completed task (preserved).",
                        is_locked=True,
                    )
                )
                completed_preserved_ids.append(task.id)

        # 2. Handle In-Progress tasks
        in_progress_tasks = [t for t in tasks if t.is_in_progress]
        for ip_task in in_progress_tasks:
            # Anchor in-progress task starting at effective_start for its remaining duration
            remaining_dur = ip_task.duration_minutes
            ip_end = effective_start + timedelta(minutes=remaining_dur)
            locked_blocks.append(
                ScheduledBlock(
                    title=f"⏳ {ip_task.title} (In Progress)",
                    block_type="task",
                    start_dt=effective_start,
                    end_dt=ip_end,
                    duration_minutes=remaining_dur,
                    task_id=ip_task.id,
                    priority=ip_task.priority,
                    status=TaskStatus.IN_PROGRESS,
                    category=ip_task.category,
                    notes="Currently in progress.",
                    is_locked=True,
                )
            )
            # Advance effective_start past this in-progress task
            effective_start = ip_end

        # 3. Generate the revised plan for remaining work
        new_result = self.planner.plan(
            tasks=tasks,
            effective_start_dt=effective_start,
            locked_blocks=locked_blocks,
        )

        # 4. Compute ChangeSummary & Explanations
        change_summary = self._compute_diff(
            tasks=tasks,
            previous_result=previous_result,
            new_result=new_result,
            completed_preserved_ids=completed_preserved_ids,
            disruption_note=disruption_note,
        )

        return new_result, change_summary

    def _compute_diff(
        self,
        tasks: List[Task],
        previous_result: Optional[ScheduleResult],
        new_result: ScheduleResult,
        completed_preserved_ids: List[str],
        disruption_note: str,
    ) -> ChangeSummary:
        """Compare previous and new schedule results to produce structured changes."""
        summary = ChangeSummary()
        summary.completed_preserved = completed_preserved_ids

        if not previous_result:
            # First schedule, no diff
            summary.added_tasks = [b.task_id for b in new_result.task_blocks if b.task_id]
            summary.explanations.append("Initial baseline schedule created.")
            return summary

        prev_blocks = {b.task_id: b for b in previous_result.task_blocks if b.task_id}
        new_blocks = {b.task_id: b for b in new_result.task_blocks if b.task_id}

        prev_unscheduled = {t.id: reason for t, reason in previous_result.unscheduled_tasks}
        new_unscheduled = {t.id: reason for t, reason in new_result.unscheduled_tasks}

        task_map = {t.id: t for t in tasks}

        # Check added and removed tasks
        for tid in new_blocks:
            if tid not in prev_blocks and tid not in completed_preserved_ids:
                summary.added_tasks.append(tid)

        for tid in prev_blocks:
            if tid not in new_blocks and tid not in new_unscheduled and tid not in completed_preserved_ids:
                summary.removed_tasks.append(tid)

        # Check moved tasks
        unchanged_count = 0
        total_compared = 0

        for tid, n_block in new_blocks.items():
            if tid in completed_preserved_ids:
                continue

            total_compared += 1
            if tid in prev_blocks:
                p_block = prev_blocks[tid]
                shift_minutes = int((n_block.start_dt - p_block.start_dt).total_seconds() // 60)

                if abs(shift_minutes) >= 1:
                    # Task moved
                    direction = f"+{shift_minutes}m" if shift_minutes > 0 else f"{shift_minutes}m"
                    task_obj = task_map.get(tid)
                    title = task_obj.title if task_obj else n_block.title

                    reason = self._generate_move_reason(
                        task=task_obj,
                        shift_minutes=shift_minutes,
                        disruption_note=disruption_note,
                    )

                    summary.moved_tasks.append({
                        "task_id": tid,
                        "title": title,
                        "old_start": p_block.start_time_str,
                        "new_start": n_block.start_time_str,
                        "shift_minutes": shift_minutes,
                        "shift_str": direction,
                        "reason": reason,
                    })
                    summary.explanations.append(
                        f"Task '{title}' moved from {p_block.start_time_str} to {n_block.start_time_str} ({direction}): {reason}"
                    )
                else:
                    summary.unaffected_tasks.append(tid)
                    unchanged_count += 1
            else:
                summary.added_tasks.append(tid)

        # Check newly unscheduled tasks
        for tid, reason in new_unscheduled.items():
            if tid in prev_blocks and tid not in completed_preserved_ids:
                t_title = task_map[tid].title if tid in task_map else tid
                summary.newly_unscheduled.append({
                    "task_id": tid,
                    "title": t_title,
                    "reason": reason,
                })
                summary.explanations.append(
                    f"Task '{t_title}' can no longer fit in today's remaining time: {reason}"
                )

        # Compute stability score
        if total_compared > 0:
            summary.stability_score = round(unchanged_count / total_compared, 2)
        else:
            summary.stability_score = 1.0

        return summary

    def _generate_move_reason(
        self,
        task: Optional[Task],
        shift_minutes: int,
        disruption_note: str,
    ) -> str:
        """Provide a plain-English explanation for why a task shifted."""
        if disruption_note:
            return disruption_note

        if shift_minutes > 0:
            if task and task.dependencies:
                return f"Delayed because prerequisite tasks were rescheduled or ran longer."
            return f"Shifted back by {shift_minutes} mins to accommodate earlier delays or higher-priority tasks."
        else:
            return f"Moved forward by {abs(shift_minutes)} mins into newly freed earlier time slot."


def replan_schedule(
    tasks: List[Task],
    config: DayPlanConfig,
    current_time: datetime,
    previous_result: Optional[ScheduleResult] = None,
    disruption_note: str = "",
) -> Tuple[ScheduleResult, ChangeSummary]:
    """Convenience functional interface for replanning."""
    engine = AdaptiveReplanner(config)
    return engine.replan(
        tasks=tasks,
        current_time=current_time,
        previous_result=previous_result,
        disruption_note=disruption_note,
    )
