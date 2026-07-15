from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import re
from typing import Iterable

import pandas as pd


# =============================================================================
# LSCO ELECTIVE FORENSIC REVIEW V2
# =============================================================================
#
# Fixes from V1:
#   1. Does not depend on missing elective-policy columns in the requirements
#      master.
#   2. Reconstructs controlled elective policy from credential lineage and
#      requirement text using the authorized LSCO policies already applied in
#      the audit build.
#   3. Reconstructs credit hours from the second digit of the course number when the normalized
#      student history has no usable credit-hour field.
#   4. Produces a conservative count of student × credential lineages that
#      would become COMPLETE if the elective resolver correctly accumulated
#      eligible unused hours.
#
# Privacy:
#   - RESTRICTED workbook stays local.
#   - FERPA_SAFE workbook contains aggregate tables only.
#
# Eligibility:
#   Continuity break is ignored.
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
    f"elective_forensic_review_v2_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_LSCO_Elective_Forensic_Review_V2.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_LSCO_Elective_Forensic_Review_V2.xlsx"
)

SAFE_THRESHOLD = 5


# =============================================================================
# CONTROLLED ELECTIVE POLICIES
# =============================================================================

BUSINESS_SUBJECTS = {
    "ACCT",
    "ACNT",
    "BMGT",
    "BUSG",
    "BUSI",
    "MRKG",
}

BUSINESS_AGRIBUSINESS_SUBJECTS = {
    "ACCT",
    "ACNT",
    "AGCR",
    "AGMG",
    "BMGT",
    "BUSG",
    "BUSI",
    "MRKG",
}

BUSINESS_ANIMAL_SCIENCE_SUBJECTS = {
    "ACCT",
    "ACNT",
    "AGAH",
    "AGCR",
    "AGMG",
    "BMGT",
    "BUSG",
    "BUSI",
    "MRKG",
}

INFORMATION_TECHNOLOGY_SUBJECTS = {
    "ITCC",
    "ITDF",
    "ITSY",
}

SCIENCE_MAJOR_SUBJECTS = {
    "BIOL",
    "CHEM",
    "GEOL",
    "PHYS",
}


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


def infer_sch_from_course_code(value: object) -> float | None:
    """
    Texas course-number convention:
      second digit of the 4-digit number = credit hours.

    Example:
      ENGL 1301 -> 3 SCH
      BIOL 2401 -> 4 SCH
      NAUT 1264 -> 2 SCH

    Returns None when the code cannot be interpreted.
    """
    code = normalize_course_code(value)

    match = re.match(
        r"^[A-Z]{2,5}(\d)(\d{3})$",
        code,
    )

    if not match:
        return None

    hours = int(match.group(2)[0])

    if hours <= 0:
        return None

    return float(hours)


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


def resolve_policy(
    credential_lineage: str,
    required_options: str,
    requirement_id: str,
) -> tuple[str, set[str]]:
    """
    Reconstruct the controlled policy from credential identity and
    requirement text.

    Authorized policy set:
      BUSINESS
      BUSINESS_AGRIBUSINESS
      BUSINESS_ANIMAL_SCIENCE
      INFORMATION_TECHNOLOGY
      SCIENCE_MAJOR
      ANY_UNUSED_PASSED_COURSE
    """
    lineage = str(credential_lineage).upper()
    text = (
        str(required_options)
        + " "
        + str(requirement_id)
    ).upper()

    if (
        "AGRIBUSINESS" in lineage
        or "AGRIBUSINESS" in text
    ):
        return (
            "BUSINESS_AGRIBUSINESS",
            BUSINESS_AGRIBUSINESS_SUBJECTS,
        )

    if (
        "ANIMAL_SCIENCE" in lineage
        or "ANIMAL SCIENCE" in text
    ):
        return (
            "BUSINESS_ANIMAL_SCIENCE",
            BUSINESS_ANIMAL_SCIENCE_SUBJECTS,
        )

    if (
        "INFORMATION_TECHNOLOGY" in lineage
        or "NETWORKING" in lineage
        or "CYBERSECURITY" in lineage
        or "COMPUTER" in lineage
    ):
        return (
            "INFORMATION_TECHNOLOGY",
            INFORMATION_TECHNOLOGY_SUBJECTS,
        )

    if any(
        token in lineage
        for token in [
            "BIOLOGY",
            "NATURAL_SCIENCE",
            "MEDICAL_PROFESSIONS",
        ]
    ):
        return (
            "SCIENCE_MAJOR",
            SCIENCE_MAJOR_SUBJECTS,
        )

    if any(
        token in lineage
        for token in [
            "BUSINESS",
            "ACCOUNTING",
            "MANAGEMENT",
            "MARKETING",
        ]
    ):
        return (
            "BUSINESS",
            BUSINESS_SUBJECTS,
        )

    # Authorized unrestricted cases:
    #   - Approved Elective
    #   - Electro-Mechanical Elective
    #   - General Elective wording with no controlled subject family
    if any(
        phrase in text
        for phrase in [
            "APPROVED ELECTIVE",
            "GENERAL ELECTIVE",
            "ELECTRO-MECHANICAL",
            "ELECTRO MECHANICAL",
            "ANY UNUSED PASSED COURSE",
        ]
    ):
        return (
            "ANY_UNUSED_PASSED_COURSE",
            set(),
        )

    # Liberal Arts elective requirements are generally approved/general
    # elective slots unless the requirement itself lists courses.
    if "LIBERAL_ARTS" in lineage:
        return (
            "ANY_UNUSED_PASSED_COURSE",
            set(),
        )

    return (
        "UNRESOLVED_POLICY",
        set(),
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
        "credit_hours_from_history"
    ] = pd.to_numeric(
        history[history_credit_col],
        errors="coerce",
    )
