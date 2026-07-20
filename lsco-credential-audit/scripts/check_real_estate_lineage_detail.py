from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIREMENTS = Path("data/processed/catalogs/requirements_master_multiyear.csv")
OUTPUT_DIR = Path("data/processed/reporting") / (
    "real_estate_lineage_detail_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_SUMMARY = OUTPUT_DIR / "FERPA_SAFE_Real_Estate_Lineage_Summary.csv"
SAFE_REQUIREMENTS = OUTPUT_DIR / "FERPA_SAFE_Real_Estate_Lineage_Requirements.csv"
SAFE_COURSE_SETS = OUTPUT_DIR / "FERPA_SAFE_Real_Estate_Lineage_Course_Sets.csv"


def normalize(value: object) -> str:
    return " ".join(str(value).upper().strip().split())


def main() -> None:
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(REQUIREMENTS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    mask = (
        req["credential_id"]
        .astype(str)
        .str.upper()
        .str.contains("REAL_ESTATE_MANAGEMENT", regex=False)
    )

    real_estate = req[mask].copy()

    if real_estate.empty:
        raise ValueError("No Real Estate Management credential rows found.")

    real_estate["credit_hours_num"] = pd.to_numeric(
        real_estate["credit_hours"],
        errors="coerce",
    )

    # One row per requirement to prevent option-row multiplication.
    one_per_requirement = (
        real_estate.sort_values(
            ["catalog_year", "credential_id", "requirement_id"],
            kind="mergesort",
        )
        .drop_duplicates(
            ["catalog_year", "credential_id", "requirement_id"],
            keep="first",
        )
        .copy()
    )

    summary = (
        one_per_requirement.groupby(
            ["catalog_year", "credential_id"],
            dropna=False,
        )
        .agg(
            requirement_count=("requirement_id", "nunique"),
            inferred_total_hours=("credit_hours_num", "sum"),
            exact_requirements=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("EXACT").sum()
                ),
            ),
            any_n_requirements=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("ANY_N").sum()
                ),
            ),
            core_bucket_requirements=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("CORE_BUCKET").sum()
                ),
            ),
            elective_requirements=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("ELECTIVE").sum()
                ),
            ),
        )
        .reset_index()
        .sort_values("catalog_year", kind="mergesort")
    )

    requirements_detail_columns = [
        column
        for column in [
            "catalog_year",
            "credential_id",
            "credential_title",
            "requirement_id",
            "requirement_name",
            "semester_name",
            "rule_type",
            "min_required",
            "credit_hours",
            "option_type",
            "option_value",
            "option_group",
        ]
        if column in real_estate.columns
    ]

    requirements_detail = (
        real_estate[requirements_detail_columns]
        .drop_duplicates()
        .sort_values(
            [
                column
                for column in [
                    "catalog_year",
                    "credential_id",
                    "requirement_id",
                    "option_group",
                    "option_value",
                ]
                if column in requirements_detail_columns
            ],
            kind="mergesort",
        )
    )

    course_rows = real_estate[
        real_estate["option_type"]
        .astype(str)
        .str.upper()
        .eq("COURSE")
    ].copy()

    course_rows["course_code"] = course_rows["option_value"].map(normalize)

    course_sets = (
        course_rows.groupby(
            ["catalog_year", "credential_id"],
            dropna=False,
        )
        .agg(
            distinct_course_count=("course_code", "nunique"),
            course_set=(
                "course_code",
                lambda s: " | ".join(sorted(set(s))),
            ),
        )
        .reset_index()
        .sort_values("catalog_year", kind="mergesort")
    )

    summary.to_csv(SAFE_SUMMARY, index=False)
    requirements_detail.to_csv(SAFE_REQUIREMENTS, index=False)
    course_sets.to_csv(SAFE_COURSE_SETS, index=False)

    print("=" * 100)
    print("REAL ESTATE MANAGEMENT LINEAGE DETAIL")
    print("=" * 100)
    print(summary.to_string(index=False))
    print()
    print(f"Summary: {SAFE_SUMMARY}")
    print(f"Requirement detail: {SAFE_REQUIREMENTS}")
    print(f"Course sets: {SAFE_COURSE_SETS}")
    print()
    print("UPLOAD ALL THREE FERPA-SAFE CSV FILES.")
    print("REAL-ESTATE DETAIL GATE: PASSED")


if __name__ == "__main__":
    main()
