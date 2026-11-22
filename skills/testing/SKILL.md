---
name: testing
description: Turn acceptance criteria into independent tests, story trace markers, reproducible failure reports, and integration QA evidence.
---

# Acceptance verification

For each criterion, identify the observable setup, action, and expected result. Look for missing
negative cases and boundary behavior. Do not treat the implementer's test suite as sufficient
evidence without inspecting its assertions.

Tests that establish story coverage must contain `covers: US-n`. Keep failures reproducible and
separate product defects from environment failures. Report commands, checked criteria, failing
tests, and a concise evidence-based conclusion.
