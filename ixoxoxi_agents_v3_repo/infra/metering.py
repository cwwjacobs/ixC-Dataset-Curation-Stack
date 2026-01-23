import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


from infra.tenancy import canonical_tenant_id, scope_path


@dataclass(frozen=True)
class MeterEvent:
    """A minimal, immutable billing/metering event.

    Design goals:
      - every event is attributable (tenant_id/job_id/meter_scope)
      - low cardinality fields are first-class; high-cardinality fields live in labels
      - append-only persistence (JSONL)
    """

    event_id: str
    ts_utc: str
    tenant_id: str
    job_id: str
    meter_scope: str
    event_type: str
    units: float
    unit_type: str
    graph_id: str
    graph_version: str
    policy_profile_id: str
    execution_mode: str
    labels: Dict[str, Any]


class MeterSinkJsonl:
    """Append-only JSONL sink, tenant-scoped.

    Files are rotated daily by UTC date.
    """

    def __init__(self, tenant_id: str, base_dir: str = "."):
        self.tenant_id = canonical_tenant_id(tenant_id)
        self.base_dir = base_dir

    def _path_for_today(self) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.base_dir, scope_path(self.tenant_id, "meters", f"{day}.jsonl"))

    def append(self, event: MeterEvent) -> str:
        path = self._path_for_today()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return path


class MeterEmitter:
    """Convenience wrapper to emit contract-aligned meter events."""

    def __init__(
        self,
        *,
        tenant_id: str,
        job_id: str,
        meter_scope: str,
        graph_id: str,
        graph_version: str,
        policy_profile_id: str,
        execution_mode: str,
        base_dir: str = ".",
    ):
        self.tenant_id = canonical_tenant_id(tenant_id)
        self.job_id = job_id
        self.meter_scope = meter_scope
        self.graph_id = graph_id
        self.graph_version = graph_version
        self.policy_profile_id = policy_profile_id
        self.execution_mode = execution_mode
        self.sink = MeterSinkJsonl(self.tenant_id, base_dir=base_dir)

    def emit(
        self,
        event_type: str,
        *,
        # Back-compat convenience (preferred in this repo)
        count: Optional[float] = None,
        bytes: Optional[float] = None,
        # Low-level interface (for external integrations)
        units: Optional[float] = None,
        unit_type: Optional[str] = None,
        labels: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Emit a meter event.

        Backward-compatible convenience:
          - count=<n>  -> units=n, unit_type="count"
          - bytes=<n>  -> units=n, unit_type="bytes"

        If units/unit_type are provided explicitly, they take precedence.
        """
        if units is None or unit_type is None:
            if bytes is not None:
                units = float(bytes)
                unit_type = "bytes"
            elif count is not None:
                units = float(count)
                unit_type = "count"
            else:
                # Default to a single count if nothing specified.
                units = 1.0
                unit_type = "count"

        evt = MeterEvent(
            event_id=str(uuid.uuid4()),
            ts_utc=datetime.now(timezone.utc).isoformat(),
            tenant_id=self.tenant_id,
            job_id=self.job_id,
            meter_scope=self.meter_scope,
            event_type=event_type,
            units=float(units),
            unit_type=str(unit_type),
            graph_id=self.graph_id,
            graph_version=self.graph_version,
            policy_profile_id=self.policy_profile_id,
            execution_mode=self.execution_mode,
            labels=labels or {},
        )
        return self.sink.append(evt)
