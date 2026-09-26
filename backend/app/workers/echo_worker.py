"""Dependency-free subprocess used to verify the worker IPC framework."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    Path(args.result).write_text(
        json.dumps({"status": "ok", "pid": os.getpid(), "payload": payload}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
