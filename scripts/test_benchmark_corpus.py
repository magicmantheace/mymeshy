"""GPU-free validation of the committed benchmark corpus contract."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "corpus.json"


def main() -> None:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert data["version"] == 1
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "benchmark case IDs must be unique"
    assert {"text", "image"} <= {case["mode"] for case in cases}
    for case in cases:
        assert case["id"].replace("_", "").isalnum()
        if case["mode"] == "text":
            assert case.get("prompt", "").strip()
        elif case["mode"] == "image":
            assert case.get("generator") in {"potion", "chair", "lamp"}
        else:
            raise AssertionError(f"unsupported mode: {case['mode']}")
    print(f"PASS: benchmark corpus contains {len(cases)} stable cases")


if __name__ == "__main__":
    main()
