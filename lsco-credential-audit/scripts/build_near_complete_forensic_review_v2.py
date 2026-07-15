from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import re
from typing import Iterable

import pandas as pd


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

CORE_LOOKUP_PATH = Path(
    "data/processed/core_bucket_lookup_multicatalog.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"near_complete_forensic_v2_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_LSCO_Near_Complete_Forensic_V2.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_LSCO_Near_Complete_Forensic_V2.xlsx"
)

SUPPRESSION_THRESHOLD = 5


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


def normalize_bucket(value: object) -> str:
    text = str(value).upper()
    text = text.replace("*", "")
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "LIFE AND PHYSICAL SCIENCES":
            "LIFE AND PHYSICAL SCIENCES",
        "LIFE OR PHYSICAL SCIENCES":
            "LIFE AND PHYSICAL SCIENCES",
        "LIFE OR PHYSICAL SCIENCE":
            "LIFE AND PHYSICAL SCIENCES",
        "SOCIAL AND BEHAVIORAL SCIENCES":
            "SOCIAL AND BEHAVIORAL SCIENCES",
        "LANGUAGE, PHILOSOPHY AND CULTURE":
            "LANGUAGE, PHILOSOPHY AND CULTURE",
        "LANGUAGE PHILOSOPHY AND CULTURE":
            "LANGUAGE, PHILOSOPHY AND CULTURE",
        "CREATIVE ARTS":
            "CREATIVE ARTS",
        "COMMUNICATION":
            "COMMUNICATION",
        "MATHEMATICS":
            "MATHEMATICS",
        "AMERICAN HISTORY":
            "AMERICAN HISTORY",
        "GOVERNMENT/POLITICAL SCIENCE":
            "GOVERNMENT/POLITICAL SCIENCE",
        "GOVERNMENT / POLITICAL SCIENCE":
            "GOVERNMENT/POLITICAL SCIENCE",
        "COMPONENT AREA OPTION":
            "COMPONENT AREA OPTION",
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

    if 0 < number < SUPPRESSION_THRESHOLD:
        return f"<{SUPPRESSION_THRESHOLD}"

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

        values = []

        for value in dataframe[column].head(5000):
            if pd.isna(value):
                values.append("")
            else:
                values.append(str(value))

        width = max(
            len(str(column)) + 2,
            max([len(value) for value in values] + [0]) + 2,
        )

        worksheet.set_column(
            column_index,
            column_index,
            min(width, 45),
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
# LOAD INPUTS
# =============================================================================

for path in [
    SUMMARY_PATH,
    DETAIL_PATH,
    HISTORY_PATH,
    ELIGIBILITY_PATH,
    CORE_LOOKUP_PATH,
]:
    require_file(path)

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

history = pd.read_csv(
    HISTORY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

core = pd.read_csv(
    CORE_LOOKUP_PATH,
    dtype=str,
    low_memory=False,
).fillna("")


# =============================================================================
# SELECT BEST ELIGIBLE 0–3 GAP POPULATION
# =============================================================================

summary["requirements_missing_numeric"] = pd.to_numeric(
    summary["requirements_missing"],
    errors="coerce",
)

summary["credential_lineage"] = summary[
    "credential_id"
].map(
    derive_lineage
)

summary["catalog_rank"] = summary[
    "catalog_year"
].map(
    catalog_rank
)

eligibility["catalog_eligible_bool"] = eligibility[
    "catalog_eligible"
].map(
    truthy
)

eligible_keys = eligibility[
    eligibility["catalog_eligible_bool"]
][
    [
        "student_id",
        "catalog_year",
        "eligibility_reason",
    ]
].drop_duplicates(
    subset=[
        "student_id",
        "catalog_year",
    ]
).rename(
    columns={
        "eligibility_reason":
            "catalog_eligibility_reason"
    }
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

diagnostic_population = selected[
    selected[
        "requirements_missing_numeric"
    ].between(
        0,
        3,
        inclusive="both",
    )
].copy()

near_complete = diagnostic_population[
    diagnostic_population[
        "requirements_missing_numeric"
    ].between(
        1,
        3,
        inclusive="both",
    )
].copy()

near_complete["join_key"] = (
    near_complete["student_id"].astype(str)
    + "||"
    + near_complete["credential_id"].astype(str)
    + "||"
    + near_complete["catalog_year"].astype(str)
)

near_keys = set(
    near_complete["join_key"]
)


# =============================================================================
# PASSED COURSE SETS
# =============================================================================

history["passed_bool"] = history[
    "passed"
].map(
    truthy
)

history["normalized_course"] = history[
    "course_code"
].map(
    normalize_course_code
)

passed_history = history[
    history["passed_bool"]
    & history["normalized_course"].ne("")
].copy()

passed_course_sets = (
    passed_history.groupby(
        "student_id"
    )[
        "normalized_course"
    ]
    .agg(
        lambda values:
            set(values)
    )
    .to_dict()
)


# =============================================================================
# CORE LOOKUP
# =============================================================================

core_catalog = first_existing(
    core.columns,
    [
        "catalog_year",
        "catalog",
    ],
    label="core catalog year",
)

core_bucket = first_existing(
    core.columns,
    [
        "bucket_name",
        "core_bucket",
        "requirement_bucket",
    ],
    label="core bucket",
)

core_course = first_existing(
    core.columns,
    [
        "course_code",
        "normalized_course_code",
    ],
    label="core course",
)

core["normalized_bucket"] = core[
    core_bucket
].map(
    normalize_bucket
)

core["normalized_course"] = core[
    core_course
].map(
    normalize_course_code
)

core_lookup = (
    core.groupby(
        [
            core_catalog,
            "normalized_bucket",
        ]
    )[
        "normalized_course"
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


# =============================================================================
# SCAN DETAIL FILE
# =============================================================================

usecols = [
    "student_id",
    "catalog_year",
    "credential_id",
    "requirement_id",
    "rule_type",
    "status",
    "matched_options",
    "matched_terms",
    "matched_term_sorts",
    "matched_grades",
    "latest_matched_term_sort",
    "latest_matched_term_taken",
    "required_options",
    "option_types",
    "used_course_count",
]

parts = []
scanned = 0
retained = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        low_memory=False,
        usecols=usecols,
        chunksize=250_000,
    ),
    start=1,
):
    chunk = chunk.fillna("")

    scanned += len(chunk)

    chunk["join_key"] = (
        chunk["student_id"].astype(str)
        + "||"
        + chunk["credential_id"].astype(str)
        + "||"
        + chunk["catalog_year"].astype(str)
    )

    keep = chunk[
        chunk["join_key"].isin(
            near_keys
        )
    ].copy()

    if not keep.empty:
        parts.append(keep)
        retained += len(keep)

    if chunk_number % 25 == 0:
        print(
            f"Scanned {scanned:,} detail rows; "
            f"retained {retained:,}"
        )

if not parts:
    raise SystemExit(
        "No detail rows matched the near-complete population."
    )

detail = pd.concat(
    parts,
    ignore_index=True,
)

detail = detail.merge(
    near_complete[
        [
            "join_key",
            "student_id",
            "credential_lineage",
            "credential_id",
            "catalog_year",
            "requirements_missing_numeric",
            "gap_band",
        ]
    ],
    on="join_key",
    how="left",
    validate="many_to_one",
    suffixes=(
        "",
        "_summary",
    ),
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

detail["required_course_list"] = detail[
    "required_options"
].map(
    parse_course_list
)

detail["normalized_bucket"] = detail.apply(
    lambda row:
        normalize_bucket(
            row["required_options"]
        )
        if row["rule_type_upper"] == "CORE_BUCKET"
        else "",
    axis=1,
)

detail["used_course_set"] = detail[
    "matched_course_list"
].map(
    set
)

used_course_sets = (
    detail.groupby(
        "join_key"
    )[
        "used_course_set"
    ]
    .agg(
        lambda sets:
            set().union(*sets)
            if len(sets)
            else set()
    )
    .to_dict()
)

unmet = detail[
    detail["status_upper"].eq(
        "UNMET"
    )
].copy()


# =============================================================================
# EXACT + ANY_N TESTS
# =============================================================================

def passed_required(row: pd.Series) -> list[str]:
    passed = passed_course_sets.get(
        str(row["student_id"]),
        set(),
    )

    return sorted(
        passed
        & set(
            row["required_course_list"]
        )
    )


def consumed_required(row: pd.Series) -> list[str]:
    used = used_course_sets.get(
        row["join_key"],
        set(),
    )

    return sorted(
        used
        & set(
            row["required_course_list"]
        )
    )


unmet["passed_required_courses"] = unmet.apply(
    passed_required,
    axis=1,
)

unmet["consumed_required_courses"] = unmet.apply(
    consumed_required,
    axis=1,
)

unmet["passed_required_count"] = unmet[
    "passed_required_courses"
].map(
    len
)

unmet["consumed_required_count"] = unmet[
    "consumed_required_courses"
].map(
    len
)

unmet["passed_required_text"] = unmet[
    "passed_required_courses"
].map(
    lambda values:
        " | ".join(values)
)

unmet["consumed_required_text"] = unmet[
    "consumed_required_courses"
].map(
    lambda values:
        " | ".join(values)
)

unmet["exact_present_in_history"] = (
    unmet["rule_type_upper"].eq("EXACT")
    & unmet["passed_required_count"].gt(0)
)

unmet["exact_consumed_elsewhere"] = (
    unmet["rule_type_upper"].eq("EXACT")
    & unmet["consumed_required_count"].gt(0)
)

unmet["any_n_has_passed_option"] = (
    unmet["rule_type_upper"].eq("ANY_N")
    & unmet["passed_required_count"].gt(0)
)

unmet["any_n_options_consumed_elsewhere"] = (
    unmet["rule_type_upper"].eq("ANY_N")
    & unmet["consumed_required_count"].gt(0)
)


# =============================================================================
# CORE-BUCKET TESTS
# =============================================================================

def passed_bucket_candidates(row: pd.Series) -> list[str]:
    if row["rule_type_upper"] != "CORE_BUCKET":
        return []

    eligible_courses = core_lookup.get(
        (
            str(row["catalog_year"]),
            str(row["normalized_bucket"]),
        ),
        set(),
    )

    passed = passed_course_sets.get(
        str(row["student_id"]),
        set(),
    )

    return sorted(
        eligible_courses
        & passed
    )


def consumed_bucket_candidates(row: pd.Series) -> list[str]:
    if row["rule_type_upper"] != "CORE_BUCKET":
        return []

    eligible_courses = core_lookup.get(
        (
            str(row["catalog_year"]),
            str(row["normalized_bucket"]),
        ),
        set(),
    )

    used = used_course_sets.get(
        row["join_key"],
        set(),
    )

    return sorted(
        eligible_courses
        & used
    )


unmet["passed_bucket_candidates"] = unmet.apply(
    passed_bucket_candidates,
    axis=1,
)

unmet["consumed_bucket_candidates"] = unmet.apply(
    consumed_bucket_candidates,
    axis=1,
)

unmet["passed_bucket_candidate_count"] = unmet[
    "passed_bucket_candidates"
].map(
    len
)

unmet["consumed_bucket_candidate_count"] = unmet[
    "consumed_bucket_candidates"
].map(
    len
)

unmet["passed_bucket_candidate_text"] = unmet[
    "passed_bucket_candidates"
].map(
    lambda values:
        " | ".join(values)
)

unmet["consumed_bucket_candidate_text"] = unmet[
    "consumed_bucket_candidates"
].map(
    lambda values:
        " | ".join(values)
)

unmet["bucket_has_passed_candidate"] = (
    unmet["rule_type_upper"].eq("CORE_BUCKET")
    & unmet["passed_bucket_candidate_count"].gt(0)
)

unmet["bucket_candidate_consumed_elsewhere"] = (
    unmet["rule_type_upper"].eq("CORE_BUCKET")
    & unmet["consumed_bucket_candidate_count"].gt(0)
)


# =============================================================================
# AGGREGATE TABLES
# =============================================================================

gap_summary = (
    diagnostic_population.groupby(
        "gap_band",
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
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
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
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

missing_requirement = (
    unmet.groupby(
        [
            "rule_type_upper",
            "required_options",
            "option_types",
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
        distinct_requirements=(
            "requirement_id",
            "nunique",
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

exact_present_summary = (
    unmet[
        unmet["exact_present_in_history"]
    ]
    .groupby(
        [
            "required_options",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        affected_rows=(
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
        passed_courses=(
            "passed_required_text",
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
        "affected_rows",
        ascending=False,
    )
)

exact_consumed_summary = (
    unmet[
        unmet["exact_consumed_elsewhere"]
    ]
    .groupby(
        [
            "required_options",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        affected_rows=(
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
        consumed_courses=(
            "consumed_required_text",
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
        "affected_rows",
        ascending=False,
    )
)

any_n_summary = (
    unmet[
        unmet["rule_type_upper"].eq("ANY_N")
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
        rows_with_passed_option=(
            "any_n_has_passed_option",
            "sum",
        ),
        rows_with_option_consumed_elsewhere=(
            "any_n_options_consumed_elsewhere",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "unmet_rows",
        ascending=False,
    )
)

bucket_summary = (
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
        rows_with_passed_candidate=(
            "bucket_has_passed_candidate",
            "sum",
        ),
        rows_with_candidate_consumed_elsewhere=(
            "bucket_candidate_consumed_elsewhere",
            "sum",
        ),
        candidate_courses=(
            "passed_bucket_candidate_text",
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
        "unmet_rows",
        ascending=False,
    )
)

by_credential = (
    diagnostic_population.groupby(
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
    )
    .reset_index()
    .sort_values(
        [
            "credential_lineage",
            "gap_band",
        ]
    )
)


# =============================================================================
# FERPA-SAFE TABLES
# =============================================================================

safe_gap_summary = suppress_counts(
    gap_summary,
    [
        "student_lineages",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_by_rule_type = suppress_counts(
    by_rule_type,
    [
        "unmet_rows",
        "distinct_students",
        "credential_lineages",
        "distinct_requirements",
    ],
)

safe_missing_requirement = suppress_counts(
    missing_requirement,
    [
        "unmet_rows",
        "distinct_students",
        "credential_lineages",
        "distinct_requirements",
    ],
)

safe_exact_present_summary = suppress_counts(
    exact_present_summary,
    [
        "affected_rows",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_exact_consumed_summary = suppress_counts(
    exact_consumed_summary,
    [
        "affected_rows",
        "distinct_students",
        "credential_lineages",
    ],
)

safe_any_n_summary = suppress_counts(
    any_n_summary,
    [
        "unmet_rows",
        "distinct_students",
        "rows_with_passed_option",
        "rows_with_option_consumed_elsewhere",
    ],
)

safe_bucket_summary = suppress_counts(
    bucket_summary,
    [
        "unmet_rows",
        "distinct_students",
        "rows_with_passed_candidate",
        "rows_with_candidate_consumed_elsewhere",
    ],
)

safe_by_credential = suppress_counts(
    by_credential,
    [
        "student_lineages",
        "distinct_students",
    ],
)


# =============================================================================
# RESTRICTED DETAIL
# =============================================================================

restricted_unmet = unmet.copy()

restricted_unmet[
    "pseudonymous_id"
] = restricted_unmet[
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
    "used_course_count",
    "passed_required_text",
    "consumed_required_text",
    "exact_present_in_history",
    "exact_consumed_elsewhere",
    "passed_bucket_candidate_text",
    "consumed_bucket_candidate_text",
    "bucket_has_passed_candidate",
    "bucket_candidate_consumed_elsewhere",
]

restricted_unmet = restricted_unmet[
    restricted_columns
].copy()


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
                "Corrected detail schema",
            "Description":
                (
                    "required_options supplies exact-course lists, ANY_N "
                    "option lists, and core-bucket labels. matched_options "
                    "supplies courses already allocated elsewhere."
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
        "Exact Present":
            restricted_unmet[
                restricted_unmet[
                    "exact_present_in_history"
                ]
            ].copy(),
        "Exact Consumed Elsewhere":
            restricted_unmet[
                restricted_unmet[
                    "exact_consumed_elsewhere"
                ]
            ].copy(),
        "Bucket Candidate":
            restricted_unmet[
                restricted_unmet[
                    "bucket_has_passed_candidate"
                ]
            ].copy(),
        "Bucket Consumed Elsewhere":
            restricted_unmet[
                restricted_unmet[
                    "bucket_candidate_consumed_elsewhere"
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
                    f"Positive counts below {SUPPRESSION_THRESHOLD} "
                    f"display as <{SUPPRESSION_THRESHOLD}."
                ),
        },
        {
            "Item":
                "Corrected schema",
            "Description":
                (
                    "The audit detail stores requirement identity in "
                    "required_options and allocated courses in matched_options."
                ),
        },
        {
            "Item":
                "Interpretation",
            "Description":
                (
                    "An unmet exact course already in passed history suggests "
                    "a coding or allocation defect. An unmet course consumed "
                    "elsewhere suggests a course-allocation conflict."
                ),
        },
    ]
)

kpis = pd.DataFrame(
    [
        {
            "Metric":
                "Eligible COMPLETE student-lineages",
            "Value":
                int(
                    (
                        diagnostic_population[
                            "requirements_missing_numeric"
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
                            "requirements_missing_numeric"
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
                            "requirements_missing_numeric"
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
                            "requirements_missing_numeric"
                        ]
                        == 3
                    ).sum()
                ),
        },
        {
            "Metric":
                "Unmet detail rows",
            "Value":
                len(unmet),
        },
        {
            "Metric":
                "Unmet EXACT rows with passed course",
            "Value":
                int(
                    unmet[
                        "exact_present_in_history"
                    ].sum()
                ),
        },
        {
            "Metric":
                "Unmet EXACT rows with course consumed elsewhere",
            "Value":
                int(
                    unmet[
                        "exact_consumed_elsewhere"
                    ].sum()
                ),
        },
        {
            "Metric":
                "Unmet ANY_N rows with passed option",
            "Value":
                int(
                    unmet[
                        "any_n_has_passed_option"
                    ].sum()
                ),
        },
        {
            "Metric":
                "Unmet ANY_N rows with option consumed elsewhere",
            "Value":
                int(
                    unmet[
                        "any_n_options_consumed_elsewhere"
                    ].sum()
                ),
        },
        {
            "Metric":
                "Unmet CORE_BUCKET rows with passed candidate",
            "Value":
                int(
                    unmet[
                        "bucket_has_passed_candidate"
                    ].sum()
                ),
        },
        {
            "Metric":
                "Unmet CORE_BUCKET rows with candidate consumed elsewhere",
            "Value":
                int(
                    unmet[
                        "bucket_candidate_consumed_elsewhere"
                    ].sum()
                ),
        },
    ]
)

kpis["Value"] = kpis["Value"].map(
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
            kpis,
        "Gap Summary":
            safe_gap_summary,
        "By Credential":
            safe_by_credential,
        "By Rule Type":
            safe_by_rule_type,
        "Missing Requirement":
            safe_missing_requirement,
        "Exact Present":
            safe_exact_present_summary,
        "Exact Consumed Elsewhere":
            safe_exact_consumed_summary,
        "ANY_N Review":
            safe_any_n_summary,
        "Core Bucket Review":
            safe_bucket_summary,
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
# CSV SUPPORT
# =============================================================================

safe_missing_requirement.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_missing_requirement_concentration_v2.csv",
    index=False,
)

safe_exact_present_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_exact_present_v2.csv",
    index=False,
)

safe_exact_consumed_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_exact_consumed_elsewhere_v2.csv",
    index=False,
)

safe_any_n_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_any_n_review_v2.csv",
    index=False,
)

safe_bucket_summary.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_core_bucket_review_v2.csv",
    index=False,
)


# =============================================================================
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("LSCO NEAR-COMPLETE FORENSIC REVIEW V2")
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
    f"EXACT unmet with passed course:                  "
    f"{int(unmet['exact_present_in_history'].sum()):,}"
)

print(
    f"EXACT unmet with course consumed elsewhere:      "
    f"{int(unmet['exact_consumed_elsewhere'].sum()):,}"
)

print(
    f"ANY_N unmet with passed option:                  "
    f"{int(unmet['any_n_has_passed_option'].sum()):,}"
)

print(
    f"ANY_N option consumed elsewhere:                 "
    f"{int(unmet['any_n_options_consumed_elsewhere'].sum()):,}"
)

print(
    f"CORE_BUCKET unmet with passed candidate:         "
    f"{int(unmet['bucket_has_passed_candidate'].sum()):,}"
)

print(
    f"CORE_BUCKET candidate consumed elsewhere:        "
    f"{int(unmet['bucket_candidate_consumed_elsewhere'].sum()):,}"
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
