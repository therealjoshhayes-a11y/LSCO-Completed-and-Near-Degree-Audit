from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


SUMMARY_PATH = Path(
    "data/processed/full_actual_audit/full_actual_credential_summary.csv"
)

OUTPUT_DIR = Path(
    "data/processed/full_actual_audit/quick_counts"
)


def lineage_from_credential_id(credential_id: str) -> str:
    """
    Collapse catalog-year variants into one credential lineage.

    Examples:
        PROCESS_OPERATING_TECHNOLOGY_2021
        PROCESS_OPERATING_TECHNOLOGY_2022
        -> PROCESS_OPERATING_TECHNOLOGY
    """
    value = str(credential_id).strip().upper()
    return re.sub(r"_(2021|2022|2023|2024|2025)$", "", value)


def main() -> None:
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Missing summary file: {SUMMARY_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    columns = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "catalog_eligible",
        "eligibility_reason",
    ]

    complete_frames: list[pd.DataFrame] = []

    for chunk in pd.read_csv(
        SUMMARY_PATH,
        usecols=columns,
        dtype=str,
        keep_default_na=False,
        chunksize=250_000,
    ):
        complete = chunk.loc[
            chunk["audit_status"].str.upper().eq("COMPLETE")
        ].copy()

        if not complete.empty:
            complete_frames.append(complete)

    if not complete_frames:
        raise RuntimeError("No COMPLETE rows found.")

    complete = pd.concat(complete_frames, ignore_index=True)

    complete["credential_lineage"] = complete["credential_id"].map(
        lineage_from_credential_id
    )

    # Raw COMPLETE rows by catalog year.
    raw_by_catalog = (
        complete.groupby("catalog_year", as_index=False)
        .agg(
            complete_rows=("student_id", "size"),
            affected_students=("student_id", "nunique"),
            credential_ids=("credential_id", "nunique"),
            credential_lineages=("credential_lineage", "nunique"),
        )
        .sort_values("catalog_year")
    )

    # Collapse multiple catalog-year COMPLETE records for the same
    # student and credential lineage.
    lineage_completions = (
        complete.sort_values(
            [
                "student_id",
                "credential_lineage",
                "catalog_year",
                "award_term_sort",
            ]
        )
        .drop_duplicates(
            subset=["student_id", "credential_lineage"],
            keep="first",
        )
    )

    # Detected completions by lineage.
    by_lineage = (
        lineage_completions.groupby(
            "credential_lineage",
            as_index=False,
        )
        .agg(
            detected_completions=("student_id", "size"),
            affected_students=("student_id", "nunique"),
            catalog_years_represented=("catalog_year", "nunique"),
            first_catalog_year=("catalog_year", "min"),
            last_catalog_year=("catalog_year", "max"),
        )
        .sort_values(
            ["detected_completions", "credential_lineage"],
            ascending=[False, True],
        )
    )

    # Assign each collapsed lineage completion to the catalog year
    # retained during collapse.
    collapsed_by_catalog = (
        lineage_completions.groupby(
            "catalog_year",
            as_index=False,
        )
        .agg(
            detected_lineage_completions=("student_id", "size"),
            affected_students=("student_id", "nunique"),
            credential_lineages=("credential_lineage", "nunique"),
        )
        .sort_values("catalog_year")
    )

    overall = pd.DataFrame(
        [
            {
                "raw_complete_rows": len(complete),
                "unique_students_with_complete": complete[
                    "student_id"
                ].nunique(),
                "detected_student_lineage_completions": len(
                    lineage_completions
                ),
                "unique_credential_lineages": complete[
                    "credential_lineage"
                ].nunique(),
            }
        ]
    )

    overall.to_csv(
        OUTPUT_DIR / "complete_counts_overall.csv",
        index=False,
    )

    raw_by_catalog.to_csv(
        OUTPUT_DIR / "complete_rows_by_catalog_year.csv",
        index=False,
    )

    collapsed_by_catalog.to_csv(
        OUTPUT_DIR / "detected_completions_by_catalog_year.csv",
        index=False,
    )

    by_lineage.to_csv(
        OUTPUT_DIR / "detected_completions_by_lineage.csv",
        index=False,
    )

    print("=" * 110)
    print("COMPLETE CREDENTIAL QUICK COUNT")
    print("=" * 110)

    print("\nOVERALL")
    print(overall.to_string(index=False))

    print("\nRAW COMPLETE ROWS BY CATALOG YEAR")
    print(raw_by_catalog.to_string(index=False))

    print("\nCOLLAPSED DETECTED COMPLETIONS BY CATALOG YEAR")
    print(collapsed_by_catalog.to_string(index=False))

    print("\nDETECTED COMPLETIONS BY CREDENTIAL LINEAGE")
    print(by_lineage.to_string(index=False))

    print(f"\nOutputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()