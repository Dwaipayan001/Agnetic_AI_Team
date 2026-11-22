from __future__ import annotations

from typing import Any

import pytest

from scripts.bootstrap_product_repo import (
    BootstrapOptions,
    GitHubApiError,
    bootstrap_repository,
    protection_payload,
    validate_options,
)


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object | None]] = []

    def request(self, method: str, path: str, payload: object | None = None) -> Any:
        self.calls.append((method, path, payload))
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "abc123"}}
        return {}


def options(**changes: object) -> BootstrapOptions:
    values: dict[str, object] = {
        "owner": "example-org",
        "name": "product",
        "codeowner": "@example-org/humans",
        "description": "A product",
        "private": True,
        "personal": False,
        "required_check": "test",
    }
    values.update(changes)
    return BootstrapOptions(**values)  # type: ignore[arg-type]


def test_main_protection_requires_human_codeowner_review() -> None:
    payload = protection_payload(required_check="test", main=True)

    assert payload["enforce_admins"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["restrictions"] is None
    assert payload["required_pull_request_reviews"] == {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": True,
        "required_approving_review_count": 1,
        "require_last_push_approval": True,
    }


def test_integration_protection_has_checks_without_review_gate() -> None:
    payload = protection_payload(required_check="test", main=False)

    assert payload["required_status_checks"] == {"strict": True, "contexts": ["test"]}
    assert payload["required_pull_request_reviews"] is None
    assert payload["allow_force_pushes"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("owner", "bad/owner"), ("name", "bad name"), ("codeowner", "not-a-handle")],
)
def test_validate_options_rejects_unsafe_identifiers(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        validate_options(options(**{field: value}))


def test_bootstrap_orders_initialization_before_protection() -> None:
    client = RecordingClient()

    bootstrap_repository(client, options())

    paths = [path for _, path, _ in client.calls]
    create_integration = paths.index("/repos/example-org/product/git/refs")
    protect_main = paths.index("/repos/example-org/product/branches/main/protection")
    protect_integration = paths.index("/repos/example-org/product/branches/integration/protection")
    assert paths[0] == "/orgs/example-org/repos"
    assert create_integration < protect_main < protect_integration
    assert client.calls[create_integration][2] == {
        "ref": "refs/heads/integration",
        "sha": "abc123",
    }


def test_bootstrap_rejects_invalid_ref_response() -> None:
    class InvalidRefClient(RecordingClient):
        def request(self, method: str, path: str, payload: object | None = None) -> Any:
            self.calls.append((method, path, payload))
            return {}

    with pytest.raises(GitHubApiError, match="invalid main branch reference"):
        bootstrap_repository(InvalidRefClient(), options())
