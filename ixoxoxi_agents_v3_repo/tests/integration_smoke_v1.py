"""Integration smoke test (stdlib-only).

Run:
  python -m tests.integration_smoke_v1

Prereq: gateway server running on 127.0.0.1:8080
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error


BASE = "http://127.0.0.1:8080"
API_KEY = "dev-key-tenant-a"


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = BASE + path
    data = None
    headers = {"X-API-Key": API_KEY}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code}: {payload}") from e


def main() -> None:
    submit = _req(
        "POST",
        "/v1/jobs",
        {
            "dataset_id": "itest-001",
            "dataset": [{"foo": "bar"}, {"foo": "bar"}, {"foo": "baz"}],
            "execution_mode": "batch",
        },
    )
    job_id = submit["job_id"]
    print("submitted", job_id)

    deadline = time.time() + 30
    while time.time() < deadline:
        ctx = _req("GET", f"/v1/jobs/{job_id}")
        status = ctx.get("status")
        if status in ("succeeded", "failed", "dlq"):
            print("status", status)
            if status != "succeeded":
                raise SystemExit(f"job ended in {status}: {ctx}")
            # verify output dataset refs exist
            refs = ctx.get("dataset_refs") or []
            if not refs:
                raise SystemExit(f"missing dataset_refs: {ctx}")
            print("dataset_refs", refs)
            return
        time.sleep(0.5)

    raise SystemExit("timeout waiting for job completion")


if __name__ == "__main__":
    main()
