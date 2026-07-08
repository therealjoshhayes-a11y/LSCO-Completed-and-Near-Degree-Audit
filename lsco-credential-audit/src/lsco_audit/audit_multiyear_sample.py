import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S"}

STUDENT_COURSES = DATA_DIR / "test" / "student_course_history_normalized.csv"
REQUIREMENTS = PROCESSED_DIR / "catalogs" / "requirements_master_multiyear.csv"
CORE_LOOKUP = PROCESSED_DIR / "core_bucket_lookup.csv"
ELIGIBILITY = PROCESSED_DIR / "student_catalog_eligibility.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "multiyear_sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "multiyear_sample_credential_summary.csv"


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


def audit_non_elective_requirement(
    group: pd.DataFrame,
    available_courses: set[str],
    core_lookup: dict[str, set[str]],
) -> tuple[str, list[str]]:
    matched = []

    for _, option in group.iterrows():
        option_type = option["option_type"]
        option_value = str(option["option_value"])

        if option_type == "COURSE":
            if option_value in available_courses:
                matched.append(option_value)

        elif option_type == "CORE_BUCKET":
            normalized_bucket = normalize_bucket_name(option_value)
            if normalized_bucket is None:
                continue

            bucket_courses = core_lookup.get(normalized_bucket, set())
            bucket_matches = sorted(available_courses.intersection(bucket_courses))
            matched.extend(bucket_matches)

    required = int(group.iloc[0]["min_required"])
    matched = sorted(set(matched))

    if len(matched) >= required:
        return "MET", matched[:required]

    return "UNMET", matched


def audit_elective_requirement(
    available_courses: set[str],
) -> tuple[str, list[str]]:
    if available_courses:
        selected = sorted(available_courses)[0]
        return "MET", [selected]

    return "UNRESOLVED_ELECTIVE", []


def get_audit_status(requirements_missing: int, unresolved: int) -> str:
    if unresolved > 0:
        return "REVIEW_REQUIRED"
    if requirements_missing == 0:
        return "COMPLETE"
    if requirements_missing <= 3:
        return "NEAR_COMPLETE"
    return "INCOMPLETE"


def audit_student_credential(
    student_id: str,
    credential_id: str,
    credential_requirements: pd.DataFrame,
    completed_courses: set[str],
    core_lookup: dict[str, set[str]],
) -> list[dict]:
    used_courses = set()
    detail_rows = []

    grouped = list(credential_requirements.groupby("requirement_id"))

    non_elective_groups = [
        (requirement_id, group)
        for requirement_id, group in grouped
        if not set(group["option_type"]) <= {"ELECTIVE"}
    ]

    elective_groups = [
        (requirement_id, group)
        for requirement_id, group in grouped
        if set(group["option_type"]) <= {"ELECTIVE"}
    ]

    ordered_groups = non_elective_groups + elective_groups

    for requirement_id, group in ordered_groups:
        available_courses = completed_courses - used_courses

        if set(group["option_type"]) <= {"ELECTIVE"}:
            status, matched = audit_elective_requirement(available_courses)
        else:
            status, matched = audit_non_elective_requirement(
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
            )

        if status == "MET":
            used_courses.update(matched)

        detail_rows.append(
            {
                "student_id": student_id,
                "catalog_year": group.iloc[0].get("catalog_year", ""),
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
                "used_course_count": len(used_courses),
            }
        )

    return detail_rows


def audit() -> None:
    courses = pd.read_csv(STUDENT_COURSES)
    requirements = pd.read_csv(REQUIREMENTS)
    core_lookup = load_core_lookup()

    if ELIGIBILITY.exists():
        eligibility = pd.read_csv(ELIGIBILITY, dtype=str)
    else:
        eligibility = pd.DataFrame(
            columns=[
                "student_id",
                "catalog_year",
                "catalog_eligible",
                "eligibility_reason",
            ]
        )

    completed = courses[courses["grade"].isin(COMPLETION_GRADES)].copy()

    detail_rows = []

    for student_id in sorted(courses["student_id"].unique()):
        student_completed = normalize_course_set(
            completed[completed["student_id"] == student_id]
        )

        for (catalog_year, credential_id), credential_requirements in requirements.groupby(
            ["catalog_year", "credential_id"]
        ):
            detail_rows.extend(
                audit_student_credential(
                    student_id=student_id,
                    credential_id=credential_id,
                    credential_requirements=credential_requirements,
                    completed_courses=student_completed,
                    core_lookup=core_lookup,
                )
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv(DETAIL_OUTPUT, index=False)

    summary_rows = []

    for (student_id, catalog_year, credential_id), group in detail_df.groupby(
        ["student_id", "catalog_year", "credential_id"]
    ):
        total = len(group)
        met = (group["status"] == "MET").sum()
        unresolved = group["status"].astype(str).str.startswith("UNRESOLVED").sum()
        missing = total - met - unresolved

        summary_rows.append(
            {
                "student_id": student_id,
                "catalog_year": catalog_year,
                "credential_id": credential_id,
                "requirements_met": met,
                "requirements_total": total,
                "requirements_missing": missing,
                "requirements_unresolved": unresolved,
                "audit_status": get_audit_status(missing, unresolved),
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    if not eligibility.empty:
        keep_cols = [
            "student_id",
            "catalog_year",
            "catalog_eligible",
            "eligibility_reason",
            "earned_course_in_catalog_year",
            "has_activity_after_catalog_life",
            "continuity_break",
            "max_missed_long_semesters_between_earned_terms",
        ]

        available_cols = [column for column in keep_cols if column in eligibility.columns]

        summary_df = summary_df.merge(
            eligibility[available_cols],
            on=["student_id", "catalog_year"],
            how="left",
        )

    summary_df.to_csv(SUMMARY_OUTPUT, index=False)

    print(f"Wrote {DETAIL_OUTPUT}")
    print(f"Wrote {SUMMARY_OUTPUT}")
    print(summary_df.head(40))


if __name__ == "__main__":
    audit()
