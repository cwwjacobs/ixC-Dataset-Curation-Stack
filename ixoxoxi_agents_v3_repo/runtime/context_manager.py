import json
import os

from infra.tenancy import canonical_tenant_id, scope_path


class ContextManager:
    """Tenant/job-scoped context persistence.

    Context is stored under:
      .tenants/<tenant_id>/jobs/<job_id>/context.json
    """

    def __init__(self, tenant_id: str, job_id: str, filename: str = "context.json"):
        self.tenant_id = canonical_tenant_id(tenant_id)
        self.job_id = str(job_id)
        self.path = scope_path(self.tenant_id, "jobs", self.job_id, filename)
        self.context = {}

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.context = json.load(f)
        except FileNotFoundError:
            self.context = {}
        return self.context

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.context, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def summarize_if_large(self, max_keys=60):
        if len(self.context) > max_keys:
            self.context = {
                "summary": "Context summarized due to memory pressure.",
                "critical_state": self.context.get("critical_state"),
                "warnings": self.context.get("warnings", []),
            }
