import json
import os
from typing import Dict, Optional

from infra.tenancy import canonical_tenant_id


class PlanStore:
    """
    Minimal tenant -> plan mapping + plan definitions.

    Precedence:
      1) .tenants/_control/plans.json (tenant->plan_id)
      2) specs/tenants/plans.json

    Plan definitions:
      - specs/plans/<plan_id>.json
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root

    def _load_json(self, path: str) -> Optional[Dict]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def tenant_plan_id(self, tenant_id: str) -> str:
        tenant_id = canonical_tenant_id(tenant_id)
        control_path = os.path.join(self.repo_root, ".tenants", "_control", "plans.json")
        spec_path = os.path.join(self.repo_root, "specs", "tenants", "plans.json")
        mapping = self._load_json(control_path) or self._load_json(spec_path) or {}
        return str(mapping.get(tenant_id) or "free")

    def plan(self, plan_id: str) -> Dict:
        plan_id = str(plan_id)
        plan_path = os.path.join(self.repo_root, "specs", "plans", f"{plan_id}.json")
        plan = self._load_json(plan_path)
        if not plan:
            # Safe default: effectively no admission (but allow local dev by setting plan files)
            return {
                "plan_id": plan_id,
                "limits": {
                    "max_jobs_per_day": 0,
                    "max_bytes_in_per_day": 0,
                },
                "allowed_model_classes": ["cheap"],
            }
        plan["plan_id"] = plan.get("plan_id") or plan_id
        return plan
