"""Select countable awards from the full audit under the maximum-award sweep.

Policy (user decisions, 2026-07-16):
    - Population: every student active between Fall 2021 and the last
      record. Maximum possible awards, without regard to when courses
      were taken.
    - Visibility: EVERY completing (student, lineage, catalog_year)
      combination is reported. No completion is hidden.
    - Countability: exactly ONE award per (student, credential_lineage).
      When multiple catalog years complete the same lineage, the LATEST
      catalog wins. Different lineages stack freely (a student may earn
      a CERT and an AA in the same sweep, as LSCO's published counts do).
    - Deadline flag: each selected award carries the graduate_by date of
      its winning catalog (from config/catalogs.csv). Awards whose ONLY
      completing catalog is near its graduate_by deadline are flagged
      so conferral can be prioritized before the catalog dies.

Inputs:
    data/processed/full_actual_audit/full_actual_credential_summary.csv
        (audit_status per student x catalog_year x credential_id --
         produced by run_full_actual_audit_chunked.py; does NOT need
         re-running when eligibility changes)
    data/processed/student_catalog_eligibility.csv
        (catalog SETS per student -- build_student_catalog_eligibility_v2.py)
    config/catalogs.csv
        (registry with graduate_by dates)

Outputs (in data/processed/reporting/award_selection_<stamp>/):
    all_completing_combinations.csv   -- every eligible COMPLETE row (visibility)
    selected_awards.csv               -- one countable award per student-lineage
    deadline_priority_review.csv      -- selected awards on a dying catalog
    award_counts_by_lineage.csv       -- aggregate counts for comparison
"""

from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
import re

import pandas as pd

SUMMARY_PATH = Path("data/processed/full_actual_audit/full_actual_credential_summary.csv")
ELIGIBILITY_PATH = Path("data/processed/student_catalog_eligibility.csv")
CATALOG_REGISTRY_PATH = Path("config/catalogs.csv")

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path(f"data/processed/reporting/award_selection_{RUN_STAMP}")

DEADLINE_WARNING_DAYS = 180


