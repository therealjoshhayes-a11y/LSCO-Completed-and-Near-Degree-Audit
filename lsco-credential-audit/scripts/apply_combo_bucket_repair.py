"""Apply the 2026-07-16 combo-bucket resolution repair to the audit engine.

Run from the repository root:

    python scripts/apply_combo_bucket_repair.py

PATCH 4 (audit engine): normalize_bucket_name() resolves "X or Y" combo
bucket phrases to their UNION lookup keys before the narrow single-bucket
phrase checks can fire.

DEFECT: catalog requirement slots written as a choice between two core
areas (e.g. "LANGUAGE, PHILOSOPHY, AND CULTURE or CREATIVE ARTS",
"COMMUNICATION or COMPONENT AREA OPTION") extract as a single CORE_BUCKET
option row. normalize_bucket_name() phrase-matched in fixed order, so:
  - "COMMUNICATION or COMPONENT AREA OPTION" hit the "COMMUNICATION"
    check first and resolved to COMMUNICATION_CORE (3 courses) instead
    of the 43-58 course union;
  - "LANGUAGE, PHILOSOPHY, AND CULTURE or CREATIVE ARTS" resolved to
    the 10-14 course LPC list, dropping the arts satisfiers;
  - "Lang, Phil, Culture OR Creative Arts" (abbreviated) matched NEITHER
    language check, fell through to "CREATIVE ARTS", and resolved to the
    3-course arts list -- the narrowest possible reading of a slot that
    should accept 13-19 courses.
A student who satisfied such a slot via the un-resolved half silently
fails to match. 67 solo combo option rows exist across the five catalogs
(2026-07-16 census), concentrated in AAS management credentials
(Business Management carries two per catalog year).

EVIDENCE OF ORIGINAL INTENT: core_bucket_lookup_multicatalog.csv already
contains fully-populated union keys for every observed variant, all five
catalog years, including a literal LANG_PHIL_CULTURE_OR_CREATIVE_ARTS
alias. The lookup was built for union resolution; the normalizer never
learned the phrases. This repair is mechanical defect correction, not a
policy change: catalog text "X or Y" means either satisfies the slot.

Canonical union keys used (verified present for all 5 catalog years):
    LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS
    COMMUNICATION_OR_COMPONENT_AREA_OPTION
The FINE ARTS variants map to the CREATIVE ARTS union key; the lookup's
..._OR_FINE_ARTS alias carries identical course counts.

The existing exact-match handling of "LIFE OR PHYSICAL SCIENCE(S)" is
unaffected: those values match neither combo family and fall through to
their existing checks.

Safety: verifies the patch target appears exactly once before writing;
aborts with no changes otherwise. Timestamped backup per repo convention.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

ENGINE = Path("src/lsco_audit/audit_multiyear_sample.py")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OLD = """def normalize_bucket_name(value: str) -> str | None:
    text = str(value).upper()

    if "COMMUNICATION" in text:
        return "COMMUNICATION_CORE"
"""

NEW = """def normalize_bucket_name(value: str) -> str | None:
    text = str(value).upper()

    # REPAIR NOTE (2026-07-16, combo-bucket repair): "X or Y" combo slots
    # must resolve to their UNION lookup keys BEFORE the narrow
    # single-bucket phrase checks below can fire. Previously
    # "COMMUNICATION or COMPONENT AREA OPTION" resolved to
    # COMMUNICATION_CORE (3 courses) instead of the 43+ course union, and
    # abbreviated forms like "Lang, Phil, Culture OR Creative Arts"
    # resolved to CREATIVE_ARTS_CORE (3 courses) instead of the 13-19
    # course union. The union keys below exist in
    # core_bucket_lookup_multicatalog.csv for all five catalog years and
    # were built for exactly this purpose. Catalog text "X or Y" means
    # either area satisfies the slot; this is defect correction, not a
    # policy change. See apply_combo_bucket_repair.py for the census.
    if " OR " in text:
        lpc_family = (
            "LANGUAGE" in text or "LANG" in text
        ) and (
            "PHILOSOPHY" in text or "PHIL" in text
        )
        arts_family = "CREATIVE ARTS" in text or "FINE ARTS" in text

        if lpc_family and arts_family:
            return "LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS"

        if "COMMUNICATION" in text and "COMPONENT AREA OPTION" in text:
            return "COMMUNICATION_OR_COMPONENT_AREA_OPTION"

    if "COMMUNICATION" in text:
        return "COMMUNICATION_CORE"
"""


def main() -> None:
    if not ENGINE.exists():
        print(f"ABORT: {ENGINE} not found. Run from the repository root.")
        sys.exit(1)

    text = ENGINE.read_text(encoding="utf-8")

    if "LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS" in text:
        print("ABORT: combo-bucket repair already applied. No changes made.")
        sys.exit(1)

    count = text.count(OLD)
    if count != 1:
        print(f"ABORT: patch target found {count} times (expected 1). "
              "Working copy differs; apply manually. No changes made.")
        sys.exit(1)

    backup = ENGINE.with_name(ENGINE.stem + f"_PRE_COMBO_BUCKET_REPAIR_{STAMP}.py")
    shutil.copyfile(ENGINE, backup)

    ENGINE.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("Applied combo-bucket repair.")
    print(f"Backup: {backup}")
    print()
    print("Engine-side change only: NO re-extraction or master rebuild needed.")
    print("This is the final patch before the chunked audit re-run.")


if __name__ == "__main__":
    main()
