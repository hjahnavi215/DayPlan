"""
Core Deterministic Scheduling Engine for DayPlan.

Responsible for generating a valid, clash-free daily schedule from tasks,
constraints, deadlines, and fixed commitments.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Set, Tuple

from dayplan.models import (
    DayPlanConfig,
    EnergyLevel,
    FixedCommitment,
    Priority,
    ScheduledBlock,
    ScheduleResult,
    Task,
    TaskStatus,
)


def detect_dependency_cycles(tasks: List[Task]) -> Tuple[bool, List[str]]:
    """
    Detect cycles in task dependencies using Kahn's algorithm (topological sort).
    Returns (has_cycle, cycle_task_ids).
    """
    task_map = {t.id: t for t in tasks}
    in_degree: Dict[str, int] = {t.id: 0 for t in tasks}
    adj: Dict[str, List[str]] = defaultdict(list)

    for t in tasks:
        for dep_id in t.dependencies:
            if dep_id in task_map:
                adj[dep_id].append(t.id)
                in_degree[t.id] += 1

    # Queue of nodes with 0 incoming dependencies
    queue = deque([t_id for t_id, deg in in_degree.items() if deg == 0])
    visited_count = 0

    while queue:
        curr = queue.popleft()
        visited_count += 1
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited_count == len(tasks):
        return False, []

    # Tasks that still have in_degree > 0 are part of or blocked by a cycle
    cycle_task_ids = [t_id for t_id, deg in in_degree.items() if deg > 0]
    return True, cycle_task_ids


def get_available_free_slots(
    day_start_dt: datetime,
    day_end_dt: datetime,
    busy_blocks: List[ScheduledBlock],
) -> List[Tuple[datetime, datetime]]:
    """
    Given the day bounds and already scheduled busy blocks (commitments, locked tasks),
    compute the list of open (start_dt, end_dt) intervals.
    """
    if day_start_dt >= day_end_dt:
        return []

    # Sort busy blocks chronologically
    sorted_busy = sorted(busy_blocks, key=lambda b: (b.start_dt, b.end_dt))

    free_slots: List[Tuple[datetime, datetime]] = []
    cursor = day_start_dt

    for block in sorted_busy:
        if block.end_dt <= cursor:
            # Block ends before cursor, skip
            continue
        if block.start_dt > cursor:
            # There is free time between cursor and block start
            slot_end = min(block.start_dt, day_end_dt)
            if slot_end > cursor:
                free_slots.append((cursor, slot_end))
        # Move cursor past this busy block
        cursor = max(cursor, block.end_dt)
        if cursor >= day_end_dt:
            break

    if cursor < day_end_dt:
        free_slots.append((cursor, day_end_dt))

    return free_slots


class ScheduleGenerator:
    """
    Generates a daily schedule using a deterministic, rule-based greedy heuristic.

    Design & Limitations:
    - This scheduler uses an urgent-first greedy strategy considering priority,
      deadlines, dependency depth, and earliest start constraints.
    - It is deterministic and explainable: every placement or rejection is tied to a rule.
    - Limitations: Greedy placement does not guarantee a globally optimal packing (e.g. knapsack/bin-packing),
      but provides fast, predictable, and explainable schedules suitable for real-time daily replanning.
    """

    def __init__(self, config: DayPlanConfig):
        self.config = config
        self.day_start_dt = datetime.combine(config.planning_date, config.day_start)
        self.day_end_dt = datetime.combine(config.planning_date, config.day_end)

    def plan(
        self,
        tasks: List[Task],
        effective_start_dt: Optional[datetime] = None,
        locked_blocks: Optional[List[ScheduledBlock]] = None,
    ) -> ScheduleResult:
        """
        Build a complete schedule for the given tasks.

        Args:
            tasks: List of all tasks to consider.
            effective_start_dt: Starting timestamp for new scheduling (defaults to day_start_dt).
            locked_blocks: Already completed or locked blocks that must not be moved.
        """
        validation_errors = self.config.validate()
        if validation_errors:
            return ScheduleResult(
                warnings=[f"Configuration Error: {err}" for err in validation_errors],
                explanations=["Schedule generation aborted due to invalid daily availability configuration."],
            )

        # Base time check
        effective_start = effective_start_dt or self.day_start_dt
        if effective_start < self.day_start_dt:
            effective_start = self.day_start_dt

        result_blocks: List[ScheduledBlock] = []
        warnings: List[str] = []
        explanations: List[str] = []
        unscheduled: List[Tuple[Task, str]] = []

        # 1. Place fixed commitments as immutable blocks
        for commitment in sorted(self.config.fixed_commitments, key=lambda c: c.start_time):
            comm_start = datetime.combine(self.config.planning_date, commitment.start_time)
            comm_end = datetime.combine(self.config.planning_date, commitment.end_time)

            # Clip commitment to day window if needed
            c_start = max(comm_start, self.day_start_dt)
            c_end = min(comm_end, self.day_end_dt)
            if c_end > c_start:
                duration = int((c_end - c_start).total_seconds() // 60)
                result_blocks.append(
                    ScheduledBlock(
                        title=f"[Commitment] {commitment.title}",
                        block_type="commitment",
                        start_dt=c_start,
                        end_dt=c_end,
                        duration_minutes=duration,
                        notes=commitment.notes,
                        is_locked=True,
                    )
                )

        # 2. Add any existing locked/completed blocks
        if locked_blocks:
            for lb in locked_blocks:
                result_blocks.append(lb)

        # Sort busy blocks
        result_blocks.sort(key=lambda b: b.start_dt)

        # 3. Handle zero or negative available time edge case
        if effective_start >= self.day_end_dt:
            warnings.append("No remaining available time on this day. Schedule start is at or past day end.")
            for t in tasks:
                if not t.is_completed:
                    unscheduled.append((t, "Day has ended or no remaining working hours available."))
            return ScheduleResult(
                blocks=result_blocks,
                unscheduled_tasks=unscheduled,
                warnings=warnings,
                explanations=["Planning window has no remaining available time."],
                metadata={"total_scheduled_minutes": 0, "free_minutes": 0},
            )

        # 4. Dependency cycle detection
        has_cycle, cycle_ids = detect_dependency_cycles(tasks)
        if has_cycle:
            warnings.append(f"Dependency cycle detected among tasks: {', '.join(cycle_ids)}. These tasks cannot be scheduled.")

        # 5. Filter tasks
        task_map = {t.id: t for t in tasks}
        completed_ids = {t.id for t in tasks if t.is_completed}

        # Validate task inputs
        valid_pending_tasks: List[Task] = []
        for t in tasks:
            if t.is_completed:
                continue

            # Check individual task errors
            errs = t.validate()
            if errs:
                unscheduled.append((t, f"Validation failure: {'; '.join(errs)}"))
                continue

            if t.id in cycle_ids:
                unscheduled.append((t, "Dependency cycle detected involving this task or its prerequisites."))
                continue

            if t.is_blocked:
                unscheduled.append((t, "Marked as manually Blocked."))
                continue

            # Check missing dependencies
            missing_deps = [dep for dep in t.dependencies if dep not in task_map]
            if missing_deps:
                unscheduled.append((t, f"Prerequisite task(s) do not exist: {', '.join(missing_deps)}"))
                continue

            valid_pending_tasks.append(t)

        # 6. Scheduling loop
        scheduled_task_ids: Set[str] = set(completed_ids)
        # Include already locked task IDs
        for b in result_blocks:
            if b.task_id:
                scheduled_task_ids.add(b.task_id)

        remaining_tasks = list(valid_pending_tasks)
        minutes_since_last_break = 0

        # We greedily find the earliest available gap and the best candidate task that can fit
        max_iterations = len(remaining_tasks) * 2 + 50
        iteration = 0

        while remaining_tasks and iteration < max_iterations:
            iteration += 1

            # Compute free slots
            free_slots = get_available_free_slots(effective_start, self.day_end_dt, result_blocks)
            if not free_slots:
                # No more free slots
                for t in remaining_tasks:
                    unscheduled.append((t, "No remaining free time slots available in your working day."))
                remaining_tasks.clear()
                break

            # Consider the first available slot
            slot_start, slot_end = free_slots[0]
            slot_duration = int((slot_end - slot_start).total_seconds() // 60)

            if slot_duration <= 0:
                effective_start = slot_end
                continue

            # Check if a break is due before starting next task
            break_freq = self.config.break_frequency_minutes
            break_dur = self.config.break_duration_minutes

            if break_dur > 0 and break_freq > 0 and minutes_since_last_break >= break_freq:
                if slot_duration >= break_dur:
                    break_end = slot_start + timedelta(minutes=break_dur)
                    result_blocks.append(
                        ScheduledBlock(
                            title="☕ Planned Rest Break",
                            block_type="break",
                            start_dt=slot_start,
                            end_dt=break_end,
                            duration_minutes=break_dur,
                            notes=f"Scheduled after {minutes_since_last_break} mins of continuous focus work.",
                        )
                    )
                    result_blocks.sort(key=lambda b: b.start_dt)
                    minutes_since_last_break = 0
                    continue
                else:
                    # Slot too small for a full break, reset or skip
                    minutes_since_last_break = 0

            # Find ready tasks: all dependencies met and earliest_start satisfied
            ready_tasks: List[Task] = []
            blocked_tasks: List[Tuple[Task, str]] = []

            for t in remaining_tasks:
                unmet_deps = [dep for dep in t.dependencies if dep not in scheduled_task_ids]
                if unmet_deps:
                    dep_titles = [task_map[d].title for d in unmet_deps if d in task_map]
                    blocked_tasks.append((t, f"Prerequisite '{', '.join(dep_titles)}' not yet completed."))
                    continue

                # Check earliest start
                if t.earliest_start:
                    earliest_dt = datetime.combine(self.config.planning_date, t.earliest_start)
                    if slot_start < earliest_dt:
                        # Cannot start right now, but might start later
                        continue

                ready_tasks.append(t)

            if not ready_tasks:
                # No tasks are ready at slot_start.
                # Check if there is a task with an earliest_start in the future within this or future slots
                future_earliest = []
                for t in remaining_tasks:
                    unmet = [dep for dep in t.dependencies if dep not in scheduled_task_ids]
                    if not unmet and t.earliest_start:
                        earliest_dt = datetime.combine(self.config.planning_date, t.earliest_start)
                        if earliest_dt < self.day_end_dt:
                            future_earliest.append((earliest_dt, t))

                if future_earliest:
                    future_earliest.sort(key=lambda x: x[0])
                    next_avail_dt = future_earliest[0][0]
                    # Advance effective start to that time
                    effective_start = max(slot_start, next_avail_dt)
                    if effective_start == slot_start:
                        # Prevent infinite loop if already at that time
                        effective_start = slot_start + timedelta(minutes=5)
                    continue
                else:
                    # All remaining tasks are blocked by incomplete prerequisites
                    for t, reason in blocked_tasks:
                        unscheduled.append((t, reason))
                    remaining_tasks.clear()
                    break

            # Score and select best candidate
            # Sorting heuristic:
            # 1. Critical priority first
            # 2. Nearest deadline (if any)
            # 3. Priority weight
            # 4. Tasks that fit cleanly into current slot
            def task_sort_key(task: Task) -> Tuple[int, int, int, int]:
                # Priority weight: 4 (Critical) to 1 (Low) -> negate for descending
                p_score = -task.priority.weight

                # Deadline score: minutes from day start to deadline, or high number if none
                if task.deadline:
                    dl_dt = datetime.combine(self.config.planning_date, task.deadline)
                    dl_minutes = int((dl_dt - self.day_start_dt).total_seconds() // 60)
                else:
                    dl_minutes = 99999

                # Fits in slot preference (0 = fits, 1 = does not fit)
                fits = 0 if task.duration_minutes <= slot_duration else 1

                # Number of tasks that depend on this task (unblocking power)
                unblock_count = sum(1 for other in remaining_tasks if task.id in other.dependencies)

                return (fits, p_score, dl_minutes, -unblock_count)

            ready_tasks.sort(key=task_sort_key)
            chosen_task = ready_tasks[0]

            # Check if chosen task fits in current slot
            if chosen_task.duration_minutes > slot_duration:
                # Does not fit in this slot.
                # Check if there is another ready task that fits
                fitting_task = next((t for t in ready_tasks if t.duration_minutes <= slot_duration), None)
                if fitting_task is not None:
                    chosen_task = fitting_task
                else:
                    # No ready task fits in this slot, skip this slot
                    effective_start = slot_end
                    continue

            # Schedule chosen task
            task_start = slot_start
            task_end = task_start + timedelta(minutes=chosen_task.duration_minutes)

            # Deadline check
            deadline_missed = False
            deadline_dt = None
            if chosen_task.deadline:
                deadline_dt = datetime.combine(self.config.planning_date, chosen_task.deadline)
                if task_end > deadline_dt:
                    deadline_missed = True
                    over_mins = int((task_end - deadline_dt).total_seconds() // 60)
                    warnings.append(
                        f"⚠️ Task '{chosen_task.title}' will finish at {task_end.strftime('%H:%M')}, "
                        f"missing its deadline ({chosen_task.deadline.strftime('%H:%M')}) by {over_mins} minutes."
                    )

            # Record block
            block = ScheduledBlock(
                title=chosen_task.title,
                block_type="task",
                start_dt=task_start,
                end_dt=task_end,
                duration_minutes=chosen_task.duration_minutes,
                task_id=chosen_task.id,
                priority=chosen_task.priority,
                status=chosen_task.status,
                category=chosen_task.category,
                notes=chosen_task.description,
                deadline_missed=deadline_missed,
                deadline_dt=deadline_dt,
            )
            result_blocks.append(block)
            result_blocks.sort(key=lambda b: b.start_dt)

            scheduled_task_ids.add(chosen_task.id)
            remaining_tasks.remove(chosen_task)
            minutes_since_last_break += chosen_task.duration_minutes

            # Explain the scheduling decision
            reason_parts = [f"Scheduled '{chosen_task.title}' at {task_start.strftime('%H:%M')}"]
            if chosen_task.priority == Priority.CRITICAL:
                reason_parts.append("prioritized due to CRITICAL priority")
            elif chosen_task.deadline:
                reason_parts.append(f"deadline is {chosen_task.deadline.strftime('%H:%M')}")
            if chosen_task.dependencies:
                reason_parts.append(f"prerequisites {chosen_task.dependencies} satisfied")
            explanations.append(" — ".join(reason_parts))

            # Optional buffer between tasks
            if self.config.buffer_minutes > 0:
                effective_start = task_end + timedelta(minutes=self.config.buffer_minutes)
            else:
                effective_start = task_end

        # Any tasks still remaining could not fit
        for t in remaining_tasks:
            unscheduled.append((t, f"Insufficient time remaining in the day (needs {t.duration_minutes}m)."))

        # Compute summary metrics
        total_scheduled_work = sum(b.duration_minutes for b in result_blocks if b.block_type == "task")
        total_breaks = sum(b.duration_minutes for b in result_blocks if b.block_type == "break")
        total_commitments = sum(b.duration_minutes for b in result_blocks if b.block_type == "commitment")
        total_day_minutes = int((self.day_end_dt - self.day_start_dt).total_seconds() // 60)
        free_minutes = max(0, total_day_minutes - (total_scheduled_work + total_breaks + total_commitments))

        metadata = {
            "total_day_minutes": total_day_minutes,
            "scheduled_work_minutes": total_scheduled_work,
            "break_minutes": total_breaks,
            "commitment_minutes": total_commitments,
            "free_minutes": free_minutes,
            "total_tasks_count": len(tasks),
            "scheduled_tasks_count": len([b for b in result_blocks if b.block_type == "task"]),
            "unscheduled_tasks_count": len(unscheduled),
        }

        return ScheduleResult(
            blocks=result_blocks,
            unscheduled_tasks=unscheduled,
            warnings=warnings,
            explanations=explanations,
            metadata=metadata,
        )


def generate_schedule(
    tasks: List[Task],
    config: DayPlanConfig,
    effective_start_dt: Optional[datetime] = None,
    locked_blocks: Optional[List[ScheduledBlock]] = None,
) -> ScheduleResult:
    """Convenience functional interface for generating a daily schedule."""
    planner = ScheduleGenerator(config)
    return planner.plan(tasks, effective_start_dt=effective_start_dt, locked_blocks=locked_blocks)
