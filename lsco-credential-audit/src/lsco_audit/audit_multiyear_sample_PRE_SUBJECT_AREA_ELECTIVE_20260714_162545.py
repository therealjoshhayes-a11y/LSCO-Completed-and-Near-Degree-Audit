import re

import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S", "E", "T"}

STUDENT_COURSES = PROCESSED_DIR / "student_course_history_normalized.csv"
REQUIREMENTS = PROCESSED_DIR / "catalogs" / "requirements_master_multiyear.csv"
CORE_LOOKUP = PROCESSED_DIR / "core_bucket_lookup.csv"

RULE_REVIEW_DIR = (
    PROCESSED_DIR
    / "full_actual_audit"
    / "evidence"
    / "rule_logic_review"
)

ELECTIVE_RULES = (
    RULE_REVIEW_DIR
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

ACADEMIC_COURSE_CROSSWALK = (
    RULE_REVIEW_DIR
    / "catalog_academic_course_crosswalk_final.csv"
)

COMPOUND_REQUIREMENT_ALTERNATIVES = (
    PROCESSED_DIR
    / "catalogs"
    / "semantic_policies"
    / "compound_requirement_alternatives.csv"
)

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


def normalize_course_code(value: str) -> str:
    return " ".join(
        str(value).upper().strip().split()
    )


def load_elective_rules() -> dict[str, dict]:
    if not ELECTIVE_RULES.exists():
        raise FileNotFoundError(
            f"Controlled elective rules not found: {ELECTIVE_RULES}"
        )

    rules = pd.read_csv(
        ELECTIVE_RULES,
        dtype=str,
        low_memory=False,
    ).fillna("")

    if rules["requirement_id"].duplicated().any():
        duplicates = sorted(
            rules.loc[
                rules["requirement_id"].duplicated(
                    keep=False
                ),
                "requirement_id",
            ]
            .astype(str)
            .unique()
        )

        raise ValueError(
            "Duplicate controlled elective requirement IDs: "
            + ", ".join(duplicates[:25])
        )

    return {
        str(row["requirement_id"]): row.to_dict()
        for _, row in rules.iterrows()
    }


def load_academic_course_lookup() -> dict[str, set[str]]:
    if not ACADEMIC_COURSE_CROSSWALK.exists():
        raise FileNotFoundError(
            "Academic course crosswalk not found: "
            f"{ACADEMIC_COURSE_CROSSWALK}"
        )

    crosswalk = pd.read_csv(
        ACADEMIC_COURSE_CROSSWALK,
        dtype=str,
        low_memory=False,
    ).fillna("")

    eligible = crosswalk[
        crosswalk[
            "academic_elective_eligible"
        ]
        .astype(str)
        .str.upper()
        .eq("TRUE")
    ].copy()

    eligible["course_code"] = (
        eligible["course_code"]
        .map(normalize_course_code)
    )

    return {
        str(catalog_year): set(
            group["course_code"]
            .dropna()
            .astype(str)
        )
        for catalog_year, group in eligible.groupby(
            "catalog_year"
        )
    }


def load_compound_requirement_alternatives() -> dict[str, list[list[str]]]:
    if not COMPOUND_REQUIREMENT_ALTERNATIVES.exists():
        raise FileNotFoundError(
            "Compound requirement alternatives not found: "
            f"{COMPOUND_REQUIREMENT_ALTERNATIVES}"
        )

    rows = pd.read_csv(
        COMPOUND_REQUIREMENT_ALTERNATIVES,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "requirement_id",
        "alternative_group",
        "alternative_course_order",
        "option_value",
    }

    missing = required_columns - set(rows.columns)

    if missing:
        raise KeyError(
            "Compound alternative file missing columns: "
            + ", ".join(sorted(missing))
        )

    rows["alternative_group_numeric"] = pd.to_numeric(
        rows["alternative_group"],
        errors="raise",
    ).astype(int)

    rows["alternative_course_order_numeric"] = pd.to_numeric(
        rows["alternative_course_order"],
        errors="raise",
    ).astype(int)

    result: dict[str, list[list[str]]] = {}

    for requirement_id, requirement_rows in rows.groupby(
        "requirement_id",
        sort=False,
    ):
        alternatives = []

        for _, alternative_rows in requirement_rows.groupby(
            "alternative_group_numeric",
            sort=True,
        ):
            alternative_rows = alternative_rows.sort_values(
                "alternative_course_order_numeric"
            )

            courses = [
                normalize_course_code(value)
                for value in alternative_rows["option_value"]
                if normalize_course_code(value)
            ]

            if not courses:
                raise ValueError(
                    f"Empty compound alternative for {requirement_id}"
                )

            alternatives.append(courses)

        result[str(requirement_id)] = alternatives

    return result


def course_credit_hours(course_code: str) -> int | None:
    parts = normalize_course_code(course_code).split()

    if len(parts) < 2:
        return None

    number = parts[1]

    if len(number) != 4 or not number.isdigit():
        return None

    return int(number[1])


def course_rubric(course_code: str) -> str:
    parts = normalize_course_code(
        course_code
    ).split()

    if not parts:
        return ""

    return parts[0]


def parse_allowed_rubrics(
    allowed_rubrics: str,
) -> set[str]:
    return {
        value.strip().upper()
        for value in re.split(
            r"[|;,]",
            str(allowed_rubrics),
        )
        if value.strip()
    }


def match_allowed_rubric_elective(
    available_courses: set[str],
    allowed_rubrics: str,
) -> list[str]:
    rubrics = parse_allowed_rubrics(
        allowed_rubrics
    )

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
    requirement_id: str,
    group: pd.DataFrame,
    available_courses: set[str],
    core_lookup: dict[str, set[str]],
    compound_alternatives: dict[str, list[list[str]]],
) -> tuple[str, list[str]]:
    normalized_available = {
        normalize_course_code(course_code)
        for course_code in available_courses
        if normalize_course_code(course_code)
    }

    alternatives = compound_alternatives.get(
        str(requirement_id)
    )

    if alternatives:
        for alternative in alternatives:
            if set(alternative).issubset(
                normalized_available
            ):
                return "MET", list(alternative)

        partial_matches = sorted({
            course
            for alternative in alternatives
            for course in alternative
            if course in normalized_available
        })

        return "UNMET", partial_matches

    matched = []

    for _, option in group.iterrows():
        option_type = str(option["option_type"])
        option_value = normalize_course_code(
            option["option_value"]
        )

        if option_type == "COURSE":
            if option_value in normalized_available:
                matched.append(option_value)

        elif option_type == "CORE_BUCKET":
            normalized_bucket = normalize_bucket_name(
                option_value
            )

            if normalized_bucket is None:
                continue

            bucket_courses = core_lookup.get(
                normalized_bucket,
                set(),
            )

            bucket_matches = sorted(
                normalized_available.intersection(
                    bucket_courses
                )
            )

            matched.extend(bucket_matches)

    required = int(group.iloc[0]["min_required"])
    matched = sorted(set(matched))

    if len(matched) >= required:
        return "MET", matched[:required]

    return "UNMET", matched


