import json
import os
import threading
import concurrent.futures
import uuid
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from infra.control_plane import ApiKeyStore
from infra.plans import PlanStore
from infra.quota import QuotaTracker
from infra.budget import BudgetTracker
from infra.tenancy import canonical_tenant_id, scope_path
from infra.job_queue import JobQueue  # Stage B: durable FS-backed
from runtime.context_manager import ContextManager
from runtime.runner import run_pipeline
from infra.graph_registry import GraphRegistry, GraphRegistryError
from infra.metering import MeterEmitter
from infra.observability import log_event
from infra.policy_gates import PolicyGateEnforcer, PolicyViolation


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class GatewayState:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.key_store = ApiKeyStore(repo_root=repo_root)
        self.queue = JobQueue(repo_root=repo_root)
        self.graphs = GraphRegistry(repo_root=repo_root)
        self.meter = MeterEmitter(repo_root=repo_root)
        self.plan_store = PlanStore(repo_root=repo_root)
        self.quota = QuotaTracker(repo_root=repo_root)
        self.budget = BudgetTracker(repo_root=repo_root)

    def resolve_tenant(self, api_key: str) -> str | None:
        return self.key_store.tenant_for_key(api_key)

    def tenant_stats(self, tenant_id: str) -> dict:
        from datetime import date
        plan_id = self.plan_store.tenant_plan_id(tenant_id)
        plan = self.plan_store.plan(plan_id)
        usage = self.quota.get(tenant_id, date.today())
        d = self.queue.stats(tenant_id)
        bu = self.budget.read_usage(tenant_id=tenant_id, day=date.today())
        d.update({"plan_id": plan_id, "plan_limits": plan.get("limits", {}), "quota_usage_today": {"jobs_admitted": usage.jobs_admitted, "bytes_in": usage.bytes_in}, "budget_usage_today": {"credits_used": bu.credits_used}, "budget_limits": plan.get("budget", {})})
        return d


class TenantWorker(threading.Thread):
    def __init__(self, state: GatewayState, tenant_id: str, poll_s: float = 0.25):
        super().__init__(daemon=True)
        self.state = state
        self.tenant_id = canonical_tenant_id(tenant_id)
        self.poll_s = poll_s
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        # crash recovery: reclaim inflight leases
        self.state.queue.reclaim_stale_inflight(self.tenant_id)
        log_event("worker_start", tenant_id=self.tenant_id)
        while not self._stop.is_set():
            item = self.state.queue.dequeue(self.tenant_id)
            if not item:
                time.sleep(self.poll_s)
                continue

            job = item.job
            job_id = str(job.get("job_id"))
            cm = ContextManager(tenant_id=self.tenant_id, job_id=job_id)
            ctx = cm.load()
            ctx["status"] = "running"
            ctx["started_ts_ms"] = int(time.time() * 1000)
            cm.set(ctx)
            cm.save()

            try:
                log_event("job_start", tenant_id=self.tenant_id, job_id=job_id, graph_id=job.get("graph_id"), graph_version=job.get("graph_version"))
                # Execute the flow (bounded)
                timeout_s = float(os.environ.get("IXO_JOB_TIMEOUT_SECONDS", "900"))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(
                        run_pipeline,
                        dataset=job.get("dataset"),
                        summary=job.get("summary"),
                        tenant_id=self.tenant_id,
                        job_id=job_id,
                        graph_id=job.get("graph_id"),
                        graph_version=job.get("graph_version"),
                        dataset_id=job.get("dataset_id"),
                        policy_profile_id=job.get("policy_profile_id") or "default",
                        meter_scope=job.get("meter_scope") or self.tenant_id,
                        execution_mode=job.get("execution_mode") or "batch",
                        parent_dataset_version=job.get("parent_dataset_version"),
                        model_overrides=job.get("model_overrides"),
                    )
                    fut.result(timeout=timeout_s)
                ctx = cm.load()
                ctx["status"] = "succeeded"
                ctx["finished_ts_ms"] = int(time.time() * 1000)
                cm.set(ctx)
                cm.save()
                self.state.queue.ack(self.tenant_id, item.inflight_path)
                log_event("job_success", tenant_id=self.tenant_id, job_id=job_id)
            except Exception as e:
                reason = f"{type(e).__name__}:{e}"
                # persist failure in context
                ctx = cm.load()
                ctx["status"] = "failed"
                ctx["error"] = reason
                ctx["finished_ts_ms"] = int(time.time() * 1000)
                cm.set(ctx)
                cm.save()
                # retry/DLQ decision managed by queue
                moved_to_dlq = self.state.queue.fail(self.tenant_id, item.inflight_path, reason=reason)
                if moved_to_dlq:
                    ctx = cm.load()
                    ctx["status"] = "dlq"
                    cm.set(ctx)
                    cm.save()
                log_event("job_failure", tenant_id=self.tenant_id, job_id=job_id, reason=reason)


