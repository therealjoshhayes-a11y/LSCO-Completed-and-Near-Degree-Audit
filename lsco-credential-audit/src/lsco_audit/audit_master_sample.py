import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S"}

STUDENT_COURSES = DATA_DIR / "test" / "student_course_history_sample.csv"
REQUIREMENTS = PROCESSED_DIR / "requirements_master.csv"
CORE_LOOKUP = PROCESSED_DIR / "core_bucket_lookup.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "master_sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "master_sample_credential_summary.csv"


def normalize_course_set(courses: pd.DataFrame) -> set[str]:
    return set(courses["course_code"].dropna().astype(str))


def normalize_bucket_name(value: str) -> str | None:
    text = str(value).upper()

    if "COMMUNICATION" in text:
        return "COMMUNICATION_CORE"

    if "MATH" in text:
        return "MATHEMATICS_CORE"

    if "LIFE AND PHYSICAL SCIENCE" in text:
        return "LIFE_AND_PHYSICAL_SCIENCES_CORE"

    if "LANGUAGE" in text and "PHILOSOPHY" in text:
        return "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE"

    if "CREATIVE ARTS" in text or "ARTS CORE" in text:
        return "CREATIVE_ARTS_CORE"

    if "AMERICAN HISTORY" in text:
        return "AMERICAN_HISTORY_CORE"

    if "GOVERNMENT" in text or "POLITICAL SCIENCE" in text:
        return "GOVERNMENT_POLITICAL_SCIENCE_CORE"

    if "SOCIAL" in text and "BEHAVIORAL" in text:
        return "SOCIAL_AND_BEHAVIORAL_SCIENCE_CORE"

    if "COMPONENT AREA OPTION" in text or "OPTION CORE" in text:
        return "COMPONENT_AREA_OPTION_CORE"

    return None


def load_core_lookup() -> dict[str, set[str]]:
    lookup = pd.read_csv(CORE_LOOKUP)

    return {
        bucket: set(group["course_code"].dropna().astype(str))
        for bucket, group in lookup.groupby("bucket_name")
    }


def audit_requirement(
    group: pd.DataFrame,
    completed_courses: set[str],
    core_lookup: dict[str, set[str]],
) -> tuple[str, list[str]]:
    matched = []
    unresolved_bucket_values = []

    for _, option in group.iterrows():
        option_type = option["option_type"]
        option_value = str(option["option_value"])

        if option_type == "COURSE":
            if option_value in completed_courses:
                matched.append(option_value)

        elif option_type == "CORE_BUCKET":
            normalized_bucket = normalize_bucket_name(option_value)

            if normalized_bucket is None:
                unresolved_bucket_values.append(option_value)
                continue

            bucket_courses = core_lookup.get(normalized_bucket, set())
            bucket_matches = sorted(completed_courses.intersection(bucket_courses))
            matched.extend(bucket_matches)

        elif option_type == "ELECTIVE":
            continue

    required = int(group.iloc[0]["min_required"])

    if set(group["option_type"]) <= {"ELECTIVE"}:
        return "UNRESOLVED_ELECTIVE", matched

    if unresolved_bucket_values and not matched:
        return "UNRESOLVED_CORE_BUCKET", matched

    status = "MET" if len(set(matched)) >= required else "UNMET"

    return status, sorted(set(matched))


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
    core_lookup = load_core_lookup()

    completed = courses[courses["grade"].isin(COMPLETION_GRADES)].copy()

    detail_rows = []

    for student_id in sorted(courses["student_id"].unique()):
        student_completed = normalize_course_set(
            completed[completed["student_id"] == student_id]
        )

        for (credential_id, requirement_id), group in requirements.groupby(
            ["credential_id", "requirement_id"]
        ):
            status, matched = audit_requirement(
                group=group,
                completed_courses=student_completed,
                core_lookup=core_lookup,
            )

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