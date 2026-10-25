"""
Duration History & Estimation Tracking for DayPlan.

Tracks planned vs actual task durations and computes empirical multipliers
and category averages once sufficient sample history is established.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TaskHistoryRecord:
    """Historical record of a completed task's planned vs actual duration."""
    task_id: str
    title: str
    category: str
    planned_minutes: int
    actual_minutes: int
    completed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def variance_minutes(self) -> int:
        return self.actual_minutes - self.planned_minutes

    @property
    def ratio(self) -> float:
        if self.planned_minutes <= 0:
            return 1.0
        return round(self.actual_minutes / self.planned_minutes, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "category": self.category,
            "planned_minutes": self.planned_minutes,
            "actual_minutes": self.actual_minutes,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskHistoryRecord:
        return cls(
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            category=str(data.get("category", "General")),
            planned_minutes=int(data["planned_minutes"]),
            actual_minutes=int(data["actual_minutes"]),
            completed_at=str(data.get("completed_at", "")),
        )


class DurationHistoryTracker:
    """
    Maintains historical performance records and provides calibration advice.
    Requires at least MIN_SAMPLE_SIZE samples before recommending adjustments.
    """
    MIN_SAMPLE_SIZE = 3

    def __init__(self, records: Optional[List[TaskHistoryRecord]] = None):
        self.records: List[TaskHistoryRecord] = records or []

    def record_completion(
        self,
        task_id: str,
        title: str,
        category: str,
        planned_minutes: int,
        actual_minutes: int,
    ) -> None:
        """Add a completion record if valid."""
        if planned_minutes > 0 and actual_minutes >= 0:
            # Check if record for this task already exists to avoid duplicates
            existing = next((r for r in self.records if r.task_id == task_id), None)
            if existing:
                existing.actual_minutes = actual_minutes
                existing.planned_minutes = planned_minutes
                existing.category = category
            else:
                self.records.append(
                    TaskHistoryRecord(
                        task_id=task_id,
                        title=title,
                        category=category,
                        planned_minutes=planned_minutes,
                        actual_minutes=actual_minutes,
                    )
                )

    def get_category_stats(self, category: str) -> Dict[str, Any]:
        """Compute statistics for a given category."""
        matching = [r for r in self.records if r.category.lower() == category.lower()]
        count = len(matching)

        if count < self.MIN_SAMPLE_SIZE:
            return {
                "category": category,
                "sample_count": count,
                "has_sufficient_history": False,
                "message": f"Insufficient history ({count}/{self.MIN_SAMPLE_SIZE} completed tasks). At least {self.MIN_SAMPLE_SIZE} needed for estimates.",
                "avg_multiplier": 1.0,
                "avg_planned": sum(r.planned_minutes for r in matching) / count if count > 0 else 0,
                "avg_actual": sum(r.actual_minutes for r in matching) / count if count > 0 else 0,
            }

        total_planned = sum(r.planned_minutes for r in matching)
        total_actual = sum(r.actual_minutes for r in matching)
        multiplier = round(total_actual / total_planned, 2) if total_planned > 0 else 1.0

        percent_diff = int(round((multiplier - 1.0) * 100))
        if percent_diff > 0:
            advice = f"Tasks in '{category}' historically take {percent_diff}% longer than estimated (multiplier: {multiplier}x)."
        elif percent_diff < 0:
            advice = f"Tasks in '{category}' historically finish {abs(percent_diff)}% faster than estimated (multiplier: {multiplier}x)."
        else:
            advice = f"Estimates in '{category}' match actual durations with high accuracy (1.0x)."

        return {
            "category": category,
            "sample_count": count,
            "has_sufficient_history": True,
            "message": advice,
            "avg_multiplier": multiplier,
            "avg_planned": round(total_planned / count, 1),
            "avg_actual": round(total_actual / count, 1),
        }

    def suggest_duration(self, category: str, proposed_duration: int) -> Tuple[int, str]:
        """
        Suggest a calibrated duration based on historical evidence.
        Returns (suggested_duration, explanation).
        """
        stats = self.get_category_stats(category)
        if not stats["has_sufficient_history"]:
            return proposed_duration, "Using original estimate (insufficient historical data)."

        multiplier = stats["avg_multiplier"]
        calibrated = max(5, int(round(proposed_duration * multiplier)))
        explanation = f"Adjusted from {proposed_duration}m to {calibrated}m based on {stats['sample_count']} historical '{category}' tasks ({multiplier}x factor)."
        return calibrated, explanation

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.records]

    @classmethod
    def from_dict_list(cls, data_list: List[Dict[str, Any]]) -> DurationHistoryTracker:
        records = [TaskHistoryRecord.from_dict(d) for d in data_list]
        return cls(records)
