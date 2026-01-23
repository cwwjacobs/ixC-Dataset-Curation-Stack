# Commercialization Layer (v1)

This stage introduces plans/quotas and invoice-ready exports without changing the frozen context contract.

## Plan model
- Tenant -> plan_id mapping: `specs/tenants/plans.json` (or `.tenants/_control/plans.json` override)
- Plan definitions: `specs/plans/<plan_id>.json`

Each plan defines:
- `limits.max_jobs_per_day`
- `limits.max_bytes_in_per_day`
- `allowed_model_classes` (enforced via policy in later iterations)

## Quota enforcement
On job admission (`POST /v1/jobs`), the gateway:
- computes `bytes_in` from the incoming `dataset` payload (JSON-serialized size)
- reserves quota in `.tenants/<tenant_id>/quota/usage/<YYYY-MM-DD>.json`
- rejects with HTTP 429 if exceeded

## Billing export
`runtime/billing_export.py` aggregates per-tenant meter JSONL logs into a CSV suitable for invoicing line items.


## Plan -> policy profile

If the caller omits `policy_profile_id` at job submission, the gateway resolves it as:

1) request `policy_profile_id` (if provided)
2) plan `default_policy_profile_id` (from `specs/plans/<plan_id>.json`)
3) fallback `default`

This keeps policy enforcement centrally governed by commercial plan defaults.


Enforcement note: model class constraints are enforced at ToolRouter `pre_tool_call`.
