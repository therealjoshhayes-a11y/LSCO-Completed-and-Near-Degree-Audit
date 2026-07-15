from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import hashlib
import math
import re
from typing import Iterable

import pandas as pd


# =============================================================================
# LSCO COURSE-TYPE FORENSIC REVIEW
# =============================================================================
#
# Goal:
#   Test whether systematic failures in EXACT, ANY_N, CORE_BUCKET, or ELECTIVE
#   logic are synthetically suppressing modeled completers.
#
# Privacy:
#   - RESTRICTED workbook contains student-level evidence and stays local.
#   - FERPA_SAFE workbook contains aggregate tables only with small-cell
#     suppression and is suitable for upload for collaborative review.
#
# Scope:
#   - Uses the best relaxed-eligible catalog for each student × credential
#     lineage, where continuity_break is ignored.
#   - Includes COMPLETE and 1–3-missing student-lineages.
#   - Scans audit detail in chunks.
#
# =============================================================================


# =============================================================================
# PATHS
# =============================================================================

SUMMARY_PATH = Path(
    "data/processed/full_actual_audit/"
    "full_actual_credential_summary.csv"
)

DETAIL_PATH = Path(
    "data/processed/full_actual_audit/"
    "full_actual_audit_results.csv"
)

HISTORY_PATH = Path(
    "data/processed/normalized_actual_student_course_history.csv"
)

ELIGIBILITY_PATH = Path(
    "data/processed/student_catalog_eligibility.csv"
)

REQUIREMENTS_PATH = Path(
    "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)

CORE_LOOKUP_PATH = Path(
    "data/processed/core_bucket_lookup_multicatalog.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"course_type_forensic_review_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_LSCO_Course_Type_Forensic_Review.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_LSCO_Course_Type_Forensic_Review.xlsx"
)

SAFE_THRESHOLD = 5


# =============================================================================
# HELPERS
# =============================================================================

def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(
            f"Required file not found: {path.resolve()}"
        )


def first_existing(
    columns: Iterable[str],
    candidates: list[str],
    *,
    required: bool = True,
    label: str = "column",
) -> str | None:
    available = set(columns)

    for candidate in candidates:
        if candidate in available:
            return candidate

    if required:
        raise SystemExit(
            f"Could not find {label}. Tried: "
            + ", ".join(candidates)
        )

    return None


def truthy(value: object) -> bool:
    return str(value).strip().upper() in {
        "TRUE",
        "1",
        "YES",
        "Y",
        "T",
        "ELIGIBLE",
        "PASSED",
        "MET",
    }


def normalize_course_code(value: object) -> str:
    text = re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    )

    match = re.search(
        r"([A-Z]{2,5})(\d{4})",
        text,
    )

    if not match:
        return ""

    return match.group(1) + match.group(2)


def parse_course_list(value: object) -> list[str]:
    text = str(value).upper()

    found = re.findall(
        r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4})\b",
        text,
    )

    return sorted(
        {
            subject + number
            for subject, number
            in found
        }
    )


def course_subject(value: object) -> str:
    code = normalize_course_code(value)

    match = re.match(
        r"^([A-Z]{2,5})\d{4}$",
        code,
    )

    return match.group(1) if match else ""


def normalize_bucket(value: object) -> str:
    text = str(value).upper()
    text = text.replace("*", "")
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "LIFE OR PHYSICAL SCIENCES":
            "LIFE AND PHYSICAL SCIENCES",
        "LIFE OR PHYSICAL SCIENCE":
            "LIFE AND PHYSICAL SCIENCES",
        "LANGUAGE PHILOSOPHY AND CULTURE":
            "LANGUAGE, PHILOSOPHY AND CULTURE",
        "GOVERNMENT / POLITICAL SCIENCE":
            "GOVERNMENT/POLITICAL SCIENCE",
    }

    return aliases.get(text, text)


def derive_lineage(credential_id: object) -> str:
    value = str(credential_id).strip().upper()

    value = re.sub(
        r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026)$",
        "",
        value,
    )

    value = re.sub(
        r"_(2021|2022|2023|2024|2025|2026)$",
        "",
        value,
    )

    return value


def catalog_rank(value: object) -> int:
    match = re.match(
        r"^\s*(20\d{2})-(20\d{2})\s*$",
        str(value),
    )

    if not match:
        return -1

    return int(match.group(1))


def pseudonym(student_id: object) -> str:
    digest = hashlib.sha256(
        str(student_id).encode("utf-8")
    ).hexdigest()

    return "S-" + digest[:12].upper()


def safe_count(value: object) -> object:
    if pd.isna(value):
        return value

    try:
        number = int(value)
    except Exception:
        return value

    if 0 < number < SAFE_THRESHOLD:
        return f"<{SAFE_THRESHOLD}"

    return number


def suppress_counts(
    dataframe: pd.DataFrame,
    count_columns: list[str],
) -> pd.DataFrame:
    result = dataframe.copy()

    for column in count_columns:
        if column in result.columns:
            result[column] = result[column].map(
                safe_count
            )

    return result


def join_unique(values: Iterable[object]) -> str:
    unique = sorted(
        {
            str(value).strip()
            for value in values
            if str(value).strip()
        }
    )

    return " | ".join(unique)


def union_sets(values: Iterable[set[str]]) -> set[str]:
    result: set[str] = set()

    for value in values:
        result.update(value)

    return result


