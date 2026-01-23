import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

from infra.tenancy import canonical_tenant_id, scope_path


@dataclass(frozen=True)
class QuotaUsage:
    jobs_admitted: int
    bytes_in: int


class QuotaTracker:
    """
    Tracks daily per-tenant quota usage on disk.

    Usage file:
      .tenants/<tenant_id>/quota/usage/<YYYY-MM-DD>.json

    Atomic updates with temp file + os.replace.
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root

    def _usage_path(self, tenant_id: str, day: date) -> str:
        tenant_id = canonical_tenant_id(tenant_id)
        rel = scope_path(tenant_id, "quota", "usage", f"{day.isoformat()}.json")
        return os.path.join(self.repo_root, rel)

    def _load(self, path: str) -> Dict:
        if not os.path.exists(path):
            return {"jobs_admitted": 0, "bytes_in": 0}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, tenant_id: str, day: date) -> QuotaUsage:
        path = self._usage_path(tenant_id, day)
        d = self._load(path)
        return QuotaUsage(jobs_admitted=int(d.get("jobs_admitted", 0)), bytes_in=int(d.get("bytes_in", 0)))

    def check_and_reserve(self, tenant_id: str, day: date, *, add_jobs: int, add_bytes_in: int, limits: Dict) -> Tuple[bool, str, QuotaUsage]:
        """
        Returns (ok, reason, new_usage_if_ok).
        Limits dict expects: max_jobs_per_day, max_bytes_in_per_day.
        """
        tenant_id = canonical_tenant_id(tenant_id)
        path = self._usage_path(tenant_id, day)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        cur = self._load(path)
        cur_jobs = int(cur.get("jobs_admitted", 0))
        cur_bytes = int(cur.get("bytes_in", 0))

        max_jobs = int(limits.get("max_jobs_per_day", 0))
        max_bytes = int(limits.get("max_bytes_in_per_day", 0))

        nxt_jobs = cur_jobs + int(add_jobs)
        nxt_bytes = cur_bytes + int(add_bytes_in)

        if max_jobs >= 0 and nxt_jobs > max_jobs:
            return False, "quota_exceeded:max_jobs_per_day", QuotaUsage(cur_jobs, cur_bytes)
        if max_bytes >= 0 and nxt_bytes > max_bytes:
            return False, "quota_exceeded:max_bytes_in_per_day", QuotaUsage(cur_jobs, cur_bytes)

        # Atomic write
        new_doc = {"jobs_admitted": nxt_jobs, "bytes_in": nxt_bytes}
        fd, tmp_path = tempfile.mkstemp(prefix="quota_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(new_doc, f, ensure_ascii=False, sort_keys=True, indent=2)
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

        return True, "ok", QuotaUsage(nxt_jobs, nxt_bytes)
