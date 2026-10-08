from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# FINALIZE OFFICIAL-AWARD SCREENING WITH TWO GOVERNED HUMAN DECISIONS
# ======================================================================================
#
# This script DOES NOT rerun the degree audit.
# It reads the already-produced 7,298-row COMPLETE screening product and applies
# only the two equivalency decisions explicitly approved by Joshua Hayes.
#
# GOVERNED HUMAN DECISION
# Authorized by: Joshua Hayes
# Decision: Official award key AAS_BSMT / ASBU / AAS suppresses only the
#           BUSINESS_MANAGEMENT audit suppression family.
# Basis: Banner program code AAS_BSMT + AAS award type; approved 2026-10-08.
# Do not alter without renewed review.
#
# GOVERNED HUMAN DECISION
# Authorized by: Joshua Hayes
# Decision: Official award key CERT1_PTAA / PTAA / CERT1 suppresses the
#           PROCESS_TECHNOLOGY audit suppression family.
# Basis: Approved equivalency of Process Tech Academy Certificate to the
#        Process Technology certificate family on 2026-10-08.
# Do not alter without renewed review.
#
# Two other previously unresolved keys remain NON-SUPPRESSING in this run:
#   * AAT_AATP / AATP / AAT
#   * CERT1_CJCC / CJCC / CERT1
#
# Run from repository root:
#   python -u .\scripts\finalize_official_award_screening.py
#
# Existing screening outputs are not overwritten.


SOURCE_DIR = Path(
    "data/processed/reporting/official_award_screening_20261008_085004"
)

COMPLETE_SCREEN = (
    SOURCE_DIR
    / "RESTRICTED_complete_combinations_official_award_screen.csv"
)

CANONICAL_OFFICIAL = (
    SOURCE_DIR
    / "RESTRICTED_canonical_official_awards_with_mapping.csv"
)

