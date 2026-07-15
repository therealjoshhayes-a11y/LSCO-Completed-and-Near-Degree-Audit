from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import math
import re
from typing import Iterable

import pandas as pd


# =============================================================================
# PURPOSE
# =============================================================================
#
# Creates TWO local workbooks:
#
# 1. RESTRICTED workbook
#    Student-level debugging evidence. Keep local. Do not upload.
#
# 2. FERPA-SAFE review workbook
#    Aggregate-only tables with small-cell suppression. This is the workbook
#    that may be uploaded for collaborative review.
#
# The script focuses on student × credential lineages that are modeled as
# COMPLETE or have 1–3 unmet requirements under their best eligible catalog.
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
    "data/processed/"
    "core_bucket_lookup_multicatalog.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"near_complete_forensic_review_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_LSCO_Near_Complete_Forensic_Detail.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_LSCO_Near_Complete_Forensic_Review.xlsx"
)

SAFE_SUPPRESSION_THRESHOLD = 5


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
    column_set = set(columns)

    for candidate in candidates:
        if candidate in column_set:
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

    return (
        match.group(1)
        + match.group(2)
    )


def extract_course_codes(value: object) -> list[str]:
    text = str(value).upper()

    codes = re.findall(
        r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4})\b",
        text,
    )

    return sorted(
        {
            subject + number
            for subject, number
            in codes
        }
    )


def derive_lineage(credential_id: object) -> str:
    value = str(
        credential_id
    ).strip().upper()

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

    return int(
        match.group(1)
    )


def safe_count(value: object) -> object:
    if pd.isna(value):
        return value

    try:
        number = int(value)
    except Exception:
        return value

    if 0 < number < SAFE_SUPPRESSION_THRESHOLD:
        return f"<{SAFE_SUPPRESSION_THRESHOLD}"

    return number


def suppress_counts(
    dataframe: pd.DataFrame,
    count_columns: list[str],
) -> pd.DataFrame:
    safe = dataframe.copy()

    for column in count_columns:
        if column in safe.columns:
            safe[column] = safe[column].map(
                safe_count
            )

    return safe


def pseudonym(student_id: object) -> str:
    digest = hashlib.sha256(
        str(student_id).encode("utf-8")
    ).hexdigest()

    return "S-" + digest[:12].upper()


def format_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    dataframe: pd.DataFrame,
) -> None:
    worksheet = writer.sheets[
        sheet_name
    ]

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

        for value in dataframe[column].head(
            5000
        ):
            if pd.isna(value):
                sample_values.append("")
            else:
                sample_values.append(
                    str(value)
                )

        width = max(
            len(str(column)) + 2,
            max(
                [
                    len(value)
                    for value
                    in sample_values
                ]
                + [0]
            )
            + 2,
        )

        worksheet.set_column(
            column_index,
            column_index,
            min(width, 45),
        )

    worksheet.freeze_panes(
        1,
        0,
    )

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
# LOAD SUMMARY + ELIGIBILITY
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

summary_student = first_existing(
    summary.columns,
    [
        "student_id",
        "student",
        "banner_id",
    ],
    label="summary student ID",
)

summary_credential = first_existing(
    summary.columns,
    [
        "credential_id",
        "credential",
        "program_id",
    ],
    label="summary credential ID",
)

summary_catalog = first_existing(
    summary.columns,
    [
        "catalog_year",
        "catalog",
    ],
    label="summary catalog year",
)

summary_status = first_existing(
    summary.columns,
    [
        "audit_status",
        "status",
    ],
    label="summary audit status",
)

summary_missing = first_existing(
    summary.columns,
    [
        "requirements_missing",
        "missing_requirements",
        "unmet_requirement_count",
        "requirements_unmet",
    ],
    label="summary missing-requirement count",
)

summary_required = first_existing(
    summary.columns,
    [
        "requirements_required",
        "total_requirements",
        "requirement_count",
    ],
    required=False,
)

summary_met = first_existing(
    summary.columns,
    [
        "requirements_met",
        "met_requirements",
    ],
    required=False,
)

eligibility_student = first_existing(
    eligibility.columns,
    [
        "student_id",
        "student",
    ],
    label="eligibility student ID",
)

eligibility_catalog = first_existing(
    eligibility.columns,
    [
        "catalog_year",
        "catalog",
    ],
    label="eligibility catalog year",
)

eligibility_flag = first_existing(
    eligibility.columns,
    [
        "catalog_eligible",
        "eligible",
        "is_eligible",
    ],
    label="eligibility flag",
)

