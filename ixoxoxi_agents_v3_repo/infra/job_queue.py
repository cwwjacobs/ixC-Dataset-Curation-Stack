import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

from infra.tenancy import canonical_tenant_id, scope_path
from infra.observability import log_event, getenv_int


@dataclass(frozen=True)
class DequeuedJob:
    job: Dict[str, Any]
    lease_id: str
    inflight_path: str


class DurableJobQueue:
    """Filesystem-backed per-tenant queue with retries + DLQ.

    Layout (per tenant):
      .tenants/<tenant_id>/queue/ready/*.json
      .tenants/<tenant_id>/queue/inflight/*.json
      .tenants/<tenant_id>/queue/dlq/*.json

    Dequeue uses an atomic rename ready -> inflight.
    Ack removes inflight file.
    Fail increments retry count and either requeues or moves to dlq.
    """

    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.max_retries = getenv_int("IXO_QUEUE_MAX_RETRIES", 3)
        self.lease_seconds = getenv_int("IXO_QUEUE_LEASE_SECONDS", 300)

    def _dir(self, tenant_id: str, kind: str) -> str:
        t = canonical_tenant_id(tenant_id)
        d = os.path.join(self.repo_root, scope_path(t, "queue", kind))
        os.makedirs(d, exist_ok=True)
        return d

    def _atomic_write_json(self, path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp.{uuid.uuid4().hex}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def enqueue(self, tenant_id: str, job: Dict[str, Any]) -> str:
        t = canonical_tenant_id(tenant_id)
        if not job.get("tenant_id") or canonical_tenant_id(str(job.get("tenant_id"))) != t:
            raise ValueError("enqueue requires job['tenant_id'] to match tenant_id")
        if not job.get("job_id"):
            raise ValueError("enqueue requires job['job_id']")
        ready_dir = self._dir(t, "ready")
        fname = f"{int(time.time()*1000)}_{uuid.uuid4().hex}.json"
        path = os.path.join(ready_dir, fname)
        payload = dict(job)
        payload.setdefault("_queue", {})
        payload["_queue"].update({"retries": int(payload["_queue"].get("retries", 0)), "enqueued_ts_ms": int(time.time()*1000)})
        self._atomic_write_json(path, payload)
        log_event("queue_enqueue", tenant_id=t, job_id=str(job["job_id"]), path=os.path.relpath(path, self.repo_root))
        return path

    def _list_ready(self, tenant_id: str) -> List[str]:
        d = self._dir(tenant_id, "ready")
        files = [os.path.join(d, fn) for fn in os.listdir(d) if fn.endswith(".json")]
        files.sort()
        return files

    def dequeue(self, tenant_id: str) -> Optional[DequeuedJob]:
        t = canonical_tenant_id(tenant_id)
        inflight_dir = self._dir(t, "inflight")
        for src in self._list_ready(t):
            lease_id = uuid.uuid4().hex
            dst = os.path.join(inflight_dir, os.path.basename(src).replace(".json", f".lease.{lease_id}.json"))
            try:
                os.replace(src, dst)  # atomic claim
            except FileNotFoundError:
                continue
            except PermissionError:
                continue
            try:
                with open(dst, "r", encoding="utf-8") as f:
                    job = json.load(f)
            except Exception as e:
                # if unreadable, move to dlq as corrupt
                self._move_to_dlq_path(t, dst, reason=f"corrupt_json:{e}")
                return None
            job.setdefault("_queue", {})
            job["_queue"].update({"lease_id": lease_id, "inflight_ts_ms": int(time.time()*1000)})
            self._atomic_write_json(dst, job)
            log_event("queue_dequeue", tenant_id=t, job_id=str(job.get("job_id")), lease_id=lease_id)
            return DequeuedJob(job=job, lease_id=lease_id, inflight_path=dst)
        return None

    def ack(self, tenant_id: str, inflight_path: str) -> None:
        t = canonical_tenant_id(tenant_id)
        try:
            os.remove(inflight_path)
            log_event("queue_ack", tenant_id=t, inflight=os.path.relpath(inflight_path, self.repo_root))
        except FileNotFoundError:
            return

    def fail(self, tenant_id: str, inflight_path: str, reason: str) -> bool:
        t = canonical_tenant_id(tenant_id)
        job = {}
        try:
            with open(inflight_path, "r", encoding="utf-8") as f:
                job = json.load(f)
        except Exception:
            # if can't read, DLQ
            self._move_to_dlq_path(t, inflight_path, reason=f"unreadable:{reason}")
            return True

        q = job.setdefault("_queue", {})
        retries = int(q.get("retries", 0)) + 1
        q["retries"] = retries
        q["last_error"] = reason
        q["last_error_ts_ms"] = int(time.time()*1000)

        if retries > self.max_retries:
            self._atomic_write_json(inflight_path, job)
            self._move_to_dlq_path(t, inflight_path, reason=reason)
            return True

        # requeue
        ready_dir = self._dir(t, "ready")
        fname = f"{int(time.time()*1000)}_{uuid.uuid4().hex}.json"
        dst = os.path.join(ready_dir, fname)
        self._atomic_write_json(dst, job)
        try:
            os.remove(inflight_path)
        except FileNotFoundError:
            pass
        log_event("queue_requeue", tenant_id=t, job_id=str(job.get("job_id")), retries=retries, reason=reason)
        return False

    def _move_to_dlq_path(self, tenant_id: str, inflight_path: str, reason: str) -> None:
        t = canonical_tenant_id(tenant_id)
        dlq_dir = self._dir(t, "dlq")
        base = os.path.basename(inflight_path)
        dst = os.path.join(dlq_dir, base)
        try:
            os.replace(inflight_path, dst)
        except FileNotFoundError:
            return
        # annotate reason (best-effort)
        try:
            with open(dst, "r", encoding="utf-8") as f:
                job = json.load(f)
            job.setdefault("_queue", {})
            job["_queue"]["dlq_reason"] = reason
            job["_queue"]["dlq_ts_ms"] = int(time.time()*1000)
            self._atomic_write_json(dst, job)
        except Exception:
            pass
        log_event("queue_dlq", tenant_id=t, inflight=os.path.relpath(dst, self.repo_root), reason=reason)

    def reclaim_stale_inflight(self, tenant_id: str) -> int:
        """Move inflight jobs back to ready if lease expired (crash recovery)."""
        t = canonical_tenant_id(tenant_id)
        inflight_dir = self._dir(t, "inflight")
        now = int(time.time()*1000)
        reclaimed = 0
        for fn in os.listdir(inflight_dir):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(inflight_dir, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    job = json.load(f)
                inflight_ts = int(job.get("_queue", {}).get("inflight_ts_ms", 0))
            except Exception:
                inflight_ts = 0
            age_s = (now - inflight_ts) / 1000 if inflight_ts else self.lease_seconds + 1
            if age_s > self.lease_seconds:
                # treat as failed due to lease expiry
                self.fail(t, path, reason="lease_expired")
                reclaimed += 1
        if reclaimed:
            log_event("queue_reclaim", tenant_id=t, reclaimed=reclaimed)
        return reclaimed

    def stats(self, tenant_id: str) -> Dict[str, int]:
        t = canonical_tenant_id(tenant_id)
        out = {}
        for kind in ("ready","inflight","dlq"):
            d = self._dir(t, kind)
            out[kind] = len([fn for fn in os.listdir(d) if fn.endswith(".json")])
        return out


# Backward-compatible name used by gateway_server
JobQueue = DurableJobQueue
