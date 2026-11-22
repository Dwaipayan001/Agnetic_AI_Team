"""Deep Agents wiring for the AI engineering team."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from agentic_sdlc.config import Settings
from agentic_sdlc.models import ReviewVerdict, TestReport

ROLE_NAMES = (
    "architect",
    "coder",
    "ui-developer",
    "devops",
    "qa-tester",
    "reviewer",
)


class RoleToolProvider(Protocol):
    """Provides a deliberately filtered set of host tools for one role."""

    def for_role(self, role: str) -> Sequence[Any]:
        """Return only tools explicitly permitted for the role."""


class EmptyRoleTools:
    """Tool provider for local construction and tests without GitHub."""

    def for_role(self, role: str) -> Sequence[Any]:
        if role not in {*ROLE_NAMES, "pm"}:
            raise ValueError(f"unknown role: {role}")
        return ()


def load_prompt(role: str) -> str:
    if role not in {*ROLE_NAMES, "pm"}:
        raise ValueError(f"unknown role: {role}")
    path = Path(__file__).with_name("prompts") / f"{role.replace('-', '_')}.md"
    return path.read_text(encoding="utf-8")


def _deepagents_api() -> tuple[Callable[..., Any], Callable[..., Any]]:
    try:
        from deepagents import FilesystemPermission, create_deep_agent
    except ImportError as exc:
        raise RuntimeError(
            "Deep Agents is not installed; run `uv sync --locked` before building the team"
        ) from exc
    return create_deep_agent, FilesystemPermission


def _write_permissions(permission: Callable[..., Any], allowed: list[str]) -> list[Any]:
    rules: list[Any] = []
    if allowed:
        rules.append(permission(operations=["write"], paths=allowed, mode="allow"))
    rules.append(permission(operations=["write"], paths=["/**"], mode="deny"))
    return rules


def build_subagent_specs(
    settings: Settings,
    github_tools: RoleToolProvider | None = None,
    *,
    permission_factory: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Create isolated, least-privilege role specifications."""
    tools = github_tools or EmptyRoleTools()
    if permission_factory is None:
        _, permission_factory = _deepagents_api()

    docs = ["/docs/**", "/workspace/repo/docs/**"]
    qa_outputs = [
        "/tests/**",
        "/workspace/repo/tests/**",
        "/docs/QA_REPORT.md",
        "/workspace/repo/docs/QA_REPORT.md",
        "/.agent/test-report.md",
        "/workspace/repo/.agent/test-report.md",
    ]
    return [
        {
            "name": "architect",
            "description": (
                "Designs architecture, API contracts, data models, and ADRs from the PRD."
            ),
            "system_prompt": load_prompt("architect"),
            "model": settings.architect_model,
            "tools": list(tools.for_role("architect")),
            "skills": ["/skills/architecture/"],
            "permissions": _write_permissions(permission_factory, docs),
            "mode": "isolated",
        },
        {
            "name": "coder",
            "description": (
                "Implements one backend or general backlog task with focused unit tests."
            ),
            "system_prompt": load_prompt("coder"),
            "model": settings.coder_model,
            "tools": [],
            "skills": ["/skills/coding/", "/skills/git-workflow/"],
            "permissions": [],
            "mode": "isolated",
        },
        {
            "name": "ui-developer",
            "description": "Implements one accessible front-end task with component and UI tests.",
            "system_prompt": load_prompt("ui-developer"),
            "model": settings.resolved_ui_developer_model,
            "tools": [],
            "skills": ["/skills/coding/", "/skills/ui/"],
            "permissions": [],
            "mode": "isolated",
        },
        {
            "name": "devops",
            "description": "Builds project scaffolding, CI, containers, and build configuration.",
            "system_prompt": load_prompt("devops"),
            "model": settings.resolved_devops_model,
            "tools": [],
            "skills": ["/skills/devops/"],
            "permissions": [],
            "mode": "isolated",
        },
        {
            "name": "qa-tester",
            "description": (
                "Independently verifies acceptance criteria and returns structured reports."
            ),
            "system_prompt": load_prompt("qa-tester"),
            "model": settings.resolved_qa_model,
            "tools": [],
            "skills": ["/skills/testing/"],
            "permissions": _write_permissions(permission_factory, qa_outputs),
            "response_format": TestReport,
            "mode": "isolated",
        },
        {
            "name": "reviewer",
            "description": "Reviews architecture and diffs and returns a head-SHA-bound verdict.",
            "system_prompt": load_prompt("reviewer"),
            "model": settings.reviewer_model,
            "tools": list(tools.for_role("reviewer")),
            "skills": ["/skills/review/"],
            "permissions": _write_permissions(permission_factory, []),
            "response_format": ReviewVerdict,
            "mode": "isolated",
        },
    ]


def build_team(
    *,
    backend: Any,
    settings: Settings,
    github_tools: RoleToolProvider | None = None,
    host_tools: Sequence[Any] = (),
    intake_tools: Sequence[Any] = (),
    checkpointer: Any = None,
    agent_factory: Callable[..., Any] | None = None,
    permission_factory: Callable[..., Any] | None = None,
) -> Any:
    """Build the PM-led Deep Agent with six isolated specialist subagents."""
    if agent_factory is None or permission_factory is None:
        deep_agent_factory, filesystem_permission = _deepagents_api()
        agent_factory = agent_factory or deep_agent_factory
        permission_factory = permission_factory or filesystem_permission

    filtered_tools = github_tools or EmptyRoleTools()
    subagents = build_subagent_specs(
        settings,
        filtered_tools,
        permission_factory=permission_factory,
    )
    pm_allowed = [
        "/docs/**",
        "/workspace/repo/docs/**",
        "/.agent/**",
        "/workspace/repo/.agent/**",
    ]
    return agent_factory(
        model=settings.pm_model,
        system_prompt=load_prompt("pm"),
        tools=[*filtered_tools.for_role("pm"), *host_tools, *intake_tools],
        subagents=subagents,
        backend=backend,
        skills=["/skills/pm/"],
        permissions=_write_permissions(permission_factory, pm_allowed),
        checkpointer=checkpointer,
        name="agentic-sdlc-pm",
    )