eligibility_reason = first_existing(
    eligibility.columns,
    [
        "eligibility_reason",
        "reason",
    ],
    required=False,
)

summary["_missing_numeric"] = pd.to_numeric(
    summary[summary_missing],
    errors="coerce",
)

summary["_catalog_rank"] = summary[
    summary_catalog
].map(
    catalog_rank
)

summary["_credential_lineage"] = summary[
    summary_credential
].map(
    derive_lineage
)

eligibility["_eligible_bool"] = eligibility[
    eligibility_flag
].map(
    truthy
)

eligible_columns = [
    eligibility_student,
    eligibility_catalog,
    "_eligible_bool",
]

if eligibility_reason:
    eligible_columns.append(
        eligibility_reason
    )

eligible_keys = eligibility[
    eligibility["_eligible_bool"]
][
    eligible_columns
].copy()

eligible_keys = eligible_keys.rename(
    columns={
        eligibility_student:
            summary_student,
        eligibility_catalog:
            summary_catalog,
    }
)

if eligibility_reason:
    eligible_keys = eligible_keys.rename(
        columns={
            eligibility_reason:
                "catalog_eligibility_reason"
        }
    )

eligible_keys = eligible_keys.drop_duplicates(
    subset=[
        summary_student,
        summary_catalog,
    ]
)

eligible_summary = summary.merge(
    eligible_keys,
    on=[
        summary_student,
        summary_catalog,
    ],
    how="inner",
    validate="many_to_one",
)

# Diagnostic selection rule:
# - use the eligible catalog with the fewest missing requirements
# - break ties by newest eligible catalog
eligible_summary = eligible_summary.sort_values(
    [
        summary_student,
        "_credential_lineage",
        "_missing_numeric",
        "_catalog_rank",
        summary_credential,
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
        summary_student,
        "_credential_lineage",
    ],
    keep="first",
).copy()