class GatewayHandler(BaseHTTPRequestHandler):
    state: GatewayState = None  # injected

    def log_message(self, fmt, *args):
        # suppress default; we use structured logs
        return

    def _auth_tenant(self):
        api_key = self.headers.get("X-API-Key")
        tenant_id = self.state.resolve_tenant(api_key)
        if not tenant_id:
            _write_json(self, 401, {"error": "unauthorized"})
            return None
        return canonical_tenant_id(tenant_id)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/healthz":
            return _write_json(self, 200, {"ok": True})

        if path == "/metrics":
            tenant_id = self._auth_tenant()
            if not tenant_id:
                return
            stats = self.state.tenant_stats(tenant_id)
            return _write_json(self, 200, {"tenant_id": tenant_id, "queue": stats})

        parts = [p for p in path.split("/") if p]
        if parts[:2] == ["v1", "jobs"] and len(parts) == 3:
            tenant_id = self._auth_tenant()
            if not tenant_id:
                return
            job_id = parts[2]
            ctx_path = os.path.join(self.state.repo_root, scope_path(tenant_id, "jobs", job_id, "context.json"))
            if not os.path.exists(ctx_path):
                return _write_json(self, 404, {"error": "not found"})
            with open(ctx_path, "r", encoding="utf-8") as f:
                return _write_json(self, 200, json.load(f))

        if parts[:2] == ["v1", "tenants"] and len(parts) == 4 and parts[3] == "status":
            tenant_id = self._auth_tenant()
            if not tenant_id:
                return
            req_tenant = canonical_tenant_id(parts[2])
            if req_tenant != tenant_id:
                return _write_json(self, 403, {"error": "forbidden"})
            active_path = os.path.join(self.state.repo_root, scope_path(tenant_id, "graphs", "active.json"))
            active = {}
            if os.path.exists(active_path):
                with open(active_path, "r", encoding="utf-8") as f:
                    active = json.load(f)
            meters_dir = os.path.join(self.state.repo_root, scope_path(tenant_id, "meters"))
            meter_files = []
            if os.path.isdir(meters_dir):
                meter_files = sorted([fn for fn in os.listdir(meters_dir) if fn.endswith(".jsonl")])[-10:]
            return _write_json(self, 200, {"tenant_id": tenant_id, "active_graph": active, "queue": self.state.tenant_stats(tenant_id), "recent_meter_files": meter_files})

        return _write_json(self, 404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/v1/jobs":
            return _write_json(self, 404, {"error": "not found"})

        tenant_id = self._auth_tenant()
        if not tenant_id:
            return

        body = _read_json_body(self)

        # Commercialization (Stage C): plan + quota enforcement at admission time
        plan_id = self.state.plan_store.tenant_plan_id(tenant_id)
        plan = self.state.plan_store.plan(plan_id)
        limits = plan.get("limits", {}) or {}
        dataset_obj = body.get("dataset")
        bytes_in = 0
        if dataset_obj is not None:
            try:
                raw = json.dumps(dataset_obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                bytes_in = len(raw)
            except Exception:
                bytes_in = 0

        # Resolve policy_profile_id (plan default if caller omitted)
        resolved_policy_profile_id = body.get("policy_profile_id") or plan.get("default_policy_profile_id") or "default"
        from datetime import date
        ok, reason, usage = self.state.quota.check_and_reserve(
            tenant_id=tenant_id,
            day=date.today(),
            add_jobs=1,
            add_bytes_in=bytes_in,
            limits=limits,
        )
        if not ok:
            # Meter and reject
            self.state.meter.emit(
                tenant_id=tenant_id,
                job_id="",
                event_type="job_rejected_quota",
                unit="count",
                amount=1,
                labels={"reason": reason, "plan_id": str(plan_id)},
            )
            log_event("job_rejected_quota", tenant_id=tenant_id, reason=reason, plan_id=str(plan_id))
            return _write_json(self, 429, {"error": reason, "plan_id": str(plan_id), "limits": limits, "usage_today": {"jobs_admitted": usage.jobs_admitted, "bytes_in": usage.bytes_in}})

        
# Budget guardrail (credits): reserve a small admission cost so over-budget tenants are denied early.
budget_cfg = plan.get("budget", {}) or {}
max_credits = float(budget_cfg.get("credits_per_day", 0.0) or 0.0)
admission_reserve = float(budget_cfg.get("admission_credit_reserve", 0.0) or 0.0)
if max_credits > 0.0 and admission_reserve > 0.0:
    ok_budget, bu = self.state.budget.try_reserve(
        tenant_id=tenant_id,
        day=date.today(),
        credits=admission_reserve,
        max_credits=max_credits,
    )
    if not ok_budget:
        self.state.meter.emit(
            tenant_id=tenant_id,
            job_id="",
            event_type="job_rejected_budget",
            unit="count",
            amount=1,
            labels={"reason": "budget_exceeded", "plan_id": str(plan_id)},
        )
        log_event("job_rejected_budget", tenant_id=tenant_id, plan_id=str(plan_id))
        return _write_json(
            self,
            429,
            {
                "error": "budget_exceeded",
                "plan_id": str(plan_id),
                "budget_limits": budget_cfg,
                "budget_usage_today": {"credits_used": bu.credits_used},
            },
        )

# Pin graph at admission time (no runtime 'latest')
        graph_id = body.get("graph_id")
        graph_version = body.get("graph_version")
        if not (graph_id and graph_version):
            active_path = os.path.join(self.state.repo_root, scope_path(tenant_id, "graphs", "active.json"))
            if os.path.exists(active_path):
                with open(active_path, "r", encoding="utf-8") as f:
                    active = json.load(f)
                    graph_id = graph_id or active.get("graph_id")
                    graph_version = graph_version or active.get("graph_version")

        if not (graph_id and graph_version):
            return _write_json(self, 400, {"error": "graph_id and graph_version required (or set tenant active graph)"})

        try:
            self.state.graphs.load_graph(graph_id=str(graph_id), graph_version=str(graph_version))
        except GraphRegistryError as e:
            return _write_json(self, 400, {"error": f"invalid_graph:{e}"})

        job_id = str(body.get("job_id") or uuid.uuid4().hex)

        # Create contract-compliant initial context (FROZEN v1)
        ctx = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "graph_id": str(graph_id),
            "graph_version": str(graph_version),
            "dataset_refs": [],
            "policy_profile_id": resolved_policy_profile_id,
            "meter_scope": body.get("meter_scope") or tenant_id,
            "execution_mode": body.get("execution_mode") or "batch",
            "status": "admitted",
            "request_id": body.get("request_id"),
            "trace_id": body.get("trace_id"),
            "tags": body.get("tags", []),
        }

        cm = ContextManager(tenant_id=tenant_id, job_id=job_id)
        cm.set(ctx)
        cm.save()

        # Admission-time policy preview (deny before enqueue)
        try:
            enforcer = PolicyGateEnforcer(
                tenant_id=tenant_id,
                policy_profile_id=resolved_policy_profile_id,
                job_id=job_id,
                repo_root=self.state.repo_root,
            )
            enforcer.pre_exec(context=ctx, payload_bytes=bytes_in)
        except PolicyViolation as e:
            # Persist denial
            denied = cm.load()
            denied["status"] = "denied"
            denied["error"] = f"PolicyViolation:{e}"
            cm.set(denied)
            cm.save()

            # Meter denial
            self.state.meter.emit(
                tenant_id=tenant_id,
                job_id=job_id,
                event_type="job_rejected_policy",
                unit="count",
                amount=1,
                labels={"reason": str(e), "policy_profile_id": str(resolved_policy_profile_id), "plan_id": str(plan_id)},
            )
            log_event("job_rejected_policy", tenant_id=tenant_id, job_id=job_id, reason=str(e), policy_profile_id=str(resolved_policy_profile_id), plan_id=str(plan_id))
            return _write_json(self, 403, {"error": "policy_denied", "reason": str(e), "policy_profile_id": str(resolved_policy_profile_id), "job_id": job_id})

        # Prepare job envelope for queue execution
        job = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "graph_id": str(graph_id),
            "graph_version": str(graph_version),
            "dataset_id": body.get("dataset_id"),
            "dataset": body.get("dataset"),
            "summary": body.get("summary"),
            "policy_profile_id": resolved_policy_profile_id,
            "meter_scope": body.get("meter_scope") or tenant_id,
            "execution_mode": body.get("execution_mode") or "batch",
            "parent_dataset_version": body.get("parent_dataset_version"),
            "model_overrides": body.get("model_overrides"),
        }

        # Admission metering
        self.state.meter.emit(
            tenant_id=tenant_id,
            job_id=job_id,
            event_type="job_admitted",
            unit="count",
            amount=1,
            labels={"graph_id": str(graph_id), "graph_version": str(graph_version)},
        )

        # Enqueue
        self.state.queue.enqueue(tenant_id=tenant_id, job=job)
        ctx = cm.load()
        ctx["status"] = "queued"
        cm.set(ctx)
        cm.save()

        log_event("job_admitted", tenant_id=tenant_id, job_id=job_id, graph_id=str(graph_id), graph_version=str(graph_version))
        return _write_json(self, 202, {"tenant_id": tenant_id, "job_id": job_id, "graph_id": str(graph_id), "graph_version": str(graph_version), "status": "queued"})


def serve(host: str = "127.0.0.1", port: int = 8080, repo_root: str | None = None, tenant_workers=None):
    if repo_root is None:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    state = GatewayState(repo_root=repo_root)

    class _H(GatewayHandler):
        pass

    _H.state = state
    httpd = HTTPServer((host, port), _H)

    workers = []
    for t in tenant_workers or []:
        w = TenantWorker(state=state, tenant_id=t)
        w.start()
        workers.append(w)

    log_event("gateway_listen", host=host, port=port, repo_root=repo_root)
    try:
        httpd.serve_forever()
    finally:
        for w in workers:
            w.stop()


if __name__ == "__main__":
    serve(tenant_workers=["tenant-a"])