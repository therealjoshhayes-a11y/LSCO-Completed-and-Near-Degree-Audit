import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S"}

STUDENT_COURSES = DATA_DIR / "test" / "student_course_history_sample.csv"
REQUIREMENTS = PROCESSED_DIR / "requirement_seed_sample.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "sample_credential_summary.csv"


def get_audit_status(requirements_missing: int) -> str:
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
        student_completed = set(
            completed.loc[completed["student_id"] == student_id, "course_code"]
        )

        for requirement_id, group in requirements.groupby("requirement_id"):
            credential_id = group.iloc[0]["credential_id"]
            rule_type = group.iloc[0]["rule_type"]
            min_required = int(group.iloc[0]["min_required"])

            options = set(group["option_value"])
            matched = sorted(student_completed.intersection(options))

            status = "MET" if len(matched) >= min_required else "UNMET"

            detail_rows.append(
                {
                    "student_id": student_id,
                    "credential_id": credential_id,
                    "requirement_id": requirement_id,
                    "rule_type": rule_type,
                    "status": status,
                    "matched_options": "; ".join(matched),
                    "required_options": "; ".join(sorted(options)),
                }
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv(DETAIL_OUTPUT, index=False)

    summary_rows = []

    for (student_id, credential_id), group in detail_df.groupby(
        ["student_id", "credential_id"]
    ):
        requirements_total = len(group)
        requirements_met = (group["status"] == "MET").sum()
        requirements_missing = requirements_total - requirements_met

        summary_rows.append(
            {
                "student_id": student_id,
                "credential_id": credential_id,
                "requirements_met": requirements_met,
                "requirements_total": requirements_total,
                "requirements_missing": requirements_missing,
                "audit_status": get_audit_status(requirements_missing),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(SUMMARY_OUTPUT, index=False)

    print(f"Wrote {DETAIL_OUTPUT}")
    print(f"Wrote {SUMMARY_OUTPUT}")
    print(summary_df)


if __name__ == "__main__":
    audit()