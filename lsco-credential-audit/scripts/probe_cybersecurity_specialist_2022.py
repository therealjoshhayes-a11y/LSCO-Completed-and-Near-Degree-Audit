from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIREMENTS = Path(
    "data/processed/catalogs/requirements_master_multiyear.csv"
)

VALIDATION = Path(
    "data/interim/catalogs/requirement_total_validation.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / (
    "cybersecurity_specialist_2022_probe_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_SUMMARY = OUTPUT_DIR / "FERPA_SAFE_Cybersecurity_Specialist_Year_Summary.csv"
SAFE_REQUIREMENTS = OUTPUT_DIR / "FERPA_SAFE_Cybersecurity_Specialist_Requirements.csv"
SAFE_DIFFS = OUTPUT_DIR / "FERPA_SAFE_Cybersecurity_Specialist_Course_Diffs.csv"
SAFE_VALIDATION = OUTPUT_DIR / "FERPA_SAFE_Cybersecurity_Specialist_Validation.csv"


TARGET_PATTERN = "CYBERSECURITY_SPECIALIST"


def norm(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def main() -> None:
    for path in (REQUIREMENTS, VALIDATION):
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    val = pd.read_csv(
        VALIDATION,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "credit_hours",
        "rule_type",
        "option_type",
        "option_value",
    }

    missing = required_columns - set(req.columns)

    if missing:
        raise RuntimeError(
            "Requirements master missing columns: "
            + ", ".join(sorted(missing))
        )

    cyber = req[
        req["credential_id"]
        .astype(str)
        .str.upper()
        .str.contains(TARGET_PATTERN, regex=False)
    ].copy()

    if cyber.empty:
        raise RuntimeError(
            "No Cybersecurity Specialist credentials found."
        )

    cyber["credit_hours_num"] = pd.to_numeric(
        cyber["credit_hours"],
        errors="coerce",
    )

    one_per_requirement = (
        cyber.sort_values(
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
            executable_hours=("credit_hours_num", "sum"),
            exact_count=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("EXACT").sum()
                ),
            ),
            any_n_count=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("ANY_N").sum()
                ),
            ),
            elective_count=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("ELECTIVE").sum()
                ),
            ),
            core_bucket_count=(
                "rule_type",
                lambda s: int(
                    s.astype(str).str.upper().eq("CORE_BUCKET").sum()
                ),
            ),
        )
        .reset_index()
        .sort_values("catalog_year", kind="mergesort")
    )

    detail_columns = [
        column
        for column in [
            "catalog_year",
            "credential_id",
            "credential_title",
            "semester_label",
            "semester_name",
            "requirement_id",
            "requirement_name",
            "rule_type",
            "min_required",
            "credit_hours",
            "option_type",
            "option_value",
            "option_group",
            "source_note",
            "repair_note",
        ]
        if column in cyber.columns
    ]

    detail = (
        cyber[detail_columns]
        .drop_duplicates()
        .sort_values(
            [
                column
                for column in [
                    "catalog_year",
                    "credential_id",
                    "semester_label",
                    "semester_name",
                    "requirement_id",
                    "option_group",
                    "option_value",
                ]
                if column in detail_columns
            ],
            kind="mergesort",
        )
    )

    course_rows = cyber[
        cyber["option_type"]
        .astype(str)
        .str.upper()
        .eq("COURSE")
    ].copy()

    course_rows["course_code"] = course_rows["option_value"].map(norm)

    course_sets = {
        catalog_year: set(
            group["course_code"]
            .dropna()
            .astype(str)
            .tolist()
        )
        for catalog_year, group in course_rows.groupby("catalog_year")
    }

    diff_rows = []

    catalog_years = sorted(course_sets)

    for left_year in catalog_years:
        for right_year in catalog_years:
            if left_year >= right_year:
                continue

            left_only = sorted(
                course_sets[left_year] - course_sets[right_year]
            )

            right_only = sorted(
                course_sets[right_year] - course_sets[left_year]
            )

            for course in left_only:
                diff_rows.append(
                    {
                        "comparison": f"{left_year} vs {right_year}",
                        "side": left_year,
                        "course_code": course,
                        "difference_type": "ONLY_IN_LEFT_YEAR",
                    }
                )

            for course in right_only:
                diff_rows.append(
                    {
                        "comparison": f"{left_year} vs {right_year}",
                        "side": right_year,
                        "course_code": course,
                        "difference_type": "ONLY_IN_RIGHT_YEAR",
                    }
                )

    diffs = pd.DataFrame(diff_rows)

    validation = val[
        val["credential_id"]
        .astype(str)
        .str.upper()
        .str.contains(TARGET_PATTERN, regex=False)
    ].copy()

    validation = validation.sort_values(
        ["catalog_year", "validation_level"],
        kind="mergesort",
    )

    summary.to_csv(SAFE_SUMMARY, index=False)
    detail.to_csv(SAFE_REQUIREMENTS, index=False)
    diffs.to_csv(SAFE_DIFFS, index=False)
    validation.to_csv(SAFE_VALIDATION, index=False)

    print("=" * 100)
    print("CYBERSECURITY SPECIALIST 2022 PROBE")
    print("=" * 100)
    print(summary.to_string(index=False))
    print()
    print(f"Summary: {SAFE_SUMMARY}")
    print(f"Requirements: {SAFE_REQUIREMENTS}")
    print(f"Course diffs: {SAFE_DIFFS}")
    print(f"Validation: {SAFE_VALIDATION}")
    print()
    print("UPLOAD ALL FOUR FERPA-SAFE CSV FILES.")
    print("CYBERSECURITY PROBE GATE: PASSED")


if __name__ == "__main__":
    main()
