---
name: git-workflow
description: Keep agent task work isolated, reviewable, and traceable using the platform branch and commit conventions.
---

# Task git workflow

Work only on the assigned `task/<id>-<slug>` branch derived from `integration`. Keep commits small
and use conventional commit subjects with `Agent-Task: <task id>` trailers.

Before handoff, ensure generated or secret-bearing files are excluded, checks pass, and the diff
contains only task-related changes. Never push directly to `main` or `integration`; publishing and
merging belong to guarded host tools.
