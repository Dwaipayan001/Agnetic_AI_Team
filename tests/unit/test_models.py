import pytest
from pydantic import ValidationError

from agentic_sdlc.models import ReviewFinding, ReviewVerdict, Story, Task
from agentic_sdlc.models import TestReport as AgentTestReport


def test_mutable_defaults_are_not_shared() -> None:
    first = Story(
        id="US-1",
        as_a="user",
        i_want="notes",
        so_that="I remember",
        acceptance=["works"],
    )
    second = Story(
        id="US-2",
        as_a="user",
        i_want="search",
        so_that="I find",
        acceptance=["works"],
    )

    first.acceptance.append("another")

    assert second.acceptance == ["works"]


def test_task_cannot_depend_on_itself() -> None:
    with pytest.raises(ValidationError, match="depend on itself"):
        Task(
            id="T-1",
            title="Build",
            epic="Core",
            owner="coder",
            acceptance=["done"],
            depends_on=["T-1"],
            size="S",
        )


def test_reviewer_cannot_approve_major_finding() -> None:
    with pytest.raises(ValidationError, match="cannot approve"):
        ReviewVerdict(
            verdict="approve",
            head_sha="abcdef123",
            findings=[ReviewFinding(severity="major", comment="Acceptance gap")],
        )


def test_passing_report_cannot_list_failures() -> None:
    with pytest.raises(ValidationError, match="cannot contain failing"):
        AgentTestReport(
            passed=True,
            commands_run=["pytest"],
            failing_tests=["test_bad"],
            summary="Contradictory",
        )
