from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import re
from typing import Iterable

import pandas as pd


# =============================================================================
# LSCO ELECTIVE FORENSIC REVIEW
# =============================================================================
#
# Purpose:
#   Determine whether ELECTIVE rule handling is synthetically suppressing
#   completion candidates.
#
# Privacy:
#   - RESTRICTED workbook contains student-level detail and stays local.
#   - FERPA_SAFE workbook contains aggregate tables only and may be uploaded.
#
# Eligibility:
#   Continuity breaks are ignored.
#
# Population:
#   Best relaxed-eligible catalog per student × credential lineage,
#   limited to COMPLETE and 1–3 missing requirements.
#
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

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"elective_forensic_review_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_LSCO_Elective_Forensic_Review.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_LSCO_Elective_Forensic_Review.xlsx"
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
    return " | ".join(
        sorted(
            {
                str(value).strip()
                for value in values
                if str(value).strip()
            }
        )
    )


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
# VALIDATE INPUTS
# =============================================================================

for path in [
    SUMMARY_PATH,
    DETAIL_PATH,
    HISTORY_PATH,
    ELIGIBILITY_PATH,
    REQUIREMENTS_PATH,
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
# LOAD COURSE HISTORY
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

history_credit_col = first_existing(
    history.columns,
    [
        "credit_hours",
        "credits",
        "earned_credit_hours",
        "course_credit_hours",
        "hours",
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

passed_course_rows = (
    passed_history.groupby(
        [
            history_student_col,
            "normalized_course",
        ],
        dropna=False,
    )
    .agg(
        course_subject=(
            "course_subject",
            "first",
        ),
        credit_hours=(
            "credit_hours_numeric",
            "max",
        ),
    )
    .reset_index()
)

student_course_credit = {
    (
        str(row[history_student_col]),
        str(row["normalized_course"]),
    ):
        (
            float(row["credit_hours"])
            if pd.notna(row["credit_hours"])
            else None
        )
    for _, row in passed_course_rows.iterrows()
}


# =============================================================================
# LOAD ELECTIVE REQUIREMENT METADATA
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
    label="requirement ID",
)

req_rule_col = first_existing(
    requirements.columns,
    [
        "rule_type",
        "requirement_type",
    ],
    required=False,
)

req_credit_col = first_existing(
    requirements.columns,
    [
        "credit_hours",
        "required_credit_hours",
        "minimum_credit_hours",
        "hours_required",
    ],
    required=False,
)

req_policy_col = first_existing(
    requirements.columns,
    [
        "elective_policy",
        "resolver_policy",
        "elective_resolver",
        "policy_code",
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

req_option_course_col = first_existing(
    requirements.columns,
    [
        "course_code",
        "option_course_code",
        "normalized_course_code",
    ],
    required=False,
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

requirements[
    "normalized_option_course"
] = (
    requirements[
        req_option_course_col
    ].map(
        normalize_course_code
    )
    if req_option_course_col
    else ""
)

elective_metadata = (
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
        required_elective_hours=(
            "required_credit_numeric",
            "max",
        ),
        elective_policy=(
            req_policy_col,
            "first",
        )
        if req_policy_col
        else (
            req_id_col,
            lambda values: "",
        ),
        allowed_subjects=(
            req_subject_col,
            "first",
        )
        if req_subject_col
        else (
            req_id_col,
            lambda values: "",
        ),
        listed_option_courses=(
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
# SCAN DETAIL FILE
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
    elective_metadata,
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

detail["matched_course_list"] = detail[
    "matched_options"
].map(
    parse_course_list
)

detail["matched_course_set"] = detail[
    "matched_course_list"
].map(
    set
)

used_courses_by_lineage = (
    detail.groupby(
        "join_key",
        dropna=False,
    )[
        "matched_course_set"
    ]
    .agg(
        lambda values:
            set().union(*values)
            if len(values)
            else set()
    )
    .to_dict()
)

elective_rows = detail[
    detail["rule_type_upper"].eq(
        "ELECTIVE"
    )
].copy()

unmet_electives = elective_rows[
    elective_rows["status_upper"].eq(
        "UNMET"
    )
].copy()


# =============================================================================
# POLICY RESOLUTION
# =============================================================================

def parse_allowed_subjects(value: object) -> set[str]:
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
            "AND",
            "OR",
        }
    }


def infer_subjects_from_policy(
    policy: str,
) -> set[str]:
    policy_upper = str(policy).upper()

    controlled = {
        "BUSINESS":
            {
                "ACCT",
                "ACNT",
                "BMGT",
                "BUSG",
                "BUSI",
                "MRKG",
            },
        "BUSINESS_AGRIBUSINESS":
            {
                "ACCT",
                "ACNT",
                "AGCR",
                "AGMG",
                "BMGT",
                "BUSG",
                "BUSI",
                "MRKG",
            },
        "BUSINESS_ANIMAL_SCIENCE":
            {
                "ACCT",
                "ACNT",
                "AGAH",
                "AGCR",
                "AGMG",
                "BMGT",
                "BUSG",
                "BUSI",
                "MRKG",
            },
        "INFORMATION_TECHNOLOGY":
            {
                "ITCC",
                "ITDF",
                "ITSY",
            },
        "SCIENCE_MAJOR":
            {
                "BIOL",
                "CHEM",
                "GEOL",
                "PHYS",
            },
    }

    for key, subjects in controlled.items():
        if key in policy_upper:
            return subjects

    return set()


unmet_electives[
    "policy_upper"
] = unmet_electives[
    "elective_policy"
].astype(str).str.strip().str.upper()

unmet_electives[
    "allowed_subject_set"
] = unmet_electives[
    "allowed_subjects"
].map(
    parse_allowed_subjects
)

unmet_electives[
    "inferred_subject_set"
] = unmet_electives[
    "policy_upper"
].map(
    infer_subjects_from_policy
)

unmet_electives[
    "effective_subject_set"
] = unmet_electives.apply(
    lambda row:
        row["allowed_subject_set"]
        if row["allowed_subject_set"]
        else row["inferred_subject_set"],
    axis=1,
)

unmet_electives[
    "required_elective_hours_numeric"
] = pd.to_numeric(
    unmet_electives[
        "required_elective_hours"
    ],
    errors="coerce",
)


# =============================================================================
# ELECTIVE CANDIDATE CALCULATION
# =============================================================================

def eligible_unused_courses(
    row: pd.Series,
) -> list[str]:
    student_id = str(row["student_id"])
    join_key = str(row["join_key"])

    passed = passed_course_sets.get(
        student_id,
        set(),
    )

    used = used_courses_by_lineage.get(
        join_key,
        set(),
    )

    unused = passed - used

    policy = row["policy_upper"]
    subjects = row["effective_subject_set"]
    listed = set(
        row["listed_option_courses"]
        if isinstance(
            row["listed_option_courses"],
            list,
        )
        else []
    )

    if (
        "ANY_UNUSED_PASSED_COURSE" in policy
        or "UNRESTRICTED" in policy
        or "APPROVED ELECTIVE" in str(
            row["required_options"]
        ).upper()
    ):
        return sorted(unused)

    if subjects:
        return sorted(
            {
                course
                for course in unused
                if course_subject(course)
                in subjects
            }
        )

    if listed:
        return sorted(
            unused & listed
        )

    return []


unmet_electives[
    "eligible_unused_courses"
] = unmet_electives.apply(
    eligible_unused_courses,
    axis=1,
)

unmet_electives[
    "eligible_unused_course_count"
] = unmet_electives[
    "eligible_unused_courses"
].map(
    len
)

unmet_electives[
    "eligible_unused_course_text"
] = unmet_electives[
    "eligible_unused_courses"
].map(
    lambda values:
        " | ".join(values)
)


def course_hours_for_row(
    row: pd.Series,
) -> list[tuple[str, float | None]]:
    result = []

    for course in row[
        "eligible_unused_courses"
    ]:
        hours = student_course_credit.get(
            (
                str(row["student_id"]),
                course,
            )
        )

        result.append(
            (
                course,
                hours,
            )
        )

    return result


unmet_electives[
    "candidate_course_hours"
] = unmet_electives.apply(
    course_hours_for_row,
    axis=1,
)

unmet_electives[
    "candidate_course_hours_text"
] = unmet_electives[
    "candidate_course_hours"
].map(
    lambda values:
        " | ".join(
            f"{course}:{hours:g}"
            if hours is not None
            else f"{course}:MISSING"
            for course, hours
            in values
        )
)

unmet_electives[
    "candidate_courses_missing_hours"
] = unmet_electives[
    "candidate_course_hours"
].map(
    lambda values:
        sum(
            1
            for _, hours in values
            if hours is None
        )
)

unmet_electives[
    "candidate_hours_total"
] = unmet_electives[
    "candidate_course_hours"
].map(
    lambda values:
        sum(
            hours
            for _, hours in values
            if hours is not None
        )
)

unmet_electives[
    "has_any_candidate"
] = unmet_electives[
    "eligible_unused_course_count"
].gt(0)

unmet_electives[
    "hours_known"
] = (
    unmet_electives[
        "candidate_courses_missing_hours"
    ].eq(0)
    & unmet_electives[
        "eligible_unused_course_count"
    ].gt(0)
)

unmet_electives[
    "has_enough_hours"
] = (
    unmet_electives[
        "required_elective_hours_numeric"
    ].notna()
    & (
        unmet_electives[
            "candidate_hours_total"
        ]
        >= unmet_electives[
            "required_elective_hours_numeric"
        ]
    )
)

unmet_electives[
    "diagnostic_status"
] = unmet_electives.apply(
    lambda row:
        "LIKELY_ENGINE_FAILURE_ENOUGH_UNUSED_HOURS"
        if row["has_enough_hours"]
        else (
            "CANDIDATES_PRESENT_BUT_CREDIT_HOURS_MISSING"
            if (
                row["has_any_candidate"]
                and row[
                    "candidate_courses_missing_hours"
                ] > 0
            )
            else (
                "CANDIDATES_PRESENT_NOT_ENOUGH_HOURS"
                if row["has_any_candidate"]
                else "NO_ELIGIBLE_UNUSED_CANDIDATE"
            )
        ),
    axis=1,
)


# =============================================================================
# COMPLETION IMPACT ESTIMATE
# =============================================================================
#
# A student-lineage can be promoted to a likely completion only when:
#   - it has exactly one missing requirement
#   - that missing requirement is ELECTIVE
#   - the elective has enough unused eligible hours
#
# This is a conservative lower-bound estimate.
#

lineage_unmet_counts = (
    detail[
        detail["status_upper"].eq("UNMET")
    ]
    .groupby(
        "join_key"
    )[
        "requirement_id"
    ]
    .nunique()
    .to_dict()
)

unmet_electives[
    "lineage_unmet_requirement_count"
] = unmet_electives[
    "join_key"
].map(
    lineage_unmet_counts
)

unmet_electives[
    "likely_promotable_to_complete"
] = (
    unmet_electives[
        "lineage_unmet_requirement_count"
    ].eq(1)
    & unmet_electives[
        "has_enough_hours"
    ]
)

promotable = unmet_electives[
    unmet_electives[
        "likely_promotable_to_complete"
    ]
].copy()


# =============================================================================
# AGGREGATE TABLES
# =============================================================================

kpi_summary = pd.DataFrame(
    [
        {
            "metric":
                "Unmet ELECTIVE rows",
            "value":
                len(unmet_electives),
        },
        {
            "metric":
                "Rows with at least one eligible unused course",
            "value":
                int(
                    unmet_electives[
                        "has_any_candidate"
                    ].sum()
                ),
        },
        {
            "metric":
                "Rows with candidate courses missing credit hours",
            "value":
                int(
                    (
                        unmet_electives[
                            "candidate_courses_missing_hours"
                        ]
                        > 0
                    ).sum()
                ),
        },
        {
            "metric":
                "Rows with known candidate hours",
            "value":
                int(
                    unmet_electives[
                        "hours_known"
                    ].sum()
                ),
        },
        {
            "metric":
                "Rows with enough unused eligible hours",
            "value":
                int(
                    unmet_electives[
                        "has_enough_hours"
                    ].sum()
                ),
        },
        {
            "metric":
                "Student-lineages conservatively promotable to COMPLETE",
            "value":
                promotable[
                    "join_key"
                ].nunique(),
        },
        {
            "metric":
                "Distinct students conservatively promotable",
            "value":
                promotable[
                    "student_id"
                ].nunique(),
        },
    ]
)

by_status = (
    unmet_electives.groupby(
        "diagnostic_status",
        dropna=False,
    )
    .agg(
        elective_rows=(
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
    )
    .reset_index()
    .sort_values(
        "elective_rows",
        ascending=False,
    )
)

by_policy = (
    unmet_electives.groupby(
        [
            "policy_upper",
            "allowed_subjects",
            "required_elective_hours_numeric",
        ],
        dropna=False,
    )
    .agg(
        elective_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_with_candidates=(
            "has_any_candidate",
            "sum",
        ),
        rows_missing_credit_hours=(
            "candidate_courses_missing_hours",
            lambda values:
                int(
                    (values > 0).sum()
                ),
        ),
        rows_with_enough_hours=(
            "has_enough_hours",
            "sum",
        ),
        promotable_lineages=(
            "likely_promotable_to_complete",
            "sum",
        ),
        average_candidate_hours=(
            "candidate_hours_total",
            "mean",
        ),
        maximum_candidate_hours=(
            "candidate_hours_total",
            "max",
        ),
    )
    .reset_index()
    .sort_values(
        "elective_rows",
        ascending=False,
    )
)

by_credential = (
    unmet_electives.groupby(
        [
            "credential_lineage",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        elective_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_with_candidates=(
            "has_any_candidate",
            "sum",
        ),
        rows_with_enough_hours=(
            "has_enough_hours",
            "sum",
        ),
        promotable_lineages=(
            "likely_promotable_to_complete",
            "sum",
        ),
        policies=(
            "policy_upper",
            join_unique,
        ),
    )
    .reset_index()
    .sort_values(
        [
            "promotable_lineages",
            "elective_rows",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

by_required_hours = (
    unmet_electives.groupby(
        "required_elective_hours_numeric",
        dropna=False,
    )
    .agg(
        elective_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        rows_with_candidates=(
            "has_any_candidate",
            "sum",
        ),
        rows_with_enough_hours=(
            "has_enough_hours",
            "sum",
        ),
        promotable_lineages=(
            "likely_promotable_to_complete",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "required_elective_hours_numeric"
    )
)

course_hour_quality = (
    passed_history.groupby(
        "normalized_course",
        dropna=False,
    )
    .agg(
        passed_rows=(
            history_student_col,
            "size",
        ),
        distinct_students=(
            history_student_col,
            "nunique",
        ),
        rows_missing_credit_hours=(
            "credit_hours_numeric",
            lambda values:
                int(
                    values.isna().sum()
                ),
        ),
        maximum_credit_hours=(
            "credit_hours_numeric",
            "max",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "rows_missing_credit_hours",
            "passed_rows",
        ],
        ascending=[
            False,
            False,
        ],
    )
)


# =============================================================================
# RESTRICTED DETAIL
# =============================================================================

unmet_electives[
    "pseudonymous_id"
] = unmet_electives[
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
    "required_options",
    "required_elective_hours_numeric",
    "policy_upper",
    "allowed_subjects",
    "matched_options",
    "eligible_unused_course_count",
    "eligible_unused_course_text",
    "candidate_course_hours_text",
    "candidate_courses_missing_hours",
    "candidate_hours_total",
    "diagnostic_status",
    "lineage_unmet_requirement_count",
    "likely_promotable_to_complete",
]

restricted_detail = unmet_electives[
    restricted_columns
].copy()


# =============================================================================
# FERPA-SAFE COPIES
# =============================================================================

safe_kpi = kpi_summary.copy()
safe_kpi["value"] = safe_kpi[
    "value"
].map(
    safe_count
)

safe_by_status = suppress_counts(
    by_status,
    [
        "elective_rows",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_by_policy = suppress_counts(
    by_policy,
    [
        "elective_rows",
        "distinct_students",
        "rows_with_candidates",
        "rows_missing_credit_hours",
        "rows_with_enough_hours",
        "promotable_lineages",
    ],
)

safe_by_credential = suppress_counts(
    by_credential,
    [
        "elective_rows",
        "distinct_students",
        "rows_with_candidates",
        "rows_with_enough_hours",
        "promotable_lineages",
    ],
)

safe_by_required_hours = suppress_counts(
    by_required_hours,
    [
        "elective_rows",
        "distinct_students",
        "rows_with_candidates",
        "rows_with_enough_hours",
        "promotable_lineages",
    ],
)

safe_course_hour_quality = suppress_counts(
    course_hour_quality,
    [
        "passed_rows",
        "distinct_students",
        "rows_missing_credit_hours",
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
                "Continuity breaks ignored.",
        },
        {
            "Item":
                "Promotable definition",
            "Description":
                (
                    "Exactly one unmet requirement, that requirement is "
                    "ELECTIVE, and unused eligible courses provide enough "
                    "known credit hours."
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
        "All Unmet Electives":
            restricted_detail,
        "Enough Hours":
            restricted_detail[
                restricted_detail[
                    "diagnostic_status"
                ].eq(
                    "LIKELY_ENGINE_FAILURE_ENOUGH_UNUSED_HOURS"
                )
            ].copy(),
        "Promotable Completers":
            restricted_detail[
                restricted_detail[
                    "likely_promotable_to_complete"
                ]
            ].copy(),
        "Missing Course Hours":
            restricted_detail[
                restricted_detail[
                    "candidate_courses_missing_hours"
                ].gt(0)
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
                "Primary question",
            "Description":
                (
                    "Do unmet elective rows already have enough unused, "
                    "policy-eligible passed credit hours?"
                ),
        },
        {
            "Item":
                "Promotable estimate",
            "Description":
                (
                    "Conservative lower bound: only student-lineages with "
                    "exactly one unmet requirement are counted."
                ),
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
            safe_kpi,
        "By Diagnostic Status":
            safe_by_status,
        "By Policy":
            safe_by_policy,
        "By Credential":
            safe_by_credential,
        "By Required Hours":
            safe_by_required_hours,
        "Course Hour Quality":
            safe_course_hour_quality,
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

safe_by_policy.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_elective_by_policy.csv",
    index=False,
)

safe_by_credential.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_elective_by_credential.csv",
    index=False,
)

safe_course_hour_quality.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_course_hour_quality.csv",
    index=False,
)

restricted_detail.to_csv(
    OUTPUT_DIR
    / "RESTRICTED_elective_detail.csv",
    index=False,
)


# =============================================================================
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("LSCO ELECTIVE FORENSIC REVIEW")
print("=" * 110)

for _, row in kpi_summary.iterrows():
    print(
        f"{row['metric']:<68} {int(row['value']):>10,}"
    )

print()
print(
    f"History credit-hour field: "
    f"{history_credit_col if history_credit_col else 'NOT FOUND'}"
)

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
