"""
Data models for DayPlan — The Adaptive Daily Planning Agent.

Provides strongly typed, validated data structures for tasks, schedules,
fixed commitments, and planning configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Priority(str, Enum):
    """Task priority levels with numeric weights for deterministic sorting."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @property
    def weight(self) -> int:
        return {
            Priority.CRITICAL: 4,
            Priority.HIGH: 3,
            Priority.MEDIUM: 2,
            Priority.LOW: 1,
        }[self]

    @classmethod
    def from_string(cls, val: str) -> Priority:
        val_clean = val.strip().capitalize()
        for member in cls:
            if member.value.lower() == val_clean.lower():
                return member
        return cls.MEDIUM


class TaskStatus(str, Enum):
    """Current state of a user task."""
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    BLOCKED = "Blocked"

    @classmethod
    def from_string(cls, val: str) -> TaskStatus:
        val_clean = val.strip().lower()
        mapping = {
            "pending": cls.PENDING,
            "in progress": cls.IN_PROGRESS,
            "in_progress": cls.IN_PROGRESS,
            "completed": cls.COMPLETED,
            "blocked": cls.BLOCKED,
        }
        return mapping.get(val_clean, cls.PENDING)


class EnergyLevel(str, Enum):
    """User energy profile for the day to calibrate pace and buffers."""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"

    @classmethod
    def from_string(cls, val: str) -> EnergyLevel:
        for member in cls:
            if member.value.lower() == val.strip().lower():
                return member
        return cls.NORMAL


