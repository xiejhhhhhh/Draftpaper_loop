# Draftpaper-loop v0.32.0 Sandbox and Container Evaluation

Date: 2026-07-18
Scope: local CLI, local jobs, local stdio MCP and project scientific execution

## Conclusion

Draftpaper-loop v0.32.0 is **not a production sandbox**. It has meaningful application-level containment for a local-first research tool, but it does not provide an operating-system security boundary against malicious scientific code. The project must not offer or claim a public hosted API until multi-tenant authentication, tenant isolation, outbound network control and private-data isolation are implemented and independently reviewed.

## Existing Controls

- CommandSpec records command risk, confirmation policy, resource class, timeout and allowed read/write roots.
- Write-set preflight rejects undeclared or escaping output roots before a mutating handler runs; post-execution verification detects unexpected project changes.
- Project paths and completion content files use confinement checks, including symlink/path traversal cases covered by tests.
- Method execution uses an executable allowlist, rejects shell operators and inline Python, and requires explicit opt-in for system binaries.
- Child processes receive an allowlisted environment; credentials and logs pass through redaction rules.
- MCP denies private locator and credential-like artifacts, excludes protected human checkpoints and uses project/command-bound capability tokens for science execution.
- Jobs have explicit command contracts, timeouts, ledgers, cancellation/recovery states and project-scoped output policies.
- Journal and registry retrieval uses HTTPS, host/DNS/private-address, redirect, timeout and response-size controls.

These controls reduce accidental writes, stale-code execution, credential leakage and common command-injection paths. They are appropriate defense in depth for trusted-user local research workflows.

## Unresolved Isolation Gaps

1. **Process isolation:** an allowed Python project script still executes with the operating-system permissions of the current user. The executable allowlist is not a kernel sandbox.
2. **Filesystem isolation:** write-set enforcement controls Draftpaper-managed changes, but an actively malicious child process could attempt reads outside the project before the application can observe them.
3. **Outbound network isolation:** URL-aware providers are constrained, but arbitrary scientific code is not forced through a deny-by-default outbound proxy.
4. **Resource isolation:** command timeouts exist, but there are no cross-platform hard CPU, memory, disk, process-count or GPU quotas.
5. **Multi-tenant isolation:** there is no tenant identity model, per-tenant encryption key, namespace boundary, quota/accounting boundary or administrative audit plane.
6. **Authentication and authorization:** local capability tokens protect MCP actions within one local process model; they are not user authentication for a network service.
7. **Container image assurance:** no signed, minimal, reproducible science-runner image and no image vulnerability/attestation gate are part of the release.

## Recommended Future Architecture

### Local optional runner

- Provide an opt-in container runner with a read-only source mount and a separate writable project-output mount.
- Run as a non-root user, drop capabilities, set a read-only root filesystem and use temporary filesystems for scratch data.
- Disable network by default; enable only declared provider destinations through an outbound policy.
- Apply CPU, memory, disk, process and wall-clock limits; record the image digest and runtime policy in the method run manifest.
- Preserve the current CommandSpec, evidence, write-set and transaction checks inside the container instead of replacing them.

### Hosted or multi-user service

- Add real user authentication, authorization and tenant-bound project identities.
- Separate storage, queues, secrets, logs and encryption keys per tenant.
- Route all outbound traffic through an authenticated allowlist proxy with request/response limits.
- Use ephemeral isolated workers, immutable signed images, artifact scanning and deletion/retention policies.
- Commission independent security testing before accepting private research data.

## v0.32.0 Release Decision

No container runtime is made mandatory in v0.32.0 because the current product remains a local-first CLI and the application-level controls are already auditable. The release documentation accurately states that there is no public hosted API. Future sandbox work must be a separate security project with threat-model, platform and operational acceptance criteria; it must not be inferred from the current write-set or executable allowlist.
