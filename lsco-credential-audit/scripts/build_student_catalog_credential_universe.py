from pathlib import Path

import pandas as pd


STUDENT_COURSES_PATH = Path("data/processed/normalized_actual_student_course_history.csv")
REQUIREMENTS_PATH = Path("data/processed/catalogs/requirements_master_multiyear.csv")
OUTPUT_PATH = Path("data/processed/student_catalog_credential_universe.csv")
QA_OUTPUT_PATH = Path("data/processed/student_catalog_credential_universe_qa.csv")


MIN_MATCHED_REQUIREMENTS = 1
MIN_OVERLAP_RATIO = 0.05


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not STUDENT_COURSES_PATH.exists():
        raise FileNotFoundError(STUDENT_COURSES_PATH)
    if not REQUIREMENTS_PATH.exists():
        raise FileNotFoundError(REQUIREMENTS_PATH)

    courses = pd.read_csv(STUDENT_COURSES_PATH, dtype=str, low_memory=False).fillna("")
    requirements = pd.read_csv(REQUIREMENTS_PATH, dtype=str, low_memory=False).fillna("")

    return courses, requirements


def build_course_requirement_index(requirements: pd.DataFrame) -> pd.DataFrame:
    course_reqs = requirements[
        requirements["option_type"].eq("COURSE")
        & requirements["option_value"].ne("")
    ].copy()

    cols = [
        "catalog_year",
        "credential_id",
        "credential_title",
        "requirement_id",
        "rule_type",
        "option_value",
    ]

    course_reqs = course_reqs[cols].drop_duplicates()
    course_reqs = course_reqs.rename(columns={"option_value": "course_code"})

    return course_reqs


def build_universe(courses: pd.DataFrame, requirements: pd.DataFrame) -> pd.DataFrame:
    student_courses = courses[["student_id", "course_code"]].drop_duplicates().copy()

    course_reqs = build_course_requirement_index(requirements)

    hits = student_courses.merge(
        course_reqs,
        on="course_code",
        how="inner",
    )

    matched = (
        hits.groupby(["student_id", "catalog_year", "credential_id", "credential_title"], dropna=False)
        .agg(
            matched_course_count=("course_code", "nunique"),
            matched_requirement_count=("requirement_id", "nunique"),
        )
        .reset_index()
    )

    req_totals = (
        requirements.groupby(["catalog_year", "credential_id"], dropna=False)
        .agg(
            total_requirement_count=("requirement_id", "nunique"),
            total_course_option_count=("option_value", lambda s: s[requirements.loc[s.index, "option_type"].eq("COURSE")].nunique()),
        )
        .reset_index()
    )

    universe = matched.merge(
        req_totals,
        on=["catalog_year", "credential_id"],
        how="left",
    )

    universe["requirement_overlap_ratio"] = (
        universe["matched_requirement_count"].astype(float)
        / universe["total_requirement_count"].replace(0, pd.NA).astype(float)
    ).fillna(0)

    universe["eligible_for_audit"] = (
        (universe["matched_requirement_count"] >= MIN_MATCHED_REQUIREMENTS)
        & (universe["requirement_overlap_ratio"] >= MIN_OVERLAP_RATIO)
    )

    universe["eligibility_reason"] = "Has direct course overlap with credential requirements"
    universe.loc[
        ~universe["eligible_for_audit"],
        "eligibility_reason",
    ] = "Below minimum direct course-overlap threshold"

    universe["catalog_eligibility_basis"] = "course-overlap-pruned mechanical audit universe"

    universe = universe.sort_values(
        [
            "student_id",
            "eligible_for_audit",
            "matched_requirement_count",
            "requirement_overlap_ratio",
            "catalog_year",
            "credential_id",
        ],
        ascending=[True, False, False, False, False, True],
        kind="mergesort",
    ).copy()

    universe["student_universe_rank"] = universe.groupby("student_id").cumcount() + 1

    return universe


def main() -> None:
    courses, requirements = load_data()
    universe = build_universe(courses, requirements)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(OUTPUT_PATH, index=False)

    qa_rows = [
        {"metric": "student_course_rows", "value": len(courses)},
        {"metric": "unique_students_in_courses", "value": courses["student_id"].nunique()},
        {"metric": "requirement_option_rows", "value": len(requirements)},
        {"metric": "universe_rows_before_engine", "value": len(universe)},
        {"metric": "eligible_universe_rows", "value": int(universe["eligible_for_audit"].sum())},
        {"metric": "unique_students_in_universe", "value": universe["student_id"].nunique()},
        {"metric": "unique_credentials_in_universe", "value": universe["credential_id"].nunique()},
    ]

    qa = pd.DataFrame(qa_rows)
    qa.to_csv(QA_OUTPUT_PATH, index=False)

    print(f"Wrote {len(universe)} universe rows to {OUTPUT_PATH}")
    print(f"Wrote QA summary to {QA_OUTPUT_PATH}")
    print()
    print("QA SUMMARY")
    print(qa.to_string(index=False))
    print()
    print("Eligible rows by catalog year:")
    print(universe[universe["eligible_for_audit"]].groupby("catalog_year").size())
    print()
    print("Top 25 universe rows:")
    print(
        universe.head(25)[[
            "student_id",
            "catalog_year",
            "credential_id",
            "matched_course_count",
            "matched_requirement_count",
            "total_requirement_count",
            "requirement_overlap_ratio",
            "eligible_for_audit",
            "student_universe_rank",
        ]].to_string(index=False)
    )


if __name__ == "__main__":
    main()