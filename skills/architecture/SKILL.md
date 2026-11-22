---
name: architecture
description: Convert an approved PRD into implementable architecture, contracts, ADRs, and a risk-based test strategy.
---

# Architecture workflow

Start from user stories and non-functional requirements. Define system boundaries and the simplest
component model that satisfies them. Make data ownership, trust boundaries, failure modes, and
external dependencies explicit.

Choose the stack by constraints and team operability, not novelty. Specify stable contracts before
internal design. Record consequential choices and rejected alternatives as ADRs.

The test strategy must map risk to unit, integration, contract, end-to-end, security, and basic
performance checks. Identify any architecture assumption that requires an early spike.
