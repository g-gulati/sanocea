# RUNTIME-001 - Windows Local Lifecycle / Process Termination Instability

Status: OPEN

Track: Runtime reliability, separate from Commerce OS product development.

Known symptoms:

- pytest can print all tests passed while the host terminal session may not return promptly.
- PowerShell service wrappers may not respond reliably to Ctrl-C.
- Force-stopping `postgres.exe` can leave the cluster requiring recovery.
- The old local Postgres `55432` data directory is unreliable and retained as forensic evidence.
- Nested PowerShell/background-terminal orchestration is unstable on this host.
- `initdb.exe` can emit Windows restricted-token error 87. In direct runs this has been observed as noisy but non-fatal when initialization completes.

Current product-development runtime:

- Postgres: `postgresql://sanocea@127.0.0.1:55433/sanocea_phase21`
- Temporal: `127.0.0.1:57233`
- MinIO: `http://127.0.0.1:59000`
- External platforms: simulated Shopify, simulated logistics, simulated payment/refund, Chatwoot harness

Operational rule:

Do not block Sanocea product development on this defect unless it causes incorrect business results, data corruption in the active clean environment, failed deterministic tests, unsafe mutation, cross-tenant access, or inability to run the workload.

Preserved fixes:

- Postgres owned shutdown must use `pg_ctl stop -m fast -w`.
- Integration tests use bounded pytest runner with diagnostics.
- Test-owned Temporal worker subprocesses are explicitly terminated and never treated as shared infrastructure.
