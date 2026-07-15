import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S", "E", "T"}

STUDENT_COURSES = PROCESSED_DIR / "student_course_history_normalized.csv"
REQUIREMENTS = PROCESSED_DIR / "catalogs" / "requirements_master_multiyear.csv"
CORE_LOOKUP = PROCESSED_DIR / "core_bucket_lookup.csv"
ELECTIVE_RULES = PROCESSED_DIR / "catalogs" / "elective_rules_multicatalog.csv"
ELIGIBILITY = PROCESSED_DIR / "student_catalog_eligibility.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "multiyear_sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "multiyear_sample_credential_summary.csv"


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


def load_elective_rules() -> dict[str, dict]:
    if not ELECTIVE_RULES.exists():
        return {}

    rules = pd.read_csv(ELECTIVE_RULES, dtype=str).fillna("")
    return {
        str(row["requirement_id"]): row.to_dict()
        for _, row in rules.iterrows()
    }


def course_rubric(course_code: str) -> str:
    parts = str(course_code).strip().split()
    if not parts:
        return ""
    return parts[0].upper()


def match_allowed_rubric_elective(
    available_courses: set[str],
    allowed_rubrics: str,
) -> list[str]:
    rubrics = {
        part.strip().upper()
        for part in str(allowed_rubrics).split(";")
        if part.strip()
    }

    if not rubrics:
        return []

    return sorted(
        course_code
        for course_code in available_courses
        if course_rubric(course_code) in rubrics
    )


def completed_course_lookup(courses: pd.DataFrame) -> dict[str, dict]:
    """Return course_code -> resolved successful attempt metadata."""

    courses = courses.copy()

    if "passed" in courses.columns:
        completed = courses[courses["passed"].astype(str).str.upper().eq("TRUE")].copy()
    else:
        completed = courses[
            courses["grade"].astype(str).str.upper().isin(COMPLETION_GRADES)
        ].copy()

    completed["term_sort"] = pd.to_numeric(completed["term_sort"], errors="coerce")
    completed = completed[completed["term_sort"].notna()].copy()
    completed["term_sort"] = completed["term_sort"].astype(int)

    completed = completed.sort_values(
        by=["course_code", "term_sort"],
        ascending=[True, False],
        kind="mergesort",
    )

    lookup = {}

    for _, row in completed.drop_duplicates(subset=["course_code"], keep="first").iterrows():
        course_code = str(row["course_code"])
        lookup[course_code] = {
            "course_code": course_code,
            "term_taken": str(row.get("term_taken", "")),
            "term_sort": int(row["term_sort"]),
            "grade": str(row.get("grade", "")),
        }

    return lookup


