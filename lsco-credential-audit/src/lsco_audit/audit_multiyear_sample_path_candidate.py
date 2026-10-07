import re

import pandas as pd

from lsco_audit.paths import DATA_DIR, PROCESSED_DIR


COMPLETION_GRADES = {"A", "B", "C", "D", "S", "E", "T"}

STUDENT_COURSES = PROCESSED_DIR / "student_course_history_normalized.csv"
REQUIREMENTS = PROCESSED_DIR / "catalogs" / "requirements_master_multiyear.csv"
CORE_LOOKUP = (
    PROCESSED_DIR
    / "core_bucket_lookup_multicatalog.csv"
)

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

ALTERNATIVE_REQUIREMENT_PATHS = (
    PROCESSED_DIR
    / "catalogs"
    / "semantic_policies"
    / "alternative_requirement_paths.csv"
)

ELIGIBILITY = PROCESSED_DIR / "student_catalog_eligibility.csv"

DETAIL_OUTPUT = PROCESSED_DIR / "multiyear_sample_audit_results.csv"
SUMMARY_OUTPUT = PROCESSED_DIR / "multiyear_sample_credential_summary.csv"


def normalize_bucket_name(value: str) -> str | None:
    text = str(value).upper()

    # REPAIR NOTE (2026-07-16, combo-bucket repair): "X or Y" combo slots
    # must resolve to their UNION lookup keys BEFORE the narrow
    # single-bucket phrase checks below can fire. Previously
    # "COMMUNICATION or COMPONENT AREA OPTION" resolved to
    # COMMUNICATION_CORE (3 courses) instead of the 43+ course union, and
    # abbreviated forms like "Lang, Phil, Culture OR Creative Arts"
    # resolved to CREATIVE_ARTS_CORE (3 courses) instead of the 13-19
    # course union. The union keys below exist in
    # core_bucket_lookup_multicatalog.csv for all five catalog years and
    # were built for exactly this purpose. Catalog text "X or Y" means
    # either area satisfies the slot; this is defect correction, not a
    # policy change. See apply_combo_bucket_repair.py for the census.
    if " OR " in text:
        lpc_family = (
            "LANGUAGE" in text or "LANG" in text
        ) and (
            "PHILOSOPHY" in text or "PHIL" in text
        )
        arts_family = "CREATIVE ARTS" in text or "FINE ARTS" in text

        if lpc_family and arts_family:
            return "LANGUAGE_PHILOSOPHY_AND_CULTURE_OR_CREATIVE_ARTS"

        if "COMMUNICATION" in text and "COMPONENT AREA OPTION" in text:
            return "COMMUNICATION_OR_COMPONENT_AREA_OPTION"

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

    # Controlled historical and teaching-plan aliases.
    # These keys exist in the catalog-year-aware core lookup.
    if text == "PHYSICAL SCIENCE":
        return "PHYSICAL_SCIENCE"

    if text in {
        "LIFE OR PHYSICAL SCIENCE",
        "LIFE OR PHYSICAL SCIENCES",
    }:
        return "LIFE_OR_PHYSICAL_SCIENCES"

    if text == "LIFE SCIENCE CORE 030":
        return "LIFE_SCIENCE_CORE_030"

    if text == "PHYSICAL SCIENCE CORE 030":
        return "PHYSICAL_SCIENCE_CORE_030"

    return None