def parse_int(value: object) -> int | None:
    number = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(number):
        return None

    return int(number)


def format_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    dataframe: pd.DataFrame,
) -> None:
    worksheet = writer.sheets[sheet_name]
    workbook = writer.book

    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#14532D",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        }
    )

    for column_index, column in enumerate(
        dataframe.columns
    ):
        worksheet.write(
            0,
            column_index,
            column,
            header,
        )

        sample_values = []

        for value in dataframe[column].head(5000):
            if pd.isna(value):
                sample_values.append("")
            else:
                sample_values.append(str(value))

        width = max(
            len(str(column)) + 2,
            max(
                [len(value) for value in sample_values]
                + [0]
            )
            + 2,
        )

        worksheet.set_column(
            column_index,
            column_index,
            min(width, 48),
        )

    worksheet.freeze_panes(1, 0)

    if len(dataframe.columns) > 0:
        worksheet.autofilter(
            0,
            0,
            max(len(dataframe), 1),
            len(dataframe.columns) - 1,
        )


# =============================================================================
# VALIDATE INPUT FILES
# =============================================================================

for path in [
    SUMMARY_PATH,
    DETAIL_PATH,
    HISTORY_PATH,
    ELIGIBILITY_PATH,
    REQUIREMENTS_PATH,
    CORE_LOOKUP_PATH,
]:
    require_file(path)


# =============================================================================
# LOAD SUMMARY + RELAXED ELIGIBILITY
# =============================================================================

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