selected["_gap_band"] = selected[
    "_missing_numeric"
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

diagnostic_population = selected[
    selected[
        "_missing_numeric"
    ].between(
        0,
        3,
        inclusive="both",
    )
].copy()

near_complete = diagnostic_population[
    diagnostic_population[
        "_missing_numeric"
    ].between(
        1,
        3,
        inclusive="both",
    )
].copy()

if near_complete.empty:
    raise SystemExit(
        "No eligible student-lineages with 1–3 missing requirements were found."
    )

near_complete["_join_key"] = (
    near_complete[summary_student].astype(str)
    + "||"
    + near_complete[summary_credential].astype(str)
    + "||"
    + near_complete[summary_catalog].astype(str)
)

near_keys = set(
    near_complete["_join_key"]
)


# =============================================================================
# LOAD PASSED COURSE HISTORY
# =============================================================================

history = pd.read_csv(
    HISTORY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

history_student = first_existing(
    history.columns,
    [
        "student_id",
        "student",
        "banner_id",
    ],
    label="history student ID",
)

history_course = first_existing(
    history.columns,
    [
        "course_code",
        "course",
        "normalized_course_code",
    ],
    label="history course code",
)

history_passed = first_existing(
    history.columns,
    [
        "passed",
        "earned_for_catalog",
        "course_passed",
    ],
    label="history passing indicator",
)

history_grade = first_existing(
    history.columns,
    [
        "final_grade",
        "grade",
    ],
    required=False,
)

history_term = first_existing(
    history.columns,
    [
        "term_sort",
        "term_taken",
    ],
    required=False,
)

history["_passed_bool"] = history[
    history_passed
].map(
    truthy
)

passed_history = history[
    history["_passed_bool"]
].copy()

passed_history["_normalized_course"] = passed_history[
    history_course
].map(
    normalize_course_code
)

passed_history = passed_history[
    passed_history[
        "_normalized_course"
    ].ne("")
].copy()

passed_course_sets = (
    passed_history.groupby(
        history_student
    )[
        "_normalized_course"
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
            history_student,
            "_normalized_course",
        ],
        dropna=False,
    )
    .agg(
        passed_attempt_rows=(
            "_normalized_course",
            "size",
        ),
        grade_values=(
            history_grade,
            lambda values:
                " | ".join(
                    sorted(
                        set(
                            str(value)
                            for value
                            in values
                            if str(value).strip()
                        )
                    )
                )
            if history_grade
            else "",
        ),
        term_values=(
            history_term,
            lambda values:
                " | ".join(
                    sorted(
                        set(
                            str(value)
                            for value
                            in values
                            if str(value).strip()
                        )
                    )
                )
            if history_term
            else "",
        ),
    )
    .reset_index()
)


# =============================================================================
# LOAD REQUIREMENTS MASTER
# =============================================================================

requirements = pd.read_csv(
    REQUIREMENTS_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

req_id_master = first_existing(
    requirements.columns,
    [
        "requirement_id",
        "requirement_group_id",
    ],
    required=False,
)

req_rule_master = first_existing(
    requirements.columns,
    [
        "rule_type",
        "requirement_type",
    ],
    required=False,
)

req_label_master = first_existing(
    requirements.columns,
    [
        "requirement_label",
        "requirement_name",
        "label",
    ],
    required=False,
)

req_course_master = first_existing(
    requirements.columns,
    [
        "course_code",
        "option_course_code",
    ],
    required=False,
)

req_bucket_master = first_existing(
    requirements.columns,
    [
        "bucket_name",
        "core_bucket",
        "requirement_bucket",
    ],
    required=False,
)


# =============================================================================
# SCAN DETAIL FILE FOR SELECTED NEAR-COMPLETE KEYS
# =============================================================================

detail_header = pd.read_csv(
    DETAIL_PATH,
    dtype=str,
    nrows=0,
)

detail_student = first_existing(
    detail_header.columns,
    [
        "student_id",
        "student",
        "banner_id",
    ],
    label="detail student ID",
)

detail_credential = first_existing(
    detail_header.columns,
    [
        "credential_id",
        "credential",
        "program_id",
    ],
    label="detail credential ID",
)

detail_catalog = first_existing(
    detail_header.columns,
    [
        "catalog_year",
        "catalog",
    ],
    label="detail catalog year",
)

detail_status = first_existing(
    detail_header.columns,
    [
        "requirement_status",
        "status",
        "result",
    ],
    required=False,
)

detail_met = first_existing(
    detail_header.columns,
    [
        "requirement_met",
        "met",
        "is_met",
    ],
    required=False,
)

detail_req_id = first_existing(
    detail_header.columns,
    [
        "requirement_id",
        "requirement_group_id",
    ],
    required=False,
)

detail_rule = first_existing(
    detail_header.columns,
    [
        "rule_type",
        "requirement_type",
    ],
    required=False,
)

detail_label = first_existing(
    detail_header.columns,
    [
        "requirement_label",
        "requirement_name",
        "label",
    ],
    required=False,
)

detail_course = first_existing(
    detail_header.columns,
    [
        "course_code",
        "required_course",
        "option_course_code",
    ],
    required=False,
)

detail_bucket = first_existing(
    detail_header.columns,
    [
        "bucket_name",
        "core_bucket",
        "requirement_bucket",
    ],
    required=False,
)

detail_matched_course = first_existing(
    detail_header.columns,
    [
        "matched_course_code",
        "matched_course",
        "applied_course_code",
        "used_course_code",
    ],
    required=False,
)

detail_columns_to_read = [
    detail_student,
    detail_credential,
    detail_catalog,
]

for optional_column in [
    detail_status,
    detail_met,
    detail_req_id,
    detail_rule,
    detail_label,
    detail_course,
    detail_bucket,
    detail_matched_course,
]:
    if (
        optional_column
        and optional_column not in detail_columns_to_read
    ):
        detail_columns_to_read.append(
            optional_column
        )

detail_parts = []
total_detail_rows = 0
selected_detail_rows = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        low_memory=False,
        usecols=detail_columns_to_read,
        chunksize=250_000,
    ),
    start=1,
):
    chunk = chunk.fillna("")

    total_detail_rows += len(
        chunk
    )

    chunk["_join_key"] = (
        chunk[detail_student].astype(str)
        + "||"
        + chunk[detail_credential].astype(str)
        + "||"
        + chunk[detail_catalog].astype(str)
    )

    selected_chunk = chunk[
        chunk["_join_key"].isin(
            near_keys
        )
    ].copy()

    if not selected_chunk.empty:
        detail_parts.append(
            selected_chunk
        )

        selected_detail_rows += len(
            selected_chunk
        )

    if chunk_number % 25 == 0:
        print(
            f"Scanned {total_detail_rows:,} detail rows; "
            f"retained {selected_detail_rows:,}"
        )

if detail_parts:
    detail = pd.concat(
        detail_parts,
        ignore_index=True,
    )

else:
    raise SystemExit(
        "No detail rows matched the selected near-complete population."
    )


# =============================================================================
# IDENTIFY UNMET DETAIL ROWS
# =============================================================================

if detail_met:
    detail["_unmet_bool"] = ~detail[
        detail_met
    ].map(
        truthy
    )