def audit_elective_requirement(
    requirement_id: str,
    catalog_year: str,
    required_credit_hours: int,
    available_courses: set[str],
    elective_rules: dict[str, dict],
    academic_course_lookup: dict[str, set[str]],
    core_lookup: dict[str, set[str]],
) -> tuple[str, list[str]]:
    rule = elective_rules.get(
        str(requirement_id)
    )

    if not rule:
        return (
            "UNRESOLVED_ELECTIVE_MISSING_RULE",
            [],
        )

    # Support both the canonical controlled-rule schema and
    # the current elective_rules_multicatalog.csv schema.
    controlled_class = str(
        rule.get("controlled_class", "")
    ).strip().upper()

    resolution_policy = str(
        rule.get("resolution_policy", "")
    ).strip().upper()

    controlled_scope = str(
        rule.get("controlled_scope", "")
    ).strip().upper()

    allowed_rubrics = str(
        rule.get(
            "allowed_rubrics_override",
            "",
        )
    ).strip()

    resolver_type = str(
        rule.get("resolver_type", "")
    ).strip().upper()

    if not allowed_rubrics:
        allowed_rubrics = str(
            rule.get("allowed_rubrics", "")
        ).strip()

    # Translate the existing CSV resolver vocabulary into the
    # engine's controlled-policy vocabulary.
    if not controlled_class and resolver_type:
        resolver_translation = {
            "RUBRIC_ELECTIVE": (
                "RUBRIC_RESTRICTED",
                "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC",
            ),
            "BUSINESS_ELECTIVE": (
                "RUBRIC_RESTRICTED",
                "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC",
            ),
            "AG_BUSINESS_ELECTIVE": (
                "RUBRIC_RESTRICTED",
                "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC",
            ),
            "SCIENCE_ELECTIVE": (
                "SCIENCE_ELECTIVE",
                "USE_SCIENCE_COURSE_CROSSWALK",
            ),
            "SCIENCE_MAJOR_ELECTIVE": (
                "SCIENCE_ELECTIVE",
                "USE_SCIENCE_COURSE_CROSSWALK",
            ),
            "CORE_AREA_ELECTIVE": (
                "CORE_COMPONENT_ELECTIVE",
                "USE_CORE_BUCKET_CROSSWALK",
            ),
            "ACADEMIC_ELECTIVE": (
                "ACADEMIC_ELECTIVE",
                "USE_ACADEMIC_COURSE_CROSSWALK",
            ),
            "GENERAL_ACADEMIC_ELECTIVE": (
                "UNRESTRICTED_ELECTIVE",
                "COUNT_UNUSED_PASSED_COURSE",
            ),
            "GENERAL_APPROVED_ELECTIVE": (
                "UNRESTRICTED_ELECTIVE",
                "COUNT_UNUSED_PASSED_COURSE",
            ),
            "GENERAL_ELECTIVE": (
                "UNRESTRICTED_ELECTIVE",
                "COUNT_UNUSED_PASSED_COURSE",
            ),
            "UNRESTRICTED_ELECTIVE": (
                "UNRESTRICTED_ELECTIVE",
                "COUNT_UNUSED_PASSED_COURSE",
            ),
            "ANY_UNUSED_PASSED_COURSE": (
                "UNRESTRICTED_ELECTIVE",
                "COUNT_UNUSED_PASSED_COURSE",
            ),
            "UNRESTRICTED_COLLEGE_LEVEL_ELECTIVE": (
                "UNRESTRICTED_COLLEGE_LEVEL_ELECTIVE",
                "COUNT_UNUSED_PASSED_COLLEGE_LEVEL_COURSE",
            ),
            "CORE_COMPONENT_ELECTIVE": (
                "CORE_COMPONENT_ELECTIVE",
                "USE_CORE_BUCKET_CROSSWALK",
            ),
            "EMS_PROGRAM_ELECTIVE": (
                "EMS_PROGRAM_ELECTIVE",
                "COUNT_UNUSED_PASSED_EMSP_PROGRAM_COURSE",
            ),
        }

        translated = resolver_translation.get(
            resolver_type
        )

        if translated:
            controlled_class = translated[0]
            resolution_policy = translated[1]

            # The current multicatalog rule table represents the
            # Language/Philosophy/Culture-or-Creative-Arts elective
            # as CORE_AREA_ELECTIVE with CORE_040;CORE_050.
            if resolver_type == "CORE_AREA_ELECTIVE":
                controlled_scope = (
                    "LANG_PHIL_CULTURE_OR_CREATIVE_ARTS"
                )

    available_courses = {
        normalize_course_code(course_code)
        for course_code in available_courses
        if normalize_course_code(course_code)
    }

    matched: list[str] = []


    # --------------------------------------------------------
    # ACADEMIC ELECTIVE
    # --------------------------------------------------------

    if (
        controlled_class
        == "ACADEMIC_ELECTIVE"
        and resolution_policy
        == "USE_ACADEMIC_COURSE_CROSSWALK"
    ):
        allowed_courses = (
            academic_course_lookup.get(
                str(catalog_year),
                set(),
            )
        )

        matched = sorted(
            available_courses.intersection(
                allowed_courses
            )
        )


    # --------------------------------------------------------
    # RUBRIC-RESTRICTED ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "RUBRIC_RESTRICTED"
        and resolution_policy
        == "COUNT_UNUSED_PASSED_ALLOWED_RUBRIC"
    ):
        if not parse_allowed_rubrics(
            allowed_rubrics
        ):
            return (
                "UNRESOLVED_ELECTIVE_INVALID_RUBRICS",
                [],
            )

        matched = match_allowed_rubric_elective(
            available_courses=available_courses,
            allowed_rubrics=allowed_rubrics,
        )


    # --------------------------------------------------------
    # SCIENCE ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "SCIENCE_ELECTIVE"
        and resolution_policy
        == "USE_SCIENCE_COURSE_CROSSWALK"
    ):
        science_rubrics = (
            allowed_rubrics
            or "BIOL | CHEM | GEOL | PHYS"
        )

        matched = match_allowed_rubric_elective(
            available_courses=available_courses,
            allowed_rubrics=science_rubrics,
        )


    # --------------------------------------------------------
    # UNRESTRICTED ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "UNRESTRICTED_ELECTIVE"
        and resolution_policy
        == "COUNT_UNUSED_PASSED_COURSE"
    ):
        matched = sorted(
            available_courses
        )


    # --------------------------------------------------------
    # UNRESTRICTED COLLEGE-LEVEL ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "UNRESTRICTED_COLLEGE_LEVEL_ELECTIVE"
        and resolution_policy
        == "COUNT_UNUSED_PASSED_COLLEGE_LEVEL_COURSE"
    ):
        developmental_rubrics = {
            "DIRW",
            "DMTH",
            "NCBM",
            "GENR",
        }

        matched = []

        for course_code in sorted(
            available_courses
        ):
            normalized = normalize_course_code(
                course_code
            )

            parts = normalized.split()

            if len(parts) != 2:
                continue

            rubric = parts[0]
            course_number = parts[1]

            if rubric in developmental_rubrics:
                continue

            if (
                len(course_number) != 4
                or not course_number.isdigit()
                or course_number.startswith("0")
            ):
                continue

            credit_hours = course_credit_hours(
                normalized
            )

            if (
                credit_hours is None
                or credit_hours <= 0
            ):
                continue

            matched.append(
                normalized
            )


    # --------------------------------------------------------
    # CORE-COMPONENT ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "CORE_COMPONENT_ELECTIVE"
        and resolution_policy
        == "USE_CORE_BUCKET_CROSSWALK"
    ):
        if (
            controlled_scope
            != "LANG_PHIL_CULTURE_OR_CREATIVE_ARTS"
        ):
            return (
                "UNRESOLVED_ELECTIVE_INVALID_CORE_SCOPE",
                [],
            )

        allowed_courses = set()

        allowed_courses.update(
            core_lookup.get(
                "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",
                set(),
            )
        )

        allowed_courses.update(
            core_lookup.get(
                "CREATIVE_ARTS_CORE",
                set(),
            )
        )

        matched = sorted(
            available_courses.intersection(
                allowed_courses
            )
        )


    # --------------------------------------------------------
    # EMS PROGRAM ELECTIVE
    # --------------------------------------------------------

    elif (
        controlled_class
        == "EMS_PROGRAM_ELECTIVE"
        and resolution_policy
        == "COUNT_UNUSED_PASSED_EMSP_PROGRAM_COURSE"
    ):
        matched = match_allowed_rubric_elective(
            available_courses=available_courses,
            allowed_rubrics=(
                allowed_rubrics
                or "EMSP"
            ),
        )


    # --------------------------------------------------------
    # INVALID CONTROLLED CONFIGURATION
    # --------------------------------------------------------

    else:
        return (
            "UNRESOLVED_ELECTIVE_INVALID_POLICY",
            [],
        )


    # Retain only eligible courses with positive semester
    # credit hours.
    eligible_courses = []

    for course_code in sorted(
        set(matched)
    ):
        credit_hours = course_credit_hours(
            course_code
        )

        if (
            credit_hours is not None
            and credit_hours > 0
        ):
            eligible_courses.append(
                (
                    course_code,
                    float(credit_hours),
                )
            )

    # A valid configured rule with no eligible course is simply
    # unmet. It is not unresolved.
    if not eligible_courses:
        return "UNMET", []

    # Select deterministically, preferring higher-credit courses
    # first, until cumulative credit hours satisfy the catalog
    # requirement.
    eligible_courses = sorted(
        eligible_courses,
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )

    selected_courses = []
    accumulated_hours = 0.0

    for course_code, credit_hours in eligible_courses:
        selected_courses.append(
            course_code
        )

        accumulated_hours += credit_hours

        if accumulated_hours >= required_credit_hours:
            return (
                "MET",
                selected_courses,
            )

    # Eligible courses existed, but their combined hours did not
    # reach the displayed elective-hour requirement.
    return "UNMET", []


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
    academic_course_lookup: dict[str, set[str]],
    compound_alternatives: dict[str, list[list[str]]],
) -> list[dict]:
    used_courses = set()
    detail_rows = []

    # REQUIREMENT_ALLOCATION_PRIORITY_V3
    #
    # Resolve literal COURSE requirements before broad core buckets.
    # Classification is based on option_type, not regex scans of all
    # option text. This prevents labels such as "CORE 010" from being
    # mistaken for course codes.
    grouped = list(
        credential_requirements.groupby(
            "requirement_id",
            sort=False,
        )
    )

    def requirement_priority(item):
        requirement_id, group = item

        rule_type = str(
            group.iloc[0].get(
                "rule_type",
                "",
            )
        ).strip().upper()

        option_types = {
            str(value).strip().upper()
            for value in group[
                "option_type"
            ].dropna()
            if str(value).strip()
        }

        literal_course_options = {
            str(value).strip().upper()
            for value in group.loc[
                group["option_type"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("COURSE"),
                "option_value",
            ].dropna()
            if str(value).strip()
        }

        course_option_count = len(
            literal_course_options
        )

        is_literal_course_requirement = (
            option_types == {"COURSE"}
            and course_option_count >= 1
        )

        is_core_bucket = (
            "CORE_BUCKET" in option_types
            or rule_type == "CORE_BUCKET"
            and not is_literal_course_requirement
        )

        is_elective = (
            "ELECTIVE" in option_types
            or rule_type == "ELECTIVE"
        )

        if (
            is_literal_course_requirement
            and course_option_count == 1
        ):
            priority = 10

        elif (
            is_literal_course_requirement
            and rule_type == "EXACT"
        ):
            priority = 20

        elif rule_type == "ANY_N":
            priority = 30

        elif is_core_bucket:
            core_option_values = {
                str(value).strip().upper()
                for value in group[
                    "option_value"
                ].dropna()
                if str(value).strip()
            }

            is_component_area_option = any(
                (
                    "COMPONENT AREA OPTION"
                    in value
                )
                or (
                    "COMPONENT_AREA_OPTION"
                    in value
                )
                or value.endswith(
                    "CORE 090"
                )
                for value in core_option_values
            )

            # Specific core components 010-080 must consume
            # before the broad Component Area Option 090.
            priority = (
                45
                if is_component_area_option
                else 40
            )

        elif is_elective:
            priority = 50

        else:
            priority = 60

        option_count_sort = (
            course_option_count
            if course_option_count > 0
            else 999999
        )

        return (
            priority,
            option_count_sort,
            str(requirement_id),
        )

    ordered_groups = sorted(
        grouped,
        key=requirement_priority,
    )

    for requirement_id, group in ordered_groups:
        available_courses = set(course_lookup) - used_courses

        if set(group["option_type"]) <= {"ELECTIVE"}:
            required_credit_hours = int(
                float(group.iloc[0]["credit_hours"])
            )

            status, matched = audit_elective_requirement(
                requirement_id=requirement_id,
                catalog_year=str(catalog_year),
                required_credit_hours=required_credit_hours,
                available_courses=available_courses,
                elective_rules=elective_rules,
                academic_course_lookup=academic_course_lookup,
                core_lookup=core_lookup,
            )
        else:
            status, matched = audit_non_elective_requirement(
                requirement_id=requirement_id,
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
                compound_alternatives=compound_alternatives,
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
    academic_course_lookup = load_academic_course_lookup()
    compound_alternatives = (
        load_compound_requirement_alternatives()
    )

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
                    academic_course_lookup=academic_course_lookup,
                    compound_alternatives=compound_alternatives,
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
