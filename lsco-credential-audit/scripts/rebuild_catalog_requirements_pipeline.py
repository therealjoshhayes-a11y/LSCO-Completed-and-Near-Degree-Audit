#!/usr/bin/env python
"""
Canonical LSCO catalog-requirements rebuild with persistent health-program recovery.

This script is the supported replacement for running
`build_multicatalog_requirements_master.py` by itself.

Pipeline:
1. Rebuild the base multicatalog requirements master from catalog extraction outputs.
2. Rebuild and validate the approved 14-credential-year health overlay.
3. Apply the overlay idempotently with backups and regression tests.
4. Rebuild and validate the executable multiyear requirements master.
5. Run a final preflight proving the recovered credentials survived the rebuild.

The generated CSV files remain ignored by Git. The reproducible repair logic lives in
the committed scripts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(command: list[str], root: Path, label: str) -> None:
    print("\n" + "=" * 118)
    print(label)
    print("=" * 118)
    print(" ".join(command))
    completed = subprocess.run(command, cwd=root)
    if completed.returncode != 0:
        raise SystemExit(
            f"{label} failed with exit code {completed.returncode}"
        )


def main() -> int:
    root = Path(".").resolve()
    scripts = root / "scripts"

    base_builder = scripts / "build_multicatalog_requirements_master.py"
    overlay_builder = scripts / "build_missing_health_credentials_overlay_v9.py"
    repair_merger = scripts / "merge_missing_health_credentials_into_production_v3.py"
    preflight = scripts / "verify_health_credentials_preflight.py"

    required = [base_builder, overlay_builder, repair_merger, preflight]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(
            "Required pipeline scripts are missing:\n- " + "\n- ".join(missing)
        )

    run(
        [sys.executable, str(base_builder)],
        root,
        "STEP 1 — REBUILD BASE MULTICATALOG MASTER",
    )

    run(
        [sys.executable, str(overlay_builder)],
        root,
        "STEP 2 — REBUILD AND VALIDATE HEALTH OVERLAY",
    )

    run(
        [
            sys.executable,
            str(repair_merger),
            "--skip-overlay-rebuild",
        ],
        root,
        "STEP 3 — APPLY PERSISTENT HEALTH REPAIR AND REGRESSION TEST",
    )

    run(
        [sys.executable, str(preflight)],
        root,
        "STEP 4 — FINAL CATALOG REQUIREMENTS PREFLIGHT",
    )

    print("\n" + "=" * 118)
    print("CANONICAL CATALOG REQUIREMENTS PIPELINE: PASS")
    print("=" * 118)
    print("The health-program repair survived a clean base-master rebuild.")
    print("The production masters are ready for the full audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
