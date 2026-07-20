from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


SELECTOR = Path("scripts/select_maximum_awards.py")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OLD = 'def derive_lineage(credential_id: object) -> str:\n    """Strip only a terminal catalog-year suffix so the same credential\n    across catalog years shares a lineage. Mirrors\n    build_credential_completion_report.py so lineage keys agree."""\n    value = normalize_text(credential_id)\n    value = re.sub(r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026)$", "", value)\n    value = re.sub(r"_(2021|2022|2023|2024|2025|2026)$", "", value)\n    return value\n'
NEW = 'def derive_lineage(credential_id: object) -> str:\n    """Strip only a terminal catalog-year suffix so the same credential\n    across catalog years shares a lineage. Mirrors\n    build_credential_completion_report.py so lineage keys agree.\n\n    Controlled lineage override:\n        REAL_ESTATE_MANAGEMENT_2025 continues the earlier\n        BUSINESS_REAL_ESTATE_MANAGEMENT AAS lineage.\n    """\n    value = normalize_text(credential_id)\n\n    if value == "REAL_ESTATE_MANAGEMENT_2025":\n        return "BUSINESS_REAL_ESTATE_MANAGEMENT"\n\n    value = re.sub(r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026)$", "", value)\n    value = re.sub(r"_(2021|2022|2023|2024|2025|2026)$", "", value)\n    return value\n'


def main() -> None:
    if not SELECTOR.exists():
        raise FileNotFoundError(SELECTOR)

    text = SELECTOR.read_text(encoding="utf-8")

    if 'if value == "REAL_ESTATE_MANAGEMENT_2025":' in text:
        print("Override already present. No change made.")
        return

    if OLD not in text:
        raise RuntimeError(
            "Expected derive_lineage() block not found. "
            "The selector may not be in the restored state."
        )

    backup = SELECTOR.with_suffix(
        SELECTOR.suffix + f".before_real_estate_direct_{STAMP}.bak"
    )
    shutil.copy2(SELECTOR, backup)

    patched = text.replace(OLD, NEW, 1)
    compile(patched, str(SELECTOR), "exec")
    SELECTOR.write_text(patched, encoding="utf-8")

    print("=" * 100)
    print("REAL ESTATE DIRECT LINEAGE OVERRIDE")
    print("=" * 100)
    print(f"Patched: {SELECTOR}")
    print(f"Backup:  {backup}")
    print("Override: REAL_ESTATE_MANAGEMENT_2025 -> BUSINESS_REAL_ESTATE_MANAGEMENT")
    print("Syntax: PASSED")
    print()
    print("Next command:")
    print(r"python -u .\scripts\select_maximum_awards.py")


if __name__ == "__main__":
    main()
