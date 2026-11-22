"""Structured contracts shared by agents and deterministic controllers."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STORY_ID = re.compile(r"^US-[1-9][0-9]*$")
TASK_ID = re.compile(r"^T-[1-9][0-9]*$")

Owner = Literal["architect", "coder", "ui-developer", "devops", "qa-tester"]
TaskStatus = Literal["todo", "in_progress", "in_review", "done", "blocked"]
Phase = Literal[
    "INTAKE",
    "PRD",
    "ARCHITECTURE",
    "PLANNING",
    "BOOTSTRAP",
    "BUILDING",
    "INTEGRATION_QA",
    "HARDENING",
    "RELEASE_READY",
    "READY_FOR_HUMAN",
    "SHIPPED",
    "NEEDS_HUMAN",
    "FAILED",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Brief(ContractModel):
    text: str = Field(min_length=1)
    constraints: dict[str, str] = Field(default_factory=dict)
    interactive: bool = False


class Story(ContractModel):
    id: str
    as_a: str = Field(min_length=1)
    i_want: str = Field(min_length=1)
    so_that: str = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    priority: Literal["must", "should", "could"] = "must"

    @field_validator("id")
    @classmethod
    def valid_story_id(cls, value: str) -> str:
        if not STORY_ID.fullmatch(value):
            raise ValueError("story id must match US-<positive integer>")
        return value

    @field_validator("acceptance")
    @classmethod
    def nonempty_acceptance(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("acceptance criteria must not be blank")
        return values


class Task(ContractModel):
    id: str
    title: str = Field(min_length=1)
    epic: str = Field(min_length=1)
    owner: Owner
    stories: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    size: Literal["S", "M", "L"]
    status: TaskStatus = "todo"

    @field_validator("id")
    @classmethod
    def valid_task_id(cls, value: str) -> str:
        if not TASK_ID.fullmatch(value):
            raise ValueError("task id must match T-<positive integer>")
        return value

    @field_validator("stories")
    @classmethod
    def valid_story_references(cls, values: list[str]) -> list[str]:
        if any(not STORY_ID.fullmatch(value) for value in values):
            raise ValueError("task story references must match US-<positive integer>")
        return values

    @field_validator("depends_on")
    @classmethod
    def valid_task_references(cls, values: list[str]) -> list[str]:
        if any(not TASK_ID.fullmatch(value) for value in values):
            raise ValueError("dependencies must match T-<positive integer>")
        return values

    @field_validator("acceptance")
    @classmethod
    def task_acceptance_not_blank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("task acceptance criteria must not be blank")
        return values

    @model_validator(mode="after")
    def cannot_depend_on_self(self) -> Task:
        if self.id in self.depends_on:
            raise ValueError("task cannot depend on itself")
        return self


class Backlog(ContractModel):
    epics: list[str] = Field(min_length=1)
    tasks: list[Task] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_task_ids(self) -> Backlog:
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique")
        return self


class ReviewFinding(ContractModel):
    severity: Literal["blocker", "major", "minor", "nit"]
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    comment: str = Field(min_length=1)


class ReviewVerdict(ContractModel):
    verdict: Literal["approve", "request_changes"]
    head_sha: str = Field(min_length=7)
    findings: list[ReviewFinding] = Field(default_factory=list)
    stories_checked: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def blockers_prevent_approval(self) -> ReviewVerdict:
        if self.verdict == "approve" and any(
            finding.severity in {"blocker", "major"} for finding in self.findings
        ):
            raise ValueError("cannot approve with blocker or major findings")
        return self


class TestReport(ContractModel):
    passed: bool
    commands_run: list[str] = Field(min_length=1)
    failing_tests: list[str] = Field(default_factory=list)
    acceptance_checked: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def passing_report_has_no_failures(self) -> TestReport:
        if self.passed and self.failing_tests:
            raise ValueError("passing report cannot contain failing tests")
        return self


class ProjectState(ContractModel):
    project_id: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    phase: Phase = "INTAKE"
    task_statuses: dict[str, TaskStatus] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)
    budgets: dict[str, float] = Field(default_factory=dict)
    verdicts: dict[str, ReviewVerdict] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
