"""
Explainability Engine for DayPlan.

Translates internal scheduler decisions, constraints, trade-offs, and diffs
into transparent, honest, plain-English explanations for the user.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from dayplan.models import ChangeSummary, Priority, ScheduleResult, Task, TaskStatus


class ExplanationEngine:
    """
    Generates plain-English explanations for schedule decisions,
    answering 'Why is this task here?', 'Why was it moved?', and 'Why could it not fit?'.
    """

    @staticmethod
    def explain_schedule(result: ScheduleResult, tasks: List[Task]) -> List[str]:
        """
        Generate overall narrative explaining the schedule composition.
        """
        narrative: List[str] = []
        task_map = {t.id: t for t in tasks}

        # 1. Total overview
        meta = result.metadata
        total_tasks = meta.get("total_tasks_count", len(tasks))
        scheduled_count = meta.get("scheduled_tasks_count", 0)
        unscheduled_count = meta.get("unscheduled_tasks_count", 0)

        narrative.append(
            f"📅 Today's Plan: {scheduled_count} of {total_tasks} tasks scheduled "
            f"({meta.get('scheduled_work_minutes', 0)} mins focus work, "
            f"{meta.get('break_minutes', 0)} mins rest, "
            f"{meta.get('free_minutes', 0)} mins buffer time remaining)."
        )

        # 2. Key prioritization rationale
        critical_tasks = [t for t in tasks if t.priority == Priority.CRITICAL and t.id in result.scheduled_task_ids]
        if critical_tasks:
            titles = ", ".join(f"'{t.title}'" for t in critical_tasks)
            narrative.append(f"⚡ High Urgency: Prioritized critical tasks ({titles}) to guarantee completion.")

        # 3. Deadline rationale
        deadline_tasks = [t for t in tasks if t.deadline and t.id in result.scheduled_task_ids]
        if deadline_tasks:
            titles = ", ".join(f"'{t.title}' ({t.deadline.strftime('%H:%M')})" for t in deadline_tasks)
            narrative.append(f"⏰ Deadlines respected: Structured around upcoming deadlines ({titles}).")

        # 4. Warnings and risks
        for warning in result.warnings:
            narrative.append(f"⚠️ Warning: {warning}")

        # 5. Unscheduled reasons
        if unscheduled_count > 0:
            for task, reason in result.unscheduled_tasks:
                narrative.append(f"❌ Postponed: '{task.title}' could not be scheduled — {reason}")

        return narrative

    @staticmethod
    def explain_block(block_id: str, result: ScheduleResult, tasks: List[Task]) -> str:
        """Provide detailed justification for an individual scheduled block."""
        block = next((b for b in result.blocks if b.task_id == block_id), None)
        if not block:
            # Check unscheduled
            unscheduled = next((reason for t, reason in result.unscheduled_tasks if t.id == block_id), None)
            if unscheduled:
                return f"Task is currently unscheduled: {unscheduled}"
            return "Block not found in current schedule."

        task = next((t for t in tasks if t.id == block_id), None)
        if not task:
            return f"Scheduled from {block.start_time_str} to {block.end_time_str}."

        reasons = []
        if block.is_locked:
            if block.status == TaskStatus.COMPLETED:
                reasons.append("Anchored because it has already been completed.")
            else:
                reasons.append("Anchored because it is currently in progress.")

        if task.priority == Priority.CRITICAL:
            reasons.append("Prioritized early due to Critical priority status.")
        elif task.priority == Priority.HIGH:
            reasons.append("Given priority over Medium/Low tasks.")

        if task.deadline:
            reasons.append(f"Deadline is set for {task.deadline.strftime('%H:%M')}.")
            if block.deadline_missed:
                reasons.append(f"⚠️ At risk: Projected end time ({block.end_time_str}) exceeds deadline.")

        if task.dependencies:
            reasons.append(f"Placed after required prerequisites ({', '.join(task.dependencies)}) were scheduled or completed.")

        if not reasons:
            reasons.append("Fitted into the best available free time window.")

        return f"Scheduled {block.start_time_str}–{block.end_time_str} ({task.duration_minutes}m). " + " ".join(reasons)

    @staticmethod
    def explain_changes(change_summary: ChangeSummary) -> List[str]:
        """Convert a ChangeSummary into clean, bulleted change notes."""
        notes = []

        if change_summary.completed_preserved:
            notes.append(f"✅ Preserved {len(change_summary.completed_preserved)} completed task(s) in place.")

        if change_summary.moved_tasks:
            for m in change_summary.moved_tasks:
                notes.append(
                    f"↔️ '{m['title']}' moved from {m['old_start']} to {m['new_start']} "
                    f"({m['shift_str']}): {m['reason']}"
                )

        if change_summary.newly_unscheduled:
            for u in change_summary.newly_unscheduled:
                notes.append(f"⚠️ '{u['title']}' was pushed off today's schedule: {u['reason']}")

        if change_summary.added_tasks:
            notes.append(f"➕ Added {len(change_summary.added_tasks)} new task(s) into the schedule.")

        if change_summary.unaffected_tasks:
            notes.append(f"📌 Kept {len(change_summary.unaffected_tasks)} task(s) at their exact original times.")

        notes.append(f"🎯 Schedule Stability Score: {int(change_summary.stability_score * 100)}%")

        return notes
