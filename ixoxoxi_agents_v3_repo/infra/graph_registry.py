import json
import os
import hashlib
import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from infra.tenancy import canonical_tenant_id, scope_path


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_graph_version(graph_def: Dict[str, Any]) -> str:
    """Deterministic graph version derived from graph_def content (excluding graph_version field if present)."""
    normalized = dict(graph_def)
    normalized.pop("graph_version", None)
    h = hashlib.sha256(_canonical_json_bytes(normalized)).hexdigest()
    return h


@dataclass(frozen=True)
class GraphSpec:
    graph_id: str
    graph_version: str
    sequence: List[str]
    metadata: Dict[str, Any]


class GraphRegistryError(Exception):
    pass


class GraphRegistry:
    """Loads immutable, versioned agent graphs from the repo (and optionally tenant-scoped overrides)."""

    def __init__(self, repo_root: str):
        self.repo_root = repo_root

    def _repo_graph_path(self, graph_id: str, graph_version: str) -> str:
        return os.path.join(self.repo_root, "specs", "graphs", graph_id, f"{graph_version}.json")

    def load_graph(self, graph_id: str, graph_version: str) -> GraphSpec:
        path = self._repo_graph_path(graph_id, graph_version)
        if not os.path.exists(path):
            raise GraphRegistryError(f"Graph not found: {graph_id}@{graph_version} ({path})")
        with open(path, "r", encoding="utf-8") as f:
            graph_def = json.load(f)

        declared_version = graph_def.get("graph_version")
        computed_version = compute_graph_version(graph_def)
        if declared_version and declared_version != computed_version:
            raise GraphRegistryError(
                f"Graph version mismatch for {graph_id}: declared={declared_version} computed={computed_version}"
            )

        seq = graph_def.get("sequence") or graph_def.get("nodes")
        if not isinstance(seq, list) or not all(isinstance(x, str) for x in seq):
            raise GraphRegistryError(f"Invalid graph sequence in {path}")

        return GraphSpec(
            graph_id=str(graph_def.get("graph_id", graph_id)),
            graph_version=computed_version,
            sequence=seq,
            metadata=dict(graph_def.get("metadata") or {}),
        )

    def register_graph(self, graph_def: Dict[str, Any]) -> Tuple[str, str, str]:
        """Write a graph definition into specs/graphs/<graph_id>/<graph_version>.json. Returns (graph_id, graph_version, path)."""
        graph_id = str(graph_def.get("graph_id") or "").strip()
        if not graph_id:
            raise GraphRegistryError("graph_def must include graph_id")
        graph_version = compute_graph_version(graph_def)
        graph_def = dict(graph_def)
        graph_def["graph_id"] = graph_id
        graph_def["graph_version"] = graph_version

        out_dir = os.path.join(self.repo_root, "specs", "graphs", graph_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{graph_version}.json")
        # Idempotent write: if exists, ensure identical.
        payload = _canonical_json_bytes(graph_def)
        if os.path.exists(out_path):
            with open(out_path, "rb") as f:
                if f.read() != payload:
                    raise GraphRegistryError(f"Graph path exists with different content: {out_path}")
        else:
            with open(out_path, "wb") as f:
                f.write(payload)
        return graph_id, graph_version, out_path


class TenantGraphManager:
    """Manages per-tenant active graph pointers and rollback history."""

    def __init__(self, tenant_id: str):
        self.tenant_id = canonical_tenant_id(tenant_id)
        self.active_path = scope_path(self.tenant_id, "graphs", "active.json")
        self.history_path = scope_path(self.tenant_id, "graphs", "history.jsonl")

    def _load_active(self) -> Dict[str, Any]:
        if not os.path.exists(self.active_path):
            return {"active": {}}
        with open(self.active_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_active(self, graph_id: str) -> Optional[str]:
        doc = self._load_active()
        ent = (doc.get("active") or {}).get(graph_id)
        if not ent:
            return None
        return ent.get("graph_version")

    def set_active(self, graph_id: str, graph_version: str, actor: str = "system", reason: str = "") -> None:
        os.makedirs(os.path.dirname(self.active_path), exist_ok=True)
        doc = self._load_active()
        doc.setdefault("active", {})
        prev = doc["active"].get(graph_id)

        now = datetime.datetime.utcnow().isoformat() + "Z"
        doc["active"][graph_id] = {
            "graph_version": graph_version,
            "updated_at": now,
            "actor": actor,
            "reason": reason,
        }
        with open(self.active_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, sort_keys=True)

        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        record = {
            "ts": now,
            "graph_id": graph_id,
            "graph_version": graph_version,
            "prev": prev,
            "actor": actor,
            "reason": reason,
        }
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def rollback(self, graph_id: str, actor: str = "system", reason: str = "rollback") -> Optional[str]:
        doc = self._load_active()
        current = (doc.get("active") or {}).get(graph_id)
        prev = (current or {}).get("prev")
        # If we don't have prev in the active doc, scan history.
        if prev is None and os.path.exists(self.history_path):
            # find last entry with prev
            with open(self.history_path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            for ln in reversed(lines):
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                if rec.get("graph_id") == graph_id and rec.get("prev") and rec["prev"].get("graph_version"):
                    prev = rec["prev"]
                    break
        if not prev or not prev.get("graph_version"):
            return None
        self.set_active(graph_id, prev["graph_version"], actor=actor, reason=reason)
        return prev["graph_version"]
