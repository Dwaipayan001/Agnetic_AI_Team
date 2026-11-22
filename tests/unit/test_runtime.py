import asyncio
from uuid import uuid4

from agentic_sdlc.runtime import ProjectActivityCallback


def test_activity_callback_emits_safe_tool_and_model_progress() -> None:
    events: list[tuple[str, str, dict[str, object] | None]] = []

    async def emit(event_type: str, message: str, data: dict[str, object] | None = None) -> None:
        events.append((event_type, message, data))

    async def exercise() -> None:
        callback = ProjectActivityCallback(emit)
        tool_run = uuid4()
        await callback.on_chat_model_start({}, [], run_id=uuid4())
        await callback.on_tool_start(
            {"name": "write_file"},
            "secret input that must not be emitted",
            run_id=tool_run,
        )
        await callback.on_tool_end(
            "secret output that must not be emitted",
            run_id=tool_run,
        )

    asyncio.run(exercise())

    messages = [message for _, message, _ in events]
    assert messages == [
        "Planning the next engineering action",
        "Writing a project file",
        "Writing a project file finished",
    ]
    serialized = str(events)
    assert "secret input" not in serialized
    assert "secret output" not in serialized
