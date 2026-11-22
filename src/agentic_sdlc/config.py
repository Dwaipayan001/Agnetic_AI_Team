"""Environment-backed runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

load_dotenv()


class Settings(BaseModel):
    """Validated settings used to construct and control the agent team."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pm_model: str
    architect_model: str
    coder_model: str
    reviewer_model: str
    ui_developer_model: str | None = None
    devops_model: str | None = None
    qa_model: str | None = None

    max_task_ci_rounds: int = Field(default=4, ge=1)
    max_task_review_rounds: int = Field(default=3, ge=1)
    max_design_review_rounds: int = Field(default=2, ge=1)
    max_bugfix_cycles: int = Field(default=3, ge=0)
    max_tasks: int = Field(default=60, ge=1)
    max_clarifying_questions: int = Field(default=5, ge=0)

    max_tokens_per_project: int | None = Field(default=None, ge=1)
    max_cost_usd_per_project: float | None = Field(default=None, gt=0)
    max_wallclock_hours: float | None = Field(default=None, gt=0)

    interactive: bool = False
    gate_plan_approval: bool = False

    @model_validator(mode="after")
    def validate_model_names(self) -> Settings:
        for field_name in (
            "pm_model",
            "architect_model",
            "coder_model",
            "reviewer_model",
            "ui_developer_model",
            "devops_model",
            "qa_model",
        ):
            value = getattr(self, field_name)
            if value is not None and ":" not in value:
                raise ValueError(f"{field_name} must use provider:model format")
        return self

    @property
    def resolved_ui_developer_model(self) -> str:
        return self.ui_developer_model or self.coder_model

    @property
    def resolved_devops_model(self) -> str:
        return self.devops_model or self.coder_model

    @property
    def resolved_qa_model(self) -> str:
        return self.qa_model or self.coder_model

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Load settings with clear errors for missing model configuration."""
        env = os.environ if environ is None else environ
        required = ("PM_MODEL", "ARCHITECT_MODEL", "CODER_MODEL", "REVIEWER_MODEL")
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        def optional_int(name: str) -> int | None:
            return int(env[name]) if env.get(name) else None

        def optional_float(name: str) -> float | None:
            return float(env[name]) if env.get(name) else None

        def boolean(name: str, default: bool = False) -> bool:
            value = env.get(name)
            if value is None:
                return default
            normalized = value.strip().lower()
            if normalized not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
                raise ValueError(f"{name} must be a boolean")
            return normalized in {"1", "true", "yes", "on"}

        return cls.model_validate(
            {
                "pm_model": env["PM_MODEL"],
                "architect_model": env["ARCHITECT_MODEL"],
                "coder_model": env["CODER_MODEL"],
                "reviewer_model": env["REVIEWER_MODEL"],
                "ui_developer_model": env.get("UI_DEVELOPER_MODEL"),
                "devops_model": env.get("DEVOPS_MODEL"),
                "qa_model": env.get("QA_MODEL"),
                "max_task_ci_rounds": int(env.get("MAX_TASK_CI_ROUNDS", "4")),
                "max_task_review_rounds": int(env.get("MAX_TASK_REVIEW_ROUNDS", "3")),
                "max_design_review_rounds": int(env.get("MAX_DESIGN_REVIEW_ROUNDS", "2")),
                "max_bugfix_cycles": int(env.get("MAX_BUGFIX_CYCLES", "3")),
                "max_tasks": int(env.get("MAX_TASKS", "60")),
                "max_clarifying_questions": int(env.get("MAX_CLARIFYING_QUESTIONS", "5")),
                "max_tokens_per_project": optional_int("MAX_TOKENS_PER_PROJECT"),
                "max_cost_usd_per_project": optional_float("MAX_COST_USD_PER_PROJECT"),
                "max_wallclock_hours": optional_float("MAX_WALLCLOCK_HOURS"),
                "interactive": boolean("INTERACTIVE"),
                "gate_plan_approval": boolean("GATE_PLAN_APPROVAL"),
            }
        )
