import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, Tuple

from infra.tenancy import canonical_tenant_id, scope_path


def iter_meter_events(repo_root: str, tenant_id: str):
    tenant_id = canonical_tenant_id(tenant_id)
    meters_dir = os.path.join(repo_root, scope_path(tenant_id, "meters"))
    if not os.path.exists(meters_dir):
        return
    for name in sorted(os.listdir(meters_dir)):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(meters_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def aggregate_daily(repo_root: str, tenant_id: str) -> Dict[Tuple[str,str,str], float]:
    """
    Returns mapping keyed by (day, event_type, unit) -> total amount.
    """
    agg = defaultdict(float)
    for ev in iter_meter_events(repo_root, tenant_id):
        ts = ev.get("ts") or ev.get("timestamp") or ""
        day = ""
        if ts:
            try:
                day = ts[:10]
            except Exception:
                day = ""
        if not day:
            day = "unknown"
        key = (day, str(ev.get("event_type","unknown")), str(ev.get("unit","unknown")))
        agg[key] += float(ev.get("amount", 0))
    return dict(agg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--out", default="billing_export.csv")
    args = ap.parse_args()

    agg = aggregate_daily(args.repo_root, args.tenant_id)
    out_path = args.out
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tenant_id","day","event_type","unit","amount"])
        for (day, event_type, unit), amount in sorted(agg.items()):
            w.writerow([canonical_tenant_id(args.tenant_id), day, event_type, unit, f"{amount:.6f}"])
    print(out_path)


if __name__ == "__main__":
    main()
