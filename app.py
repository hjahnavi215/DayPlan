"""
DayPlan — The Adaptive Daily Planning Agent
Main Streamlit Application.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import io
import json
from typing import List, Optional

import streamlit as st

from dayplan.explanations import ExplanationEngine
from dayplan.history import DurationHistoryTracker
from dayplan.models import (
    ChangeSummary,
    DayPlanConfig,
    EnergyLevel,
    FixedCommitment,
    Priority,
    ScheduledBlock,
    ScheduleResult,
    Task,
    TaskStatus,
)
from dayplan.planner import generate_schedule
from dayplan.presets import get_all_scenarios
from dayplan.replanner import replan_schedule
from dayplan.storage import StorageManager

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DayPlan — Adaptive Daily Planning Agent",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Custom Styling (Calm, Modern Productivity Dashboard)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Global layout & typography */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Top Brand Header */
    .brand-header {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border-radius: 12px;
        padding: 24px 28px;
        color: white;
        margin-bottom: 24px;
        border: 1px solid #334155;
    }
    .brand-title {
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.02em;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .brand-subtitle {
        color: #94A3B8;
        font-size: 0.95rem;
        margin-top: 6px;
        margin-bottom: 0;
    }
    .brand-badge {
        display: inline-block;
        background: #3B82F6;
        color: white;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 6px;
        vertical-align: middle;
        letter-spacing: 0.05em;
    }
    
    /* Metric Cards */
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);
    }
    .metric-label {
        font-size: 0.82rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0F172A;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #94A3B8;
        margin-top: 2px;
    }

    /* Timeline Task Item */
    .timeline-item {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 5px solid #3B82F6;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .timeline-item.completed {
        border-left-color: #10B981;
        background: #F0FDF4;
    }
    .timeline-item.in-progress {
        border-left-color: #F59E0B;
        background: #FFFBEB;
    }
    .timeline-item.break {
        border-left-color: #8B5CF6;
        background: #FAF5FF;
    }
    .timeline-item.commitment {
        border-left-color: #64748B;
        background: #F8FAFC;
    }
    .timeline-item.at-risk {
        border-left-color: #EF4444;
        background: #FEF2F2;
    }

    /* Status & Priority Pills */
    .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .pill-critical { background: #FEE2E2; color: #991B1B; }
    .pill-high { background: #FFEDD5; color: #9A3412; }
    .pill-medium { background: #DBEAFE; color: #1E40AF; }
    .pill-low { background: #F1F5F9; color: #475569; }
    .pill-completed { background: #D1FAE5; color: #065F46; }
    .pill-in-progress { background: #FEF3C7; color: #92400E; }
    .pill-blocked { background: #FFE4E6; color: #9F1239; }
    .pill-pending { background: #F3F4F6; color: #374151; }

    /* Action bar */
    .replan-box {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 22px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Session State Initialization
# -----------------------------------------------------------------------------
def init_session():
    """Initialize isolated browser-session data."""
    if "config" not in st.session_state:
        st.session_state.config = DayPlanConfig(
            planning_date=date.today(),
            day_start=time(9, 0),
            day_end=time(17, 30),
            break_duration_minutes=15,
            break_frequency_minutes=90,
            energy_level=EnergyLevel.NORMAL,
            fixed_commitments=[
                FixedCommitment(id="FC-1", title="Team Lunch", start_time=time(12, 30), end_time=time(13, 30))
            ],
        )

    if "tasks" not in st.session_state:
        # Prepopulate with starter tasks for immediate beginner experience
        st.session_state.tasks = [
            Task(id="T-101", title="Review Code & Pull Requests", duration_minutes=45, priority=Priority.HIGH, category="Engineering"),
            Task(id="T-102", title="Implement Authentication Endpoint", duration_minutes=90, priority=Priority.HIGH, dependencies=["T-101"], category="Engineering"),
            Task(id="T-103", title="Prepare Weekly Status Report", duration_minutes=45, priority=Priority.MEDIUM, deadline=time(15, 0), category="Admin"),
            Task(id="T-104", title="Write Integration Tests", duration_minutes=60, priority=Priority.HIGH, dependencies=["T-102"], category="Engineering"),
            Task(id="T-105", title="Inbox Zero & Documentation", duration_minutes=45, priority=Priority.LOW, category="Admin"),
        ]

    if "history" not in st.session_state:
        st.session_state.history = DurationHistoryTracker()

    if "schedule_result" not in st.session_state:
        st.session_state.schedule_result = None

    if "change_summary" not in st.session_state:
        st.session_state.change_summary = None

    if "last_replanned_at" not in st.session_state:
        st.session_state.last_replanned_at = None


init_session()

# Recompute schedule if missing
if st.session_state.schedule_result is None:
    st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)


# -----------------------------------------------------------------------------
# Top Header
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="brand-header">
        <h1 class="brand-title">
            📅 DayPlan <span class="brand-badge">Adaptive Planning Agent</span>
        </h1>
        <p class="brand-subtitle">
            Deterministic rule-based rescheduling that absorbs delays, preserves finished work, protects breaks, and explains every decision.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Sidebar: Quick Presets & Session Info
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎯 Quick Demo Presets")
    st.caption("Load real-world disruption scenarios to observe adaptive rescheduling in action:")

    scenarios = get_all_scenarios(st.session_state.config.planning_date)
    preset_names = {k: v.name for k, v in scenarios.items()}
    chosen_preset_key = st.selectbox(
        "Select Scenario Preset",
        options=list(preset_names.keys()),
        format_func=lambda k: preset_names[k],
    )

    if st.button("🚀 Load Selected Scenario", use_container_width=True):
        loaded_sc = scenarios[chosen_preset_key]
        st.session_state.config = loaded_sc.config
        st.session_state.tasks = [Task.from_dict(t.to_dict()) for t in loaded_sc.tasks]
        st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
        st.session_state.change_summary = None
        st.session_state.last_replanned_at = None
        st.success(f"Loaded: {loaded_sc.name}")
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔒 Session Privacy")
    st.info(
        "**Browser Isolated**: Your tasks and schedule exist solely within your active browser session. "
        "No shared server storage or tracking is used. Use the **Data Backup** tab to save or restore your work.",
        icon="ℹ️",
    )

    st.markdown("---")
    st.caption("DayPlan v1.0.0 • Rule-based Deterministic Planner")


# -----------------------------------------------------------------------------
# Main Navigation Tabs
# -----------------------------------------------------------------------------
tab_dashboard, tab_tasks, tab_availability, tab_explain, tab_history, tab_data = st.tabs([
    "📊 Schedule & Dashboard",
    "📝 Task Manager",
    "⚙️ Daily Availability",
    "🧠 Why This Plan?",
    "📈 Duration Intelligence",
    "💾 Data Backup & Restore",
])


# =============================================================================
# TAB 1: SCHEDULE & DASHBOARD
# =============================================================================
with tab_dashboard:
    curr_res = st.session_state.schedule_result
    config = st.session_state.config
    tasks = st.session_state.tasks

    # 1. Dashboard Metrics
    meta = curr_res.metadata if curr_res else {}
    col1, col2, col3, col4 = st.columns(4)

    total_tasks_count = len(tasks)
    completed_count = sum(1 for t in tasks if t.is_completed)
    scheduled_tasks_count = len(curr_res.task_blocks) if curr_res else 0
    unscheduled_count = len(curr_res.unscheduled_tasks) if curr_res else 0
    at_risk_deadlines = sum(1 for b in curr_res.task_blocks if b.deadline_missed) if curr_res else 0
    free_mins = meta.get("free_minutes", 0)

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Tasks Progress</div>
                <div class="metric-value">{completed_count} / {total_tasks_count}</div>
                <div class="metric-sub">{scheduled_tasks_count} scheduled on timeline</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Free Time Remaining</div>
                <div class="metric-value">{free_mins} <span style="font-size:1rem;font-weight:500;">min</span></div>
                <div class="metric-sub">Buffer before day end</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Unscheduled Tasks</div>
                <div class="metric-value" style="color: {'#EF4444' if unscheduled_count > 0 else '#0F172A'};">{unscheduled_count}</div>
                <div class="metric-sub">{'Requires attention' if unscheduled_count > 0 else 'All tasks fit cleanly'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Deadline Warnings</div>
                <div class="metric-value" style="color: {'#EF4444' if at_risk_deadlines > 0 else '#10B981'};">{at_risk_deadlines}</div>
                <div class="metric-sub">{'Infeasible deadlines' if at_risk_deadlines > 0 else 'All deadlines feasible'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. Prominent Replan Bar
    with st.container():
        st.markdown(
            """
            <div class="replan-box">
                <h4 style="margin:0 0 8px 0; color:#1E3A8A;">🔄 Adaptive Rescheduling Engine</h4>
                <p style="margin:0 0 12px 0; font-size:0.92rem; color:#3B82F6;">
                    Did your morning run late? Did a task take longer? Or did an emergency task land on your desk?
                    Click below to recalculate your remaining day while preserving completed work and keeping existing plans as stable as possible.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        r_col1, r_col2, r_col3 = st.columns([2, 3, 2])
        with r_col1:
            replan_time = st.time_input("Current Real-world Time", value=config.day_start)
        with r_col2:
            replan_note = st.text_input("Reason for Replan (optional)", placeholder="e.g., Morning task took 45m longer than expected")
        with r_col3:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if st.button("⚡ Replan My Day Now", type="primary", use_container_width=True):
                replan_dt = datetime.combine(config.planning_date, replan_time)
                new_res, change_summary = replan_schedule(
                    tasks=st.session_state.tasks,
                    config=st.session_state.config,
                    current_time=replan_dt,
                    previous_result=st.session_state.schedule_result,
                    disruption_note=replan_note,
                )
                st.session_state.schedule_result = new_res
                st.session_state.change_summary = change_summary
                st.session_state.last_replanned_at = replan_time.strftime("%H:%M")
                st.success(f"Schedule recalculated successfully from {replan_time.strftime('%H:%M')} forward!")
                st.rerun()

    # Show Change Summary Alert if available
    if st.session_state.change_summary and st.session_state.change_summary.moved_tasks:
        cs = st.session_state.change_summary
        st.warning(
            f"**Schedule Shifted:** {len(cs.moved_tasks)} task(s) moved to accommodate recent changes. "
            f"Stability score: **{int(cs.stability_score * 100)}%**. Check the 'Why This Plan?' tab for details."
        )

    # 3. Warnings Section
    if curr_res and curr_res.warnings:
        for w in curr_res.warnings:
            st.error(w, icon="⚠️")

    # 4. Chronological Timeline
    st.markdown("### 🕒 Today's Schedule Timeline")

    if not curr_res or not curr_res.blocks:
        st.info("No scheduled blocks. Add tasks in the Task Manager or click Replan.")
    else:
        for block in curr_res.blocks:
            # Determine visual class
            if block.block_type == "break":
                item_class = "timeline-item break"
                badge = "<span class='pill' style='background:#EDE9FE;color:#6D28D9;'>BREAK</span>"
            elif block.block_type == "commitment":
                item_class = "timeline-item commitment"
                badge = "<span class='pill' style='background:#E2E8F0;color:#334155;'>COMMITMENT</span>"
            elif block.deadline_missed:
                item_class = "timeline-item at-risk"
                badge = "<span class='pill' style='background:#FEE2E2;color:#991B1B;'>DEADLINE MISSED</span>"
            elif block.status == TaskStatus.COMPLETED:
                item_class = "timeline-item completed"
                badge = "<span class='pill pill-completed'>COMPLETED</span>"
            elif block.status == TaskStatus.IN_PROGRESS:
                item_class = "timeline-item in-progress"
                badge = "<span class='pill pill-in-progress'>IN PROGRESS</span>"
            else:
                item_class = "timeline-item"
                p_class = f"pill-{block.priority.value.lower()}" if block.priority else "pill-medium"
                p_label = block.priority.value if block.priority else "Medium"
                badge = f"<span class='pill {p_class}'>{p_label}</span>"

            dl_str = f" • <span style='color:#DC2626;'>Due {block.deadline_dt.strftime('%H:%M')}</span>" if block.deadline_dt else ""
            notes_str = f"<div style='font-size:0.85rem;color:#64748B;margin-top:4px;'>{block.notes}</div>" if block.notes else ""

            st.markdown(
                f"""
                <div class="{item_class}">
                    <div>
                        <span style="font-weight:700;font-size:1.05rem;color:#0F172A;">{block.title}</span>
                        {badge}
                        {notes_str}
                    </div>
                    <div style="text-align:right;">
                        <span style="font-weight:700;font-size:1.15rem;color:#1E293B;">{block.start_time_str} – {block.end_time_str}</span>
                        <div style="font-size:0.8rem;color:#64748B;">{block.duration_minutes} min{dl_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 5. Unscheduled Tasks Section
    if curr_res and curr_res.unscheduled_tasks:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### ❌ Unscheduled Tasks & Postponements")
        st.caption("These tasks could not be scheduled within available hours or constraints. Explanations are listed below:")

        for task, reason in curr_res.unscheduled_tasks:
            st.markdown(
                f"""
                <div style="background:#FFF1F2;border:1px solid #FECDD3;border-radius:8px;padding:12px 16px;margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-weight:600;color:#9F1239;">{task.title}</span>
                        <span style="font-size:0.85rem;color:#9F1239;font-weight:500;">Needs {task.duration_minutes} mins</span>
                    </div>
                    <div style="font-size:0.85rem;color:#BE123C;margin-top:4px;">
                        <strong>Reason:</strong> {reason}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# =============================================================================
# TAB 2: TASK MANAGER
# =============================================================================
with tab_tasks:
    st.markdown("### 📝 Task Manager")
    st.caption("Create, edit, complete, block, or delete tasks. Durations and constraints are validated deterministically.")

    # A. Create New Task Form
    with st.expander("➕ Add a New Task", expanded=False):
        with st.form("new_task_form", clear_on_submit=True):
            f_col1, f_col2 = st.columns([3, 1])
            with f_col1:
                t_title = st.text_input("Task Title *", placeholder="e.g. Write integration test suite")
            with f_col2:
                t_id = st.text_input("Task ID *", value=f"T-{len(st.session_state.tasks)+101}")

            t_desc = st.text_area("Description (optional)", placeholder="Key goals or acceptance criteria")

            c_col1, c_col2, c_col3 = st.columns(3)
            with c_col1:
                t_category = st.text_input("Category", value="Engineering")
            with c_col2:
                t_priority = st.selectbox("Priority", options=["Critical", "High", "Medium", "Low"], index=2)
            with c_col3:
                # Check history tracker for suggestion
                hist_suggest, hist_reason = st.session_state.history.suggest_duration(t_category, 30)
                t_duration = st.number_input("Estimated Duration (mins) *", min_value=5, max_value=720, value=hist_suggest, step=5)
                if hist_suggest != 30:
                    st.caption(f"💡 {hist_reason}")

            d_col1, d_col2 = st.columns(2)
            with d_col1:
                has_deadline = st.checkbox("Set a Deadline")
                t_deadline = st.time_input("Deadline Time", value=time(17, 0)) if has_deadline else None
            with d_col2:
                has_earliest = st.checkbox("Set Earliest Start Time")
                t_earliest = st.time_input("Earliest Start Time", value=time(9, 0)) if has_earliest else None

            # Dependencies
            existing_ids = [t.id for t in st.session_state.tasks]
            t_deps = st.multiselect("Prerequisite Dependencies (Task must finish first)", options=existing_ids)

            submitted = st.form_submit_button("Create Task", type="primary")
            if submitted:
                new_t = Task(
                    id=t_id.strip(),
                    title=t_title.strip(),
                    description=t_desc.strip(),
                    duration_minutes=int(t_duration),
                    priority=Priority.from_string(t_priority),
                    category=t_category.strip() or "General",
                    deadline=t_deadline,
                    earliest_start=t_earliest,
                    dependencies=t_deps,
                )
                errs = new_t.validate()
                if any(t.id == new_t.id for t in st.session_state.tasks):
                    errs.append(f"A task with ID '{new_t.id}' already exists.")

                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    st.session_state.tasks.append(new_t)
                    st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                    st.success(f"Task '{new_t.title}' created and schedule updated!")
                    st.rerun()

    # B. Existing Tasks List & Quick Actions
    st.markdown("#### Current Tasks")

    if not st.session_state.tasks:
        st.info("No tasks registered. Click 'Add a New Task' above or load a demo preset from the sidebar.")
    else:
        for idx, task in enumerate(st.session_state.tasks):
            with st.container():
                cols = st.columns([4, 2, 2, 2, 2])
                with cols[0]:
                    st.markdown(f"**{task.title}** `[{task.id}]`")
                    meta_details = [f"📂 {task.category}", f"⏱️ {task.duration_minutes}m"]
                    if task.deadline:
                        meta_details.append(f"⏰ Due: {task.deadline.strftime('%H:%M')}")
                    if task.dependencies:
                        meta_details.append(f"🔗 Prereqs: {', '.join(task.dependencies)}")
                    st.caption(" • ".join(meta_details))

                with cols[1]:
                    # Status badge / selector
                    new_status_str = st.selectbox(
                        "Status",
                        options=["Pending", "In Progress", "Completed", "Blocked"],
                        index=["Pending", "In Progress", "Completed", "Blocked"].index(task.status.value),
                        key=f"status_{task.id}_{idx}",
                        label_visibility="collapsed",
                    )
                    new_status = TaskStatus.from_string(new_status_str)
                    if new_status != task.status:
                        task.status = new_status
                        st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                        st.rerun()

                with cols[2]:
                    # Actual duration input for completed tasks
                    if task.status == TaskStatus.COMPLETED:
                        act_dur = st.number_input(
                            "Actual Mins",
                            min_value=0,
                            max_value=720,
                            value=task.actual_duration_minutes or task.duration_minutes,
                            step=5,
                            key=f"act_{task.id}_{idx}",
                            label_visibility="collapsed",
                        )
                        if act_dur != task.actual_duration_minutes:
                            task.actual_duration_minutes = act_dur
                            # Record in history tracker
                            st.session_state.history.record_completion(
                                task_id=task.id,
                                title=task.title,
                                category=task.category,
                                planned_minutes=task.duration_minutes,
                                actual_minutes=act_dur,
                            )
                            st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                            st.rerun()
                    else:
                        st.markdown(f"<span class='pill pill-{task.priority.value.lower()}'>{task.priority.value}</span>", unsafe_allow_html=True)

                with cols[3]:
                    # Priority changer if pending
                    if task.status != TaskStatus.COMPLETED:
                        new_prio_str = st.selectbox(
                            "Priority",
                            options=["Critical", "High", "Medium", "Low"],
                            index=["Critical", "High", "Medium", "Low"].index(task.priority.value),
                            key=f"prio_{task.id}_{idx}",
                            label_visibility="collapsed",
                        )
                        new_prio = Priority.from_string(new_prio_str)
                        if new_prio != task.priority:
                            task.priority = new_prio
                            st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                            st.rerun()

                with cols[4]:
                    if st.button("🗑️ Delete", key=f"del_{task.id}_{idx}", use_container_width=True):
                        st.session_state.tasks = [t for t in st.session_state.tasks if t.id != task.id]
                        # Clean up dependencies in other tasks
                        for other in st.session_state.tasks:
                            if task.id in other.dependencies:
                                other.dependencies.remove(task.id)
                        st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                        st.rerun()

                st.markdown("<hr style='margin:6px 0 12px 0;'>", unsafe_allow_html=True)


# =============================================================================
# TAB 3: DAILY AVAILABILITY & COMMITMENTS
# =============================================================================
with tab_availability:
    st.markdown("### ⚙️ Daily Working Hours & Commitments")
    st.caption("Configure your working boundaries, rest cadence, and non-negotiable appointments.")

    config = st.session_state.config

    a_col1, a_col2, a_col3 = st.columns(3)
    with a_col1:
        new_date = st.date_input("Planning Date", value=config.planning_date)
    with a_col2:
        new_start = st.time_input("Day Start Time", value=config.day_start)
    with a_col3:
        new_end = st.time_input("Day End Time", value=config.day_end)

    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        new_break_dur = st.number_input("Break Duration (minutes)", min_value=0, max_value=120, value=config.break_duration_minutes, step=5)
    with b_col2:
        new_break_freq = st.number_input("Preferred Work Frequency Before Break (mins)", min_value=15, max_value=240, value=config.break_frequency_minutes, step=15)
    with b_col3:
        new_energy = st.selectbox("Energy Level Profile", options=["Low", "Normal", "High"], index=["Low", "Normal", "High"].index(config.energy_level.value))

    if (
        new_date != config.planning_date
        or new_start != config.day_start
        or new_end != config.day_end
        or new_break_dur != config.break_duration_minutes
        or new_break_freq != config.break_frequency_minutes
        or new_energy != config.energy_level.value
    ):
        config.planning_date = new_date
        config.day_start = new_start
        config.day_end = new_end
        config.break_duration_minutes = int(new_break_dur)
        config.break_frequency_minutes = int(new_break_freq)
        config.energy_level = EnergyLevel.from_string(new_energy)

        val_errs = config.validate()
        if val_errs:
            for ve in val_errs:
                st.error(ve)
        else:
            st.session_state.schedule_result = generate_schedule(st.session_state.tasks, config)
            st.success("Working hours and rest cadence updated!")
            st.rerun()

    st.markdown("---")
    st.markdown("#### Fixed Commitments (Meetings & Appointments)")
    st.caption("Fixed commitments are locked on the calendar and cannot be shifted.")

    with st.expander("➕ Add Fixed Commitment", expanded=False):
        with st.form("add_comm_form"):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                comm_title = st.text_input("Commitment Title", placeholder="e.g. Doctor appointment, Board meeting")
            with c2:
                comm_start = st.time_input("Start Time", value=time(12, 0))
            with c3:
                comm_end = st.time_input("End Time", value=time(13, 0))
            comm_notes = st.text_input("Notes (optional)")

            comm_sub = st.form_submit_button("Add Commitment")
            if comm_sub:
                new_c = FixedCommitment(
                    id=f"FC-{len(config.fixed_commitments)+1}",
                    title=comm_title.strip() or "Untitled Commitment",
                    start_time=comm_start,
                    end_time=comm_end,
                    notes=comm_notes.strip(),
                )
                errs = new_c.validate()
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    config.fixed_commitments.append(new_c)
                    st.session_state.schedule_result = generate_schedule(st.session_state.tasks, config)
                    st.success(f"Added: {new_c.title}")
                    st.rerun()

    if config.fixed_commitments:
        for idx, comm in enumerate(config.fixed_commitments):
            c_row1, c_row2 = st.columns([5, 1])
            with c_row1:
                st.markdown(f"**📌 {comm.title}** ({comm.start_time.strftime('%H:%M')} – {comm.end_time.strftime('%H:%M')})")
                if comm.notes:
                    st.caption(comm.notes)
            with c_row2:
                if st.button("Remove", key=f"rm_comm_{comm.id}_{idx}"):
                    config.fixed_commitments.remove(comm)
                    st.session_state.schedule_result = generate_schedule(st.session_state.tasks, config)
                    st.rerun()
            st.markdown("<hr style='margin:4px 0;'>", unsafe_allow_html=True)
    else:
        st.info("No fixed commitments scheduled.")


# =============================================================================
# TAB 4: EXPLAINABLE PLANNING ("WHY THIS PLAN?")
# =============================================================================
with tab_explain:
    st.markdown("### 🧠 Explainable Planning & Reasoning")
    st.caption("DayPlan explains every schedule placement and shift using concrete mathematical rules — never invented text.")

    curr_res = st.session_state.schedule_result
    tasks = st.session_state.tasks

    if curr_res:
        # 1. High-level narrative
        st.markdown("#### 📖 Planning Narrative")
        narrative = ExplanationEngine.explain_schedule(curr_res, tasks)
        for item in narrative:
            st.markdown(f"- {item}")

        # 2. Recent Replan Change Explanations (if replan occurred)
        if st.session_state.change_summary:
            st.markdown("---")
            st.markdown("#### ↔️ Most Recent Replan Changes")
            change_notes = ExplanationEngine.explain_changes(st.session_state.change_summary)
            for note in change_notes:
                st.markdown(f"- {note}")

        # 3. Block-by-block Justifications
        st.markdown("---")
        st.markdown("#### 🔍 Block-by-Block Decisions")
        st.caption("Inspect why a specific task was assigned its exact time window:")

        for block in curr_res.blocks:
            if block.task_id:
                reason_text = ExplanationEngine.explain_block(block.task_id, curr_res, tasks)
                with st.expander(f"Task: {block.title} ({block.start_time_str} – {block.end_time_str})"):
                    st.write(reason_text)


# =============================================================================
# TAB 5: DURATION INTELLIGENCE & HISTORY
# =============================================================================
with tab_history:
    st.markdown("### 📈 Duration Intelligence & Calibration")
    st.caption(
        "DayPlan tracks planned vs actual durations. Once at least 3 completed tasks exist in a category, "
        "it calculates an empirical multiplier to calibrate future estimates."
    )

    history = st.session_state.history

    # Summary table of categories
    categories = list(set([r.category for r in history.records] + [t.category for t in st.session_state.tasks]))
    categories.sort()

    cat_cols = st.columns(len(categories) if categories else 1)
    for idx, cat in enumerate(categories):
        stats = history.get_category_stats(cat)
        with cat_cols[idx % len(cat_cols)]:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{cat}</div>
                    <div class="metric-value">{stats['avg_multiplier']}x</div>
                    <div class="metric-sub">{stats['sample_count']} sample(s) • {'Calibrated' if stats['has_sufficient_history'] else 'Need 3+'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # History Table
    st.markdown("#### Completed Task History Log")
    if not history.records:
        st.info("No completed task duration history yet. Complete tasks in the Task Manager with their actual duration to populate empirical data.")
    else:
        history_data = [
            {
                "Task ID": r.task_id,
                "Title": r.title,
                "Category": r.category,
                "Planned (mins)": r.planned_minutes,
                "Actual (mins)": r.actual_minutes,
                "Variance (mins)": f"{'+' if r.variance_minutes > 0 else ''}{r.variance_minutes}m",
                "Factor": f"{r.ratio}x",
            }
            for r in history.records
        ]
        st.dataframe(history_data, use_container_width=True)


# =============================================================================
# TAB 6: DATA BACKUP & RESTORE
# =============================================================================
with tab_data:
    st.markdown("### 💾 Portable JSON Backup & Restore")
    st.caption("Export your schedule data to a JSON backup file or restore a previous session safely.")

    col_exp, col_imp = st.columns(2)

    with col_exp:
        st.markdown("#### 📤 Export Session Data")
        st.write("Download your full tasks, working configuration, and history records as a portable JSON file.")
        export_json = StorageManager.export_to_json(
            st.session_state.config,
            st.session_state.tasks,
            st.session_state.history,
        )
        st.download_button(
            label="⬇️ Download DayPlan JSON Backup",
            data=export_json,
            file_name=f"dayplan_backup_{st.session_state.config.planning_date.isoformat()}.json",
            mime="application/json",
            type="primary",
            use_container_width=True,
        )

    with col_imp:
        st.markdown("#### 📥 Restore from JSON Backup")
        st.write("Upload a previously exported DayPlan JSON file to restore your tasks and settings.")
        uploaded_file = st.file_uploader("Select JSON file", type=["json"])
        if uploaded_file is not None:
            content = uploaded_file.getvalue().decode("utf-8")
            if st.button("Confirm and Load Backup", type="primary", use_container_width=True):
                success, imp_config, imp_tasks, imp_hist, imp_errs = StorageManager.import_from_json(content)
                if not success:
                    st.error("Failed to restore backup due to the following errors:")
                    for err in imp_errs:
                        st.markdown(f"- {err}")
                else:
                    if imp_config:
                        st.session_state.config = imp_config
                    if imp_tasks:
                        st.session_state.tasks = imp_tasks
                    if imp_hist:
                        st.session_state.history = imp_hist

                    st.session_state.schedule_result = generate_schedule(st.session_state.tasks, st.session_state.config)
                    st.session_state.change_summary = None
                    st.success("Backup restored successfully!")
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 🛡️ Hosting & Architecture Details")
    st.markdown(
        """
        - **Session Scope:** User data is stored in Streamlit's `st.session_state`, ensuring strict isolation between browser sessions.
        - **Zero Cloud Leakage:** No database or shared server file is written. Other users cannot view or mutate your tasks.
        - **Session Lifetime:** On free Streamlit Community Cloud instances, closing the browser tab or server idling clears the session. Use the JSON backup above to persist your schedule across sessions.
        """
    )