def latest_attempt_metadata(
    matched: list[str],
    course_lookup: dict[str, dict],
) -> tuple[str, str, str]:
    matched_rows = [
        course_lookup[course_code]
        for course_code in matched
        if course_code in course_lookup
    ]

    if not matched_rows:
        return "", "", ""

    latest = max(matched_rows, key=lambda row: row["term_sort"])

    term_sorts = "; ".join(str(row["term_sort"]) for row in matched_rows)
    terms = "; ".join(str(row["term_taken"]) for row in matched_rows)
    grades = "; ".join(str(row["grade"]) for row in matched_rows)

    return str(latest["term_sort"]), str(latest["term_taken"]), grades


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
    requirement_id: str,
    available_courses: set[str],
    elective_rules: dict[str, dict],
) -> tuple[str, list[str]]:
    rule = elective_rules.get(str(requirement_id))

    if not rule:
        return "UNRESOLVED_ELECTIVE", []

    resolver_type = str(rule.get("resolver_type", ""))
    allowed_rubrics = str(rule.get("allowed_rubrics", ""))

    if resolver_type in {"RUBRIC_ELECTIVE", "BUSINESS_ELECTIVE"}:
        matched = match_allowed_rubric_elective(
            available_courses=available_courses,
            allowed_rubrics=allowed_rubrics,
        )

        if matched:
            return "MET", [matched[0]]

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
    catalog_year: str,
    credential_id: str,
    credential_requirements: pd.DataFrame,
    course_lookup: dict[str, dict],
    core_lookup: dict[str, set[str]],
    elective_rules: dict[str, dict],
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
        available_courses = set(course_lookup) - used_courses

        if set(group["option_type"]) <= {"ELECTIVE"}:
            status, matched = audit_elective_requirement(
                requirement_id=requirement_id,
                available_courses=available_courses,
                elective_rules=elective_rules,
            )
        else:
            status, matched = audit_non_elective_requirement(
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
            )

        if status == "MET":
            used_courses.update(matched)

        latest_term_sort, latest_term_taken, matched_grades = latest_attempt_metadata(
            matched=matched,
            course_lookup=course_lookup,
        )

        matched_terms = "; ".join(
            str(course_lookup[course_code]["term_taken"])
            for course_code in matched
            if course_code in course_lookup
        )

        matched_term_sorts = "; ".join(
            str(course_lookup[course_code]["term_sort"])
            for course_code in matched
            if course_code in course_lookup
        )

        detail_rows.append(
            {
                "student_id": student_id,
                "catalog_year": catalog_year,
                "credential_id": credential_id,
                "requirement_id": requirement_id,
                "rule_type": group.iloc[0]["rule_type"],
                "status": status,
                "matched_options": "; ".join(matched),
                "matched_terms": matched_terms,
                "matched_term_sorts": matched_term_sorts,
                "matched_grades": matched_grades,
                "latest_matched_term_sort": latest_term_sort,
                "latest_matched_term_taken": latest_term_taken,
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


def summarize_award_term(group: pd.DataFrame, audit_status: str) -> tuple[str, str]:
    if audit_status != "COMPLETE":
        return "", ""

    met = group[group["status"].eq("MET")].copy()
    met["latest_matched_term_sort_numeric"] = pd.to_numeric(
        met["latest_matched_term_sort"],
        errors="coerce",
    )
    met = met[met["latest_matched_term_sort_numeric"].notna()].copy()

    if met.empty:
        return "", ""

    latest_row = met.sort_values(
        by="latest_matched_term_sort_numeric",
        ascending=False,
        kind="mergesort",
    ).iloc[0]

    return (
        str(int(latest_row["latest_matched_term_sort_numeric"])),
        str(latest_row["latest_matched_term_taken"]),
    )


def audit() -> None:
    courses = pd.read_csv(STUDENT_COURSES, dtype=str, low_memory=False)
    requirements = pd.read_csv(REQUIREMENTS)
    core_lookup = load_core_lookup()
    elective_rules = load_elective_rules()

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

    detail_rows = []

    for student_id in sorted(courses["student_id"].unique()):
        student_courses = courses[courses["student_id"] == student_id]
        course_lookup = completed_course_lookup(student_courses)

        for (catalog_year, credential_id), credential_requirements in requirements.groupby(
            ["catalog_year", "credential_id"]
        ):
            detail_rows.extend(
                audit_student_credential(
                    student_id=student_id,
                    catalog_year=catalog_year,
                    credential_id=credential_id,
                    credential_requirements=credential_requirements,
                    course_lookup=course_lookup,
                    core_lookup=core_lookup,
                    elective_rules=elective_rules,
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
        audit_status = get_audit_status(missing, unresolved)
        award_term_sort, award_term_taken = summarize_award_term(group, audit_status)

        summary_rows.append(
            {
                "student_id": student_id,
                "catalog_year": catalog_year,
                "credential_id": credential_id,
                "requirements_met": met,
                "requirements_total": total,
                "requirements_missing": missing,
                "requirements_unresolved": unresolved,
                "audit_status": audit_status,
                "award_term_sort": award_term_sort,
                "award_term_taken": award_term_taken,
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
