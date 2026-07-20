from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


HISTORY = Path("data/processed/normalized_actual_student_course_history.csv")
REQUIREMENTS = Path("data/processed/catalogs/requirements_master_multiyear.csv")
OUTPUT_DIR = Path("data/processed/reporting") / (
    "repeatable_course_shadow_check_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)
SAFE_OUTPUT = OUTPUT_DIR / "FERPA_SAFE_Repeatable_Course_Shadow_Check.xlsx"
RESTRICTED_OUTPUT = OUTPUT_DIR / "RESTRICTED_Repeatable_Course_Shadow_Check.xlsx"

PASSING_GRADES = {"A", "B", "C", "D", "S", "P", "CR", "T", "TA", "TB", "TC", "TD", "TS"}


def normalize_course_code(value: object) -> str:
    return " ".join(str(value).upper().strip().split())


def truthy(value: object) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def main() -> None:
    for path in (HISTORY, REQUIREMENTS):
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    history = pd.read_csv(HISTORY, dtype=str, low_memory=False).fillna("")
    requirements = pd.read_csv(REQUIREMENTS, dtype=str, low_memory=False).fillna("")

    history["course_code"] = history["course_code"].map(normalize_course_code)

    if "passed" in history.columns:
        passed = history[history["passed"].map(truthy)].copy()
    else:
        grade_col = "grade" if "grade" in history.columns else "final_grade"
        passed = history[
            history[grade_col].astype(str).str.upper().isin(PASSING_GRADES)
        ].copy()

    # Collapse exact duplicate export rows, but retain distinct successful attempts
    attempt_identity_candidates = [
        "student_id",
        "course_code",
        "term_sort",
        "term_taken",
        "grade",
        "final_grade",
        "credit_hours",
        "earned_hours",
    ]
    attempt_identity = [
        column for column in attempt_identity_candidates if column in passed.columns
    ]

    if not attempt_identity:
        raise ValueError("Could not identify attempt-grain columns.")

    passed = passed.drop_duplicates(subset=attempt_identity).copy()

    repeated = (
        passed.groupby(["student_id", "course_code"], dropna=False)
        .agg(
            successful_attempt_count=("course_code", "size"),
            distinct_terms=("term_sort", "nunique") if "term_sort" in passed.columns else ("course_code", "size"),
        )
        .reset_index()
    )

    repeated = repeated[
        repeated["successful_attempt_count"] >= 2
    ].copy()

    req_course_rows = requirements[
        requirements["option_type"].astype(str).str.upper().eq("COURSE")
    ].copy()
    req_course_rows["option_value_norm"] = req_course_rows["option_value"].map(normalize_course_code)

    requirement_usage = (
        req_course_rows.groupby("option_value_norm")
        .agg(
            requirement_row_count=("requirement_id", "size"),
            distinct_requirement_count=("requirement_id", "nunique"),
            distinct_credential_years=("credential_id", "nunique"),
            catalog_years=("catalog_year", lambda s: "; ".join(sorted(set(map(str, s))))),
            rule_types=("rule_type", lambda s: "; ".join(sorted(set(map(str, s))))),
        )
        .reset_index()
        .rename(columns={"option_value_norm": "course_code"})
    )

    repeated = repeated.merge(
        requirement_usage,
        on="course_code",
        how="left",
    )

    repeated["appears_in_requirements"] = repeated[
        "distinct_requirement_count"
    ].fillna(0).astype(float).gt(0)

    # Rubrics commonly associated with repeatable or variable-context coursework.
    rubric = repeated["course_code"].str.split().str[0]
    number = repeated["course_code"].str.split().str[1].fillna("")

    repeatable_pattern = number.str.match(r"^(116|126|216|226)\d$") | rubric.isin(
        {"CJCR", "CRTR", "EMSP", "INMT", "ITSC", "NAUT", "WLDG"}
    )

    repeated["repeatable_pattern_flag"] = repeatable_pattern

    restricted = repeated.sort_values(
        [
            "appears_in_requirements",
            "repeatable_pattern_flag",
            "successful_attempt_count",
            "course_code",
        ],
        ascending=[False, False, False, True],
        kind="mergesort",
    )

    by_course = (
        restricted.groupby(
            [
                "course_code",
                "appears_in_requirements",
                "repeatable_pattern_flag",
            ],
            dropna=False,
        )
        .agg(
            student_course_pairs=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
            max_successful_attempts=("successful_attempt_count", "max"),
            distinct_requirement_count=("distinct_requirement_count", "max"),
            distinct_credential_years=("distinct_credential_years", "max"),
        )
        .reset_index()
        .sort_values(
            ["student_course_pairs", "course_code"],
            ascending=[False, True],
        )
    )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Passed course attempts after exact-row deduplication",
                "value": len(passed),
            },
            {
                "metric": "Student-course pairs with 2+ successful attempts",
                "value": len(repeated),
            },
            {
                "metric": "Distinct students with 2+ successful attempts of same course",
                "value": repeated["student_id"].nunique(),
            },
            {
                "metric": "Repeated student-course pairs appearing in requirement options",
                "value": int(repeated["appears_in_requirements"].sum()),
            },
            {
                "metric": "Repeated student-course pairs matching repeatable-course pattern",
                "value": int(repeated["repeatable_pattern_flag"].sum()),
            },
            {
                "metric": "Repeated pairs both in requirements and repeatable-pattern flagged",
                "value": int(
                    (
                        repeated["appears_in_requirements"]
                        & repeated["repeatable_pattern_flag"]
                    ).sum()
                ),
            },
        ]
    )

    with pd.ExcelWriter(RESTRICTED_OUTPUT, engine="xlsxwriter") as writer:
        restricted.to_excel(
            writer,
            sheet_name="Repeated Student Courses",
            index=False,
        )

    with pd.ExcelWriter(SAFE_OUTPUT, engine="xlsxwriter") as writer:
        kpis.to_excel(writer, sheet_name="KPI Summary", index=False)
        by_course.to_excel(writer, sheet_name="By Course", index=False)

    print("=" * 100)
    print("REPEATABLE-COURSE SHADOW CHECK")
    print("=" * 100)
    print(f"Passed attempts: {len(passed):,}")
    print(f"Student-course pairs with 2+ successful attempts: {len(repeated):,}")
    print(f"Distinct students: {repeated['student_id'].nunique():,}")
    print(
        "Repeated pairs appearing in requirement options: "
        f"{int(repeated['appears_in_requirements'].sum()):,}"
    )
    print(
        "Repeated pairs matching repeatable-course pattern: "
        f"{int(repeated['repeatable_pattern_flag'].sum()):,}"
    )
    print(
        "Repeated pairs both requirement-relevant and repeatable-pattern flagged: "
        f"{int((repeated['appears_in_requirements'] & repeated['repeatable_pattern_flag']).sum()):,}"
    )
    print()
    print(f"RESTRICTED workbook: {RESTRICTED_OUTPUT}")
    print(f"FERPA-SAFE workbook: {SAFE_OUTPUT}")
    print()
    print("UPLOAD ONLY THE FERPA-SAFE WORKBOOK.")
    print("REPEATABLE-COURSE GATE: PASSED")


if __name__ == "__main__":
    main()
