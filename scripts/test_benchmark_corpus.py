"""GPU-free validation of the committed benchmark corpus and suite contracts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "corpus.json"
SUITE = ROOT / "benchmarks" / "suite.json"


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

    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    assert suite["version"] == 1
    assert suite["adapters"], "benchmark suite must contain at least one adapter"
    assert set(suite["adapters"]) <= {"triposr", "hunyuan3d"}
    assert suite["cases"], "benchmark suite must contain at least one case"
    assert set(suite["cases"]) <= set(ids), "suite references an unknown corpus case"
    settings = suite["settings"]
    assert int(settings["target_polycount"]) > 0
    assert int(settings["texture_size"]) in {256, 512, 1024, 2048, 4096}
    assert isinstance(settings["seed"], int)

    print(
        f"PASS: benchmark corpus has {len(cases)} stable cases; "
        f"suite defines {len(suite['adapters']) * len(suite['cases'])} runs"
    )


if __name__ == "__main__":
    main()
