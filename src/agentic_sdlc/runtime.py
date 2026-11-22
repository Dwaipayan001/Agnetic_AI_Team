"""Project runner implementations used by the HTTP API."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from agentic_sdlc.config import Settings
from agentic_sdlc.filesystem_backend import create_workspace_backend
from agentic_sdlc.models import Brief
from agentic_sdlc.team import build_team

EmitEvent = Callable[[str, str, dict[str, object] | None], Awaitable[None]]

TOOL_ACTIVITY = {
    "task": "Delegating work to a specialist",
    "write_file": "Writing a project file",
    "edit_file": "Editing a project file",
    "read_file": "Reading project context",
    "ls": "Inspecting the project workspace",
    "glob": "Finding relevant project files",
    "grep": "Searching the project workspace",
}


@dataclass(slots=True)
class ProjectRunContext:
    """Everything a runner needs, without depending on FastAPI internals."""

    project_id: str
    brief: Brief
    workspace: Path
    answers: asyncio.Queue[str]
    emit: EmitEvent


class ProjectRunner(Protocol):
    async def run(self, context: ProjectRunContext) -> None:
        """Run one project until completion, failure, cancellation, or an interrupt."""


class ProjectActivityCallback(AsyncCallbackHandler):
    """Translate safe agent lifecycle callbacks into user-facing progress events."""

    def __init__(self, emit: EmitEvent) -> None:
        self._emit = emit
        self._tools: dict[UUID, tuple[str, str]] = {}
        self._model_calls = 0

    async def on_chat_model_start(
        self,
        _serialized: dict[str, Any],
        _messages: list[list[Any]],
        *,
        run_id: UUID,
        **_kwargs: Any,
    ) -> None:
        self._model_calls += 1
        await self._emit(
            "agent",
            "Planning the next engineering action",
            {"state": "thinking", "model_call": self._model_calls, "run_id": str(run_id)},
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        _input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or serialized.get("name") or "tool")
        message = TOOL_ACTIVITY.get(name, f"Running {name.replace('_', ' ')}")
        self._tools[run_id] = (name, message)
        await self._emit("agent", message, {"tool": name, "state": "started"})

    async def on_tool_end(
        self,
        _output: Any,
        *,
        run_id: UUID,
        **_kwargs: Any,
    ) -> None:
        name, message = self._tools.pop(run_id, ("tool", "Agent task"))
        await self._emit("agent", f"{message} finished", {"tool": name, "state": "finished"})


class DeepAgentProjectRunner:
    """Run the PM team against a file workspace without local shell execution."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def run(self, context: ProjectRunContext) -> None:
        settings = self._settings or Settings.from_env()
        await context.emit("phase", "Preparing project workspace", {"phase": "INTAKE"})
        self._prepare_workspace(context)

        try:
            from langgraph.checkpoint.memory import InMemorySaver
        except ImportError as exc:
            raise RuntimeError(
                "Deep Agents runtime dependencies are unavailable; run `uv sync --locked`"
            ) from exc

        backend = create_workspace_backend(context.workspace)
        team = build_team(
            backend=backend,
            checkpointer=InMemorySaver(),
            settings=settings,
        )
        await context.emit(
            "phase",
            "PM team started discovery and implementation",
            {"phase": "BUILDING"},
        )
        result = await team.ainvoke(
            {"messages": [{"role": "user", "content": self._project_prompt(context.brief)}]},
            config={
                "configurable": {"thread_id": context.project_id},
                "callbacks": [ProjectActivityCallback(context.emit)],
            },
        )
        await context.emit(
            "result",
            "Agent team finished its file-generation run",
            {"summary": self._last_message(result), "phase": "BUILDING"},
        )

    @staticmethod
    def _project_prompt(brief: Brief) -> str:
        constraints = json.dumps(brief.constraints, indent=2, sort_keys=True)
        return f"""Create the smallest coherent product that satisfies this brief.

Brief:
{brief.text}

Constraints:
{constraints}

Operate autonomously. Record assumptions, create the PRD, stories, architecture, and backlog,
then delegate implementation to the appropriate specialists. Generate source, tests, README, and
delivery configuration in this workspace. This API uses a file-only backend: do not claim that
commands or tests ran. End with a concise summary of artifacts and remaining checks.
"""

    @staticmethod
    def _last_message(result: object) -> str:
        if not isinstance(result, dict):
            return str(result)
        messages = result.get("messages", [])
        if not messages:
            return "Run completed without a final message."
        content = getattr(messages[-1], "content", None)
        if content is None and isinstance(messages[-1], dict):
            content = messages[-1].get("content")
        return str(content or "Run completed.")[:4000]

    @staticmethod
    def _prepare_workspace(context: ProjectRunContext) -> None:
        context.workspace.mkdir(parents=True, exist_ok=True)
        (context.workspace / "brief.md").write_text(context.brief.text, encoding="utf-8")
        skill_source = Path(__file__).parents[2] / "skills"
        skill_target = context.workspace / "skills"
        if skill_source.is_dir() and not skill_target.exists():
            shutil.copytree(skill_source, skill_target)