def load_core_lookup() -> dict[tuple[str, str], set[str]]:
    lookup = pd.read_csv(
        CORE_LOOKUP,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "catalog_year",
        "bucket_name",
        "course_code",
    }

    missing_columns = (
        required_columns
        - set(lookup.columns)
    )

    if missing_columns:
        raise ValueError(
            "Core lookup is missing required columns: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    lookup["catalog_year"] = (
        lookup["catalog_year"]
        .astype(str)
        .str.strip()
    )

    lookup["bucket_name"] = (
        lookup["bucket_name"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    lookup["course_code"] = (
        lookup["course_code"]
        .map(normalize_course_code)
    )

    lookup = lookup[
        lookup["catalog_year"].ne("")
        & lookup["bucket_name"].ne("")
        & lookup["course_code"].ne("")
    ].copy()

    duplicate_pairs = lookup.duplicated(
        subset=[
            "catalog_year",
            "bucket_name",
            "course_code",
        ],
        keep=False,
    )

    if duplicate_pairs.any():
        duplicate_count = int(
            duplicate_pairs.sum()
        )

        raise ValueError(
            "Duplicate catalog-year/bucket/course "
            f"lookup rows detected: {duplicate_count}"
        )

    return {
        (
            str(catalog_year),
            str(bucket_name),
        ):
            set(
                group["course_code"]
            )
        for (
            catalog_year,
            bucket_name,
        ), group in lookup.groupby(
            [
                "catalog_year",
                "bucket_name",
            ],
            sort=False,
        )
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



def load_alternative_requirement_paths() -> pd.DataFrame:
    required_columns = [
        "catalog_year",
        "credential_id",
        "path_group_id",
        "path_id",
        "path_label",
        "path_order",
        "requirement_id",
        "path_expected_applied_hours",
    ]

    if not ALTERNATIVE_REQUIREMENT_PATHS.exists():
        raise FileNotFoundError(
            "Required alternative-path semantic policy file "
            f"not found: {ALTERNATIVE_REQUIREMENT_PATHS}"
        )

    rows = pd.read_csv(
        ALTERNATIVE_REQUIREMENT_PATHS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    missing = set(required_columns) - set(rows.columns)

    if missing:
        raise KeyError(
            "Alternative requirement path file missing columns: "
            + ", ".join(sorted(missing))
        )

    for column in [
        "catalog_year",
        "credential_id",
        "path_group_id",
        "path_id",
        "path_label",
        "requirement_id",
    ]:
        rows[column] = (
            rows[column]
            .astype(str)
            .str.strip()
        )

        if rows[column].eq("").any():
            raise ValueError(
                "Blank value in alternative-path column: "
                f"{column}"
            )

    rows["path_order_numeric"] = pd.to_numeric(
        rows["path_order"],
        errors="raise",
    ).astype(int)

    rows[
        "path_expected_applied_hours_numeric"
    ] = pd.to_numeric(
        rows["path_expected_applied_hours"],
        errors="raise",
    ).astype(float)

    duplicate_membership = rows.duplicated(
        subset=[
            "catalog_year",
            "credential_id",
            "path_group_id",
            "requirement_id",
        ],
        keep=False,
    )

    if duplicate_membership.any():
        bad = rows.loc[
            duplicate_membership,
            [
                "catalog_year",
                "credential_id",
                "path_group_id",
                "path_id",
                "requirement_id",
            ],
        ]

        raise ValueError(
            "Requirement assigned to more than one path "
            "within the same path group:\n"
            + bad.to_string(index=False)
        )

    for (
        catalog_year,
        credential_id,
        path_group_id,
    ), group in rows.groupby(
        [
            "catalog_year",
            "credential_id",
            "path_group_id",
        ],
        sort=False,
    ):
        if group["path_id"].nunique() < 2:
            raise ValueError(
                "Alternative path group must contain at least "
                "two paths: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id}"
            )

        path_orders = (
            group[
                [
                    "path_id",
                    "path_order_numeric",
                ]
            ]
            .drop_duplicates()
        )

        duplicate_path_orders = (
            path_orders[
                "path_order_numeric"
            ].duplicated(
                keep=False
            )
        )

        if duplicate_path_orders.any():
            bad = path_orders.loc[
                duplicate_path_orders
            ].sort_values(
                [
                    "path_order_numeric",
                    "path_id",
                ]
            )

            raise ValueError(
                "Duplicate path_order values within "
                "alternative path group: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id}\n"
                + bad.to_string(index=False)
            )

        for path_id, path_rows in group.groupby(
            "path_id",
            sort=False,
        ):
            if path_rows["path_label"].nunique() != 1:
                raise ValueError(
                    "Inconsistent path_label for "
                    f"{catalog_year} / {credential_id} / "
                    f"{path_group_id} / {path_id}"
                )

            if (
                path_rows[
                    "path_order_numeric"
                ].nunique()
                != 1
            ):
                raise ValueError(
                    "Inconsistent path_order for "
                    f"{catalog_year} / {credential_id} / "
                    f"{path_group_id} / {path_id}"
                )

            if (
                path_rows[
                    "path_expected_applied_hours_numeric"
                ].nunique()
                != 1
            ):
                raise ValueError(
                    "Inconsistent expected applied hours for "
                    f"{catalog_year} / {credential_id} / "
                    f"{path_group_id} / {path_id}"
                )

    return rows



def validate_alternative_requirement_paths(
    paths: pd.DataFrame,
    requirements: pd.DataFrame,
) -> None:
    if paths.empty:
        return

    required_columns = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "credit_hours",
    }

    missing = required_columns - set(requirements.columns)

    if missing:
        raise KeyError(
            "Requirements file missing columns needed for "
            "alternative-path validation: "
            + ", ".join(sorted(missing))
        )

    req = requirements[
        [
            "catalog_year",
            "credential_id",
            "requirement_id",
            "credit_hours",
        ]
    ].copy()

    for column in [
        "catalog_year",
        "credential_id",
        "requirement_id",
    ]:
        req[column] = (
            req[column]
            .astype(str)
            .str.strip()
        )

    membership = paths.merge(
        req[
            [
                "catalog_year",
                "credential_id",
                "requirement_id",
            ]
        ].drop_duplicates(),
        on=[
            "catalog_year",
            "credential_id",
            "requirement_id",
        ],
        how="left",
        indicator=True,
    )

    missing_requirements = membership[
        membership["_merge"].ne("both")
    ]

    if not missing_requirements.empty:
        raise ValueError(
            "Alternative-path policy references requirements "
            "not present in the exact credential/catalog:\n"
            + missing_requirements[
                [
                    "catalog_year",
                    "credential_id",
                    "path_group_id",
                    "path_id",
                    "requirement_id",
                ]
            ].to_string(index=False)
        )

    path_group_counts = (
        paths.groupby(
            [
                "catalog_year",
                "credential_id",
            ]
        )["path_group_id"]
        .nunique()
    )

    multiple_groups = path_group_counts[
        path_group_counts > 1
    ]

    if not multiple_groups.empty:
        raise ValueError(
            "Current alternative-path evaluator supports "
            "one path group per credential. Found multiple groups: "
            + ", ".join(
                f"{catalog_year} / {credential_id}"
                for catalog_year, credential_id
                in multiple_groups.index
            )
        )

    credit_variance = (
        req.groupby(
            [
                "catalog_year",
                "credential_id",
                "requirement_id",
            ],
            sort=False,
        )["credit_hours"]
        .nunique(dropna=False)
    )

    mapped_keys = {
        (
            str(row["catalog_year"]),
            str(row["credential_id"]),
            str(row["requirement_id"]),
        )
        for _, row in paths.iterrows()
    }

    bad_credit_keys = [
        key
        for key, count in credit_variance.items()
        if count > 1 and key in mapped_keys
    ]

    if bad_credit_keys:
        raise ValueError(
            "Alternative-path requirement has inconsistent "
            "credit_hours across option rows: "
            + ", ".join(
                " / ".join(key)
                for key in bad_credit_keys
            )
        )

    req_unique = (
        req.drop_duplicates(
            subset=[
                "catalog_year",
                "credential_id",
                "requirement_id",
            ],
            keep="first",
        )
        .copy()
    )

    req_unique["credit_hours_numeric"] = pd.to_numeric(
        req_unique["credit_hours"],
        errors="coerce",
    )

    for (
        catalog_year,
        credential_id,
        path_group_id,
        path_id,
    ), path_rows in paths.groupby(
        [
            "catalog_year",
            "credential_id",
            "path_group_id",
            "path_id",
        ],
        sort=False,
    ):
        requirement_ids = set(
            path_rows["requirement_id"]
        )

        selected = req_unique[
            req_unique["catalog_year"].eq(
                str(catalog_year)
            )
            & req_unique["credential_id"].eq(
                str(credential_id)
            )
            & req_unique["requirement_id"].isin(
                requirement_ids
            )
        ]

        if selected[
            "credit_hours_numeric"
        ].isna().any():
            raise ValueError(
                "Non-numeric applied hours in alternative path: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id} / {path_id}"
            )

        actual_hours = float(
            selected[
                "credit_hours_numeric"
            ].sum()
        )

        expected_values = path_rows[
            "path_expected_applied_hours_numeric"
        ].unique()

        if len(expected_values) != 1:
            raise ValueError(
                "Inconsistent expected applied hours for path: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id} / {path_id}"
            )

        expected_hours = float(
            expected_values[0]
        )

        if abs(actual_hours - expected_hours) > 1e-9:
            raise ValueError(
                "Alternative-path applied-hour mismatch: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id} / {path_id}: "
                f"requirements={actual_hours:g}, "
                f"policy={expected_hours:g}"
            )



def build_alternative_path_lookup(
    paths: pd.DataFrame,
) -> dict[tuple[str, str], pd.DataFrame]:
    if paths.empty:
        return {}

    return {
        (
            str(catalog_year),
            str(credential_id),
        ): group.copy()
        for (
            catalog_year,
            credential_id,
        ), group in paths.groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            sort=False,
        )
    }


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
    catalog_year: str,
    group: pd.DataFrame,
    available_courses: set[str],
    core_lookup: dict[tuple[str, str], set[str]],
    compound_alternatives: dict[str, list[list[str]]],
    used_courses: set[str] | None = None,
    course_lookup: dict[str, dict] | None = None,
    prefer_earliest_compound_completion: bool = False,
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
        satisfied = [
            (
                alternative_index,
                list(alternative),
            )
            for alternative_index, alternative
            in enumerate(alternatives)
            if set(alternative).issubset(
                normalized_available
            )
        ]

        if satisfied:
            if (
                prefer_earliest_compound_completion
                and course_lookup is not None
            ):
                def compound_completion_score(item):
                    alternative_index, alternative = item

                    term_sorts = [
                        int(
                            course_lookup[
                                course_code
                            ]["term_sort"]
                        )
                        for course_code in alternative
                        if course_code in course_lookup
                    ]

                    completion_term = (
                        max(term_sorts)
                        if len(term_sorts)
                        == len(alternative)
                        else float("inf")
                    )

                    return (
                        completion_term,
                        alternative_index,
                    )

                _, selected_alternative = min(
                    satisfied,
                    key=compound_completion_score,
                )

                return (
                    "MET",
                    selected_alternative,
                )

            return (
                "MET",
                satisfied[0][1],
            )

        partial_matches = sorted({
            course
            for alternative in alternatives
            for course in alternative
            if course in normalized_available
        })

        return "UNMET", partial_matches

    matched = []
    missing_core_keys = []

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

            lookup_key = (
                str(catalog_year),
                str(normalized_bucket),
            )

            if lookup_key not in core_lookup:
                missing_core_keys.append(
                    lookup_key
                )
                continue

            bucket_courses = core_lookup[
                lookup_key
            ]

            bucket_matches = sorted(
                normalized_available.intersection(
                    bucket_courses
                )
            )

            matched.extend(bucket_matches)

    if missing_core_keys:
        return (
            "UNRESOLVED_CORE_LOOKUP_MISSING",
            [],
        )

    required = int(group.iloc[0]["min_required"])
    matched = sorted(set(matched))

    if len(matched) >= required:
        return "MET", matched[:required]

    # TRIPWIRE (2026-07-16, starvation repairs): if this requirement's
    # single COURSE option was already consumed by a sibling requirement
    # in the same credential (one-course-one-slot allocation), say so
    # loudly instead of reporting a bare UNMET. A single-option course
    # requirement starving on its own course is the signature of a
    # duplicated requirement row or a merged credential (see the
    # Safety, Health and/,and Environment Oxford-comma collision that
    # locked two programs at zero completions, diagnosed 2026-07-16).
    # Completion arithmetic is unchanged: this status still counts as a
    # missing requirement. It exists so this defect class can never
    # again hide inside ordinary UNMET noise.
    course_option_values = [
        normalize_course_code(option["option_value"])
        for _, option in group.iterrows()
        if str(option["option_type"]).strip().upper() == "COURSE"
    ]

    if (
        used_courses
        and len(course_option_values) == 1
        and course_option_values[0] in used_courses
    ):
        return "UNMET_CONSUMED_BY_SIBLING", matched

    return "UNMET", matched


def audit_elective_requirement(
    requirement_id: str,
    catalog_year: str,
    required_credit_hours: int,
    available_courses: set[str],
    elective_rules: dict[str, dict],
    academic_course_lookup: dict[str, set[str]],
    core_lookup: dict[tuple[str, str], set[str]],
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
            "SUBJECT_AREA_ELECTIVE": (
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

        required_core_keys = [
            (
                str(catalog_year),
                "LANGUAGE_PHILOSOPHY_AND_CULTURE_CORE",
            ),
            (
                str(catalog_year),
                "CREATIVE_ARTS_CORE",
            ),
        ]

        missing_core_keys = [
            lookup_key
            for lookup_key
            in required_core_keys
            if lookup_key not in core_lookup
        ]

        if missing_core_keys:
            return (
                "UNRESOLVED_ELECTIVE_MISSING_CORE_LOOKUP",
                [],
            )

        allowed_courses = set()

        for lookup_key in required_core_keys:
            allowed_courses.update(
                core_lookup[
                    lookup_key
                ]
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


def audit_student_credential_single_stream(
    student_id: str,
    catalog_year: str,
    credential_id: str,
    credential_requirements: pd.DataFrame,
    course_lookup: dict[str, dict],
    core_lookup: dict[tuple[str, str], set[str]],
    elective_rules: dict[str, dict],
    academic_course_lookup: dict[str, set[str]],
    compound_alternatives: dict[str, list[list[str]]],
    initial_used_courses: set[str] | None = None,
    prefer_earliest_compound_completion: bool = False,
) -> list[dict]:
    used_courses = set(
        initial_used_courses
        if initial_used_courses is not None
        else set()
    )
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
                catalog_year=str(catalog_year),
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
                compound_alternatives=compound_alternatives,
                used_courses=used_courses,
                course_lookup=course_lookup,
                prefer_earliest_compound_completion=(
                    prefer_earliest_compound_completion
                ),
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



def matched_courses_from_detail(
    detail_rows: list[dict],
) -> set[str]:
    matched_courses = set()

    for row in detail_rows:
        if str(
            row.get("status", "")
        ).strip().upper() != "MET":
            continue

        for value in str(
            row.get(
                "matched_options",
                "",
            )
        ).split(";"):
            course_code = normalize_course_code(
                value
            )

            if course_code:
                matched_courses.add(
                    course_code
                )

    return matched_courses


def path_selection_score(
    detail_rows: list[dict],
    common_rows: list[dict],
    requirement_hours: dict[str, float],
    path_order: int,
    path_id: str,
) -> tuple:
    if not detail_rows:
        raise ValueError(
            f"Alternative path contains no audit rows: {path_id}"
        )

    statuses = [
        str(
            row.get(
                "status",
                "",
            )
        ).strip().upper()
        for row in detail_rows
    ]

    complete = all(
        status == "MET"
        for status in statuses
    )

    if complete:
        completion_terms = []

        # For two complete alternative paths, compare the
        # completion term of the credential through each path,
        # not merely the completion term of the path-specific
        # requirements. Common requirements therefore participate
        # in the completion-term tie-break.
        for row in common_rows + detail_rows:
            value = pd.to_numeric(
                row.get(
                    "latest_matched_term_sort",
                    "",
                ),
                errors="coerce",
            )

            if pd.notna(value):
                completion_terms.append(
                    float(value)
                )

        completion_term = (
            max(completion_terms)
            if completion_terms
            else float("inf")
        )

        return (
            0,
            completion_term,
            int(path_order),
            str(path_id),
        )

    missing_ids = [
        str(
            row.get(
                "requirement_id",
                "",
            )
        )
        for row, status in zip(
            detail_rows,
            statuses,
        )
        if status != "MET"
    ]

    missing_requirements = len(
        missing_ids
    )

    missing_applied_hours = sum(
        float(
            requirement_hours.get(
                requirement_id,
                0.0,
            )
        )
        for requirement_id in missing_ids
    )

    return (
        1,
        missing_requirements,
        missing_applied_hours,
        int(path_order),
        str(path_id),
    )


def annotate_path_rows(
    rows: list[dict],
    *,
    path_group_id: str = "",
    path_id: str = "",
    path_label: str = "",
    path_order: str = "",
    path_expected_applied_hours: str = "",
    path_selected: str = "",
) -> None:
    for row in rows:
        row["path_group_id"] = path_group_id
        row["path_id"] = path_id
        row["path_label"] = path_label
        row["path_order"] = path_order
        row[
            "path_expected_applied_hours"
        ] = path_expected_applied_hours
        row["path_selected"] = path_selected


def audit_student_credential(
    student_id: str,
    catalog_year: str,
    credential_id: str,
    credential_requirements: pd.DataFrame,
    course_lookup: dict[str, dict],
    core_lookup: dict[tuple[str, str], set[str]],
    elective_rules: dict[str, dict],
    academic_course_lookup: dict[str, set[str]],
    compound_alternatives: dict[str, list[list[str]]],
    alternative_path_lookup: dict[
        tuple[str, str],
        pd.DataFrame,
    ] | None = None,
) -> list[dict]:
    alternative_path_lookup = (
        alternative_path_lookup or {}
    )

    policy = alternative_path_lookup.get(
        (
            str(catalog_year),
            str(credential_id),
        )
    )

    # Ordinary credentials retain the existing single-stream
    # behavior exactly.
    if policy is None or policy.empty:
        rows = (
            audit_student_credential_single_stream(
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

        annotate_path_rows(
            rows
        )

        return rows

    mapped_requirement_ids = set(
        policy[
            "requirement_id"
        ]
        .astype(str)
        .str.strip()
    )

    common_requirements = (
        credential_requirements[
            ~credential_requirements[
                "requirement_id"
            ]
            .astype(str)
            .isin(
                mapped_requirement_ids
            )
        ]
        .copy()
    )

    common_rows = (
        audit_student_credential_single_stream(
            student_id=student_id,
            catalog_year=catalog_year,
            credential_id=credential_id,
            credential_requirements=common_requirements,
            course_lookup=course_lookup,
            core_lookup=core_lookup,
            elective_rules=elective_rules,
            academic_course_lookup=academic_course_lookup,
            compound_alternatives=compound_alternatives,
        )
    )

    annotate_path_rows(
        common_rows
    )

    common_used_courses = (
        matched_courses_from_detail(
            common_rows
        )
    )

    requirement_hours = (
        credential_requirements[
            [
                "requirement_id",
                "credit_hours",
            ]
        ]
        .drop_duplicates(
            subset=[
                "requirement_id"
            ],
            keep="first",
        )
        .assign(
            credit_hours_numeric=lambda df:
                pd.to_numeric(
                    df["credit_hours"],
                    errors="coerce",
                ).fillna(0.0)
        )
        .set_index(
            "requirement_id"
        )["credit_hours_numeric"]
        .to_dict()
    )

    all_rows = list(
        common_rows
    )

    for (
        path_group_id,
        group_policy,
    ) in policy.groupby(
        "path_group_id",
        sort=False,
    ):
        path_metadata = (
            group_policy[
                [
                    "path_id",
                    "path_label",
                    "path_order_numeric",
                    "path_expected_applied_hours_numeric",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                [
                    "path_order_numeric",
                    "path_id",
                ],
                kind="mergesort",
            )
        )

        candidates = []

        for _, metadata in path_metadata.iterrows():
            path_id = str(
                metadata["path_id"]
            )

            path_policy = group_policy[
                group_policy[
                    "path_id"
                ].eq(path_id)
            ]

            path_requirement_ids = set(
                path_policy[
                    "requirement_id"
                ]
                .astype(str)
                .str.strip()
            )

            path_requirements = (
                credential_requirements[
                    credential_requirements[
                        "requirement_id"
                    ]
                    .astype(str)
                    .isin(
                        path_requirement_ids
                    )
                ]
                .copy()
            )

            path_rows = (
                audit_student_credential_single_stream(
                    student_id=student_id,
                    catalog_year=catalog_year,
                    credential_id=credential_id,
                    credential_requirements=path_requirements,
                    course_lookup=course_lookup,
                    core_lookup=core_lookup,
                    elective_rules=elective_rules,
                    academic_course_lookup=academic_course_lookup,
                    compound_alternatives=compound_alternatives,
                    initial_used_courses=set(
                        common_used_courses
                    ),
                    prefer_earliest_compound_completion=True,
                )
            )

            path_label = str(
                metadata["path_label"]
            )

            path_order = int(
                metadata[
                    "path_order_numeric"
                ]
            )

            expected_hours = float(
                metadata[
                    "path_expected_applied_hours_numeric"
                ]
            )

            annotate_path_rows(
                path_rows,
                path_group_id=str(
                    path_group_id
                ),
                path_id=path_id,
                path_label=path_label,
                path_order=str(
                    path_order
                ),
                path_expected_applied_hours=(
                    f"{expected_hours:g}"
                ),
                path_selected="FALSE",
            )

            score = path_selection_score(
                path_rows,
                common_rows=common_rows,
                requirement_hours=requirement_hours,
                path_order=path_order,
                path_id=path_id,
            )

            candidates.append(
                {
                    "path_id": path_id,
                    "score": score,
                    "rows": path_rows,
                }
            )

        if not candidates:
            raise ValueError(
                "Alternative path group produced no candidates: "
                f"{catalog_year} / {credential_id} / "
                f"{path_group_id}"
            )

        selected = min(
            candidates,
            key=lambda candidate:
                candidate["score"],
        )

        for candidate in candidates:
            selected_flag = (
                "TRUE"
                if candidate["path_id"]
                == selected["path_id"]
                else "FALSE"
            )

            for row in candidate["rows"]:
                row[
                    "path_selected"
                ] = selected_flag

            all_rows.extend(
                candidate["rows"]
            )

    return all_rows


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

    alternative_paths = (
        load_alternative_requirement_paths()
    )

    validate_alternative_requirement_paths(
        alternative_paths,
        requirements,
    )

    alternative_path_lookup = (
        build_alternative_path_lookup(
            alternative_paths
        )
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
                    alternative_path_lookup=alternative_path_lookup,
                )
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_df.to_csv(DETAIL_OUTPUT, index=False)

    summary_rows = []

    for (student_id, catalog_year, credential_id), group in detail_df.groupby(
        ["student_id", "catalog_year", "credential_id"]
    ):
        path_group = (
            group["path_group_id"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        path_selected = (
            group["path_selected"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        counted = group[
            path_group.eq("")
            | path_selected.eq("TRUE")
        ].copy()

        total = len(counted)

        met = (
            counted["status"]
            == "MET"
        ).sum()

        unresolved = (
            counted["status"]
            .astype(str)
            .str.startswith(
                "UNRESOLVED"
            )
            .sum()
        )

        missing = (
            total
            - met
            - unresolved
        )

        audit_status = get_audit_status(
            missing,
            unresolved,
        )

        (
            award_term_sort,
            award_term_taken,
        ) = summarize_award_term(
            counted,
            audit_status,
        )

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
