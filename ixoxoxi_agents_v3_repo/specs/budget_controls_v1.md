# Budget controls v1 (credits)

This repository uses an abstract unit called **credits** as a deterministic budget guardrail.

Credits are **not** the billing source of truth (meters are). Credits are used to:
- deny admission when a tenant is over budget
- prevent runaway tool/model calls at runtime

## Where credits are defined
- `specs/plans/<plan_id>.json`
  - `budget.credits_per_day`
  - `budget.admission_credit_reserve`
  - `pricing.credits_per_model_call_by_class`
  - `pricing.credits_per_tool_call_by_name`

## Enforcement points
1) **Admission** (`POST /v1/jobs`)
   - reserves `budget.admission_credit_reserve`
   - denies with `job_rejected_budget` if budget would be exceeded

2) **Runtime ToolRouter**
   - reserves credits per call (model/tool) before execution
   - denies on exceed
   - optional degradation for models:
     - env `IXO_BUDGET_STRATEGY=degrade` (default)
     - attempts to downgrade model_class in order: reasoning -> transform -> cheap
     - emits `budget_degrade` meter event when downgrade occurs

## Storage
- `.tenants/<tenant_id>/budget/usage/<YYYY-MM-DD>.json`
  - `{ "credits_used": <float> }`
