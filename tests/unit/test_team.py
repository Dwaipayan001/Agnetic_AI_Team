from typing import Any

from agentic_sdlc.config import Settings
from agentic_sdlc.models import ReviewVerdict
from agentic_sdlc.models import TestReport as AgentTestReport
from agentic_sdlc.team import EmptyRoleTools, build_subagent_specs, build_team


def settings() -> Settings:
    return Settings(
        pm_model="openai:pm",
        architect_model="openai:architect",
        coder_model="openai:coder",
        reviewer_model="anthropic:reviewer",
    )


def permission(**kwargs: Any) -> dict[str, Any]:
    return kwargs


def test_all_six_specialists_are_isolated_and_have_explicit_tools() -> None:
    specs = build_subagent_specs(settings(), EmptyRoleTools(), permission_factory=permission)

    assert {spec["name"] for spec in specs} == {
        "architect",
        "coder",
        "ui-developer",
        "devops",
        "qa-tester",
        "reviewer",
    }
    assert all(spec["mode"] == "isolated" for spec in specs)
    assert all("tools" in spec for spec in specs)
    assert all(spec["skills"] for spec in specs)
    qa = next(spec for spec in specs if spec["name"] == "qa-tester")
    reviewer = next(spec for spec in specs if spec["name"] == "reviewer")
    assert qa["response_format"] is AgentTestReport
    assert reviewer["response_format"] is ReviewVerdict


def test_reviewer_is_read_only_and_coder_does_not_inherit_pm_permissions() -> None:
    specs = build_subagent_specs(settings(), permission_factory=permission)
    reviewer = next(spec for spec in specs if spec["name"] == "reviewer")
    coder = next(spec for spec in specs if spec["name"] == "coder")

    assert reviewer["permissions"][-1] == {
        "operations": ["write"],
        "paths": ["/**"],
        "mode": "deny",
    }
    assert coder["permissions"] == []


def test_build_team_passes_pm_and_subagents_to_factory() -> None:
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "compiled-team"

    result = build_team(
        backend="sandbox",
        settings=settings(),
        agent_factory=factory,
        permission_factory=permission,
    )

    assert result == "compiled-team"
    assert captured["model"] == "openai:pm"
    assert captured["backend"] == "sandbox"
    assert len(captured["subagents"]) == 6
    assert captured["skills"] == ["/skills/pm/"]
    assert captured["name"] == "agentic-sdlc-pm"
