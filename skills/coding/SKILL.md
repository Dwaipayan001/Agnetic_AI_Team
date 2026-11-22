---
name: coding
description: Implement one bounded backlog task safely within an existing repository and verify it with focused tests and project-native checks.
---

# Coding workflow

Inspect the repository's own instructions, tooling, architecture, and nearby implementation before
editing. Preserve public contracts unless the task explicitly changes them.

Implement the smallest cohesive change that meets acceptance. Test behavior and edge cases, not
implementation trivia. Add `covers: US-n` where a test verifies a story. Use the repository's own
formatter, linter, type checker, and test commands and report exactly what ran.

Do not hide failures, weaken tests, or introduce unrelated cleanup. Propose an ADR when the task
reveals a necessary architectural change.