elif detail_status:
    detail["_unmet_bool"] = ~detail[
        detail_status
    ].astype(str).str.strip().str.upper().isin(
        {
            "MET",
            "COMPLETE",
            "SATISFIED",
            "TRUE",
            "1",
            "YES",
        }
    )

else:
    raise SystemExit(
        "Detail file has neither a requirement-met flag nor status column."
    )

unmet = detail[
    detail["_unmet_bool"]
].copy()

unmet = unmet.merge(
    near_complete[
        [
            "_join_key",
            summary_student,
            summary_credential,
            summary_catalog,
            "_credential_lineage",
            "_missing_numeric",
            "_gap_band",
        ]
    ],
    on="_join_key",
    how="left",
    validate="many_to_one",
    suffixes=(
        "",
        "_summary",
    ),
)

if detail_rule:
    unmet["_rule_type"] = unmet[
        detail_rule
    ].astype(str).str.strip().str.upper()
else:
    unmet["_rule_type"] = ""

if detail_label:
    unmet["_requirement_label"] = unmet[
        detail_label
    ].astype(str).str.strip()
else:
    unmet["_requirement_label"] = ""

if detail_course:
    unmet["_detail_course"] = unmet[
        detail_course
    ].map(
        normalize_course_code
    )
else:
    unmet["_detail_course"] = ""

if detail_bucket:
    unmet["_bucket_name"] = unmet[
        detail_bucket
    ].astype(str).str.strip()
else:
    unmet["_bucket_name"] = ""

if detail_req_id:
    unmet["_requirement_id"] = unmet[
        detail_req_id
    ].astype(str).str.strip()
else:
    unmet["_requirement_id"] = ""


# =============================================================================
# HYDRATE FROM REQUIREMENTS MASTER WHEN POSSIBLE
# =============================================================================

if (
    detail_req_id
    and req_id_master
):
    req_columns = [
        req_id_master,
    ]

    for column in [
        req_rule_master,
        req_label_master,
        req_course_master,
        req_bucket_master,
    ]:
        if (
            column
            and column not in req_columns
        ):
            req_columns.append(
                column
            )

    req_lookup = requirements[
        req_columns
    ].drop_duplicates(
        subset=[
            req_id_master,
        ]
    ).copy()

    rename_map = {
        req_id_master:
            "_requirement_id",
    }

    if req_rule_master:
        rename_map[
            req_rule_master
        ] = "_master_rule_type"

    if req_label_master:
        rename_map[
            req_label_master
        ] = "_master_requirement_label"

    if req_course_master:
        rename_map[
            req_course_master
        ] = "_master_course"

    if req_bucket_master:
        rename_map[
            req_bucket_master
        ] = "_master_bucket"

    req_lookup = req_lookup.rename(
        columns=rename_map
    )

    unmet = unmet.merge(
        req_lookup,
        on="_requirement_id",
        how="left",
        validate="many_to_one",
    )

else:
    unmet["_master_rule_type"] = ""
    unmet["_master_requirement_label"] = ""
    unmet["_master_course"] = ""
    unmet["_master_bucket"] = ""

for column in [
    "_master_rule_type",
    "_master_requirement_label",
    "_master_course",
    "_master_bucket",
]:
    if column not in unmet.columns:
        unmet[column] = ""

unmet["_final_rule_type"] = unmet[
    "_rule_type"
].where(
    unmet[
        "_rule_type"
    ].ne(""),
    unmet[
        "_master_rule_type"
    ].astype(str).str.strip().str.upper(),
)

unmet["_final_requirement_label"] = unmet[
    "_requirement_label"
].where(
    unmet[
        "_requirement_label"
    ].ne(""),
    unmet[
        "_master_requirement_label"
    ].astype(str).str.strip(),
)

unmet["_final_bucket_name"] = unmet[
    "_bucket_name"
].where(
    unmet[
        "_bucket_name"
    ].ne(""),
    unmet[
        "_master_bucket"
    ].astype(str).str.strip(),
)

unmet["_master_course_normalized"] = unmet[
    "_master_course"
].map(
    normalize_course_code
)

unmet["_final_course"] = unmet[
    "_detail_course"
].where(
    unmet[
        "_detail_course"
    ].ne(""),
    unmet[
        "_master_course_normalized"
    ],
)

unmet["_label_course_codes"] = unmet[
    "_final_requirement_label"
].map(
    extract_course_codes
)

