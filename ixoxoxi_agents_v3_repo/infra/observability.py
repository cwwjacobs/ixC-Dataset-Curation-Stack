import json
import os
import sys
import time
from typing import Any, Dict, Optional

def now_ms() -> int:
    return int(time.time() * 1000)

def log_event(event: str, **fields: Any) -> None:
    """Emit a single structured log line (JSON) to stdout.

    Keep this extremely stable; logs are an ops interface.
    """
    payload: Dict[str, Any] = {
        "ts_ms": now_ms(),
        "event": event,
    }
    payload.update(fields)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def getenv_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default