eligibility = pd.read_csv(
    ELIGIBILITY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

required_summary_columns = {
    "student_id",
    "catalog_year",
    "credential_id",
    "audit_status",
    "requirements_missing",
}

required_eligibility_columns = {
    "student_id",
    "catalog_year",
    "earned_course_in_catalog_year",
    "has_activity_after_catalog_life",
    "continuity_break",
}

missing_summary_columns = (
    required_summary_columns
    - set(summary.columns)
)

missing_eligibility_columns = (
    required_eligibility_columns
    - set(eligibility.columns)
)

if missing_summary_columns:
    raise SystemExit(
        "Summary missing columns: "
        + ", ".join(
            sorted(missing_summary_columns)
        )
    )

if missing_eligibility_columns:
    raise SystemExit(
        "Eligibility missing columns: "
        + ", ".join(
            sorted(missing_eligibility_columns)
        )
    )

summary[
    "requirements_missing_numeric"
] = pd.to_numeric(
    summary["requirements_missing"],
    errors="coerce",
)

summary[
    "credential_lineage"
] = summary[
    "credential_id"
].map(
    derive_lineage
)

summary[
    "catalog_rank"
] = summary[
    "catalog_year"
].map(
    catalog_rank
)

eligibility[
    "earned_in_catalog_year_bool"
] = eligibility[
    "earned_course_in_catalog_year"
].map(
    truthy
)

eligibility[
    "activity_after_catalog_life_bool"
] = eligibility[
    "has_activity_after_catalog_life"
].map(
    truthy
)

eligibility[
    "continuity_break_bool"
] = eligibility[
    "continuity_break"
].map(
    truthy
)

eligibility[
    "relaxed_catalog_eligible"
] = (
    eligibility[
        "earned_in_catalog_year_bool"
    ]
    & ~eligibility[
        "activity_after_catalog_life_bool"
    ]
)

eligible_keys = eligibility[
    eligibility[
        "relaxed_catalog_eligible"
    ]
][
    [
        "student_id",
        "catalog_year",
        "continuity_break_bool",
    ]
].drop_duplicates(
    subset=[
        "student_id",
        "catalog_year",
    ]
)

eligible_summary = summary.merge(
    eligible_keys,
    on=[
        "student_id",
        "catalog_year",
    ],
    how="inner",
    validate="many_to_one",
)

eligible_summary = eligible_summary.sort_values(
    [
        "student_id",
        "credential_lineage",
        "requirements_missing_numeric",
        "catalog_rank",
        "credential_id",
    ],
    ascending=[
        True,
        True,
        True,
        False,
        False,
    ],
    kind="mergesort",
)

selected = eligible_summary.drop_duplicates(
    subset=[
        "student_id",
        "credential_lineage",
    ],
    keep="first",
).copy()

selected["gap_band"] = selected[
    "requirements_missing_numeric"
].map(
    lambda value:
        "COMPLETE"
        if value == 0
        else (
            f"{int(value)} MISSING"
            if pd.notna(value)
            and 1 <= int(value) <= 3
            else "4+ MISSING"
        )
)

population = selected[
    selected[
        "requirements_missing_numeric"
    ].between(
        0,
        3,
        inclusive="both",
    )
].copy()

population["join_key"] = (
    population["student_id"].astype(str)
    + "||"
    + population["credential_id"].astype(str)
    + "||"
    + population["catalog_year"].astype(str)
)

population_keys = set(
    population["join_key"]
)


# =============================================================================
# LOAD HISTORY
# =============================================================================

history = pd.read_csv(
    HISTORY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

history_student_col = first_existing(
    history.columns,
    [
        "student_id",
        "student",
        "banner_id",
    ],
    label="history student ID",
)

history_course_col = first_existing(
    history.columns,
    [
        "course_code",
        "normalized_course_code",
        "course",
    ],
    label="history course code",
)

history_passed_col = first_existing(
    history.columns,
    [
        "passed",
        "earned_for_catalog",
        "course_passed",
    ],
    label="history passed flag",
)

history_grade_col = first_existing(
    history.columns,
    [
        "final_grade",
        "grade",
    ],
    required=False,
)

history_credit_col = first_existing(
    history.columns,
    [
        "credit_hours",
        "credits",
        "earned_credit_hours",
    ],
    required=False,
)

history["passed_bool"] = history[
    history_passed_col
].map(
    truthy
)

history["normalized_course"] = history[
    history_course_col
].map(
    normalize_course_code
)

history["course_subject"] = history[
    "normalized_course"
].map(
    course_subject
)

if history_credit_col:
    history[
        "credit_hours_numeric"
    ] = pd.to_numeric(
        history[history_credit_col],
        errors="coerce",
    )
else:
    history[
        "credit_hours_numeric"
    ] = pd.NA

passed_history = history[
    history["passed_bool"]
    & history["normalized_course"].ne("")
].copy()

passed_course_sets = (
    passed_history.groupby(
        history_student_col
    )[
        "normalized_course"
    ]
    .agg(
        lambda values:
            set(values)
    )
    .to_dict()
)

passed_subject_sets = (
    passed_history.groupby(
        history_student_col
    )[
        "course_subject"
    ]
    .agg(
        lambda values:
            {
                value
                for value in values
                if value
            }
    )
    .to_dict()
)

course_credit_lookup = (
    passed_history.groupby(
        [
            history_student_col,
            "normalized_course",
        ],
        dropna=False,
    )[
        "credit_hours_numeric"
    ]
    .max()
    .to_dict()
)


# =============================================================================
# LOAD REQUIREMENTS MASTER FOR RULE METADATA
# =============================================================================

requirements = pd.read_csv(
    REQUIREMENTS_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

req_id_col = first_existing(
    requirements.columns,
    [
        "requirement_id",
        "requirement_group_id",
    ],
    label="requirements master requirement ID",
)

req_rule_col = first_existing(
    requirements.columns,
    [
        "rule_type",
        "requirement_type",
    ],
    required=False,
)

req_n_col = first_existing(
    requirements.columns,
    [
        "required_count",
        "required_n",
        "minimum_count",
        "courses_required",
        "option_count_required",
        "n_required",
    ],
    required=False,
)

req_credit_col = first_existing(
    requirements.columns,
    [
        "credit_hours",
        "required_credit_hours",
        "minimum_credit_hours",
    ],
    required=False,
)

req_elective_policy_col = first_existing(
    requirements.columns,
    [
        "elective_policy",
        "resolver_policy",
        "elective_resolver",
        "policy_code",
    ],
    required=False,
)

req_option_course_col = first_existing(
    requirements.columns,
    [
        "course_code",
        "option_course_code",
        "normalized_course_code",
    ],
    required=False,
)

req_subject_col = first_existing(
    requirements.columns,
    [
        "allowed_subjects",
        "subject_filter",
        "rubric_filter",
        "elective_subjects",
    ],
    required=False,
)

requirements[
    "normalized_option_course"
] = (
    requirements[req_option_course_col].map(
        normalize_course_code
    )
    if req_option_course_col
    else ""
)

requirements[
    "required_n_numeric"
] = (
    pd.to_numeric(
        requirements[req_n_col],
        errors="coerce",
    )
    if req_n_col
    else pd.NA
)

requirements[
    "required_credit_numeric"
] = (
    pd.to_numeric(
        requirements[req_credit_col],
        errors="coerce",
    )
    if req_credit_col
    else pd.NA
)

req_grouped = (
    requirements.groupby(
        req_id_col,
        dropna=False,
    )
    .agg(
        master_rule_type=(
            req_rule_col,
            "first",
        )
        if req_rule_col
        else (
            req_id_col,
            lambda values: "",
        ),
        required_n_master=(
            "required_n_numeric",
            "max",
        ),
        required_credit_master=(
            "required_credit_numeric",
            "max",
        ),
        master_option_courses=(
            "normalized_option_course",
            lambda values:
                sorted(
                    {
                        value
                        for value in values
                        if value
                    }
                ),
        ),
        elective_policy=(
            req_elective_policy_col,
            "first",
        )
        if req_elective_policy_col
        else (
            req_id_col,
            lambda values: "",
        ),
        allowed_subjects_master=(
            req_subject_col,
            "first",
        )
        if req_subject_col
        else (
            req_id_col,
            lambda values: "",
        ),
    )
    .reset_index()
    .rename(
        columns={
            req_id_col:
                "requirement_id"
        }
    )
)


# =============================================================================
# LOAD CORE LOOKUP
# =============================================================================

core = pd.read_csv(
    CORE_LOOKUP_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

core_catalog_col = first_existing(
    core.columns,
    [
        "catalog_year",
        "catalog",
    ],
    label="core catalog",
)

core_bucket_col = first_existing(
    core.columns,
    [
        "bucket_name",
        "core_bucket",
        "requirement_bucket",
    ],
    label="core bucket",
)

core_course_col = first_existing(
    core.columns,
    [
        "course_code",
        "normalized_course_code",
    ],
    label="core course",
)

core[
    "normalized_bucket"
] = core[
    core_bucket_col
].map(
    normalize_bucket
)

core[
    "normalized_course"
] = core[
    core_course_col
].map(
    normalize_course_code
)

core_lookup = (
    core.groupby(
        [
            core_catalog_col,
            "normalized_bucket",
        ],
        dropna=False,
    )[
        "normalized_course"
    ]
    .agg(
        lambda values:
            {
                value
                for value in values
                if value
            }
    )
    .to_dict()
)

cross_catalog_core_lookup = (
    core.groupby(
        "normalized_bucket",
        dropna=False,
    )[
        "normalized_course"
    ]
    .agg(
        lambda values:
            {
                value
                for value in values
                if value
            }
    )
    .to_dict()
)


# =============================================================================
# SCAN AUDIT DETAIL
# =============================================================================

detail_columns = [
    "student_id",
    "catalog_year",
    "credential_id",
    "requirement_id",
    "rule_type",
    "status",
    "matched_options",
    "required_options",
    "option_types",
    "used_course_count",
]

parts = []
rows_scanned = 0
rows_retained = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        low_memory=False,
        usecols=detail_columns,
        chunksize=250_000,
    ),
    start=1,
):
    chunk = chunk.fillna("")

    rows_scanned += len(chunk)

    chunk["join_key"] = (
        chunk["student_id"].astype(str)
        + "||"
        + chunk["credential_id"].astype(str)
        + "||"
        + chunk["catalog_year"].astype(str)
    )

    kept = chunk[
        chunk["join_key"].isin(
            population_keys
        )
    ].copy()

    if not kept.empty:
        parts.append(kept)
        rows_retained += len(kept)

    if chunk_number % 25 == 0:
        print(
            f"Scanned {rows_scanned:,} detail rows; "
            f"retained {rows_retained:,}"
        )

if not parts:
    raise SystemExit(
        "No detail rows matched the selected population."
    )

detail = pd.concat(
    parts,
    ignore_index=True,
)

detail = detail.merge(
    population[
        [
            "join_key",
            "student_id",
            "credential_lineage",
            "credential_id",
            "catalog_year",
            "audit_status",
            "requirements_missing_numeric",
            "gap_band",
            "continuity_break_bool",
        ]
    ],
    on="join_key",
    how="left",
    validate="many_to_one",
    suffixes=(
        "",
        "_population",
    ),
)

detail = detail.merge(
    req_grouped,
    on="requirement_id",
    how="left",
    validate="many_to_one",
)

detail["status_upper"] = detail[
    "status"
].astype(str).str.strip().str.upper()

detail["rule_type_upper"] = detail[
    "rule_type"
].astype(str).str.strip().str.upper()

detail["required_course_list"] = detail[
    "required_options"
].map(
    parse_course_list
)

detail["matched_course_list"] = detail[
    "matched_options"
].map(
    parse_course_list
)

detail["master_option_courses"] = detail[
    "master_option_courses"
].map(
    lambda value:
        value
        if isinstance(value, list)
        else []
)

detail["candidate_course_list"] = detail.apply(
    lambda row:
        sorted(
            set(
                row["required_course_list"]
                + row["master_option_courses"]
            )
        ),
    axis=1,
)

detail["normalized_bucket"] = detail.apply(
    lambda row:
        normalize_bucket(
            row["required_options"]
        )
        if row["rule_type_upper"]
        == "CORE_BUCKET"
        else "",
    axis=1,
)

detail["used_course_set"] = detail[
    "matched_course_list"
].map(
    set
)

used_courses_by_lineage = (
    detail.groupby(
        "join_key",
        dropna=False,
    )[
        "used_course_set"
    ]
    .agg(
        union_sets
    )
    .to_dict()
)

unmet = detail[
    detail["status_upper"].eq(
        "UNMET"
    )
].copy()


# =============================================================================
# RULE-TYPE FORENSIC TESTS
# =============================================================================

def passed_courses_for_row(
    row: pd.Series,
) -> set[str]:
    return passed_course_sets.get(
        str(row["student_id"]),
        set(),
    )


def used_courses_for_row(
    row: pd.Series,
) -> set[str]:
    return used_courses_by_lineage.get(
        str(row["join_key"]),
        set(),
    )


def exact_passed_candidates(
    row: pd.Series,
) -> list[str]:
    return sorted(
        passed_courses_for_row(row)
        & set(row["candidate_course_list"])
    )


def exact_consumed_candidates(
    row: pd.Series,
) -> list[str]:
    return sorted(
        used_courses_for_row(row)
        & set(row["candidate_course_list"])
    )


def exact_unused_candidates(
    row: pd.Series,
) -> list[str]:
    return sorted(
        (
            passed_courses_for_row(row)
            & set(row["candidate_course_list"])
        )
        - used_courses_for_row(row)
    )


unmet[
    "passed_candidate_courses"
] = unmet.apply(
    exact_passed_candidates,
    axis=1,
)

unmet[
    "consumed_candidate_courses"
] = unmet.apply(
    exact_consumed_candidates,
    axis=1,
)

unmet[
    "unused_candidate_courses"
] = unmet.apply(
    exact_unused_candidates,
    axis=1,
)

for prefix in [
    "passed_candidate",
    "consumed_candidate",
    "unused_candidate",
]:
    source = prefix + "_courses"

    unmet[
        prefix + "_count"
    ] = unmet[source].map(len)

    unmet[
        prefix + "_text"
    ] = unmet[source].map(
        lambda values:
            " | ".join(values)
    )


# EXACT flags
unmet[
    "exact_required_course_present"
] = (
    unmet["rule_type_upper"].eq("EXACT")
    & unmet[
        "passed_candidate_count"
    ].gt(0)
)

unmet[
    "exact_required_course_unused"
] = (
    unmet["rule_type_upper"].eq("EXACT")
    & unmet[
        "unused_candidate_count"
    ].gt(0)
)

unmet[
    "exact_required_course_consumed"
] = (
    unmet["rule_type_upper"].eq("EXACT")
    & unmet[
        "consumed_candidate_count"
    ].gt(0)
)


# ANY_N required N
unmet[
    "required_n_effective"
] = pd.to_numeric(
    unmet["required_n_master"],
    errors="coerce",
)

unmet.loc[
    unmet["rule_type_upper"].eq("ANY_N")
    & unmet["required_n_effective"].isna(),
    "required_n_effective",
] = 1

unmet[
    "any_n_enough_passed"
] = (
    unmet["rule_type_upper"].eq("ANY_N")
    & (
        unmet[
            "passed_candidate_count"
        ]
        >= unmet[
            "required_n_effective"
        ]
    )
)

unmet[
    "any_n_enough_unused"
] = (
    unmet["rule_type_upper"].eq("ANY_N")
    & (
        unmet[
            "unused_candidate_count"
        ]
        >= unmet[
            "required_n_effective"
        ]
    )
)

unmet[
    "any_n_candidates_consumed"
] = (
    unmet["rule_type_upper"].eq("ANY_N")
    & unmet[
        "consumed_candidate_count"
    ].gt(0)
)


# CORE_BUCKET flags
def catalog_bucket_courses(
    row: pd.Series,
) -> set[str]:
    return core_lookup.get(
        (
            str(row["catalog_year"]),
            str(row["normalized_bucket"]),
        ),
        set(),
    )


def cross_catalog_bucket_courses(
    row: pd.Series,
) -> set[str]:
    return cross_catalog_core_lookup.get(
        str(row["normalized_bucket"]),
        set(),
    )


def bucket_passed(
    row: pd.Series,
) -> list[str]:
    return sorted(
        passed_courses_for_row(row)
        & catalog_bucket_courses(row)
    )


def bucket_unused(
    row: pd.Series,
) -> list[str]:
    return sorted(
        (
            passed_courses_for_row(row)
            & catalog_bucket_courses(row)
        )
        - used_courses_for_row(row)
    )


def bucket_cross_catalog_only(
    row: pd.Series,
) -> list[str]:
    current = catalog_bucket_courses(row)
    all_years = cross_catalog_bucket_courses(row)

    return sorted(
        passed_courses_for_row(row)
        & (all_years - current)
    )


unmet[
    "bucket_passed_candidates"
] = unmet.apply(
    bucket_passed,
    axis=1,
)

unmet[
    "bucket_unused_candidates"
] = unmet.apply(
    bucket_unused,
    axis=1,
)

unmet[
    "bucket_cross_catalog_candidates"
] = unmet.apply(
    bucket_cross_catalog_only,
    axis=1,
)

for prefix in [
    "bucket_passed",
    "bucket_unused",
    "bucket_cross_catalog",
]:
    source = prefix + "_candidates"

    unmet[
        prefix + "_count"
    ] = unmet[source].map(len)

    unmet[
        prefix + "_text"
    ] = unmet[source].map(
        lambda values:
            " | ".join(values)
    )

unmet[
    "core_bucket_has_current_candidate"
] = (
    unmet["rule_type_upper"].eq("CORE_BUCKET")
    & unmet[
        "bucket_passed_count"
    ].gt(0)
)

unmet[
    "core_bucket_has_unused_candidate"
] = (
    unmet["rule_type_upper"].eq("CORE_BUCKET")
    & unmet[
        "bucket_unused_count"
    ].gt(0)
)

unmet[
    "core_bucket_cross_catalog_only"
] = (
    unmet["rule_type_upper"].eq("CORE_BUCKET")
    & unmet[
        "bucket_passed_count"
    ].eq(0)
    & unmet[
        "bucket_cross_catalog_count"
    ].gt(0)
)


# ELECTIVE diagnostic
def parse_allowed_subjects(
    value: object,
) -> set[str]:
    text = str(value).upper()

    return {
        token
        for token in re.findall(
            r"\b[A-Z]{2,5}\b",
            text,
        )
        if token not in {
            "ANY",
            "COURSE",
            "UNUSED",
            "PASSED",
            "ELECTIVE",
            "APPROVED",
        }
    }


unmet[
    "allowed_subject_set"
] = unmet[
    "allowed_subjects_master"
].map(
    parse_allowed_subjects
)

unmet[
    "elective_policy_upper"
] = unmet[
    "elective_policy"
].astype(str).str.strip().str.upper()

def elective_candidate_courses(
    row: pd.Series,
) -> list[str]:
    if row["rule_type_upper"] != "ELECTIVE":
        return []

    passed = passed_courses_for_row(row)
    used = used_courses_for_row(row)
    unused = passed - used

    policy = row["elective_policy_upper"]
    allowed_subjects = row["allowed_subject_set"]

    if (
        "ANY_UNUSED_PASSED_COURSE" in policy
        or "UNRESTRICTED" in policy
        or policy == ""
    ):
        return sorted(unused)

    if allowed_subjects:
        return sorted(
            {
                course
                for course in unused
                if course_subject(course)
                in allowed_subjects
            }
        )

    listed = set(
        row["candidate_course_list"]
    )

    if listed:
        return sorted(
            unused & listed
        )

    return []


unmet[
    "elective_candidate_courses"
] = unmet.apply(
    elective_candidate_courses,
    axis=1,
)

unmet[
    "elective_candidate_count"
] = unmet[
    "elective_candidate_courses"
].map(len)

unmet[
    "elective_candidate_text"
] = unmet[
    "elective_candidate_courses"
].map(
    lambda values:
        " | ".join(values)
)

def elective_candidate_hours(
    row: pd.Series,
) -> float:
    total = 0.0

    for course in row[
        "elective_candidate_courses"
    ]:
        value = course_credit_lookup.get(
            (
                str(row["student_id"]),
                course,
            )
        )

        if pd.notna(value):
            total += float(value)

    return total


unmet[
    "elective_candidate_hours"
] = unmet.apply(
    elective_candidate_hours,
    axis=1,
)

unmet[
    "elective_required_hours"
] = pd.to_numeric(
    unmet["required_credit_master"],
    errors="coerce",
)

unmet[
    "elective_has_candidate_course"
] = (
    unmet["rule_type_upper"].eq("ELECTIVE")
    & unmet[
        "elective_candidate_count"
    ].gt(0)
)

unmet[
    "elective_has_enough_hours"
] = (
    unmet["rule_type_upper"].eq("ELECTIVE")
    & unmet[
        "elective_required_hours"
    ].notna()
    & (
        unmet[
            "elective_candidate_hours"
        ]
        >= unmet[
            "elective_required_hours"
        ]
    )
)


# =============================================================================
# RULE SHAPE AND PARSE DIAGNOSTICS
# =============================================================================

unmet[
    "required_options_blank"
] = unmet[
    "required_options"
].astype(str).str.strip().eq("")

unmet[
    "candidate_list_blank"
] = unmet[
    "candidate_course_list"
].map(
    len
).eq(0)

unmet[
    "malformed_course_text"
] = unmet.apply(
    lambda row:
        (
            row["rule_type_upper"]
            in {
                "EXACT",
                "ANY_N",
            }
            and not row[
                "required_options_blank"
            ]
            and row[
                "candidate_list_blank"
            ]
        ),
    axis=1,
)

unmet[
    "rule_metadata_missing"
] = unmet[
    "master_rule_type"
].astype(str).str.strip().eq("")


# =============================================================================
# AGGREGATE TABLES
# =============================================================================

kpi_rows = [
    (
        "Selected COMPLETE student-lineages",
        int(
            (
                population[
                    "requirements_missing_numeric"
                ]
                == 0
            ).sum()
        ),
    ),
    (
        "Selected 1–3 missing student-lineages",
        int(
            (
                population[
                    "requirements_missing_numeric"
                ]
                .between(
                    1,
                    3,
                    inclusive="both",
                )
            ).sum()
        ),
    ),
    (
        "Unmet detail rows",
        len(unmet),
    ),
    (
        "EXACT failures with required course passed",
        int(
            unmet[
                "exact_required_course_present"
            ].sum()
        ),
    ),
    (
        "EXACT failures with unused required course",
        int(
            unmet[
                "exact_required_course_unused"
            ].sum()
        ),
    ),
    (
        "EXACT failures with course consumed elsewhere",
        int(
            unmet[
                "exact_required_course_consumed"
            ].sum()
        ),
    ),
    (
        "ANY_N failures with enough passed options",
        int(
            unmet[
                "any_n_enough_passed"
            ].sum()
        ),
    ),
    (
        "ANY_N failures with enough unused options",
        int(
            unmet[
                "any_n_enough_unused"
            ].sum()
        ),
    ),
    (
        "CORE_BUCKET failures with current-year candidate",
        int(
            unmet[
                "core_bucket_has_current_candidate"
            ].sum()
        ),
    ),
    (
        "CORE_BUCKET failures with unused candidate",
        int(
            unmet[
                "core_bucket_has_unused_candidate"
            ].sum()
        ),
    ),
    (
        "CORE_BUCKET failures with cross-catalog-only candidate",
        int(
            unmet[
                "core_bucket_cross_catalog_only"
            ].sum()
        ),
    ),
    (
        "ELECTIVE failures with at least one candidate",
        int(
            unmet[
                "elective_has_candidate_course"
            ].sum()
        ),
    ),
    (
        "ELECTIVE failures with enough candidate hours",
        int(
            unmet[
                "elective_has_enough_hours"
            ].sum()
        ),
    ),
    (
        "Malformed EXACT/ANY_N requirement text",
        int(
            unmet[
                "malformed_course_text"
            ].sum()
        ),
    ),
    (
        "Unmet rows missing requirement metadata",
        int(
            unmet[
                "rule_metadata_missing"
            ].sum()
        ),
    ),
]

kpi_summary = pd.DataFrame(
    kpi_rows,
    columns=[
        "metric",
        "value",
    ],
)

by_rule_type = (
    unmet.groupby(
        "rule_type_upper",
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
        distinct_requirements=(
            "requirement_id",
            "nunique",
        ),
        candidate_parse_failures=(
            "malformed_course_text",
            "sum",
        ),
        missing_metadata_rows=(
            "rule_metadata_missing",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

exact_review = (
    unmet[
        unmet["rule_type_upper"].eq("EXACT")
    ]
    .groupby(
        [
            "required_options",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
        rows_course_passed=(
            "exact_required_course_present",
            "sum",
        ),
        rows_course_unused=(
            "exact_required_course_unused",
            "sum",
        ),
        rows_course_consumed=(
            "exact_required_course_consumed",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

any_n_review = (
    unmet[
        unmet["rule_type_upper"].eq("ANY_N")
    ]
    .groupby(
        [
            "required_options",
            "required_n_effective",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_with_any_passed_option=(
            "passed_candidate_count",
            lambda values:
                int(
                    (values > 0).sum()
                ),
        ),
        rows_with_enough_passed_options=(
            "any_n_enough_passed",
            "sum",
        ),
        rows_with_enough_unused_options=(
            "any_n_enough_unused",
            "sum",
        ),
        rows_with_consumed_options=(
            "any_n_candidates_consumed",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

core_review = (
    unmet[
        unmet["rule_type_upper"].eq("CORE_BUCKET")
    ]
    .groupby(
        [
            "normalized_bucket",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_current_candidate=(
            "core_bucket_has_current_candidate",
            "sum",
        ),
        rows_unused_candidate=(
            "core_bucket_has_unused_candidate",
            "sum",
        ),
        rows_cross_catalog_only=(
            "core_bucket_cross_catalog_only",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

elective_review = (
    unmet[
        unmet["rule_type_upper"].eq("ELECTIVE")
    ]
    .groupby(
        [
            "elective_policy_upper",
            "allowed_subjects_master",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_with_candidate_course=(
            "elective_has_candidate_course",
            "sum",
        ),
        rows_with_enough_candidate_hours=(
            "elective_has_enough_hours",
            "sum",
        ),
        average_candidate_hours=(
            "elective_candidate_hours",
            "mean",
        ),
        maximum_candidate_hours=(
            "elective_candidate_hours",
            "max",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

failure_concentration = (
    unmet.groupby(
        [
            "credential_lineage",
            "rule_type_upper",
            "required_options",
        ],
        dropna=False,
    )
    .agg(
        unmet_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        catalogs=(
            "catalog_year",
            join_unique,
        ),
    )
    .reset_index()
    .sort_values(
        [
            "unmet_rows",
            "distinct_students",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

by_credential = (
    population.groupby(
        [
            "credential_lineage",
            "gap_band",
        ],
        dropna=False,
    )
    .agg(
        student_lineages=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        catalogs=(
            "catalog_year",
            join_unique,
        ),
    )
    .reset_index()
    .sort_values(
        [
            "credential_lineage",
            "gap_band",
        ]
    )
)

rule_parse_review = (
    unmet.groupby(
        [
            "rule_type_upper",
            "required_options_blank",
            "candidate_list_blank",
            "malformed_course_text",
            "rule_metadata_missing",
        ],
        dropna=False,
    )
    .agg(
        rows=(
            "student_id",
            "size",
        ),
        distinct_requirements=(
            "requirement_id",
            "nunique",
        ),
        distinct_credentials=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "rows",
        ascending=False,
    )
)


# =============================================================================
# RESTRICTED DETAIL TABLES
# =============================================================================

unmet["pseudonymous_id"] = unmet[
    "student_id"
].map(
    pseudonym
)

restricted_columns = [
    "student_id",
    "pseudonymous_id",
    "credential_lineage",
    "credential_id",
    "catalog_year",
    "gap_band",
    "requirement_id",
    "rule_type_upper",
    "required_options",
    "option_types",
    "matched_options",
    "required_n_effective",
    "required_credit_master",
    "elective_policy_upper",
    "allowed_subjects_master",
    "passed_candidate_text",
    "unused_candidate_text",
    "consumed_candidate_text",
    "bucket_passed_text",
    "bucket_unused_text",
    "bucket_cross_catalog_text",
    "elective_candidate_text",
    "elective_candidate_hours",
    "exact_required_course_present",
    "exact_required_course_unused",
    "exact_required_course_consumed",
    "any_n_enough_passed",
    "any_n_enough_unused",
    "core_bucket_has_current_candidate",
    "core_bucket_has_unused_candidate",
    "core_bucket_cross_catalog_only",
    "elective_has_candidate_course",
    "elective_has_enough_hours",
    "malformed_course_text",
    "rule_metadata_missing",
]

restricted_unmet = unmet[
    restricted_columns
].copy()


# =============================================================================
# FERPA-SAFE COPIES
# =============================================================================

safe_kpi_summary = kpi_summary.copy()
safe_kpi_summary["value"] = safe_kpi_summary[
    "value"
].map(
    safe_count
)

safe_by_rule_type = suppress_counts(
    by_rule_type,
    [
        "unmet_rows",
        "distinct_students",
        "credential_lineages",
        "distinct_requirements",
        "candidate_parse_failures",
        "missing_metadata_rows",
    ],
)

safe_exact_review = suppress_counts(
    exact_review,
    [
        "unmet_rows",
        "distinct_students",
        "credential_lineages",
        "rows_course_passed",
        "rows_course_unused",
        "rows_course_consumed",
    ],
)

safe_any_n_review = suppress_counts(
    any_n_review,
    [
        "unmet_rows",
        "distinct_students",
        "rows_with_any_passed_option",
        "rows_with_enough_passed_options",
        "rows_with_enough_unused_options",
        "rows_with_consumed_options",
    ],
)

safe_core_review = suppress_counts(
    core_review,
    [
        "unmet_rows",
        "distinct_students",
        "rows_current_candidate",
        "rows_unused_candidate",
        "rows_cross_catalog_only",
    ],
)

safe_elective_review = suppress_counts(
    elective_review,
    [
        "unmet_rows",
        "distinct_students",
        "rows_with_candidate_course",
        "rows_with_enough_candidate_hours",
    ],
)

safe_failure_concentration = suppress_counts(
    failure_concentration,
    [
        "unmet_rows",
        "distinct_students",
    ],
)

safe_by_credential = suppress_counts(
    by_credential,
    [
        "student_lineages",
        "distinct_students",
    ],
)

safe_rule_parse_review = suppress_counts(
    rule_parse_review,
    [
        "rows",
        "distinct_requirements",
        "distinct_credentials",
    ],
)


# =============================================================================
# WRITE WORKBOOKS
# =============================================================================

restricted_readme = pd.DataFrame(
    [
        {
            "Item":
                "Classification",
            "Description":
                "RESTRICTED — contains student-level education records.",
        },
        {
            "Item":
                "Upload status",
            "Description":
                "Do not upload this workbook.",
        },
        {
            "Item":
                "Eligibility",
            "Description":
                (
                    "Continuity break ignored. Requires earned activity in "
                    "catalog year and no activity after catalog life."
                ),
        },
        {
            "Item":
                "Population",
            "Description":
                (
                    "Best relaxed-eligible catalog per student × credential "
                    "lineage, limited to COMPLETE and 1–3 missing."
                ),
        },
    ]
)

with pd.ExcelWriter(
    RESTRICTED_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    restricted_sheets = {
        "Read Me":
            restricted_readme,
        "All Unmet Detail":
            restricted_unmet,
        "EXACT Suspects":
            restricted_unmet[
                restricted_unmet[
                    "exact_required_course_present"
                ]
            ].copy(),
        "ANY_N Suspects":
            restricted_unmet[
                restricted_unmet[
                    "any_n_enough_passed"
                ]
            ].copy(),
        "CORE Suspects":
            restricted_unmet[
                restricted_unmet[
                    "core_bucket_has_current_candidate"
                ]
                | restricted_unmet[
                    "core_bucket_cross_catalog_only"
                ]
            ].copy(),
        "ELECTIVE Suspects":
            restricted_unmet[
                restricted_unmet[
                    "elective_has_candidate_course"
                ]
            ].copy(),
        "Parse Suspects":
            restricted_unmet[
                restricted_unmet[
                    "malformed_course_text"
                ]
                | restricted_unmet[
                    "rule_metadata_missing"
                ]
            ].copy(),
    }

    for sheet_name, dataframe in restricted_sheets.items():
        dataframe.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
        )

        format_sheet(
            writer,
            sheet_name,
            dataframe,
        )


safe_readme = pd.DataFrame(
    [
        {
            "Item":
                "Classification",
            "Description":
                "FERPA-SAFE AGGREGATE REVIEW COPY.",
        },
        {
            "Item":
                "Student identifiers",
            "Description":
                "None included.",
        },
        {
            "Item":
                "Small-cell suppression",
            "Description":
                (
                    f"Positive counts below {SAFE_THRESHOLD} display "
                    f"as <{SAFE_THRESHOLD}."
                ),
        },
        {
            "Item":
                "Primary interpretation",
            "Description":
                (
                    "Rows showing enough passed/unused candidates under an "
                    "UNMET rule are likely engine, allocation, lookup, or "
                    "rule-metadata defects."
                ),
        },
        {
            "Item":
                "Continuity",
            "Description":
                "Continuity breaks are ignored for this forensic experiment.",
        },
    ]
)

with pd.ExcelWriter(
    SAFE_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    safe_sheets = {
        "Read Me":
            safe_readme,
        "KPI Summary":
            safe_kpi_summary,
        "By Rule Type":
            safe_by_rule_type,
        "EXACT Review":
            safe_exact_review,
        "ANY_N Review":
            safe_any_n_review,
        "Core Bucket Review":
            safe_core_review,
        "Elective Review":
            safe_elective_review,
        "Failure Concentration":
            safe_failure_concentration,
        "By Credential":
            safe_by_credential,
        "Rule Parse Review":
            safe_rule_parse_review,
    }

    for sheet_name, dataframe in safe_sheets.items():
        dataframe.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
        )

        format_sheet(
            writer,
            sheet_name,
            dataframe,
        )


# =============================================================================
# SUPPORTING CSV FILES
# =============================================================================

safe_exact_review.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_exact_review.csv",
    index=False,
)

safe_any_n_review.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_any_n_review.csv",
    index=False,
)

safe_core_review.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_core_bucket_review.csv",
    index=False,
)

safe_elective_review.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_elective_review.csv",
    index=False,
)

safe_failure_concentration.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_failure_concentration.csv",
    index=False,
)


# =============================================================================
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("LSCO COURSE-TYPE FORENSIC REVIEW")
print("=" * 110)

for metric, value in kpi_rows:
    print(
        f"{metric:<66} {value:>10,}"
    )

print()
print(
    f"RESTRICTED workbook: {RESTRICTED_WORKBOOK}"
)

print(
    f"FERPA-SAFE workbook: {SAFE_WORKBOOK}"
)

print()
print(
    "UPLOAD ONLY THE FERPA-SAFE WORKBOOK."
)

print(
    "REPORT GATE: PASSED"
)