@dataclass
class Task:
    """
    Represents an actionable task with scheduling constraints and status.
    """
    id: str
    title: str
    duration_minutes: int
    priority: Priority = Priority.MEDIUM
    description: str = ""
    deadline: Optional[time] = None
    earliest_start: Optional[time] = None
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    actual_duration_minutes: Optional[int] = None
    category: str = "General"
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None

    def validate(self) -> List[str]:
        """
        Validate task fields and return a list of human-readable error messages.
        Returns an empty list if valid.
        """
        errors = []
        if not self.id or not str(self.id).strip():
            errors.append("Task ID cannot be empty.")
        if not self.title or not self.title.strip():
            errors.append("Task title cannot be empty.")
        if not isinstance(self.duration_minutes, int) or self.duration_minutes <= 0:
            errors.append(f"Duration must be a positive integer in minutes (got {self.duration_minutes}).")
        if self.duration_minutes > 720:  # 12 hours cap for a single task
            errors.append(f"Task duration cannot exceed 720 minutes (12 hours). Break large tasks into subtasks.")
        if self.actual_duration_minutes is not None and self.actual_duration_minutes < 0:
            errors.append("Actual duration cannot be negative.")
        if self.id in self.dependencies:
            errors.append(f"Task cannot depend on itself (self-dependency in '{self.id}').")
        if self.earliest_start and self.deadline and self.earliest_start >= self.deadline:
            errors.append(f"Earliest start ({self.earliest_start}) must be before deadline ({self.deadline}).")
        return errors

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_in_progress(self) -> bool:
        return self.status == TaskStatus.IN_PROGRESS

    @property
    def is_blocked(self) -> bool:
        return self.status == TaskStatus.BLOCKED

    def to_dict(self) -> Dict[str, Any]:
        """Convert task into a serializable dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "duration_minutes": self.duration_minutes,
            "priority": self.priority.value,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "earliest_start": self.earliest_start.isoformat() if self.earliest_start else None,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "actual_duration_minutes": self.actual_duration_minutes,
            "category": self.category,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "scheduled_end": self.scheduled_end.isoformat() if self.scheduled_end else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Task:
        """Construct a Task from a dictionary safely."""
        raw_deadline = data.get("deadline")
        deadline = time.fromisoformat(raw_deadline) if raw_deadline else None

        raw_earliest = data.get("earliest_start")
        earliest_start = time.fromisoformat(raw_earliest) if raw_earliest else None

        raw_start = data.get("scheduled_start")
        scheduled_start = datetime.fromisoformat(raw_start) if raw_start else None

        raw_end = data.get("scheduled_end")
        scheduled_end = datetime.fromisoformat(raw_end) if raw_end else None

        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            description=str(data.get("description", "")).strip(),
            duration_minutes=int(data.get("duration_minutes", 30)),
            priority=Priority.from_string(str(data.get("priority", "Medium"))),
            deadline=deadline,
            earliest_start=earliest_start,
            dependencies=[str(d).strip() for d in data.get("dependencies", []) if str(d).strip()],
            status=TaskStatus.from_string(str(data.get("status", "Pending"))),
            actual_duration_minutes=data.get("actual_duration_minutes"),
            category=str(data.get("category", "General")).strip() or "General",
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )


@dataclass
class FixedCommitment:
    """A non-negotiable event during the day (e.g. meeting, doctor appointment)."""
    id: str
    title: str
    start_time: time
    end_time: time
    notes: str = ""

    def validate(self) -> List[str]:
        errors = []
        if not self.title or not self.title.strip():
            errors.append("Commitment title cannot be empty.")
        if self.start_time >= self.end_time:
            errors.append(f"Commitment '{self.title}' start time ({self.start_time}) must be earlier than end time ({self.end_time}).")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FixedCommitment:
        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            start_time=time.fromisoformat(data["start_time"]),
            end_time=time.fromisoformat(data["end_time"]),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass
class DayPlanConfig:
    """User configuration for the daily scheduling window and pacing."""
    planning_date: date = field(default_factory=date.today)
    day_start: time = field(default_factory=lambda: time(9, 0))
    day_end: time = field(default_factory=lambda: time(17, 30))
    break_duration_minutes: int = 15
    break_frequency_minutes: int = 90
    energy_level: EnergyLevel = EnergyLevel.NORMAL
    fixed_commitments: List[FixedCommitment] = field(default_factory=list)
    buffer_minutes: int = 0

    def validate(self) -> List[str]:
        errors = []
        if self.day_start >= self.day_end:
            errors.append(f"Day start ({self.day_start}) must be earlier than day end ({self.day_end}). Overnight schedules are not supported in the MVP.")
        if self.break_duration_minutes < 0:
            errors.append("Break duration cannot be negative.")
        if self.break_frequency_minutes <= 0:
            errors.append("Break frequency must be a positive number of minutes.")
        for commitment in self.fixed_commitments:
            errors.extend(commitment.validate())
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planning_date": self.planning_date.isoformat(),
            "day_start": self.day_start.isoformat(),
            "day_end": self.day_end.isoformat(),
            "break_duration_minutes": self.break_duration_minutes,
            "break_frequency_minutes": self.break_frequency_minutes,
            "energy_level": self.energy_level.value,
            "fixed_commitments": [c.to_dict() for c in self.fixed_commitments],
            "buffer_minutes": self.buffer_minutes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DayPlanConfig:
        raw_date = data.get("planning_date")
        planning_date = date.fromisoformat(raw_date) if raw_date else date.today()
        day_start = time.fromisoformat(data.get("day_start", "09:00:00"))
        day_end = time.fromisoformat(data.get("day_end", "17:30:00"))
        commitments = [FixedCommitment.from_dict(c) for c in data.get("fixed_commitments", [])]
        return cls(
            planning_date=planning_date,
            day_start=day_start,
            day_end=day_end,
            break_duration_minutes=int(data.get("break_duration_minutes", 15)),
            break_frequency_minutes=int(data.get("break_frequency_minutes", 90)),
            energy_level=EnergyLevel.from_string(data.get("energy_level", "Normal")),
            fixed_commitments=commitments,
            buffer_minutes=int(data.get("buffer_minutes", 0)),
        )


@dataclass
class ScheduledBlock:
    """A concrete time block on the schedule (task, break, or commitment)."""
    title: str
    block_type: str  # "task", "break", "commitment"
    start_dt: datetime
    end_dt: datetime
    duration_minutes: int
    task_id: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[TaskStatus] = None
    category: Optional[str] = None
    notes: str = ""
    is_locked: bool = False
    deadline_missed: bool = False
    deadline_dt: Optional[datetime] = None

    @property
    def start_time_str(self) -> str:
        return self.start_dt.strftime("%H:%M")

    @property
    def end_time_str(self) -> str:
        return self.end_dt.strftime("%H:%M")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "block_type": self.block_type,
            "start_dt": self.start_dt.isoformat(),
            "end_dt": self.end_dt.isoformat(),
            "duration_minutes": self.duration_minutes,
            "task_id": self.task_id,
            "priority": self.priority.value if self.priority else None,
            "status": self.status.value if self.status else None,
            "category": self.category,
            "notes": self.notes,
            "is_locked": self.is_locked,
            "deadline_missed": self.deadline_missed,
            "deadline_dt": self.deadline_dt.isoformat() if self.deadline_dt else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScheduledBlock:
        raw_dl = data.get("deadline_dt")
        deadline_dt = datetime.fromisoformat(raw_dl) if raw_dl else None
        p_val = data.get("priority")
        priority = Priority.from_string(p_val) if p_val else None
        s_val = data.get("status")
        status = TaskStatus.from_string(s_val) if s_val else None

        return cls(
            title=data["title"],
            block_type=data["block_type"],
            start_dt=datetime.fromisoformat(data["start_dt"]),
            end_dt=datetime.fromisoformat(data["end_dt"]),
            duration_minutes=int(data["duration_minutes"]),
            task_id=data.get("task_id"),
            priority=priority,
            status=status,
            category=data.get("category"),
            notes=data.get("notes", ""),
            is_locked=bool(data.get("is_locked", False)),
            deadline_missed=bool(data.get("deadline_missed", False)),
            deadline_dt=deadline_dt,
        )


@dataclass
class ScheduleResult:
    """The complete result of generating or recalculating a schedule."""
    blocks: List[ScheduledBlock] = field(default_factory=list)
    unscheduled_tasks: List[Tuple[Task, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def scheduled_task_ids(self) -> List[str]:
        return [b.task_id for b in self.blocks if b.task_id is not None]

    @property
    def task_blocks(self) -> List[ScheduledBlock]:
        return [b for b in self.blocks if b.block_type == "task"]


@dataclass
class ChangeSummary:
    """Detailed diff between a previous schedule and a newly replanned schedule."""
    added_tasks: List[str] = field(default_factory=list)
    removed_tasks: List[str] = field(default_factory=list)
    moved_tasks: List[Dict[str, Any]] = field(default_factory=list)
    completed_preserved: List[str] = field(default_factory=list)
    unaffected_tasks: List[str] = field(default_factory=list)
    newly_unscheduled: List[Dict[str, Any]] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    stability_score: float = 1.0  # Fraction of tasks that stayed in original position
