from __future__ import annotations

import argparse
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Required for GitHub Actions
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import yaml


@dataclass
class Task:
    name: str
    base_name: str
    category: str
    estimated_hours: float


@dataclass
class DailyPlan:
    day: date
    capacity_hours: float
    tasks: list[Task]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def infer_category(task_name: str) -> str:
    """
    Infer task category from the task name.

    Examples:
    "Methods: model calibration" -> "Methods"
    "Results: model comparison" -> "Results"
    """
    if ":" in task_name:
        return task_name.split(":", 1)[0].strip()
    return "Other"


def load_project(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_daily_capacity(day: date, project: dict[str, Any]) -> float:
    available = project.get("available_time", {})
    weekday_hours = float(available.get("weekdays_hours", 3))
    weekend_hours = float(available.get("weekends_hours", 1))
    return weekend_hours if day.weekday() >= 5 else weekday_hours


def expand_tasks(project: dict[str, Any]) -> list[Task]:
    """
    Convert large project sections into smaller task chunks.
    Each chunk is around 2 hours.
    """
    tasks: list[Task] = []
    sections = project.get("sections", [])

    for section in sections:
        base_name = section["name"]
        category = infer_category(base_name)
        hours = float(section.get("estimated_hours", 2))

        n_chunks = max(1, math.ceil(hours / 2))
        chunk_hours = hours / n_chunks

        for i in range(1, n_chunks + 1):
            if n_chunks == 1:
                task_name = base_name
            else:
                task_name = f"{base_name} — part {i}/{n_chunks}"

            tasks.append(
                Task(
                    name=task_name,
                    base_name=base_name,
                    category=category,
                    estimated_hours=chunk_hours,
                )
            )

    return tasks


def build_schedule(project: dict[str, Any]) -> list[DailyPlan]:
    start = parse_date(project["start_date"])
    deadline = parse_date(project["deadline"])

    if deadline < start:
        raise ValueError("Deadline cannot be earlier than start_date.")

    tasks = expand_tasks(project)
    schedule: list[DailyPlan] = []

    current_day = start
    task_index = 0

    while current_day <= deadline and task_index < len(tasks):
        capacity = get_daily_capacity(current_day, project)
        remaining_capacity = capacity
        daily_tasks: list[Task] = []

        while task_index < len(tasks):
            task = tasks[task_index]

            if task.estimated_hours <= remaining_capacity + 1e-9:
                daily_tasks.append(task)
                remaining_capacity -= task.estimated_hours
                task_index += 1
            else:
                break

        schedule.append(
            DailyPlan(
                day=current_day,
                capacity_hours=capacity,
                tasks=daily_tasks,
            )
        )

        current_day += timedelta(days=1)

    while current_day <= deadline:
        capacity = get_daily_capacity(current_day, project)
        schedule.append(
            DailyPlan(
                day=current_day,
                capacity_hours=capacity,
                tasks=[],
            )
        )
        current_day += timedelta(days=1)

    if task_index < len(tasks):
        remaining = tasks[task_index:]
        remaining_hours = sum(t.estimated_hours for t in remaining)

        warning_task = Task(
            name=f"WARNING: schedule overloaded. {remaining_hours:.1f} hours could not be assigned before the deadline.",
            base_name="WARNING",
            category="Warning",
            estimated_hours=0,
        )

        schedule.append(
            DailyPlan(
                day=deadline,
                capacity_hours=0,
                tasks=[warning_task],
            )
        )

    return schedule


def render_markdown(project: dict[str, Any], schedule: list[DailyPlan]) -> str:
    title = project["project_name"]
    deadline = project["deadline"]
    target = project.get("target_journal", "Not specified")
    summary = project.get("research_summary", "").strip()
    status = project.get("current_status", [])
    outputs = project.get("main_outputs", [])

    lines: list[str] = []

    lines.append(f"# Research schedule: {title}")
    lines.append("")
    lines.append(f"**Deadline:** {deadline}")
    lines.append(f"**Target:** {target}")
    lines.append("")

    lines.append("## Research summary")
    lines.append("")
    lines.append(summary if summary else "No summary provided.")
    lines.append("")

    lines.append("## Current status")
    lines.append("")
    for item in status:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Main outputs")
    lines.append("")
    for item in outputs:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Daily schedule")
    lines.append("")
    lines.append("| Date | Day | Capacity | Tasks |")
    lines.append("|---|---:|---:|---|")

    for plan in schedule:
        day_name = plan.day.strftime("%A")

        if plan.tasks:
            task_text = "<br>".join(
                f"{task.name} ({task.estimated_hours:.1f} h)"
                for task in plan.tasks
            )
        else:
            if plan.day.weekday() >= 5:
                task_text = "Recovery / buffer day"
            else:
                task_text = "Buffer: revise weak sections, check logic, or catch up"

        lines.append(
            f"| {plan.day.isoformat()} | {day_name} | {plan.capacity_hours:.1f} h | {task_text} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- The Markdown table provides daily task details.")
    lines.append("- The Gantt chart provides a visual overview of the project timeline.")
    lines.append("- Weekend work is kept light when weekend capacity is set low.")
    lines.append("- If the schedule is overloaded, reduce scope or increase available hours.")
    lines.append("")

    return "\n".join(lines)


def build_gantt_blocks(schedule: list[DailyPlan]) -> list[dict[str, Any]]:
    """
    Group task chunks by their original task name.
    This converts daily chunks into Gantt chart blocks.
    """
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for plan in schedule:
        for task in plan.tasks:
            if task.category == "Warning":
                continue

            if task.base_name not in grouped:
                grouped[task.base_name] = {
                    "task_name": task.base_name,
                    "category": task.category,
                    "start": plan.day,
                    "end": plan.day,
                    "total_hours": task.estimated_hours,
                }
            else:
                grouped[task.base_name]["end"] = plan.day
                grouped[task.base_name]["total_hours"] += task.estimated_hours

    return list(grouped.values())


def save_gantt_chart(
    project: dict[str, Any],
    schedule: list[DailyPlan],
    output_path: Path,
) -> None:
    blocks = build_gantt_blocks(schedule)

    if not blocks:
        return

    category_colors = {
        "Methods": "#4C78A8",
        "Figures": "#F58518",
        "Results": "#54A24B",
        "Discussion": "#E45756",
        "Abstract": "#72B7B2",
        "Final": "#B279A2",
        "Other": "#9D755D",
    }

    def get_color(category: str) -> str:
        if category in category_colors:
            return category_colors[category]
        if category.lower().startswith("figure"):
            return category_colors["Figures"]
        if category.lower().startswith("abstract"):
            return category_colors["Abstract"]
        if category.lower().startswith("final"):
            return category_colors["Final"]
        return category_colors["Other"]

    fig_height = max(5, len(blocks) * 0.6)
    fig, ax = plt.subplots(figsize=(13, fig_height))

    y_positions = list(range(len(blocks)))

    for i, block in enumerate(blocks):
        start_num = mdates.date2num(block["start"])
        end_num = mdates.date2num(block["end"])
        duration = max(1, end_num - start_num + 1)

        ax.barh(
            y=i,
            width=duration,
            left=start_num,
            height=0.55,
            color=get_color(block["category"]),
            edgecolor="black",
            linewidth=0.8,
            alpha=0.9,
        )

        ax.text(
            start_num + duration + 0.15,
            i,
            f'{block["total_hours"]:.1f} h',
            va="center",
            fontsize=9,
        )

    # Add horizontal separator lines between weeks
    week_keys = [
        (block["start"].isocalendar().year, block["start"].isocalendar().week)
        for block in blocks
    ]

    for i in range(1, len(blocks)):
        if week_keys[i] != week_keys[i - 1]:
            ax.axhline(
                y=i - 0.5,
                color="gray",
                linestyle="--",
                linewidth=1.0,
                alpha=0.7,
            )

    ax.set_yticks(y_positions)
    ax.set_yticklabels([b["task_name"] for b in blocks], fontsize=9)
    ax.invert_yaxis()

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))

    plt.xticks(rotation=45, ha="right")

    deadline = parse_date(project["deadline"])
    ax.axvline(
        mdates.date2num(deadline),
        color="red",
        linestyle="--",
        linewidth=1.5,
        label="Deadline",
    )

    ax.set_title(f"Gantt chart: {project['project_name']}", fontsize=14, pad=12)
    ax.set_xlabel("Date")
    ax.set_ylabel("Tasks")
    ax.grid(axis="x", linestyle="--", alpha=0.35)

    used_categories = []
    for block in blocks:
        category = block["category"]
        if category not in used_categories:
            used_categories.append(category)

    handles = [
        plt.Rectangle(
            (0, 0),
            1,
            1,
            color=get_color(category),
            label=category,
        )
        for category in used_categories
    ]

    handles.append(
        plt.Line2D(
            [0],
            [0],
            color="red",
            linestyle="--",
            label="Deadline",
        )
    )

    ax.legend(handles=handles, loc="best", fontsize=9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
