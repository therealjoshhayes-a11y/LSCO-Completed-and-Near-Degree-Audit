import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S"}

STUDENT_COURSES = DATA_DIR / "test" / "student_course_history_sample.csv"
REQUIREMENTS = PROCESSED_DIR / "requirements_master.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "master_sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "master_sample_credential_summary.csv"


def normalize_course_set(courses: pd.DataFrame) -> set[str]:
    return set(courses["course_code"].dropna().astype(str))


def audit_requirement(group: pd.DataFrame, completed_courses: set[str]) -> tuple[str, list[str]]:
    option_type_values = set(group["option_type"])

    matched = []

    course_options = group[group["option_type"] == "COURSE"]["option_value"].astype(str)

    for course in course_options:
        if course in completed_courses:
            matched.append(course)

    # CORE_BUCKET and ELECTIVE are carried but not resolved yet.
    required = int(group.iloc[0]["min_required"])

    status = "MET" if len(matched) >= required else "UNMET"

    if option_type_values <= {"CORE_BUCKET"}:
        status = "UNRESOLVED_CORE_BUCKET"

    if option_type_values <= {"ELECTIVE"}:
        status = "UNRESOLVED_ELECTIVE"

    return status, matched


def get_audit_status(requirements_missing: int, unresolved: int) -> str:
    if unresolved > 0:
        return "REVIEW_REQUIRED"
    if requirements_missing == 0:
        return "COMPLETE"
    if requirements_missing <= 3:
        return "NEAR_COMPLETE"
    return "INCOMPLETE"


def audit() -> None:
    courses = pd.read_csv(STUDENT_COURSES)
    requirements = pd.read_csv(REQUIREMENTS)

    completed = courses[courses["grade"].isin(COMPLETION_GRADES)].copy()

    detail_rows = []

    for student_id in sorted(courses["student_id"].unique()):
        student_completed = normalize_course_set(
            completed[completed["student_id"] == student_id]
        )

        for (credential_id, requirement_id), group in requirements.groupby(
            ["credential_id", "requirement_id"]
        ):
            status, matched = audit_requirement(group, student_completed)

            detail_rows.append(
                {
                    "student_id": student_id,
                    "credential_id": credential_id,
                    "requirement_id": requirement_id,
                    "rule_type": group.iloc[0]["rule_type"],
                    "status": status,
                    "matched_options": "; ".join(matched),
                    "required_options": "; ".join(
                        group["option_value"].dropna().astype(str).tolist()
                    ),
                    "option_types": "; ".join(
                        sorted(group["option_type"].dropna().astype(str).unique())
                    ),
                }
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv(DETAIL_OUTPUT, index=False)

    summary_rows = []

    for (student_id, credential_id), group in detail_df.groupby(
        ["student_id", "credential_id"]
    ):
        total = len(group)
        met = (group["status"] == "MET").sum()
        unresolved = group["status"].astype(str).str.startswith("UNRESOLVED").sum()
        missing = total - met - unresolved

        summary_rows.append(
            {
                "student_id": student_id,
                "credential_id": credential_id,
                "requirements_met": met,
                "requirements_total": total,
                "requirements_missing": missing,
                "requirements_unresolved": unresolved,
                "audit_status": get_audit_status(missing, unresolved),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(SUMMARY_OUTPUT, index=False)

    print(f"Wrote {DETAIL_OUTPUT}")
    print(f"Wrote {SUMMARY_OUTPUT}")
    print(summary_df.head(40))


if __name__ == "__main__":
    audit()