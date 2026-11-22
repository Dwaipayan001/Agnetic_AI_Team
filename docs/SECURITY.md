# Security model

The project is being implemented incrementally. The authoritative target controls are listed in
section 9 of `AGENTIC_SDLC_PLAN.md`; this document will be completed during M12.

M0 establishes these foundations:

- repository setup is an explicit administrator operation outside the agent runtime;
- the administrator token is read from an environment variable and is never printed or persisted;
- `main` requires a pull request, one approving CODEOWNER review, and the required CI check;
- branch protection applies to administrators and does not grant the runtime App a bypass;
- force pushes and branch deletion are disabled on `main` and `integration`.

