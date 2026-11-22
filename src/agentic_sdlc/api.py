"""FastAPI application for submitting and observing agentic SDLC projects."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agentic_sdlc.models import Brief, Phase
from agentic_sdlc.runtime import DeepAgentProjectRunner, ProjectRunContext, ProjectRunner

ProjectStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
REQUIRED_MODEL_ENV = ("PM_MODEL", "ARCHITECT_MODEL", "CODER_MODEL", "REVIEWER_MODEL")
ARTIFACT_POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 10.0


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(ApiModel):
    brief: str = Field(min_length=1)
    constraints: dict[str, str] = Field(default_factory=dict)
    interactive: bool = False


class AnswerRequest(ApiModel):
    answer: str = Field(min_length=1)


class ProjectEvent(ApiModel):
    sequence: int
    type: str
    message: str
    timestamp: datetime
    data: dict[str, object] = Field(default_factory=dict)


class ArtifactInfo(ApiModel):
    path: str
    size: int


class ProjectView(ApiModel):
    project_id: str
    status: ProjectStatus
    phase: Phase
    brief: Brief
    workspace: str
    artifacts: list[ArtifactInfo]
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateProjectResponse(ApiModel):
    project_id: str
    status: ProjectStatus
    phase: Phase
    workspace: str


@dataclass(slots=True)
class _ProjectRecord:
    project_id: str
    brief: Brief
    workspace: Path
    status: ProjectStatus = "queued"
    phase: Phase = "INTAKE"
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[ProjectEvent] = field(default_factory=list)
    answers: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None


class ProjectService:
    """In-process project registry and one-task-per-project worker."""

    def __init__(self, runner: ProjectRunner, workspace_root: Path) -> None:
        self._runner = runner
        self._workspace_root = workspace_root.resolve()
        self._projects: dict[str, _ProjectRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, request: CreateProjectRequest) -> _ProjectRecord:
        project_id = uuid.uuid4().hex
        record = _ProjectRecord(
            project_id=project_id,
            brief=Brief(
                text=request.brief,
                constraints=request.constraints,
                interactive=request.interactive,
            ),
            workspace=self._workspace_root / project_id,
        )
        async with self._lock:
            self._projects[project_id] = record
        await self._emit(record, "queued", "Project accepted and queued", {"phase": "INTAKE"})
        record.task = asyncio.create_task(self._execute(record), name=f"project-{project_id}")
        return record

    async def get(self, project_id: str) -> _ProjectRecord:
        async with self._lock:
            record = self._projects.get(project_id)
        if record is None:
            raise KeyError(project_id)
        return record

    async def answer(self, project_id: str, answer: str) -> None:
        record = await self.get(project_id)
        if record.status in TERMINAL_STATUSES:
            raise RuntimeError("project is no longer accepting answers")
        await record.answers.put(answer)
        await self._emit(record, "answer", "Clarification answer received", {})

    async def cancel(self, project_id: str) -> _ProjectRecord:
        record = await self.get(project_id)
        if record.status in TERMINAL_STATUSES:
            return record
        if record.task is not None:
            record.task.cancel()
        record.status = "cancelled"
        record.updated_at = datetime.now(UTC)
        await self._emit(record, "cancelled", "Project cancellation requested", {})
        return record

    def artifacts(self, record: _ProjectRecord) -> list[ArtifactInfo]:
        if not record.workspace.exists():
            return []
        artifacts: list[ArtifactInfo] = []
        for path in record.workspace.rglob("*"):
            relative = path.relative_to(record.workspace)
            if not path.is_file() or relative.parts[0] == "skills":
                continue
            artifacts.append(ArtifactInfo(path=relative.as_posix(), size=path.stat().st_size))
        return sorted(artifacts, key=lambda artifact: artifact.path)

    def artifact_path(self, record: _ProjectRecord, requested: str) -> Path:
        candidate = (record.workspace / requested).resolve()
        try:
            candidate.relative_to(record.workspace.resolve())
        except ValueError as exc:
            raise FileNotFoundError(requested) from exc
        if not candidate.is_file() or candidate.parts[: len(record.workspace.parts) + 1] == (
            *record.workspace.parts,
            "skills",
        ):
            raise FileNotFoundError(requested)
        return candidate

    async def stream(self, record: _ProjectRecord, after: int) -> AsyncIterator[str]:
        index = max(after, 0)
        while True:
            while index < len(record.events):
                event = record.events[index]
                index += 1
                payload = event.model_dump_json()
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {payload}\n\n"
            if record.status in TERMINAL_STATUSES:
                return
            try:
                async with record.condition:
                    await asyncio.wait_for(record.condition.wait(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"

    async def _execute(self, record: _ProjectRecord) -> None:
        record.status = "running"
        record.updated_at = datetime.now(UTC)
        await self._emit(record, "started", "Project worker started", {"phase": "INTAKE"})

        async def emit(event_type: str, message: str, data: dict[str, object] | None) -> None:
            if data and isinstance(data.get("phase"), str):
                record.phase = data["phase"]  # type: ignore[assignment]
            await self._emit(record, event_type, message, data or {})

        context = ProjectRunContext(
            project_id=record.project_id,
            brief=record.brief,
            workspace=record.workspace,
            answers=record.answers,
            emit=emit,
        )
        monitor = asyncio.create_task(
            self._watch_progress(record), name=f"project-monitor-{record.project_id}"
        )
        try:
            await self._runner.run(context)
        except asyncio.CancelledError:
            record.status = "cancelled"
            await self._emit(record, "cancelled", "Project worker stopped", {})
        except Exception as exc:  # boundary converts runner failures into project state
            record.status = "failed"
            record.phase = "FAILED"
            record.error = str(exc)
            await self._emit(record, "failed", "Project run failed", {"error": str(exc)})
        else:
            record.status = "completed"
            await self._emit_artifact_snapshot(record, final=True)
            await self._emit(
                record,
                "completed",
                "Project file generation completed; artifacts are ready for inspection",
                {"artifact_count": len(self.artifacts(record))},
            )
        finally:
            monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor

    async def _watch_progress(self, record: _ProjectRecord) -> None:
        known: tuple[tuple[str, int, int], ...] = ()
        last_heartbeat = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(ARTIFACT_POLL_SECONDS)
            signature = self._artifact_signature(record)
            if signature != known:
                before = {path for path, _, _ in known}
                created = [path for path, _, _ in signature if path not in before]
                known = signature
                await self._emit_artifact_snapshot(record, created=created)

            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                artifacts = self.artifacts(record)
                elapsed = int((datetime.now(UTC) - record.created_at).total_seconds())
                await self._emit(
                    record,
                    "heartbeat",
                    f"Worker active in {record.phase.replace('_', ' ').title()}",
                    {
                        "phase": record.phase,
                        "artifact_count": len(artifacts),
                        "elapsed_seconds": elapsed,
                    },
                )
                last_heartbeat = now

    def _artifact_signature(self, record: _ProjectRecord) -> tuple[tuple[str, int, int], ...]:
        signature: list[tuple[str, int, int]] = []
        if not record.workspace.exists():
            return ()
        for path in record.workspace.rglob("*"):
            relative = path.relative_to(record.workspace)
            if not path.is_file() or relative.parts[0] == "skills":
                continue
            stat = path.stat()
            signature.append((relative.as_posix(), stat.st_size, stat.st_mtime_ns))
        return tuple(sorted(signature))

    async def _emit_artifact_snapshot(
        self,
        record: _ProjectRecord,
        *,
        created: list[str] | None = None,
        final: bool = False,
    ) -> None:
        artifacts = self.artifacts(record)
        count = len(artifacts)
        if final:
            message = f"Final workspace contains {count} project file{'s' if count != 1 else ''}"
        elif created:
            message = (
                f"Created {len(created)} file{'s' if len(created) != 1 else ''}: "
                + ", ".join(created[:3])
            )
            if len(created) > 3:
                message += f" and {len(created) - 3} more"
        else:
            message = (
                f"Workspace updated; {count} project file{'s' if count != 1 else ''} available"
            )
        await self._emit(
            record,
            "artifact",
            message,
            {"artifact_count": count, "created": (created or [])[:20], "final": final},
        )

    async def _emit(
        self,
        record: _ProjectRecord,
        event_type: str,
        message: str,
        data: dict[str, object],
    ) -> None:
        record.updated_at = datetime.now(UTC)
        event = ProjectEvent(
            sequence=len(record.events) + 1,
            type=event_type,
            message=message,
            timestamp=record.updated_at,
            data=data,
        )
        record.events.append(event)
        async with record.condition:
            record.condition.notify_all()


def _view(service: ProjectService, record: _ProjectRecord) -> ProjectView:
    return ProjectView(
        project_id=record.project_id,
        status=record.status,
        phase=record.phase,
        brief=record.brief,
        workspace=str(record.workspace),
        artifacts=service.artifacts(record),
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def runtime_readiness() -> dict[str, object]:
    missing = [name for name in REQUIRED_MODEL_ENV if not os.environ.get(name)]
    try:
        deepagents_version = importlib.metadata.version("deepagents")
    except importlib.metadata.PackageNotFoundError:
        deepagents_version = None
    expected_version = "0.7.41"
    issues: list[str] = []
    if missing:
        issues.append(f"missing model settings: {', '.join(missing)}")
    configured_models = [os.environ.get(name, "") for name in REQUIRED_MODEL_ENV]
    if any(model.startswith("openai:") for model in configured_models) and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        issues.append("OPENAI_API_KEY is required for configured OpenAI models")
    if deepagents_version != expected_version:
        issues.append(
            f"deepagents {expected_version} is required; installed: {deepagents_version or 'none'}"
        )
    return {
        "ready": not issues,
        "issues": issues,
        "deepagents_version": deepagents_version,
        "execution": "file-only",
    }


def create_app(
    *,
    runner: ProjectRunner | None = None,
    workspace_root: Path | None = None,
) -> FastAPI:
    root = workspace_root or Path(
        os.environ.get("AGENTIC_SDLC_WORKSPACE_ROOT", ".agentic-sdlc/projects")
    )
    service = ProjectService(runner or DeepAgentProjectRunner(), root)
    app = FastAPI(title="Agentic SDLC API", version="0.1.0")
    app.state.project_service = service

    async def project_or_404(project_id: str) -> _ProjectRecord:
        try:
            return await service.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, object]:
        return runtime_readiness()

    @app.post(
        "/projects",
        response_model=CreateProjectResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
        record = await service.create(request)
        return CreateProjectResponse(
            project_id=record.project_id,
            status=record.status,
            phase=record.phase,
            workspace=str(record.workspace),
        )

    @app.get("/projects/{project_id}", response_model=ProjectView)
    async def get_project(project_id: str) -> ProjectView:
        return _view(service, await project_or_404(project_id))

    @app.get("/projects/{project_id}/events")
    async def project_events(
        project_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        record = await project_or_404(project_id)
        cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
        return StreamingResponse(
            service.stream(record, cursor),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/projects/{project_id}/answers", status_code=status.HTTP_202_ACCEPTED)
    async def answer_project(project_id: str, request: AnswerRequest) -> dict[str, str]:
        try:
            await service.answer(project_id, request.answer)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "accepted"}

    @app.post("/projects/{project_id}/cancel", response_model=ProjectView)
    async def cancel_project(project_id: str) -> ProjectView:
        try:
            record = await service.cancel(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return _view(service, record)

    @app.get("/projects/{project_id}/artifacts/{artifact_path:path}")
    async def get_artifact(project_id: str, artifact_path: str) -> FileResponse:
        record = await project_or_404(project_id)
        try:
            path = service.artifact_path(record, artifact_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        return FileResponse(path)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("agentic_sdlc.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
