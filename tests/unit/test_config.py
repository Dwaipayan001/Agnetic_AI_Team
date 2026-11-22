import pytest
from pydantic import ValidationError

from agentic_sdlc.config import Settings


def model_env() -> dict[str, str]:
    return {
        "PM_MODEL": "openai:gpt-pm",
        "ARCHITECT_MODEL": "openai:gpt-architect",
        "CODER_MODEL": "openai:gpt-coder",
        "REVIEWER_MODEL": "anthropic:reviewer",
    }


def test_settings_fail_fast_on_missing_models() -> None:
    with pytest.raises(ValueError, match="ARCHITECT_MODEL"):
        Settings.from_env({"PM_MODEL": "openai:test"})


def test_settings_load_defaults_and_model_fallbacks() -> None:
    settings = Settings.from_env(model_env())

    assert settings.max_tasks == 60
    assert settings.resolved_qa_model == "openai:gpt-coder"
    assert settings.interactive is False


def test_settings_reject_model_without_provider() -> None:
    env = model_env()
    env["CODER_MODEL"] = "model-only"

    with pytest.raises(ValidationError, match="provider:model"):
        Settings.from_env(env)
