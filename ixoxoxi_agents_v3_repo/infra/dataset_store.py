import json
import os
import hashlib
import datetime
from typing import Any, Dict, Optional, Tuple, List

from infra.tenancy import canonical_tenant_id, scope_path


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    # Stable JSON encoding for deterministic version hashes.
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


class DatasetStore:
    """Content-addressed dataset blob + manifest store.

    Layout:
      .tenants/<tenant_id>/datasets/<dataset_id>/
        blobs/<sha256>
        manifests/<manifest_sha256>.json

    dataset_version := sha256(canonical_json(manifest))
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = canonical_tenant_id(tenant_id)

    def _ds_root(self, dataset_id: str) -> str:
        return scope_path(self.tenant_id, "datasets", str(dataset_id))

    def _blob_path(self, dataset_id: str, blob_sha256: str) -> str:
        return os.path.join(self._ds_root(dataset_id), "blobs", blob_sha256)

    def _manifest_path(self, dataset_id: str, version: str) -> str:
        return os.path.join(self._ds_root(dataset_id), "manifests", f"{version}.json")

    def write_blob(self, dataset_id: str, payload: bytes) -> Tuple[str, str]:
        """Write payload as a content-addressed blob. Returns (sha256, path)."""
        sha = _sha256_bytes(payload)
        path = self._blob_path(dataset_id, sha)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Idempotent write: if exists, do not overwrite.
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(payload)
        return sha, path

    def build_manifest_v1(
        self,
        dataset_id: str,
        *,
        parent_version: Optional[str] = None,
        source: Optional[str] = None,
        content_blob_sha256: Optional[str] = None,
        content_media_type: str = "application/json",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a manifest dict (uncommitted)."""
        m = {
            "manifest_version": 1,
            "tenant_id": self.tenant_id,
            "dataset_id": str(dataset_id),
            "created_at": _utc_now_iso(),
            "parent_version": parent_version,
            "source": source,
            "content": {
                "blob_sha256": content_blob_sha256,
                "media_type": content_media_type,
            },
            "metadata": metadata or {},
        }
        return m

    def commit_manifest(self, dataset_id: str, manifest: Dict[str, Any]) -> str:
        """Commit manifest and return dataset_version."""
        # Ensure tenant/dataset binding.
        manifest = dict(manifest)
        manifest["tenant_id"] = self.tenant_id
        manifest["dataset_id"] = str(dataset_id)

        version = _sha256_bytes(_canonical_json_bytes(manifest))
        path = self._manifest_path(dataset_id, version)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=True)
        return version

    def load_manifest(self, dataset_id: str, dataset_version: str) -> Dict[str, Any]:
        path = self._manifest_path(dataset_id, dataset_version)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def resolve_content_blob(self, dataset_id: str, dataset_version: str) -> Tuple[str, bytes]:
        m = self.load_manifest(dataset_id, dataset_version)
        blob_sha = m.get("content", {}).get("blob_sha256")
        if not blob_sha:
            raise ValueError("Manifest missing content.blob_sha256")
        path = self._blob_path(dataset_id, blob_sha)
        with open(path, "rb") as f:
            return blob_sha, f.read()


def json_bytes(obj: Any) -> bytes:
    """Helper for producing deterministic JSON payload bytes."""
    return _canonical_json_bytes(obj)