SOURCE_CROSSWALK = (
    SOURCE_DIR
    / "FERPA_SAFE_official_award_suppression_crosswalk.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"official_award_screening_final_{RUN_STAMP}"


APPROVED = {
    ("AAS_BSMT", "ASBU", "AAS"): "BUSINESS_MANAGEMENT",
    ("CERT1_PTAA", "PTAA", "CERT1"): "PROCESS_TECHNOLOGY",
}

APPROVAL_NOTE = {
    ("AAS_BSMT", "ASBU", "AAS"):
        "GOVERNED HUMAN DECISION 2026-10-08: suppress BUSINESS_MANAGEMENT only.",
    ("CERT1_PTAA", "PTAA", "CERT1"):
        "GOVERNED HUMAN DECISION 2026-10-08: Process Tech Academy -> PROCESS_TECHNOLOGY.",
}

EXPECTED_OFFICIAL_ROWS_BY_KEY = {
    ("AAS_BSMT", "ASBU", "AAS"): 1,
    ("CERT1_PTAA", "PTAA", "CERT1"): 8,
}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def clean(value: object) -> str:
    return str(value).strip().upper()


def key_tuple(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    return list(
        zip(
            frame["Curr1ProgramCode"].map(clean),
            frame["Major1Code"].map(clean),
            frame["DegreeCode"].map(clean),
        )
    )


def joined(values) -> str:
    return " | ".join(
        sorted(
            {
                str(v).strip()
                for v in values
                if str(v).strip()
            }
        )
    )


def main() -> None:
    for path in (
        COMPLETE_SCREEN,
        CANONICAL_OFFICIAL,
        SOURCE_CROSSWALK,
    ):
        require(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)

    screened = pd.read_csv(
        COMPLETE_SCREEN,
        dtype=str,
        low_memory=False,
    ).fillna("")

    official = pd.read_csv(
        CANONICAL_OFFICIAL,
        dtype=str,
        low_memory=False,
    ).fillna("")

    crosswalk = pd.read_csv(
        SOURCE_CROSSWALK,
        dtype=str,
        low_memory=False,
    ).fillna("")

    # ------------------------------------------------------------------
    # Validate the source screening products before touching anything.
    # ------------------------------------------------------------------
    if len(screened) != 7_298:
        raise RuntimeError(
            "Source COMPLETE screening row count changed: "
            f"{len(screened):,} != 7,298"
        )

    source_suppressed = int(
        screened["official_award_screen_status"]
        .eq("ALREADY_OFFICIALLY_AWARDED")
        .sum()
    )

    source_unsuppressed = int(
        screened["official_award_screen_status"]
        .eq("NOT_OFFICIALLY_AWARDED")
        .sum()
    )

    if (source_suppressed, source_unsuppressed) != (5_875, 1_423):
        raise RuntimeError(
            "Source screening counts changed: "
            f"suppressed={source_suppressed:,}, "
            f"unsuppressed={source_unsuppressed:,}"
        )

    # ------------------------------------------------------------------
    # Apply the two approved official-award key mappings.
    # ------------------------------------------------------------------
    official_keys = key_tuple(official)

    for key, family in APPROVED.items():
        mask = pd.Series(
            [candidate == key for candidate in official_keys],
            index=official.index,
        )

        observed_rows = int(mask.sum())
        expected_rows = EXPECTED_OFFICIAL_ROWS_BY_KEY[key]

        if observed_rows != expected_rows:
            raise RuntimeError(
                f"Official key {key} row count changed: "
                f"{observed_rows:,} != {expected_rows:,}"
            )

        official.loc[mask, "mapping_status"] = (
            "MAPPED_GOVERNED_HUMAN_DECISION"
        )
        official.loc[mask, "suppression_family"] = family
        official.loc[mask, "mapping_note"] = APPROVAL_NOTE[key]

    # Preserve the two explicitly non-suppressing decisions.
    remain_non_suppressing = {
        ("AAT_AATP", "AATP", "AAT"),
        ("CERT1_CJCC", "CJCC", "CERT1"),
    }

    for key in remain_non_suppressing:
        mask = pd.Series(
            [candidate == key for candidate in official_keys],
            index=official.index,
        )
        if mask.any():
            official.loc[mask, "mapping_status"] = (
                "REVIEWED_NON_SUPPRESSING_20261008"
            )
            official.loc[mask, "suppression_family"] = ""

    # ------------------------------------------------------------------
    # Update the FERPA-safe key crosswalk accordingly.
    # ------------------------------------------------------------------
    crosswalk_keys = key_tuple(crosswalk)

    for key, family in APPROVED.items():
        mask = pd.Series(
            [candidate == key for candidate in crosswalk_keys],
            index=crosswalk.index,
        )

        if int(mask.sum()) != 1:
            raise RuntimeError(
                f"Expected exactly one crosswalk row for approved key {key}; "
                f"found {int(mask.sum())}"
            )

        crosswalk.loc[mask, "mapping_status"] = (
            "MAPPED_GOVERNED_HUMAN_DECISION"
        )
        crosswalk.loc[mask, "suppression_family"] = family
        crosswalk.loc[mask, "mapping_note"] = APPROVAL_NOTE[key]

    for key in remain_non_suppressing:
        mask = pd.Series(
            [candidate == key for candidate in crosswalk_keys],
            index=crosswalk.index,
        )
        if mask.any():
            crosswalk.loc[mask, "mapping_status"] = (
                "REVIEWED_NON_SUPPRESSING_20261008"
            )
            crosswalk.loc[mask, "suppression_family"] = ""

    # ------------------------------------------------------------------
    # Build only the newly approved student + family evidence.
    # ------------------------------------------------------------------
    approved_official = official[
        official["mapping_status"]
        .eq("MAPPED_GOVERNED_HUMAN_DECISION")
        & official["suppression_family"].ne("")
    ].copy()

    evidence = (
        approved_official.groupby(
            ["ID", "suppression_family"],
            dropna=False,
        )
        .agg(
            governed_official_award_count=("StudGradTerm", "size"),
            governed_official_first_grad_term=("StudGradTerm", "min"),
            governed_official_last_grad_term=("StudGradTerm", "max"),
            governed_official_major_codes=("Major1Code", joined),
            governed_official_degree_codes=("DegreeCode", joined),
        )
        .reset_index()
        .rename(columns={"ID": "student_id"})
    )

    if evidence.duplicated(
        ["student_id", "suppression_family"]
    ).any():
        raise RuntimeError(
            "Governed official-award evidence is not unique at "
            "student + suppression_family grain."
        )

    # ------------------------------------------------------------------
    # Apply ONLY to rows not already suppressed.
    # ------------------------------------------------------------------
    finalized = screened.merge(
        evidence,
        on=["student_id", "suppression_family"],
        how="left",
        validate="many_to_one",
    )

    if len(finalized) != len(screened):
        raise RuntimeError(
            "Governed evidence merge changed COMPLETE row count."
        )

    # Left-merge nonmatches are NaN, not empty strings. Using .ne("")
    # would incorrectly treat NaN as evidence and suppress unrelated families.
    has_governed_evidence = (
        finalized["governed_official_award_count"].notna()
    )

    newly_suppressed_mask = (
        finalized["official_award_screen_status"]
        .eq("NOT_OFFICIALLY_AWARDED")
        & has_governed_evidence
    )

    finalized["official_award_screen_status_before_governed"] = (
        finalized["official_award_screen_status"]
    )

    finalized.loc[
        newly_suppressed_mask,
        "official_award_screen_status",
    ] = "ALREADY_OFFICIALLY_AWARDED"

    finalized["official_award_screen_basis"] = (
        "SOURCE_SUPPORTED_MAPPING"
    )

    finalized.loc[
        finalized[
            "official_award_screen_status_before_governed"
        ].eq("ALREADY_OFFICIALLY_AWARDED"),
        "official_award_screen_basis",
    ] = "SOURCE_SUPPORTED_MAPPING"

    finalized.loc[
        newly_suppressed_mask,
        "official_award_screen_basis",
    ] = "GOVERNED_HUMAN_DECISION_20261008"

    # ------------------------------------------------------------------
    # Exact reconciliation.
    # ------------------------------------------------------------------
    final_suppressed = finalized[
        finalized["official_award_screen_status"]
        .eq("ALREADY_OFFICIALLY_AWARDED")
    ].copy()

    final_unsuppressed = finalized[
        finalized["official_award_screen_status"]
        .eq("NOT_OFFICIALLY_AWARDED")
    ].copy()

    if len(final_suppressed) + len(final_unsuppressed) != len(finalized):
        raise RuntimeError(
            "Final suppressed + unsuppressed does not equal COMPLETE universe."
        )

    delta = int(newly_suppressed_mask.sum())

    if len(final_suppressed) != source_suppressed + delta:
        raise RuntimeError(
            "Final suppressed count failed delta reconciliation."
        )

    if len(final_unsuppressed) != source_unsuppressed - delta:
        raise RuntimeError(
            "Final unsuppressed count failed delta reconciliation."
        )

    # No row may be newly suppressed outside the two approved families.
    approved_families = set(APPROVED.values())

    unexpected = finalized.loc[
        newly_suppressed_mask
        & ~finalized["suppression_family"].isin(approved_families)
    ]

    if not unexpected.empty:
        raise RuntimeError(
            "A row outside the two approved families was newly suppressed."
        )

    # ------------------------------------------------------------------
    # Write new final products; do not overwrite the original screen.
    # ------------------------------------------------------------------
    official.to_csv(
        OUTPUT_DIR
        / "RESTRICTED_canonical_official_awards_final_mapping.csv",
        index=False,
    )

    crosswalk.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_official_award_suppression_crosswalk_FINAL.csv",
        index=False,
    )

    finalized.to_csv(
        OUTPUT_DIR
        / "RESTRICTED_complete_combinations_official_award_screen_FINAL.csv",
        index=False,
    )

    final_suppressed.to_csv(
        OUTPUT_DIR
        / "RESTRICTED_already_officially_awarded_complete_combinations_FINAL.csv",
        index=False,
    )

    final_unsuppressed.to_csv(
        OUTPUT_DIR
        / "RESTRICTED_unsuppressed_complete_combinations_FINAL.csv",
        index=False,
    )

    newly_suppressed = finalized.loc[
        newly_suppressed_mask
    ].copy()

    newly_suppressed.to_csv(
        OUTPUT_DIR
        / "RESTRICTED_newly_suppressed_by_governed_decisions.csv",
        index=False,
    )

    # FERPA-safe impact by approved decision.
    decision_impact = (
        newly_suppressed.groupby(
            "suppression_family",
            dropna=False,
        )
        .agg(
            newly_suppressed_complete_combinations=(
                "student_id",
                "size",
            ),
            affected_students=(
                "student_id",
                "nunique",
            ),
            credential_ids=(
                "credential_id",
                joined,
            ),
            catalog_years=(
                "catalog_year",
                joined,
            ),
        )
        .reset_index()
    )

    decision_impact.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_governed_decision_impact.csv",
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {"metric": "complete_combinations", "value": len(finalized)},
            {"metric": "source_suppressed_combinations", "value": source_suppressed},
            {"metric": "source_unsuppressed_combinations", "value": source_unsuppressed},
            {"metric": "newly_suppressed_by_governed_decisions", "value": delta},
            {"metric": "final_suppressed_combinations", "value": len(final_suppressed)},
            {"metric": "final_unsuppressed_combinations", "value": len(final_unsuppressed)},
            {"metric": "governed_mapping_keys_applied", "value": len(APPROVED)},
            {"metric": "reviewed_non_suppressing_keys", "value": len(remain_non_suppressing)},
        ]
    )

    metrics.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_official_award_screen_FINAL_metrics.csv",
        index=False,
    )

    print("=" * 100)
    print("OFFICIAL AWARD SCREENING — FINALIZED")
    print("=" * 100)
    print("No degree-audit computation was rerun.")
    print()
    print(f"COMPLETE combinations:                     {len(finalized):,}")
    print(f"Previously suppressed:                     {source_suppressed:,}")
    print(f"Previously unsuppressed:                   {source_unsuppressed:,}")
    print(f"Newly suppressed by approved decisions:    {delta:,}")
    print(f"Final suppressed:                          {len(final_suppressed):,}")
    print(f"Final unsuppressed:                        {len(final_unsuppressed):,}")
    print()
    print("GOVERNED DECISION IMPACT")
    if decision_impact.empty:
        print("<none>")
    else:
        print(decision_impact.to_string(index=False))
    print()
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
