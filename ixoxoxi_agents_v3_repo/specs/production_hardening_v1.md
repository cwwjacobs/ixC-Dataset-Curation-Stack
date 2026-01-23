# Production Hardening v1 (Stage B)

This stage upgrades the runtime from "dev-only" to "restart-safe, auditable, bounded retry" operation.

## Durable Queue

Per-tenant filesystem-backed queue:

- `.tenants/<tenant_id>/queue/ready/*.json`
- `.tenants/<tenant_id>/queue/inflight/*.json`
- `.tenants/<tenant_id>/queue/dlq/*.json`

Semantics:

- Enqueue: atomic write to `ready`
- Dequeue: atomic rename `ready -> inflight` (claim)
- Ack: delete inflight file
- Fail: increment retry counter; if `retries > max_retries` move to `dlq`, else requeue to `ready`
- Reclaim: on worker start (and optionally periodically), move stale `inflight` back to `ready` via `fail(..., reason="lease_expired")`

Config:

- `IXO_QUEUE_MAX_RETRIES` (default 3)
- `IXO_QUEUE_LEASE_SECONDS` (default 300)

## Crash-safe Context Writes

Job context is written atomically using temp-file + replace:

`.tenants/<tenant_id>/jobs/<job_id>/context.json`

## Job State Machine (v1)

States are best-effort but monotonic:

- `admitted` -> `queued` -> `running` -> `succeeded`
- failures set `failed`; if retries exhausted and job moved to DLQ, state becomes `dlq`

## Observability

Structured JSON logs emitted to stdout. Stable fields:

- `ts_ms`, `event`, `tenant_id`, `job_id` (when applicable)
- additional fields: `graph_id`, `graph_version`, `reason`, etc.

Health / metrics:

- `GET /healthz` -> `{ ok: true }`
- `GET /metrics` -> tenant-scoped queue counts (requires auth)

## Non-goals (v1)

- distributed queues / multi-host coordination
- persistence beyond local filesystem
- central metrics store
