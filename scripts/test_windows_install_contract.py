"""GPU-free source checks for the preferred Windows real-model install path."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "scripts" / "install-models.ps1").read_text(encoding="utf-8")
WORKERS = (ROOT / "scripts" / "setup-workers.ps1").read_text(encoding="utf-8")
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
    assert "Sync-ShallowRepo" in WORKERS
    assert 'Set-EnvValue $envFile "MYMESHY_ISOLATED_WORKERS" "true"' in WORKERS
    assert "MYMESHY_TRIPOSR_WORKER_PYTHON" in WORKERS
    assert "MYMESHY_HUNYUAN_SHAPE_WORKER_PYTHON" in WORKERS
    assert RUNBOOK.is_file()

    print("PASS: Windows real-model install delegates image-to-3D models to isolated workers")


if __name__ == "__main__":
    main()
