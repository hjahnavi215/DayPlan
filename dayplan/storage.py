"""
Validated JSON Storage & Serialization for DayPlan.

Provides secure, schema-validated export and import of user tasks, daily
configuration, and historical task records.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

from dayplan.history import DurationHistoryTracker, TaskHistoryRecord
from dayplan.models import DayPlanConfig, FixedCommitment, Task


SCHEMA_VERSION = "1.0.0"


class StorageManager:
    """Handles serialization and deserialization with strict validation."""

    @staticmethod
    def export_to_json(
        config: DayPlanConfig,
        tasks: List[Task],
        history: Optional[DurationHistoryTracker] = None,
    ) -> str:
        """Export current session data to a formatted JSON string."""
        payload = {
            "version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "config": config.to_dict(),
            "tasks": [t.to_dict() for t in tasks],
            "history": history.to_dict_list() if history else [],
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def import_from_json(
        json_str: str,
    ) -> Tuple[bool, Optional[DayPlanConfig], Optional[List[Task]], Optional[DurationHistoryTracker], List[str]]:
        """
        Safely parse and validate imported JSON data.

        Returns:
            (success, config, tasks, history, error_messages)
        """
        errors: List[str] = []

        if not json_str or not json_str.strip():
            return False, None, None, None, ["Import file is completely empty."]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return False, None, None, None, [f"Invalid JSON format: {str(exc)}"]

        if not isinstance(data, dict):
            return False, None, None, None, ["Root element of imported JSON must be an object/dict."]

        # Validate config
        config = None
        if "config" in data and isinstance(data["config"], dict):
            try:
                config = DayPlanConfig.from_dict(data["config"])
                config_errs = config.validate()
                if config_errs:
                    errors.extend([f"Configuration issue: {err}" for err in config_errs])
            except Exception as exc:
                errors.append(f"Failed to parse daily configuration: {str(exc)}")
                config = DayPlanConfig()
        else:
            config = DayPlanConfig()

        # Validate tasks
        parsed_tasks: List[Task] = []
        raw_tasks = data.get("tasks")
        if raw_tasks is not None:
            if not isinstance(raw_tasks, list):
                errors.append("Field 'tasks' must be a list.")
            else:
                for idx, t_data in enumerate(raw_tasks):
                    if not isinstance(t_data, dict):
                        errors.append(f"Task item at index {idx} is not an object.")
                        continue
                    try:
                        task = Task.from_dict(t_data)
                        task_errs = task.validate()
                        if task_errs:
                            errors.extend([f"Task '{task.title or idx}' error: {e}" for e in task_errs])
                        parsed_tasks.append(task)
                    except Exception as exc:
                        errors.append(f"Failed to parse task at index {idx}: {str(exc)}")

        # Validate history
        history_tracker = DurationHistoryTracker()
        raw_history = data.get("history")
        if raw_history is not None:
            if isinstance(raw_history, list):
                try:
                    history_tracker = DurationHistoryTracker.from_dict_list(raw_history)
                except Exception as exc:
                    errors.append(f"Warning: could not parse historical records: {str(exc)}")

        success = len(errors) == 0
        return success, config, parsed_tasks, history_tracker, errors
