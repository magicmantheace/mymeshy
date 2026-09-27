"""GPU-free source checks for the preferred Windows real-model install path."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "scripts" / "install-models.ps1").read_text(encoding="utf-8")
WORKERS = (ROOT / "scripts" / "setup-workers.ps1").read_text(encoding="utf-8")
LOCKS_PATH = ROOT / "backend" / "model-sources.json"
RUNBOOK = ROOT / "docs" / "WINDOWS_SETUP.md"


def main() -> None:
    assert "[switch]$CompileHunyuanPaint" in INSTALL
    assert 'uv pip install --python $py torch torchvision' in INSTALL
    assert 'backend\\requirements-ml.txt' in INSTALL
    assert '& $workerSetup -CompileHunyuanPaint' in INSTALL
    assert '& $workerSetup' in INSTALL

    # Image-to-3D source/dependency setup belongs to the isolated worker script,
    # not a second shared-backend installation path.
    assert "git clone" not in INSTALL
    assert "Sync-LockedRepo" in WORKERS
    assert "git -C $Path fetch --depth 1 origin $Revision" in WORKERS
    assert "git -C $Path checkout --detach --force FETCH_HEAD" in WORKERS
    assert 'Set-EnvValue $envFile "MYMESHY_ISOLATED_WORKERS" "true"' in WORKERS
    assert "MYMESHY_TRIPOSR_WORKER_PYTHON" in WORKERS
    assert "MYMESHY_HUNYUAN_SHAPE_WORKER_PYTHON" in WORKERS

    locks = json.loads(LOCKS_PATH.read_text(encoding="utf-8"))
    assert locks["version"] == 1
    assert set(locks["sources"]) == {"triposr", "hunyuan3d_2"}
    for name, source in locks["sources"].items():
        assert source["url"].startswith("https://github.com/")
        assert re.fullmatch(r"[0-9a-f]{40}", source["revision"]), name

    assert RUNBOOK.is_file()
    print("PASS: Windows model setup uses isolated workers with explicit source revision locks")


if __name__ == "__main__":
    main()
