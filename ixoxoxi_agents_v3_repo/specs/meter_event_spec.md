# Meter Event Spec v1

This document specifies the minimum event format used for fine-grained billing meters.

## Goals

- Every event is attributable to a tenant and job.
- Events are append-only, durable, and easy to aggregate.
- Low-cardinality dimensions are first-class fields; high-cardinality dimensions live in `labels`.

## Storage

Events are stored as JSONL (one JSON object per line) under:

`.tenants/<tenant_id>/meters/<YYYY-MM-DD>.jsonl` (rotated daily by UTC date)

## Schema (required fields)

- `event_id` (string, UUID)
- `ts_utc` (string, ISO-8601 UTC)
- `tenant_id` (string)
- `job_id` (string)
- `meter_scope` (string)
- `event_type` (string)
- `units` (number)
- `unit_type` (string; e.g., `count`, `bytes`, `tokens_ms`)
- `graph_id` (string)
- `graph_version` (string)
- `policy_profile_id` (string)
- `execution_mode` (string)
- `labels` (object)

## Event types (v1)

- `job_admitted` (`count=1`)
- `job_rejected_quota` (`count=1`, labels: `reason`, `plan_id`)
- `job_rejected_policy` (`count=1`, labels: `reason`, `policy_profile_id`, `plan_id`)
- `job_start` (`count=1`)
- `job_complete` (`count=1`)
- `agent_run` (`count=1`, label: `agent_name`)
- `payload_bytes_in` (`bytes=<n>`)
- `payload_bytes_out` (`bytes=<n>`)
- `dataset_blob_write` (`bytes=<n>`, labels: `dataset_id`, `dataset_version`, `blob_sha256`)

## Contract linkage

All meter events must be emitted with `tenant_id` + `job_id` and must be consistent with the frozen context contract v1.

## Forward compatibility

New event types may be added without breaking existing aggregations. Unknown `labels` must be ignored by aggregators.


### model_call
- unit_type: count
- labels: agent_name, model_class, model_id

### tool_call
- unit_type: count
- labels: agent_name, tool_name


## budget_degrade
Emitted when ToolRouter downgrades a model call due to budget pressure.
Labels: agent_name, from_model_class, to_model_class.


## job_rejected_budget
Emitted when admission is denied because daily credits budget would be exceeded.
Labels: reason, plan_id.
