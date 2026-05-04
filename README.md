# Research Schedule Assistant

A lightweight GitHub-friendly tool for turning a research project deadline into a detailed writing / analysis schedule.

## What it does

You provide a YAML file with:

- project name
- project type
- deadline
- current status
- available working time
- research summary
- main outputs

The script generates a Markdown schedule with daily tasks.

## Quick start

Install dependencies:

```bash
pip install pyyaml
```

Run:

```bash
python scripts/generate_schedule.py projects/gcb_pwn_landscape.yml
```

The output will be saved to:

```text
schedules/gcb_pwn_landscape_schedule.md
```

## Example input

See:

```text
projects/gcb_pwn_landscape.yml
```

## Optional GitHub Actions

This repo includes a workflow file:

```text
.github/workflows/generate_schedule.yml
```

It can regenerate schedules automatically when project YAML files are changed.
