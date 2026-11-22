"""Create and protect a product repository before agents are allowed to use it.

This script requires an administrator credential and is intentionally outside the agent runtime.
It never logs the credential or writes it to disk.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol

API_VERSION = "2022-11-28"
DEFAULT_API_URL = "https://api.github.com"
DEFAULT_REQUIRED_CHECK = "test"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

INITIAL_README = """# Generated product

This repository is managed by Agentic SDLC. Agents integrate work through pull requests to
`integration`. A human reviews and merges release pull requests from `integration` to `main`.
"""

INITIAL_GITIGNORE = """.agent/
.env
.env.*
__pycache__/
.pytest_cache/
.venv/
node_modules/
dist/
"""

INITIAL_CI = """name: CI

on:
  push:
    branches: [main, integration]
  pull_request:
    branches: [main, integration]

permissions:
  contents: read

jobs:
  test:
    name: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify repository scaffold
        run: test -f README.md && test -f .github/CODEOWNERS
"""


class ApiClient(Protocol):
    """Small surface used by the bootstrap workflow and its tests."""

    def request(self, method: str, path: str, payload: object | None = None) -> Any:
        """Send one authenticated GitHub API request."""


class GitHubApiError(RuntimeError):
    """A sanitized GitHub API failure."""


@dataclass(slots=True)
class GitHubClient:
    """Minimal GitHub REST client using a bearer token held only in memory."""

    token: str
    api_url: str = DEFAULT_API_URL

    def request(self, method: str, path: str, payload: object | None = None) -> Any:
        url = f"{self.api_url.rstrip('/')}/{path.lstrip('/')}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "agentic-sdlc-bootstrap",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = _http_error_detail(exc)
            raise GitHubApiError(
                f"GitHub API {method} {path} failed ({exc.code}): {detail}"
            ) from None
        except urllib.error.URLError as exc:
            raise GitHubApiError(f"GitHub API {method} {path} failed: {exc.reason}") from None
        return json.loads(body) if body else None


@dataclass(frozen=True, slots=True)
class BootstrapOptions:
    owner: str
    name: str
    codeowner: str
    description: str
    private: bool
    personal: bool
    required_check: str

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.name}"


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "request rejected"
    message = body.get("message") if isinstance(body, dict) else None
    return str(message or "request rejected")


def validate_options(options: BootstrapOptions) -> None:
    """Reject malformed names before they are interpolated into API paths."""
    for label, value in (("owner", options.owner), ("name", options.name)):
        if not NAME_PATTERN.fullmatch(value):
            raise ValueError(f"{label} must contain only letters, digits, '.', '_', or '-'")
    if not options.codeowner.startswith("@") or any(char.isspace() for char in options.codeowner):
        raise ValueError("codeowner must be one GitHub handle or team beginning with '@'")
    if not options.required_check.strip():
        raise ValueError("required check must not be empty")


def protection_payload(*, required_check: str, main: bool) -> dict[str, object]:
    """Build a branch protection request with no actor bypasses."""
    return {
        "required_status_checks": {"strict": True, "contexts": [required_check]},
        "enforce_admins": True,
        "required_pull_request_reviews": (
            {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "required_approving_review_count": 1,
                "require_last_push_approval": True,
            }
            if main
            else None
        ),
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": main,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def create_repository(client: ApiClient, options: BootstrapOptions) -> None:
    endpoint = "/user/repos" if options.personal else f"/orgs/{options.owner}/repos"
    client.request(
        "POST",
        endpoint,
        {
            "name": options.name,
            "description": options.description,
            "private": options.private,
            "auto_init": False,
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
            "delete_branch_on_merge": True,
            "squash_merge_commit_title": "PR_TITLE",
            "squash_merge_commit_message": "PR_BODY",
        },
    )


def put_file(client: ApiClient, repository: str, path: str, content: str, message: str) -> None:
    encoded_path = urllib.parse.quote(path, safe="/")
    client.request(
        "PUT",
        f"/repos/{repository}/contents/{encoded_path}",
        {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": "main",
        },
    )


def bootstrap_repository(client: ApiClient, options: BootstrapOptions) -> None:
    """Create initial files, branches, and protection in dependency order."""
    validate_options(options)
    repository = options.repository
    create_repository(client, options)
    put_file(client, repository, "README.md", INITIAL_README, "chore: initialize repository")
    put_file(
        client, repository, ".gitignore", INITIAL_GITIGNORE, "chore: add generated-file ignores"
    )
    put_file(
        client,
        repository,
        ".github/CODEOWNERS",
        f"* {options.codeowner}\n",
        "chore: require human code ownership",
    )
    put_file(
        client,
        repository,
        ".github/workflows/ci.yml",
        INITIAL_CI,
        "ci: add bootstrap check",
    )

    ref = client.request("GET", f"/repos/{repository}/git/ref/heads/main")
    try:
        main_sha = ref["object"]["sha"]
    except (KeyError, TypeError) as exc:
        raise GitHubApiError("GitHub returned an invalid main branch reference") from exc
    client.request(
        "POST",
        f"/repos/{repository}/git/refs",
        {"ref": "refs/heads/integration", "sha": main_sha},
    )
    client.request(
        "PUT",
        f"/repos/{repository}/branches/main/protection",
        protection_payload(required_check=options.required_check, main=True),
    )
    client.request(
        "PUT",
        f"/repos/{repository}/branches/integration/protection",
        protection_payload(required_check=options.required_check, main=False),
    )


def operation_summary(options: BootstrapOptions) -> str:
    visibility = "private" if options.private else "public"
    account = "personal" if options.personal else "organization"
    return (
        f"Would create {visibility} {account} repository {options.repository}, initialize main, "
        f"create integration, and require check {options.required_check!r}."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="GitHub organization or authenticated user")
    parser.add_argument("--name", required=True, help="new repository name")
    parser.add_argument(
        "--codeowner", required=True, help="human GitHub handle/team, e.g. @org/team"
    )
    parser.add_argument("--description", default="Product managed by Agentic SDLC")
    parser.add_argument("--public", action="store_true", help="create a public repository")
    parser.add_argument("--personal", action="store_true", help="create under authenticated user")
    parser.add_argument("--required-check", default=DEFAULT_REQUIRED_CHECK)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = BootstrapOptions(
        owner=args.owner,
        name=args.name,
        codeowner=args.codeowner,
        description=args.description,
        private=not args.public,
        personal=args.personal,
        required_check=args.required_check,
    )
    try:
        validate_options(options)
    except ValueError as exc:
        fail(str(exc))
    if args.dry_run:
        print(operation_summary(options))
        return 0

    token = os.environ.get("GITHUB_ADMIN_TOKEN")
    if not token:
        fail("GITHUB_ADMIN_TOKEN is required unless --dry-run is used")
    try:
        bootstrap_repository(GitHubClient(token=token, api_url=args.api_url), options)
    except GitHubApiError as exc:
        fail(str(exc))
    print(f"Bootstrapped and protected https://github.com/{options.repository}")
    print("Manual runtime App permission verification is still required; see README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
