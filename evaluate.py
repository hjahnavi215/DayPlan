"""
Benchmark and Evaluation Script for DayPlan.

Measures the deterministic performance of the DayPlan scheduling engine across
all 7 standard test scenarios:
- Runtime performance (ms)
- Task completion coverage (%)
- Schedule conflict detection (0 expected overlaps)
- Deadline feasibility & adherence
- Schedule stability (stability score & shift volatility)
"""

from __future__ import annotations

from datetime import date, datetime
import time
from typing import Any, Dict, List

from dayplan.planner import generate_schedule
from dayplan.presets import get_all_scenarios
from dayplan.replanner import replan_schedule


def run_benchmark() -> List[Dict[str, Any]]:
    scenarios = get_all_scenarios(date.today())
    results: List[Dict[str, Any]] = []

    print("\n" + "=" * 80)
    print("DAYPLAN SCHEDULING ENGINE BENCHMARK & EVALUATION REPORT")
    print("=" * 80)

    for key, sc in scenarios.items():
        start_time = time.perf_counter()

        # Step 1: Initial plan
        initial_res = generate_schedule(sc.tasks, sc.config)

        # Step 2: Replanning at simulated timestamp
        sim_dt = datetime.combine(sc.config.planning_date, sc.simulated_current_time)
        replan_res, change_summary = replan_schedule(
            tasks=sc.tasks,
            config=sc.config,
            current_time=sim_dt,
            previous_result=initial_res,
            disruption_note=sc.disruption_note,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Check for schedule conflicts (overlaps)
        sorted_blocks = sorted(replan_res.blocks, key=lambda b: b.start_dt)
        conflicts = 0
        for i in range(len(sorted_blocks) - 1):
            if sorted_blocks[i].end_dt > sorted_blocks[i + 1].start_dt:
                conflicts += 1

        # Calculate metrics
        total_tasks = len(sc.tasks)
        scheduled_tasks = len(replan_res.task_blocks)
        coverage_pct = round((scheduled_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 100.0

        missed_deadlines = sum(1 for b in replan_res.task_blocks if b.deadline_missed)

        row = {
            "scenario": sc.name,
            "tasks": total_tasks,
            "scheduled": scheduled_tasks,
            "coverage_pct": coverage_pct,
            "conflicts": conflicts,
            "missed_deadlines": missed_deadlines,
            "warnings_count": len(replan_res.warnings),
            "stability_score": change_summary.stability_score,
            "moved_tasks": len(change_summary.moved_tasks),
            "runtime_ms": round(elapsed_ms, 2),
        }
        results.append(row)

        print(f"\nScenario: {sc.name}")
        print(f"  • Description: {sc.description}")
        print(f"  • Disruption:  {sc.disruption_note}")
        print(f"  • Coverage:    {scheduled_tasks}/{total_tasks} tasks ({coverage_pct}%)")
        print(f"  • Conflicts:   {conflicts} overlaps detected")
        print(f"  • Deadlines:   {missed_deadlines} flagged as infeasible or missed")
        print(f"  • Stability:   {int(change_summary.stability_score * 100)}% unchanged ({len(change_summary.moved_tasks)} moved)")
        print(f"  • Runtime:     {row['runtime_ms']} ms")

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Scenario':<38} | {'Coverage':<10} | {'Conflicts':<10} | {'Stability':<10} | {'Runtime':<10}")
    print("-" * 86)
    for r in results:
        print(f"{r['scenario'][:37]:<38} | {r['coverage_pct']}%{'':<4} | {r['conflicts']:<10} | {int(r['stability_score'] * 100)}%{'':<5} | {r['runtime_ms']} ms")
    print("=" * 80 + "\n")

    return results


if __name__ == "__main__":
    run_benchmark()
