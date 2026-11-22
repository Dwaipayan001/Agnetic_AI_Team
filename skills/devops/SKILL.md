---
name: devops
description: Scaffold reproducible builds, least-privilege CI, and non-root containers from an approved architecture.
---

# Delivery scaffolding

Expose clear install, lint, type-check, test, build, and run commands. Pin dependency inputs and
make CI execute the same commands developers use locally.

Grant workflows only required permissions. Containers should use a small runtime stage, run as a
non-root user, copy only needed artifacts, define a health check where meaningful, and keep secrets
out of layers and build arguments.
