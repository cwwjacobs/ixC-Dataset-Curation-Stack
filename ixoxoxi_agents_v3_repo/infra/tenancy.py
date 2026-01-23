import os
import re
from typing import Any, Dict


_TENANT_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")


def canonical_tenant_id(tenant_id: str) -> str:
    """Normalize/validate tenant_id.

    Rules:
      - kebab-case: lowercase letters, digits, hyphen
      - 1..63 chars
    """
    if tenant_id is None:
        raise ValueError("tenant_id is required")
    t = str(tenant_id).strip().lower()
    if not _TENANT_SAFE_RE.match(t):
        raise ValueError(
            f"Invalid tenant_id '{tenant_id}'. Expected kebab-case [a-z0-9-], length 1..63."
        )
    return t


def scope_path(tenant_id: str, *parts: str) -> str:
    """Return a tenant-scoped relative path under .tenants/<tenant_id>/..."""
    t = canonical_tenant_id(tenant_id)
    cleaned = [p for p in parts if p not in (None, "", ".")]
    return os.path.join(".tenants", t, *cleaned)


def scope_key(tenant_id: str, key: str) -> str:
    """Return a tenant-qualified key for caches / indexes."""
    t = canonical_tenant_id(tenant_id)
    return f"{t}:{key}"


def require_tenant(ctx_or_job: Dict[str, Any]) -> str:
    """Extract and validate tenant_id from a context/job dict."""
    if not isinstance(ctx_or_job, dict):
        raise ValueError("Expected dict containing tenant_id")
    return canonical_tenant_id(ctx_or_job.get("tenant_id"))
