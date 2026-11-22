from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentic_sdlc import api as api_module
from agentic_sdlc.api import create_app
from agentic_sdlc.runtime import ProjectRunContext


class SuccessfulRunner:
    async def run(self, context: ProjectRunContext) -> None:
        context.workspace.mkdir(parents=True, exist_ok=True)
        (context.workspace / "hello.txt").write_text("hello", encoding="utf-8")
        await context.emit("phase", "Building", {"phase": "BUILDING"})


class BlockingRunner:
    async def run(self, context: ProjectRunContext) -> None:
        context.workspace.mkdir(parents=True, exist_ok=True)
        await asyncio.sleep(3600)


class FailingRunner:
    async def run(self, context: ProjectRunContext) -> None:
        raise RuntimeError("model unavailable")


class ProgressiveRunner:
    async def run(self, context: ProjectRunContext) -> None:
        context.workspace.mkdir(parents=True, exist_ok=True)
        (context.workspace / "first.py").write_text("first = True", encoding="utf-8")
        await asyncio.sleep(0.04)
        (context.workspace / "second.py").write_text("second = True", encoding="utf-8")
        await asyncio.sleep(0.04)


def wait_for_terminal(client: TestClient, project_id: str) -> dict[str, object]:
    for _ in range(100):
        response = client.get(f"/projects/{project_id}")
        body = response.json()
        if body["status"] in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.01)
    raise AssertionError("project did not reach a terminal status")


def test_create_project_runs_in_background_and_exposes_artifacts(tmp_path: Path) -> None:
    app = create_app(runner=SuccessfulRunner(), workspace_root=tmp_path)
    with TestClient(app) as client:
        response = client.post("/projects", json={"brief": "Create a greeting file"})

        assert response.status_code == 202
        project_id = response.json()["project_id"]
        project = wait_for_terminal(client, project_id)
        assert project["status"] == "completed"
        assert project["phase"] == "BUILDING"
        assert {item["path"] for item in project["artifacts"]} == {"hello.txt"}

        artifact = client.get(f"/projects/{project_id}/artifacts/hello.txt")
        assert artifact.status_code == 200
        assert artifact.text == "hello"

        events = client.get(f"/projects/{project_id}/events")
        assert events.status_code == 200
        assert "event: completed" in events.text


def test_runner_failure_is_project_state_not_http_crash(tmp_path: Path) -> None:
    app = create_app(runner=FailingRunner(), workspace_root=tmp_path)
    with TestClient(app) as client:
        response = client.post("/projects", json={"brief": "Create something"})
        project = wait_for_terminal(client, response.json()["project_id"])

    assert project["status"] == "failed"
    assert project["phase"] == "FAILED"
    assert project["error"] == "model unavailable"


def test_answer_and_cancel_active_project(tmp_path: Path) -> None:
    app = create_app(runner=BlockingRunner(), workspace_root=tmp_path)
    with TestClient(app) as client:
        created = client.post("/projects", json={"brief": "Wait for me"}).json()
        project_id = created["project_id"]

        answer = client.post(
            f"/projects/{project_id}/answers",
            json={"answer": "Use SQLite"},
        )
        cancelled = client.post(f"/projects/{project_id}/cancel")

        assert answer.status_code == 202
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


def test_unknown_project_returns_not_found(tmp_path: Path) -> None:
    app = create_app(runner=SuccessfulRunner(), workspace_root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/projects/not-real")

    assert response.status_code == 404


def test_active_run_streams_heartbeats_and_artifact_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_module, "ARTIFACT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(api_module, "HEARTBEAT_SECONDS", 0.02)
    app = create_app(runner=ProgressiveRunner(), workspace_root=tmp_path)

    with TestClient(app) as client:
        created = client.post("/projects", json={"brief": "Create files progressively"}).json()
        project = wait_for_terminal(client, created["project_id"])
        stream = client.get(f"/projects/{created['project_id']}/events")

    assert project["status"] == "completed"
    assert len(project["artifacts"]) == 2
    assert "event: artifact" in stream.text
    assert '"artifact_count":2' in stream.text
    assert "event: heartbeat" in stream.text


def test_readiness_explains_missing_runtime_configuration(
    tmp_path: Path, monkeypatch: object
) -> None:
    for name in ("PM_MODEL", "ARCHITECT_MODEL", "CODER_MODEL", "REVIEWER_MODEL"):
        monkeypatch.delenv(name, raising=False)  # type: ignore[attr-defined]
    app = create_app(runner=SuccessfulRunner(), workspace_root=tmp_path)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "missing model settings" in response.json()["issues"][0]