def normalize_text(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def derive_lineage(credential_id: object) -> str:
    """Strip only a terminal catalog-year suffix so the same credential
    across catalog years shares a lineage. Mirrors
    build_credential_completion_report.py so lineage keys agree."""
    value = normalize_text(credential_id)
    value = re.sub(r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026)$", "", value)
    value = re.sub(r"_(2021|2022|2023|2024|2025|2026)$", "", value)
    return value


def catalog_sort_key(catalog_year: object) -> int:
    match = re.match(r"^\s*(20\d{2})-(20\d{2})\s*$", str(catalog_year))
    if not match:
        return -1
    return int(match.group(1))


def truthy(value: object) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y", "ELIGIBLE"}


def require(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Required file not found: {path.resolve()}")


def main() -> None:
    require(SUMMARY_PATH)
    require(ELIGIBILITY_PATH)
    require(CATALOG_REGISTRY_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(SUMMARY_PATH, dtype=str, low_memory=False).fillna("")
    eligibility = pd.read_csv(ELIGIBILITY_PATH, dtype=str, low_memory=False).fillna("")
    registry = pd.read_csv(CATALOG_REGISTRY_PATH, dtype=str).fillna("")

    for frame, name, cols in (
        (summary, "summary", {"student_id", "catalog_year", "credential_id", "audit_status"}),
        (eligibility, "eligibility", {"student_id", "catalog_year", "catalog_eligible"}),
        (registry, "catalog registry", {"catalog_year", "graduate_by"}),
    ):
        missing = cols - set(frame.columns)
        if missing:
            raise SystemExit(f"{name} file is missing columns: {', '.join(sorted(missing))}")

    # ------------------------------------------------------------------
    # 1. Every eligible COMPLETE combination (the visibility layer)
    # ------------------------------------------------------------------
    complete = summary[
        summary["audit_status"].str.strip().str.upper().eq("COMPLETE")
    ].copy()

    eligible_pairs = eligibility[eligibility["catalog_eligible"].map(truthy)][
        ["student_id", "catalog_year"]
    ].drop_duplicates()

    combos = complete.merge(eligible_pairs, on=["student_id", "catalog_year"], how="inner")
    combos["credential_lineage"] = combos["credential_id"].map(derive_lineage)
    combos["catalog_rank"] = combos["catalog_year"].map(catalog_sort_key)

    graduate_by = dict(zip(registry["catalog_year"], registry["graduate_by"]))
    combos["catalog_graduate_by"] = combos["catalog_year"].map(graduate_by).fillna("")

    combos_out = combos.drop(columns=["catalog_rank"]).sort_values(
        ["student_id", "credential_lineage", "catalog_year"], kind="mergesort"
    )
    combos_out.to_csv(OUTPUT_DIR / "all_completing_combinations.csv", index=False)

    # ------------------------------------------------------------------
    # 2. Countable selection: one per (student, lineage), LATEST catalog
    # ------------------------------------------------------------------
    selected = (
        combos.sort_values(
            ["student_id", "credential_lineage", "catalog_rank"],
            ascending=[True, True, False],
            kind="mergesort",
        )
        .drop_duplicates(subset=["student_id", "credential_lineage"], keep="first")
        .copy()
    )

    # How many catalog years completed this lineage (visibility metric)
    completing_counts = (
        combos.groupby(["student_id", "credential_lineage"])["catalog_year"]
        .nunique()
        .rename("completing_catalog_count")
        .reset_index()
    )
    selected = selected.merge(completing_counts, on=["student_id", "credential_lineage"], how="left")

    selected = selected.drop(columns=["catalog_rank"]).sort_values(
        ["student_id", "credential_lineage"], kind="mergesort"
    )

    # ------------------------------------------------------------------
    # 3. Deadline priority: selected awards on a catalog nearing death
    #    (computed BEFORE writing selected_awards.csv so the column
    #    persists in both outputs)
    # ------------------------------------------------------------------
    def days_until(value: str) -> int | None:
        try:
            deadline = date.fromisoformat(str(value).strip())
        except ValueError:
            return None
        return (deadline - date.today()).days

    selected["days_until_graduate_by"] = selected["catalog_graduate_by"].map(days_until)

    selected.to_csv(OUTPUT_DIR / "selected_awards.csv", index=False)

    deadline_review = selected[
        selected["days_until_graduate_by"].notna()
        & (selected["days_until_graduate_by"] <= DEADLINE_WARNING_DAYS)
    ].sort_values("days_until_graduate_by", kind="mergesort")

    deadline_review.to_csv(OUTPUT_DIR / "deadline_priority_review.csv", index=False)

    # ------------------------------------------------------------------
    # 4. Aggregates for comparison against published counts
    # ------------------------------------------------------------------
    counts = (
        selected.groupby(["credential_lineage", "catalog_year"])
        .size()
        .rename("selected_award_count")
        .reset_index()
        .sort_values(["credential_lineage", "catalog_year"], kind="mergesort")
    )
    counts.to_csv(OUTPUT_DIR / "award_counts_by_lineage.csv", index=False)

    # ------------------------------------------------------------------
    # Console report (aggregates only -- FERPA-safe to share)
    # ------------------------------------------------------------------
    print("=" * 100)
    print("MAXIMUM-AWARD SELECTION REPORT")
    print("=" * 100)
    print(f"Eligible COMPLETE combinations (all catalogs):  {len(combos):,}")
    print(f"Selected countable awards (1 per lineage):      {len(selected):,}")
    print(f"Distinct students with at least one award:      {selected['student_id'].nunique():,}")
    print(f"Distinct credential lineages awarded:           {selected['credential_lineage'].nunique():,}")
    print(f"Awards where multiple catalogs completed:       {(selected['completing_catalog_count'] > 1).sum():,}")
    print()
    print("Selected awards by winning catalog year:")
    print(selected["catalog_year"].value_counts().sort_index().to_string())
    print()
    print(f"DEADLINE PRIORITY (graduate_by within {DEADLINE_WARNING_DAYS} days): "
          f"{len(deadline_review):,} awards")
    if not deadline_review.empty:
        print(deadline_review.groupby("catalog_year").size().to_string())
    print()
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
