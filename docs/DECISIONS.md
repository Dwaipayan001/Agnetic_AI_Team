# Decisions

## 2026-11-22: M0 repository bootstrap uses the GitHub REST API

The plan does not prescribe a bootstrap implementation. The utility uses the standard library and
GitHub REST API rather than a local `git` credential helper or the GitHub CLI. This keeps the
administrator token out of repository remotes and child-process arguments and avoids adding a
runtime dependency for an admin-only operation.

The initial repository contains a minimal Python CI workflow whose required check is named `test`.
Protection is applied only after the workflow and both branches exist. The generated product's
M6 bootstrap PR is expected to replace this placeholder workflow with stack-appropriate CI.

Organization repositories are the default because CODEOWNERS teams and centrally managed GitHub
Apps are the intended production shape. `--personal` supports playground repositories.

## 2026-11-22: M0 dependency versions are exact and lockfile-backed

All direct and build dependencies are exact-pinned. The selected stable versions are Pydantic
2.13.5, pytest 9.1.1, Ruff 0.16.8, and Hatchling 1.32.4. They are intentionally a small patch behind
the newest releases verified during M0 because those versions were available to the restricted
local resolver; `uv.lock` fixes their complete transitive dependency graph. Upgrades will be
explicit changes with their own verification, rather than implicit installs of newly published
packages.

## 2026-11-22: Build the Deep Agents team before live GitHub integration

The product owner reprioritized implementation so the functional AI engineering team comes before
live GitHub setup. GitHub remains behind a role-filtered tool-provider protocol and defaults to an
empty provider for local construction. This preserves the boundary without making credentials or
repository provisioning prerequisites for testing agent composition.

All specialist subagents use Deep Agents' isolated mode, explicit tool lists, and explicit
filesystem permission replacement. Empty permission lists on implementation roles are deliberate:
omitting the field would inherit the PM's document-only write policy. QA and reviewer structured
outputs use the shared Pydantic contracts.

Deep Agents is pinned to 0.7.41. Its current declarative subagent API supports the fields used by
the team factory: isolated `mode`, explicit `tools`, role `model`, `skills`, filesystem
`permissions`, and Pydantic `response_format`. Permission rules protect built-in filesystem tools;
the sandbox backend remains responsible for containing shell execution.

## 2026-11-22: HTTP projects use a file-only Deep Agents backend by default

The FastAPI runner uses `FilesystemBackend` with virtual paths. It does not use
`LocalShellBackend`: that backend executes unrestricted commands on the API host and Deep Agents
explicitly documents it as inappropriate for server workloads. Consequently, the first API can
generate product artifacts but must state that builds and tests have not run. Executing generated
code will be enabled only through the planned isolated Docker sandbox provider.

## 2026-11-22: Add the product console after the first HTTP project runner

The product owner explicitly reprioritized a React console once the project API was available.
The UI consumes the existing FastAPI contract instead of introducing a second backend model:
project submission and state use HTTP, progress uses named server-sent events, and artifacts are
downloaded through the guarded artifact route. Recent run IDs are browser-local because the
current API registry is intentionally in-process and does not yet expose a project-list endpoint.

Generated application files remain outside the platform source tree under
`.agentic-sdlc/projects/<project-id>/`. The frontend is a separately locked Vite application so it
can evolve independently while the Python milestone checks remain unchanged.

## 2026-11-22: Normalize Windows extended paths at the workspace backend boundary

Deep Agents may return a Windows path with the `\\?\` extended-length prefix and later compare it
with the same unprefixed workspace root. The stock virtual filesystem backend rejects that pair as
different roots. The API runner now uses a small `FilesystemBackend` subclass that canonicalizes
both representations before resolving or virtualizing a path. It retains the root-containment and
path-traversal checks, so this compatibility fix does not broaden agent filesystem access.

