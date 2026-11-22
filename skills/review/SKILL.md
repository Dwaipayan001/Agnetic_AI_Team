---
name: review
description: Review designs and code changes against requirements, architecture, correctness, security, tests, and maintainability.
---

# Independent review

Review the submitted state, not the author's description. Trace the change to its task and stories,
then inspect correctness, failure handling, contracts, tests, security boundaries, and operational
impact.

Use blocker for unsafe or unusable work; major for required behavior, correctness, or test gaps;
minor for non-blocking maintainability problems; and nit for optional polish. Cite concrete files
and lines when possible. Approval is invalid while blocker or major findings remain.