unmet["_candidate_exact_courses"] = unmet.apply(
    lambda row:
        sorted(
            set(
                (
                    [row["_final_course"]]
                    if row["_final_course"]
                    else []
                )
                + row["_label_course_codes"]
            )
        ),
    axis=1,
)


# =============================================================================
# EXACT-COURSE PRESENT TEST
# =============================================================================

def passed_exact_courses(
    student_id: object,
    candidate_courses: list[str],
) -> list[str]:
    passed = passed_course_sets.get(
        str(student_id),
        set(),
    )

    return sorted(
        set(candidate_courses)
        & passed
    )


unmet["_passed_candidate_courses"] = unmet.apply(
    lambda row:
        passed_exact_courses(
            row[summary_student],
            row["_candidate_exact_courses"],
        ),
    axis=1,
)

unmet["_exact_course_present"] = unmet[
    "_passed_candidate_courses"
].map(
    bool
)

unmet["_passed_candidate_course_text"] = unmet[
    "_passed_candidate_courses"
].map(
    lambda values:
        " | ".join(values)
)


# =============================================================================
# OPTIONAL CORE-BUCKET CANDIDATE TEST
# =============================================================================

bucket_candidate_detail = pd.DataFrame()

if CORE_LOOKUP_PATH.exists():
    core = pd.read_csv(
        CORE_LOOKUP_PATH,
        dtype=str,
        low_memory=False,
    ).fillna("")

    core_catalog = first_existing(
        core.columns,
        [
            "catalog_year",
            "catalog",
        ],
        required=False,
    )

    core_bucket = first_existing(
        core.columns,
        [
            "bucket_name",
            "core_bucket",
            "requirement_bucket",
        ],
        required=False,
    )

    core_course = first_existing(
        core.columns,
        [
            "course_code",
            "normalized_course_code",
        ],
        required=False,
    )

    if (
        core_catalog
        and core_bucket
        and core_course
    ):
        core["_normalized_course"] = core[
            core_course
        ].map(
            normalize_course_code
        )

        core_lookup = (
            core.groupby(
                [
                    core_catalog,
                    core_bucket,
                ]
            )[
                "_normalized_course"
            ]
            .agg(
                lambda values:
                    {
                        value
                        for value
                        in values
                        if value
                    }
            )
            .to_dict()
        )

        bucket_rows = unmet[
            unmet[
                "_final_bucket_name"
            ].ne("")
        ].copy()

        def bucket_candidates(row: pd.Series) -> list[str]:
            eligible_courses = core_lookup.get(
                (
                    str(row[summary_catalog]),
                    str(
                        row[
                            "_final_bucket_name"
                        ]
                    ),
                ),
                set(),
            )

            passed_courses = passed_course_sets.get(
                str(row[summary_student]),
                set(),
            )

            return sorted(
                eligible_courses
                & passed_courses
            )

        bucket_rows[
            "_passed_bucket_candidates"
        ] = bucket_rows.apply(
            bucket_candidates,
            axis=1,
        )

        bucket_rows[
            "_passed_bucket_candidate_count"
        ] = bucket_rows[
            "_passed_bucket_candidates"
        ].map(
            len
        )

        bucket_rows[
            "_passed_bucket_candidate_text"
        ] = bucket_rows[
            "_passed_bucket_candidates"
        ].map(
            lambda values:
                " | ".join(values)
        )

        bucket_candidate_detail = bucket_rows[
            bucket_rows[
                "_passed_bucket_candidate_count"
            ].gt(0)
        ].copy()


# =============================================================================
# AGGREGATE DIAGNOSTICS
# =============================================================================

