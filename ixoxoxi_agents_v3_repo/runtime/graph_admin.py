import argparse
import json
import os
import sys

from infra.graph_registry import GraphRegistry, TenantGraphManager


def main():
    ap = argparse.ArgumentParser(description="Graph registry admin (register/activate/rollback).")
    ap.add_argument("--repo-root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register", help="Register a graph definition JSON file into specs/graphs.")
    r.add_argument("graph_def_path")

    a = sub.add_parser("activate", help="Activate a graph version for a tenant.")
    a.add_argument("tenant_id")
    a.add_argument("graph_id")
    a.add_argument("graph_version")
    a.add_argument("--actor", default="system")
    a.add_argument("--reason", default="")

    rb = sub.add_parser("rollback", help="Rollback tenant's active graph to previous version.")
    rb.add_argument("tenant_id")
    rb.add_argument("graph_id")
    rb.add_argument("--actor", default="system")
    rb.add_argument("--reason", default="rollback")

    args = ap.parse_args()

    if args.cmd == "register":
        with open(args.graph_def_path, "r", encoding="utf-8") as f:
            graph_def = json.load(f)
        reg = GraphRegistry(repo_root=args.repo_root)
        graph_id, graph_version, path = reg.register_graph(graph_def)
        print(json.dumps({"graph_id": graph_id, "graph_version": graph_version, "path": path}, indent=2))
        return 0

    if args.cmd == "activate":
        mgr = TenantGraphManager(args.tenant_id)
        mgr.set_active(args.graph_id, args.graph_version, actor=args.actor, reason=args.reason)
        print(json.dumps({"tenant_id": args.tenant_id, "graph_id": args.graph_id, "graph_version": args.graph_version}, indent=2))
        return 0

    if args.cmd == "rollback":
        mgr = TenantGraphManager(args.tenant_id)
        v = mgr.rollback(args.graph_id, actor=args.actor, reason=args.reason)
        print(json.dumps({"tenant_id": args.tenant_id, "graph_id": args.graph_id, "graph_version": v}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