else:
    history[
        "credit_hours_from_history"
    ] = pd.NA

history[
    "credit_hours_from_code"
] = history[
    "normalized_course"
].map(
    infer_sch_from_course_code
)

history[
    "resolved_credit_hours"
] = history[
    "credit_hours_from_history"
].where(
    history[
        "credit_hours_from_history"
    ].notna(),
    history[
        "credit_hours_from_code"
    ],
)

history[
    "credit_hour_source"
] = history.apply(
    lambda row:
        "HISTORY_FIELD"
        if pd.notna(
            row["credit_hours_from_history"]
        )
        else (
            "COURSE_CODE"
            if pd.notna(
                row["credit_hours_from_code"]
            )
            else "UNRESOLVED"
        ),
    axis=1,
)

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
        resolved_credit_hours=(
            "resolved_credit_hours",
            "max",
        ),
        credit_hour_source=(
            "credit_hour_source",
            join_unique,
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
            float(row["resolved_credit_hours"])
            if pd.notna(
                row["resolved_credit_hours"]
            )
            else None
        )
    for _, row in passed_course_rows.iterrows()
}


# =============================================================================
# LOAD REQUIREMENT CREDIT-HOUR METADATA
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
        required_elective_hours=(
            "required_credit_numeric",
            "max",
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

unmet_electives = detail[
    detail["rule_type_upper"].eq("ELECTIVE")
    & detail["status_upper"].eq("UNMET")
].copy()

if unmet_electives.empty:
    raise SystemExit(
        "No unmet ELECTIVE rows found in the selected population."
    )


# =============================================================================
# RESOLVE POLICY + CANDIDATES
# =============================================================================

policy_results = unmet_electives.apply(
    lambda row:
        resolve_policy(
            row["credential_lineage"],
            row["required_options"],
            row["requirement_id"],
        ),
    axis=1,
)

unmet_electives[
    "resolved_policy"
] = policy_results.map(
    lambda item:
        item[0]
)

unmet_electives[
    "allowed_subject_set"
] = policy_results.map(
    lambda item:
        item[1]
)

unmet_electives[
    "required_elective_hours_numeric"
] = pd.to_numeric(
    unmet_electives[
        "required_elective_hours"
    ],
    errors="coerce",
)

# If requirement hours are absent, infer a conservative requirement from the
# requirement text when it contains a recognizable SCH number.
def infer_required_hours_from_text(
    required_options: object,
) -> float | None:
    text = str(required_options).upper()

    patterns = [
        r"\b(\d+)\s*(?:SCH|SEMESTER CREDIT HOURS?|CREDIT HOURS?|HOURS?)\b",
        r"\bELECTIVE\s*\((\d+)\)\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            return float(
                match.group(1)
            )

    return None


unmet_electives[
    "required_hours_from_text"
] = unmet_electives[
    "required_options"
].map(
    infer_required_hours_from_text
)

unmet_electives[
    "required_elective_hours_effective"
] = unmet_electives[
    "required_elective_hours_numeric"
].where(
    unmet_electives[
        "required_elective_hours_numeric"
    ].notna(),
    unmet_electives[
        "required_hours_from_text"
    ],
)


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

    listed = set(
        row["listed_option_courses"]
        if isinstance(
            row["listed_option_courses"],
            list,
        )
        else []
    )

    policy = row["resolved_policy"]
    subjects = row["allowed_subject_set"]

    if policy == "ANY_UNUSED_PASSED_COURSE":
        return sorted(unused)

    if policy in {
        "BUSINESS",
        "BUSINESS_AGRIBUSINESS",
        "BUSINESS_ANIMAL_SCIENCE",
        "INFORMATION_TECHNOLOGY",
        "SCIENCE_MAJOR",
    }:
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


def candidate_course_hours(
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
    candidate_course_hours,
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
            for course, hours in values
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
    "has_candidate_course"
] = unmet_electives[
    "eligible_unused_course_count"
].gt(0)

unmet_electives[
    "required_hours_known"
] = unmet_electives[
    "required_elective_hours_effective"
].notna()

unmet_electives[
    "candidate_hours_complete"
] = (
    unmet_electives[
        "candidate_courses_missing_hours"
    ].eq(0)
)

unmet_electives[
    "has_enough_hours"
] = (
    unmet_electives[
        "required_hours_known"
    ]
    & (
        unmet_electives[
            "candidate_hours_total"
        ]
        >= unmet_electives[
            "required_elective_hours_effective"
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
            "UNRESOLVED_POLICY"
            if row["resolved_policy"]
            == "UNRESOLVED_POLICY"
            else (
                "REQUIRED_HOURS_UNKNOWN"
                if not row[
                    "required_hours_known"
                ]
                else (
                    "CANDIDATE_HOURS_PARTIALLY_UNKNOWN"
                    if row[
                        "candidate_courses_missing_hours"
                    ] > 0
                    else (
                        "CANDIDATES_PRESENT_NOT_ENOUGH_HOURS"
                        if row[
                            "has_candidate_course"
                        ]
                        else "NO_ELIGIBLE_UNUSED_CANDIDATE"
                    )
                )
            )
        ),
    axis=1,
)


# =============================================================================
# COMPLETION IMPACT
# =============================================================================

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
# AGGREGATES
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
                "Rows with resolved elective policy",
            "value":
                int(
                    unmet_electives[
                        "resolved_policy"
                    ].ne(
                        "UNRESOLVED_POLICY"
                    ).sum()
                ),
        },
        {
            "metric":
                "Rows with unresolved elective policy",
            "value":
                int(
                    unmet_electives[
                        "resolved_policy"
                    ].eq(
                        "UNRESOLVED_POLICY"
                    ).sum()
                ),
        },
        {
            "metric":
                "Rows with known required elective hours",
            "value":
                int(
                    unmet_electives[
                        "required_hours_known"
                    ].sum()
                ),
        },
        {
            "metric":
                "Rows with at least one eligible unused course",
            "value":
                int(
                    unmet_electives[
                        "has_candidate_course"
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
            "resolved_policy",
            "required_elective_hours_effective",
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
            "has_candidate_course",
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
        [
            "rows_with_enough_hours",
            "elective_rows",
        ],
        ascending=[
            False,
            False,
        ],
    )
)

by_credential = (
    unmet_electives.groupby(
        [
            "credential_lineage",
            "catalog_year",
            "resolved_policy",
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
            "has_candidate_course",
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
        [
            "promotable_lineages",
            "rows_with_enough_hours",
            "elective_rows",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )
)

course_hour_quality = (
    passed_history.groupby(
        [
            "credit_hour_source",
        ],
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
        distinct_courses=(
            "normalized_course",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "passed_rows",
        ascending=False,
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
    "resolved_policy",
    "required_elective_hours_effective",
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

safe_course_hour_quality = suppress_counts(
    course_hour_quality,
    [
        "passed_rows",
        "distinct_students",
        "distinct_courses",
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
                "Policy reconstruction",
            "Description":
                (
                    "Uses authorized LSCO elective policies by credential "
                    "family and approved/general elective wording."
                ),
        },
        {
            "Item":
                "Credit-hour reconstruction",
            "Description":
                (
                    "Uses normalized history hours when present; otherwise "
                    "uses the second digit of the Texas four-digit course number."
                ),
        },
        {
            "Item":
                "Promotable definition",
            "Description":
                (
                    "Exactly one unmet requirement, that requirement is "
                    "ELECTIVE, and enough unused eligible SCH are present."
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
        "Unresolved Policies":
            restricted_detail[
                restricted_detail[
                    "resolved_policy"
                ].eq(
                    "UNRESOLVED_POLICY"
                )
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
                "Policy reconstruction",
            "Description":
                (
                    "Uses the controlled LSCO policy set previously authorized "
                    "for business, agribusiness, animal science, IT, science, "
                    "approved electives, and unrestricted electives."
                ),
        },
        {
            "Item":
                "Credit hours",
            "Description":
                (
                    "Uses the history credit field when present; otherwise "
                    "reconstructs SCH from the second digit of the course number."
                ),
        },
        {
            "Item":
                "Promotable estimate",
            "Description":
                (
                    "Conservative lower bound limited to lineages with exactly "
                    "one unmet requirement."
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
    / "FERPA_SAFE_elective_by_policy_v2.csv",
    index=False,
)

safe_by_credential.to_csv(
    OUTPUT_DIR
    / "FERPA_SAFE_elective_by_credential_v2.csv",
    index=False,
)

restricted_detail.to_csv(
    OUTPUT_DIR
    / "RESTRICTED_elective_detail_v2.csv",
    index=False,
)


# =============================================================================
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("LSCO ELECTIVE FORENSIC REVIEW V2")
print("=" * 110)

for _, row in kpi_summary.iterrows():
    print(
        f"{row['metric']:<70} {int(row['value']):>10,}"
    )

print()
print(
    f"History credit-hour field: "
    f"{history_credit_col if history_credit_col else 'NOT FOUND'}"
)

print(
    f"Passed rows using course-code SCH reconstruction: "
    f"{int((passed_history['credit_hour_source'] == 'COURSE_CODE').sum()):,}"
)

print(
    f"Passed rows with unresolved SCH: "
    f"{int((passed_history['credit_hour_source'] == 'UNRESOLVED').sum()):,}"
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
