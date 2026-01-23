import json
import os
from typing import Dict, Optional

from infra.tenancy import canonical_tenant_id


class ApiKeyStore:
    """Minimal API key -> tenant mapping.

    Precedence:
      1) .tenants/_control/api_keys.json
      2) specs/tenants/api_keys.json
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root

    def _load(self, path: str) -> Optional[Dict[str, str]]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("api_keys.json must be an object mapping api_key -> tenant_id")
        # normalize tenant ids
        return {k: canonical_tenant_id(v) for k, v in data.items()}

    def load_map(self) -> Dict[str, str]:
        control = os.path.join(self.repo_root, ".tenants", "_control", "api_keys.json")
        spec = os.path.join(self.repo_root, "specs", "tenants", "api_keys.json")
        return self._load(control) or self._load(spec) or {}

    def tenant_for_key(self, api_key: str) -> Optional[str]:
        if not api_key:
            return None
        return self.load_map().get(api_key)
