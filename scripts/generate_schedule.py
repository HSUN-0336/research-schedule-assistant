from __future__ import annotations

import argparse
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # 让 GitHub Actions 在无界面环境下也能画图
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
    """Parse a YYYY-MM-DD date string."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_project(path: Path) -> dict[str, Any]:
    """Load project YAML."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_daily_capacity(day: date, project: dict[str, Any]) -> float:
    """Return available working hours for a given day."""
    available = project.get("available_time", {})
    weekday_hours = float(available.get("weekdays_hours", 3))
    weekend_hours = float(available.get("weekends_hours", 1))
    return weekend_hours if day.weekday() >= 5 else weekday_hours


def expand_tasks(project: dict[str, Any]) -> list[Task]:
    """
    Convert section-level work packages into smaller tasks.

    Rule:
    - Each task block is split into chunks of about 2 hours.
    - This avoids putting one huge vague task on a single day.
    """
    tasks: list[Task] = []
    sections = project.get("sections", [])

    for section in sections:
        name = section["name"]
        hours = float(section.get("estimated_hours", 2))
        n_chunks = max(1, math.ceil(hours / 2))
        chunk_hours = hours / n_chunks

        for i in range(1, n_chunks + 1):
            if n_chunks == 1:
                task_name = name
            else:
                task_name = f"{name} — part {i}/{n_chunks}"
            tasks.append(Task(name=task_name, estimated_hours=chunk_hours))

    return tasks


def build_schedule(project: dict[str, Any]) -> list[DailyPlan]:
    """Generate a date-based schedule from start date to deadline."""
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
        daily_tasks: list[str] = []

        while task_index < len(tasks):
            task = tasks[task_index]

            # If the task fits today, assign it.
            if task.estimated_hours <= remaining_capacity + 1e-9:
                daily_tasks.append(f"{task.name} ({task.estimated_hours:.1f} h)")
                remaining_capacity -= task.estimated_hours
                task_index += 1
            else:
                # Do not split tiny leftover capacity into messy fragments.
                break

        # If low-energy mode is on, make weekends explicitly light.
        low_energy = bool(project.get("available_time", {}).get("low_energy_mode", False))
        if low_energy and current_day.weekday() >= 5 and not daily_tasks:
            daily_tasks.append("Recovery day: only optional reading or figure notes")

        schedule.append(DailyPlan(day=current_day, capacity_hours=capacity, tasks=daily_tasks))
        current_day += timedelta(days=1)

    # Add remaining empty days until deadline for review/rest.
    while current_day <= deadline:
        capacity = get_daily_capacity(current_day, project)
        if current_day.weekday() >= 5:
            tasks_for_day = ["Recovery / buffer day"]
        else:
            tasks_for_day = ["Buffer: revise weak sections, check logic, or catch up"]
        schedule.append(DailyPlan(day=current_day, capacity_hours=capacity, tasks=tasks_for_day))
        current_day += timedelta(days=1)

    if task_index < len(tasks):
        remaining = tasks[task_index:]
        remaining_hours = sum(t.estimated_hours for t in remaining)
        schedule.append(
            DailyPlan(
                day=deadline,
                capacity_hours=0,
                tasks=[
                    f"WARNING: schedule is overloaded. About {remaining_hours:.1f} h could not be assigned before the deadline."
                ],
            )
        )

    return schedule


def render_markdown(project: dict[str, Any], schedule: list[DailyPlan]) -> str:
    """Render schedule as Markdown."""
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
        task_text = "<br>".join(plan.tasks) if plan.tasks else "No assigned task"
        lines.append(
            f"| {plan.day.isoformat()} | {day_name} | {plan.capacity_hours:.1f} h | {task_text} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- The schedule is intentionally chunked into small tasks.")
    lines.append("- Weekend work is kept light when low-energy mode is enabled.")
    lines.append("- If the schedule is overloaded, reduce scope or increase available hours.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a research project schedule.")
    parser.add_argument("project_file", type=str, help="Path to project YAML file.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="schedules",
        help="Directory where the Markdown schedule will be saved.",
    )

    args = parser.parse_args()
    project_path = Path(args.project_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = load_project(project_path)
    schedule = build_schedule(project)
    markdown = render_markdown(project, schedule)

    slug = project.get("project_slug") or project_path.stem
    output_path = output_dir / f"{slug}_schedule.md"

    output_path.write_text(markdown, encoding="utf-8")
    print(f"Schedule written to: {output_path}")


if __name__ == "__main__":
    main()
