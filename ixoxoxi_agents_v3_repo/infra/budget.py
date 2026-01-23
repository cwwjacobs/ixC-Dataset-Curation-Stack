import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

from infra.tenancy import canonical_tenant_id, scope_path


@dataclass(frozen=True)
class BudgetUsage:
    credits_used: float


class BudgetTracker:
    """
    Tracks daily per-tenant budget usage (in abstract "credits") on disk.

    Usage file:
      .tenants/<tenant_id>/budget/usage/<YYYY-MM-DD>.json

    Design:
      - append-only meters are the source of truth for billing
      - budget usage is a lightweight guardrail for admission/runtime enforcement
      - atomic writes (temp + replace)
    """

    def __init__(self, repo_root: str = ".") -> None:
        self._repo_root = repo_root

    def _usage_path(self, tenant_id: str, day: date) -> str:
        return scope_path(canonical_tenant_id(tenant_id), "budget", "usage", f"{day.isoformat()}.json")

    def read_usage(self, *, tenant_id: str, day: date) -> BudgetUsage:
        path = os.path.join(self._repo_root, self._usage_path(tenant_id, day))
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BudgetUsage(credits_used=float(data.get("credits_used", 0.0)))
        except FileNotFoundError:
            return BudgetUsage(credits_used=0.0)

    def try_reserve(self, *, tenant_id: str, day: date, credits: float, max_credits: float) -> Tuple[bool, BudgetUsage]:
        """Attempt to reserve credits. Returns (ok, new_usage)."""
        tenant_id = canonical_tenant_id(tenant_id)
        credits = float(max(0.0, credits))
        max_credits = float(max_credits)

        usage = self.read_usage(tenant_id=tenant_id, day=day)
        new_total = usage.credits_used + credits
        if new_total > max_credits:
            return False, usage

        rel_path = self._usage_path(tenant_id, day)
        abs_path = os.path.join(self._repo_root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        payload: Dict[str, float] = {"credits_used": new_total}

        fd, tmp_path = tempfile.mkstemp(prefix="budget_", suffix=".json", dir=os.path.dirname(abs_path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, sort_keys=True)
            os.replace(tmp_path, abs_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        return True, BudgetUsage(credits_used=new_total)