near_complete_summary = (
    diagnostic_population.groupby(
        "_gap_band",
        dropna=False,
    )
    .agg(
        student_lineages=(
            summary_student,
            "size",
        ),
        distinct_students=(
            summary_student,
            "nunique",
        ),
        credential_lineages=(
            "_credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
)

by_credential = (
    diagnostic_population.groupby(
        [
            "_credential_lineage",
            "_gap_band",
        ],
        dropna=False,
    )
    .agg(
        student_lineages=(
            summary_student,
            "size",
        ),
        distinct_students=(
            summary_student,
            "nunique",
        ),
        catalog_years=(
            summary_catalog,
            lambda values:
                " | ".join(
                    sorted(
                        set(
                            str(value)
                            for value
                            in values
                        )
                    )
                ),
        ),
    )
    .reset_index()
    .sort_values(
        [
            "_credential_lineage",
            "_gap_band",
        ]
    )
)

missing_rule_concentration = (
    unmet.groupby(
        [
            "_final_rule_type",
            "_final_requirement_label",
            "_final_course",
            "_final_bucket_name",
        ],
        dropna=False,
    )
    .agg(
        unmet_student_lineages=(
            summary_student,
            "size",
        ),
        distinct_students=(
            summary_student,
            "nunique",
        ),
        credential_lineages=(
            "_credential_lineage",
            "nunique",
        ),
        catalogs=(
            summary_catalog,
            lambda values:
                " | ".join(
                    sorted(
                        set(
                            str(value)
                            for value
                            in values
                        )
                    )
                ),
        ),
    )
    .reset_index()
    .sort_values(
        [
            "unmet_student_lineages",
            "distinct_students",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

rule_type_summary = (
    unmet.groupby(
        "_final_rule_type",
        dropna=False,
    )
    .agg(
        unmet_rows=(
            summary_student,
            "size",
        ),
        distinct_students=(
            summary_student,
            "nunique",
        ),
        credential_lineages=(
            "_credential_lineage",
            "nunique",
        ),
        distinct_requirements=(
            "_requirement_id",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

exact_course_present = unmet[
    unmet[
        "_exact_course_present"
    ]
].copy()

exact_course_present_summary = (
    exact_course_present.groupby(
        [
            "_final_course",
            "_final_requirement_label",
            "_final_rule_type",
        ],
        dropna=False,
    )
    .agg(
        affected_student_lineages=(
            summary_student,
            "size",
        ),
        distinct_students=(
            summary_student,
            "nunique",
        ),
        credential_lineages=(
            "_credential_lineage",
            "nunique",
        ),
        passed_candidate_courses=(
            "_passed_candidate_course_text",
            lambda values:
                " | ".join(
                    sorted(
                        set(
                            value
                            for value
                            in values
                            if value
                        )
                    )
                ),
        ),
    )
    .reset_index()
    .sort_values(
        "affected_student_lineages",
        ascending=False,
    )
)

if not bucket_candidate_detail.empty:
    bucket_candidate_summary = (
        bucket_candidate_detail.groupby(
            [
                "_final_bucket_name",
                "_final_requirement_label",
                summary_catalog,
            ],
            dropna=False,
        )
        .agg(
            affected_student_lineages=(
                summary_student,
                "size",
            ),
            distinct_students=(
                summary_student,
                "nunique",
            ),
            credential_lineages=(
                "_credential_lineage",
                "nunique",
            ),
            candidate_courses=(
                "_passed_bucket_candidate_text",
                lambda values:
                    " | ".join(
                        sorted(
                            {
                                course
                                for value
                                in values
                                for course
                                in str(value).split(" | ")
                                if course
                            }
                        )
                    ),
            ),
        )
        .reset_index()
        .sort_values(
            "affected_student_lineages",
            ascending=False,
        )
    )

else:
    bucket_candidate_summary = pd.DataFrame(
        columns=[
            "_final_bucket_name",
            "_final_requirement_label",
            summary_catalog,
            "affected_student_lineages",
            "distinct_students",
            "credential_lineages",
            "candidate_courses",
        ]
    )

grade_rejection_summary = pd.DataFrame()

if history_grade:
    all_history = history.copy()

    all_history[
        "_normalized_course"
    ] = all_history[
        history_course
    ].map(
        normalize_course_code
    )

    candidate_course_set = {
        course
        for values
        in unmet[
            "_candidate_exact_courses"
        ]
        for course
        in values
    }

    relevant_history = all_history[
        all_history[
            "_normalized_course"
        ].isin(
            candidate_course_set
        )
    ].copy()

    grade_rejection_summary = (
        relevant_history.groupby(
            [
                history_grade,
                "_passed_bool",
            ],
            dropna=False,
        )
        .agg(
            course_attempt_rows=(
                history_student,
                "size",
            ),
            distinct_students=(
                history_student,
                "nunique",
            ),
            distinct_courses=(
                "_normalized_course",
                "nunique",
            ),
        )
        .reset_index()
        .sort_values(
            "course_attempt_rows",
            ascending=False,
        )
    )


# =============================================================================
# RESTRICTED STUDENT-LEVEL TABLES
# =============================================================================

restricted_near = near_complete.copy()

restricted_near[
    "pseudonymous_id"
] = restricted_near[
    summary_student
].map(
    pseudonym
)

restricted_near = restricted_near[
    [
        summary_student,
        "pseudonymous_id",
        "_credential_lineage",
        summary_credential,
        summary_catalog,
        "_missing_numeric",
        "_gap_band",
    ]
    + (
        [summary_required]
        if summary_required
        else []
    )
    + (
        [summary_met]
        if summary_met
        else []
    )
    + (
        ["catalog_eligibility_reason"]
        if "catalog_eligibility_reason"
        in restricted_near.columns
        else []
    )
].copy()

restricted_unmet = unmet.copy()

restricted_unmet[
    "pseudonymous_id"
] = restricted_unmet[
    summary_student
].map(
    pseudonym
)

restricted_unmet = restricted_unmet[
    [
        summary_student,
        "pseudonymous_id",
        "_credential_lineage",
        summary_credential,
        summary_catalog,
        "_gap_band",
        "_requirement_id",
        "_final_rule_type",
        "_final_requirement_label",
        "_final_course",
        "_final_bucket_name",
        "_passed_candidate_course_text",
        "_exact_course_present",
    ]
].copy()

restricted_bucket = bucket_candidate_detail.copy()

if not restricted_bucket.empty:
    restricted_bucket[
        "pseudonymous_id"
    ] = restricted_bucket[
        summary_student
    ].map(
        pseudonym
    )

    restricted_bucket = restricted_bucket[
        [
            summary_student,
            "pseudonymous_id",
            "_credential_lineage",
            summary_credential,
            summary_catalog,
            "_gap_band",
            "_requirement_id",
            "_final_rule_type",
            "_final_requirement_label",
            "_final_bucket_name",
            "_passed_bucket_candidate_count",
            "_passed_bucket_candidate_text",
        ]
    ].copy()


# =============================================================================
# FERPA-SAFE AGGREGATE TABLES
# =============================================================================

safe_near_complete_summary = suppress_counts(
    near_complete_summary,
    [
        "student_lineages",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_by_credential = suppress_counts(
    by_credential,
    [
        "student_lineages",
        "distinct_students",
    ],
)

safe_missing_rule_concentration = suppress_counts(
    missing_rule_concentration,
    [
        "unmet_student_lineages",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_rule_type_summary = suppress_counts(
    rule_type_summary,
    [
        "unmet_rows",
        "distinct_students",
        "credential_lineages",
        "distinct_requirements",
    ],
)

safe_exact_course_present_summary = suppress_counts(
    exact_course_present_summary,
    [
        "affected_student_lineages",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_bucket_candidate_summary = suppress_counts(
    bucket_candidate_summary,
    [
        "affected_student_lineages",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_grade_rejection_summary = suppress_counts(
    grade_rejection_summary,
    [
        "course_attempt_rows",
        "distinct_students",
        "distinct_courses",
    ],
)


# =============================================================================
# WRITE RESTRICTED WORKBOOK
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
                "Do not upload this workbook to ChatGPT or external systems.",
        },
        {
            "Item":
                "Selection rule",
            "Description":
                (
                    "Best eligible catalog per student × credential lineage: "
                    "fewest missing requirements, then newest eligible catalog."
                ),
        },
        {
            "Item":
                "Gap interpretation",
            "Description":
                (
                    "1–3 MISSING means unmet requirement rows, not yet a "
                    "guaranteed minimum number of courses."
                ),
        },
        {
            "Item":
                "Detail source",
            "Description":
                str(DETAIL_PATH),
        },
        {
            "Item":
                "Summary source",
            "Description":
                str(SUMMARY_PATH),
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
        "Near Complete Students":
            restricted_near,
        "Unmet Requirement Detail":
            restricted_unmet,
        "Exact Course Present":
            restricted_unmet[
                restricted_unmet[
                    "_exact_course_present"
                ]
            ].copy(),
        "Bucket Candidate Detail":
            restricted_bucket,
        "Passed Course Rows":
            passed_course_rows,
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


# =============================================================================
# WRITE FERPA-SAFE WORKBOOK
# =============================================================================

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
                    f"Positive counts below {SAFE_SUPPRESSION_THRESHOLD} "
                    f"are displayed as <{SAFE_SUPPRESSION_THRESHOLD}."
                ),
        },
        {
            "Item":
                "Permitted review use",
            "Description":
                (
                    "This aggregate workbook is designed for upload and "
                    "collaborative debugging. The restricted workbook must "
                    "remain local."
                ),
        },
        {
            "Item":
                "Primary questions",
            "Description":
                (
                    "Which requirements dominate 1–3-gap records? "
                    "How often is an unmet exact course already passed? "
                    "How often does an unmet core bucket have a passed "
                    "candidate course?"
                ),
        },
        {
            "Item":
                "Gap interpretation",
            "Description":
                (
                    "The current bands use unmet requirement counts, not a "
                    "fully optimized minimum-course count."
                ),
        },
    ]
)

safe_kpis = pd.DataFrame(
    [
        {
            "Metric":
                "Eligible COMPLETE student-lineages",
            "Value":
                int(
                    (
                        diagnostic_population[
                            "_missing_numeric"
                        ]
                        == 0
                    ).sum()
                ),
        },
        {
            "Metric":
                "Eligible 1-missing student-lineages",
            "Value":
                int(
                    (
                        diagnostic_population[
                            "_missing_numeric"
                        ]
                        == 1
                    ).sum()
                ),
        },
        {
            "Metric":
                "Eligible 2-missing student-lineages",
            "Value":
                int(
                    (
                        diagnostic_population[
                            "_missing_numeric"
                        ]
                        == 2
                    ).sum()
                ),
        },
        {
            "Metric":
                "Eligible 3-missing student-lineages",
            "Value":
                int(
                    (
                        diagnostic_population[
                            "_missing_numeric"
                        ]
                        == 3
                    ).sum()
                ),
        },
        {
            "Metric":
                "Unmet detail rows scanned",
            "Value":
                len(unmet),
        },
        {
            "Metric":
                "Unmet rows with an exact passed candidate",
            "Value":
                len(exact_course_present),
        },
        {
            "Metric":
                "Unmet bucket rows with passed candidates",
            "Value":
                len(bucket_candidate_detail),
        },
    ]
)

safe_kpis["Value"] = safe_kpis[
    "Value"
].map(
    safe_count
)

with pd.ExcelWriter(
    SAFE_WORKBOOK,
    engine="xlsxwriter",
) as writer:
    safe_sheets = {
        "Read Me":
            safe_readme,
        "KPI Summary":
            safe_kpis,
        "Near Complete Summary":
            safe_near_complete_summary,
        "By Credential":
            safe_by_credential,
        "By Rule Type":
            safe_rule_type_summary,
        "Missing Requirement":
            safe_missing_rule_concentration,
        "Exact Course Present":
            safe_exact_course_present_summary,
        "Bucket Candidates":
            safe_bucket_candidate_summary,
        "Grade Review":
            safe_grade_rejection_summary,
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

    workbook = writer.book

    summary_sheet = writer.sheets[
        "Near Complete Summary"
    ]

    if not near_complete_summary.empty:
        chart = workbook.add_chart(
            {
                "type":
                    "column"
            }
        )

        last_row = len(
            near_complete_summary
        )

        chart.add_series(
            {
                "name":
                    "Student-lineages",
                "categories":
                    [
                        "Near Complete Summary",
                        1,
                        0,
                        last_row,
                        0,
                    ],
                "values":
                    [
                        "Near Complete Summary",
                        1,
                        1,
                        last_row,
                        1,
                    ],
                "data_labels":
                    {
                        "value":
                            True
                    },
            }
        )

        chart.set_title(
            {
                "name":
                    "Eligible Completion and Near-Completion Bands"
            }
        )

        chart.set_y_axis(
            {
                "name":
                    "Student-lineages"
            }
        )

        chart.set_legend(
            {
                "none":
                    True
            }
        )

        chart.set_style(
            10
        )

        summary_sheet.insert_chart(
            "F2",
            chart,
            {
                "x_scale":
                    1.35,
                "y_scale":
                    1.25,
            },
        )


# =============================================================================
# SUPPORTING CSV FILES
# =============================================================================

safe_missing_rule_concentration.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_missing_requirement_concentration.csv",
    index=False,
)

safe_exact_course_present_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_exact_course_present_summary.csv",
    index=False,
)

safe_bucket_candidate_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_bucket_candidate_summary.csv",
    index=False,
)

restricted_unmet.to_csv(
    OUTPUT_DIR
    / "RESTRICTED_unmet_requirement_detail.csv",
    index=False,
)


# =============================================================================
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("LSCO NEAR-COMPLETE FORENSIC REVIEW")
print("=" * 110)

print(
    f"Eligible selected student-lineages, 0–3 missing: "
    f"{len(diagnostic_population):,}"
)

print(
    f"Near-complete student-lineages, 1–3 missing:     "
    f"{len(near_complete):,}"
)

print(
    f"Retained detail rows:                            "
    f"{len(detail):,}"
)

print(
    f"Unmet detail rows:                               "
    f"{len(unmet):,}"
)

print(
    f"Unmet rows with exact passed candidate:          "
    f"{len(exact_course_present):,}"
)

print(
    f"Unmet bucket rows with passed candidates:        "
    f"{len(bucket_candidate_detail):,}"
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
