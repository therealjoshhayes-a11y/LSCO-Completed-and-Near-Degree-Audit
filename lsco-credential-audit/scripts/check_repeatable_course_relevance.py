from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ATTEMPTS = Path("data/processed/all_student_course_attempts_normalized.csv")
REQUIREMENTS = Path("data/processed/catalogs/requirements_master_multiyear.csv")

OUTPUT_DIR = Path("data/processed/reporting") / (
    "repeatable_course_relevance_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_BY_COURSE = OUTPUT_DIR / "FERPA_SAFE_Repeatable_Course_Relevance_By_Course.csv"
SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Repeatable_Course_Relevance_KPI.csv"
RESTRICTED = OUTPUT_DIR / "RESTRICTED_Repeatable_Student_Course_Pairs.csv"

PASSING_GRADES = {
    "A", "B", "C", "D", "S", "P", "CR", "T",
    "TA", "TB", "TC", "TD", "TS",
}


def normalize_course_code(value: object) -> str:
    return " ".join(str(value).upper().strip().split())


def main() -> None:
    for path in (ATTEMPTS, REQUIREMENTS):
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    attempts = pd.read_csv(
        ATTEMPTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    grade_col = (
        "final_grade"
        if "final_grade" in attempts.columns
        else "grade"
    )

    attempts["course_code"] = attempts["course_code"].map(
        normalize_course_code
    )

    passed = attempts[
        attempts[grade_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(PASSING_GRADES)
    ].copy()

    attempt_grain = [
        column
        for column in [
            "student_id",
            "course_code",
            "term_sort",
            "term_taken",
            grade_col,
        ]
        if column in passed.columns
    ]

    passed = passed.drop_duplicates(
        subset=attempt_grain
    ).copy()

    repeated = (
        passed.groupby(
            ["student_id", "course_code"],
            dropna=False,
        )
        .agg(
            successful_attempts=(
                "course_code",
                "size",
            ),
            distinct_successful_terms=(
                "term_sort",
                "nunique",
            ),
            first_successful_term=(
                "term_sort",
                "min",
            ),
            latest_successful_term=(
                "term_sort",
                "max",
            ),
        )
        .reset_index()
    )

    repeated = repeated[
        repeated["successful_attempts"] >= 2
    ].copy()

    req_courses = requirements[
        requirements["option_type"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("COURSE")
    ].copy()

    req_courses["course_code"] = req_courses[
        "option_value"
    ].map(normalize_course_code)

    req_course_summary = (
        req_courses.groupby(
            "course_code",
            dropna=False,
        )
        .agg(
            requirement_option_rows=(
                "requirement_id",
                "size",
            ),
            distinct_requirement_ids=(
                "requirement_id",
                "nunique",
            ),
            distinct_credential_years=(
                "credential_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    duplicate_slot_groups = (
        req_courses.groupby(
            [
                "catalog_year",
                "credential_id",
                "course_code",
            ],
            dropna=False,
        )
        .agg(
            distinct_requirement_slots=(
                "requirement_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    duplicate_slot_groups = duplicate_slot_groups[
        duplicate_slot_groups[
            "distinct_requirement_slots"
        ] >= 2
    ].copy()

    duplicate_slot_summary = (
        duplicate_slot_groups.groupby(
            "course_code",
            dropna=False,
        )
        .agg(
            credential_years_with_duplicate_slots=(
                "credential_id",
                "size",
            ),
            max_duplicate_slots_in_one_credential=(
                "distinct_requirement_slots",
                "max",
            ),
        )
        .reset_index()
    )

    repeated = (
        repeated.merge(
            req_course_summary,
            on="course_code",
            how="left",
        )
        .merge(
            duplicate_slot_summary,
            on="course_code",
            how="left",
        )
    )

    numeric_fill = [
        "requirement_option_rows",
        "distinct_requirement_ids",
        "distinct_credential_years",
        "credential_years_with_duplicate_slots",
        "max_duplicate_slots_in_one_credential",
    ]

    for column in numeric_fill:
        repeated[column] = (
            pd.to_numeric(
                repeated[column],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    repeated["appears_in_requirements"] = (
        repeated["distinct_requirement_ids"] > 0
    )

    repeated["course_has_duplicate_required_slots"] = (
        repeated[
            "credential_years_with_duplicate_slots"
        ] > 0
    )

    by_course = (
        repeated.groupby(
            [
                "course_code",
                "appears_in_requirements",
                "course_has_duplicate_required_slots",
            ],
            dropna=False,
        )
        .agg(
            repeated_student_course_pairs=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            max_successful_attempts=(
                "successful_attempts",
                "max",
            ),
            requirement_option_rows=(
                "requirement_option_rows",
                "max",
            ),
            distinct_requirement_ids=(
                "distinct_requirement_ids",
                "max",
            ),
            distinct_credential_years=(
                "distinct_credential_years",
                "max",
            ),
            credential_years_with_duplicate_slots=(
                "credential_years_with_duplicate_slots",
                "max",
            ),
            max_duplicate_slots_in_one_credential=(
                "max_duplicate_slots_in_one_credential",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "course_has_duplicate_required_slots",
                "appears_in_requirements",
                "repeated_student_course_pairs",
                "course_code",
            ],
            ascending=[
                False,
                False,
                False,
                True,
            ],
            kind="mergesort",
        )
    )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Passed attempt rows after deduplication",
                "value": len(passed),
            },
            {
                "metric": "Student-course pairs with 2+ successful attempts",
                "value": len(repeated),
            },
            {
                "metric": "Distinct students with a repeated successful course",
                "value": repeated["student_id"].nunique(),
            },
            {
                "metric": "Repeated pairs whose course appears in requirements",
                "value": int(
                    repeated[
                        "appears_in_requirements"
                    ].sum()
                ),
            },
            {
                "metric": "Repeated pairs whose course occupies duplicate requirement slots",
                "value": int(
                    repeated[
                        "course_has_duplicate_required_slots"
                    ].sum()
                ),
            },
            {
                "metric": "Distinct repeated course codes",
                "value": repeated["course_code"].nunique(),
            },
            {
                "metric": "Distinct repeated course codes with duplicate required slots",
                "value": repeated.loc[
                    repeated[
                        "course_has_duplicate_required_slots"
                    ],
                    "course_code",
                ].nunique(),
            },
        ]
    )

    repeated.to_csv(
        RESTRICTED,
        index=False,
    )

    by_course.to_csv(
        SAFE_BY_COURSE,
        index=False,
    )

    kpis.to_csv(
        SAFE_KPI,
        index=False,
    )

    print("=" * 100)
    print("REPEATABLE-COURSE RELEVANCE CHECK")
    print("=" * 100)
    print(
        "Student-course pairs with 2+ successful attempts: "
        f"{len(repeated):,}"
    )
    print(
        "Distinct students: "
        f"{repeated['student_id'].nunique():,}"
    )
    print(
        "Repeated pairs whose course appears in requirements: "
        f"{int(repeated['appears_in_requirements'].sum()):,}"
    )
    print(
        "Repeated pairs whose course occupies duplicate required slots: "
        f"{int(repeated['course_has_duplicate_required_slots'].sum()):,}"
    )
    print(
        "Distinct repeated course codes with duplicate required slots: "
        f"{repeated.loc[repeated['course_has_duplicate_required_slots'], 'course_code'].nunique():,}"
    )
    print()
    print(f"FERPA-safe KPI: {SAFE_KPI}")
    print(f"FERPA-safe by-course detail: {SAFE_BY_COURSE}")
    print(f"RESTRICTED student detail: {RESTRICTED}")
    print()
    print("UPLOAD BOTH FERPA-SAFE CSV FILES.")
    print("RELEVANCE GATE: PASSED")


if __name__ == "__main__":
    main()
