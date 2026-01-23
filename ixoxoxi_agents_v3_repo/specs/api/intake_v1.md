# Job Intake API (v1)

This is a minimal job-admission gateway that produces a **contract-compliant** job envelope for the runner.

## Auth
Header: `X-API-Key: <api_key>`
The gateway maps API key -> tenant_id via:
1) `.tenants/_control/api_keys.json`
2) `specs/tenants/api_keys.json`

## Submit Job
`POST /v1/jobs`

Request JSON:
- `dataset_id` (string, required)
- `dataset` (any JSON-serializable value, required)
- `graph_id` (string, optional)
- `graph_version` (string, optional; if provided must match registry)
- `policy_profile_id` (string, optional; default "default")
- `meter_scope` (string, optional; default tenant_id)
- `execution_mode` (string, optional; default "batch")

Version pinning rules (no implicit "latest" at runtime):
- If `graph_id` + `graph_version` are provided, they are used.
- Else the gateway reads `.tenants/<tenant_id>/graphs/active.json` and pins both fields.
- If neither is available, admission is denied.

Response JSON (201):
- `tenant_id`
- `job_id`
- `graph_id`
- `graph_version`
- `status`: "admitted"

## Get Job
`GET /v1/jobs/{job_id}` returns the persisted context.json (read-only).

## Tenant Status
`GET /v1/tenants/{tenant_id}/status` returns:
- active graph pointer
- recent meter file names


## Example (curl)

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "X-API-Key: dev-key-tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"test-001","dataset":{"foo":"bar"},"execution_mode":"batch"}'

curl -X GET http://127.0.0.1:8080/v1/jobs/<job_id> \
  -H "X-API-Key: dev-key-tenant-a"
```
