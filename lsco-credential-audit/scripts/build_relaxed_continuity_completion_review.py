from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import re

import pandas as pd


# =============================================================================
# PURPOSE
# =============================================================================
#
# Re-evaluate COMPLETE audit rows using a RELAXED catalog eligibility rule:
#
#   earned_course_in_catalog_year == True
#   AND has_activity_after_catalog_life == False
#
# continuity_break is retained for review but is NOT used to exclude records.
#
# Outputs:
#   1. Restricted student-level workbook (keep local)
#   2. FERPA-safe aggregate workbook (safe to upload)
#
# =============================================================================


SUMMARY_PATH = Path(
    "data/processed/full_actual_audit/"
    "full_actual_credential_summary.csv"
)

ELIGIBILITY_PATH = Path(
    "data/processed/student_catalog_eligibility.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"relaxed_continuity_completion_review_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESTRICTED_WORKBOOK = (
    OUTPUT_DIR
    / "RESTRICTED_Relaxed_Continuity_Completion_Candidates.xlsx"
)

SAFE_WORKBOOK = (
    OUTPUT_DIR
    / "FERPA_SAFE_Relaxed_Continuity_Completion_Review.xlsx"
)

RELAXED_ELIGIBILITY_CSV = (
    OUTPUT_DIR
    / "student_catalog_eligibility_no_continuity.csv"
)

SELECTED_CANDIDATES_CSV = (
    OUTPUT_DIR
    / "RESTRICTED_selected_completion_candidates.csv"
)

SAFE_THRESHOLD = 5


# =============================================================================
# TERM DEFINITIONS
# =============================================================================

FALL_SUFFIXES = {
    90,
    91,
    92,
    95,
}

SPRING_SUFFIXES = {
    10,
    13,
    15,
}

SUMMER_SUFFIXES = {
    60,
    64,
}


# =============================================================================
# HELPERS
# =============================================================================

def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(
            f"Required file not found: {path.resolve()}"
        )


def truthy(value: object) -> bool:
    return str(value).strip().upper() in {
        "TRUE",
        "1",
        "YES",
        "Y",
        "T",
        "ELIGIBLE",
    }


def numeric_term(value: object) -> int:
    number = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(number):
        return -1

    return int(number)


def academic_year_from_term(value: object) -> str:
    term = numeric_term(value)

    if term < 0:
        return ""

    year = term // 100
    suffix = term % 100

    if suffix in FALL_SUFFIXES:
        return f"{year}-{year + 1}"

    if suffix in SPRING_SUFFIXES or suffix in SUMMER_SUFFIXES:
        return f"{year - 1}-{year}"

    return ""


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


def award_type(lineage: object) -> str:
    text = str(lineage).upper()

    degree_tokens = [
        "_AAS",
        "_AA",
        "_AS",
        "_AAT",
        "ASSOCIATE",
    ]

    certificate_tokens = [
        "CERT",
        "CERTIFICATE",
    ]

    institutional_award_tokens = [
        "_IA",
        "INSTITUTIONAL_AWARD",
    ]

    if any(token in text for token in degree_tokens):
        return "DEGREE"

    if any(token in text for token in certificate_tokens):
        return "CERTIFICATE"

    if any(token in text for token in institutional_award_tokens):
        return "INSTITUTIONAL_AWARD"

    return "OTHER"


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
# LOAD
# =============================================================================

for path in [
    SUMMARY_PATH,
    ELIGIBILITY_PATH,
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


# =============================================================================
# VALIDATE
# =============================================================================

required_summary = {
    "student_id",
    "catalog_year",
    "credential_id",
    "audit_status",
    "award_term_sort",
    "award_term_taken",
}

required_eligibility = {
    "student_id",
    "catalog_year",
    "earned_course_in_catalog_year",
    "has_activity_after_catalog_life",
    "continuity_break",
    "catalog_eligible",
    "eligibility_reason",
}

missing_summary = required_summary - set(summary.columns)
missing_eligibility = required_eligibility - set(eligibility.columns)

if missing_summary:
    raise SystemExit(
        "Summary is missing columns: "
        + ", ".join(sorted(missing_summary))
    )

if missing_eligibility:
    raise SystemExit(
        "Eligibility is missing columns: "
        + ", ".join(sorted(missing_eligibility))
    )


# =============================================================================
# BUILD RELAXED ELIGIBILITY
# =============================================================================

eligibility[
    "earned_in_catalog_year_bool"
] = eligibility[
    "earned_course_in_catalog_year"
].map(truthy)

eligibility[
    "activity_after_life_bool"
] = eligibility[
    "has_activity_after_catalog_life"
].map(truthy)

eligibility[
    "continuity_break_bool"
] = eligibility[
    "continuity_break"
].map(truthy)

eligibility[
    "original_catalog_eligible_bool"
] = eligibility[
    "catalog_eligible"
].map(truthy)

eligibility[
    "relaxed_catalog_eligible"
] = (
    eligibility[
        "earned_in_catalog_year_bool"
    ]
    & ~eligibility[
        "activity_after_life_bool"
    ]
)

eligibility[
    "relaxed_eligibility_reason"
] = eligibility.apply(
    lambda row:
        "ELIGIBLE_CONTINUITY_IGNORED"
        if (
            row["relaxed_catalog_eligible"]
            and row["continuity_break_bool"]
        )
        else (
            "ELIGIBLE"
            if row["relaxed_catalog_eligible"]
            else (
                "NO_EARNED_COURSE_IN_CATALOG_YEAR"
                if not row["earned_in_catalog_year_bool"]
                else "COURSE_ACTIVITY_AFTER_CATALOG_LIFE"
            )
        ),
    axis=1,
)

eligibility.to_csv(
    RELAXED_ELIGIBILITY_CSV,
    index=False,
)


# =============================================================================
# COMPLETE ROWS + RELAXED ELIGIBILITY
# =============================================================================

complete = summary[
    summary[
        "audit_status"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
    .eq("COMPLETE")
].copy()

relaxed_keys = eligibility[
    eligibility[
        "relaxed_catalog_eligible"
    ]
][
    [
        "student_id",
        "catalog_year",
        "relaxed_eligibility_reason",
        "continuity_break_bool",
        "original_catalog_eligible_bool",
        "earned_in_catalog_year_bool",
        "activity_after_life_bool",
        "first_earned_term_sort",
        "latest_earned_term_sort",
        "latest_activity_term_sort",
    ]
].drop_duplicates(
    subset=[
        "student_id",
        "catalog_year",
    ]
)

relaxed_complete = complete.merge(
    relaxed_keys,
    on=[
        "student_id",
        "catalog_year",
    ],
    how="inner",
    validate="many_to_one",
)

relaxed_complete[
    "credential_lineage"
] = relaxed_complete[
    "credential_id"
].map(derive_lineage)

relaxed_complete[
    "award_type"
] = relaxed_complete[
    "credential_lineage"
].map(award_type)

relaxed_complete[
    "completion_year"
] = relaxed_complete[
    "award_term_sort"
].map(academic_year_from_term)

relaxed_complete[
    "catalog_rank"
] = relaxed_complete[
    "catalog_year"
].map(catalog_rank)

relaxed_complete[
    "award_term_numeric"
] = relaxed_complete[
    "award_term_sort"
].map(numeric_term)

relaxed_complete[
    "newly_admitted_by_relaxation"
] = (
    relaxed_complete[
        "relaxed_catalog_eligible"
    ]
    if "relaxed_catalog_eligible"
    in relaxed_complete.columns
    else True
)

relaxed_complete[
    "newly_admitted_by_relaxation"
] = (
    ~relaxed_complete[
        "original_catalog_eligible_bool"
    ]
    & relaxed_complete[
        "continuity_break_bool"
    ]
)


# =============================================================================
# DEDUPE TO STUDENT × CREDENTIAL LINEAGE
# =============================================================================
#
# Primary candidate selection:
#   earliest modeled completion term
#   then newest eligible catalog at that same completion term
#
# This preserves one modeled award event per student × credential lineage.
#

relaxed_complete = relaxed_complete.sort_values(
    [
        "student_id",
        "credential_lineage",
        "award_term_numeric",
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

relaxed_complete[
    "eligible_complete_versions_in_lineage"
] = relaxed_complete.groupby(
    [
        "student_id",
        "credential_lineage",
    ]
)[
    "credential_id"
].transform("size")

selected_candidates = relaxed_complete.drop_duplicates(
    subset=[
        "student_id",
        "credential_lineage",
    ],
    keep="first",
).copy()

selected_candidates[
    "collapsed_catalog_versions"
] = (
    selected_candidates[
        "eligible_complete_versions_in_lineage"
    ]
    - 1
)

selected_candidates[
    "pseudonymous_id"
] = selected_candidates[
    "student_id"
].map(pseudonym)

selected_candidates[
    "selection_reason"
] = (
    "Earliest modeled completion term; newest relaxed-eligible "
    "catalog used only to label ties"
)

selected_candidates.to_csv(
    SELECTED_CANDIDATES_CSV,
    index=False,
)


# =============================================================================
# AGGREGATES
# =============================================================================

original_eligible_complete_rows = int(
    relaxed_complete[
        "original_catalog_eligible_bool"
    ].sum()
)

new_complete_rows_from_relaxation = int(
    relaxed_complete[
        "newly_admitted_by_relaxation"
    ].sum()
)

original_selected_candidates = selected_candidates[
    selected_candidates[
        "original_catalog_eligible_bool"
    ]
].copy()

new_selected_candidates = selected_candidates[
    selected_candidates[
        "newly_admitted_by_relaxation"
    ]
].copy()

funnel = pd.DataFrame(
    [
        {
            "stage":
                "Raw COMPLETE catalog-version rows",
            "rows":
                len(complete),
            "distinct_students":
                complete["student_id"].nunique(),
            "distinct_credentials_or_lineages":
                complete["credential_id"].nunique(),
        },
        {
            "stage":
                "Original eligible COMPLETE catalog-version rows",
            "rows":
                original_eligible_complete_rows,
            "distinct_students":
                relaxed_complete[
                    relaxed_complete[
                        "original_catalog_eligible_bool"
                    ]
                ]["student_id"].nunique(),
            "distinct_credentials_or_lineages":
                relaxed_complete[
                    relaxed_complete[
                        "original_catalog_eligible_bool"
                    ]
                ]["credential_id"].nunique(),
        },
        {
            "stage":
                "Relaxed eligible COMPLETE catalog-version rows",
            "rows":
                len(relaxed_complete),
            "distinct_students":
                relaxed_complete["student_id"].nunique(),
            "distinct_credentials_or_lineages":
                relaxed_complete["credential_id"].nunique(),
        },
        {
            "stage":
                "New COMPLETE rows admitted by removing continuity",
            "rows":
                new_complete_rows_from_relaxation,
            "distinct_students":
                relaxed_complete[
                    relaxed_complete[
                        "newly_admitted_by_relaxation"
                    ]
                ]["student_id"].nunique(),
            "distinct_credentials_or_lineages":
                relaxed_complete[
                    relaxed_complete[
                        "newly_admitted_by_relaxation"
                    ]
                ]["credential_id"].nunique(),
        },
        {
            "stage":
                "Distinct relaxed completion candidates",
            "rows":
                len(selected_candidates),
            "distinct_students":
                selected_candidates["student_id"].nunique(),
            "distinct_credentials_or_lineages":
                selected_candidates[
                    "credential_lineage"
                ].nunique(),
        },
        {
            "stage":
                "Distinct new candidates admitted by relaxation",
            "rows":
                len(new_selected_candidates),
            "distinct_students":
                new_selected_candidates[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                new_selected_candidates[
                    "credential_lineage"
                ].nunique(),
        },
    ]
)

by_completion_year = (
    selected_candidates.groupby(
        [
            "completion_year",
            "award_type",
        ],
        dropna=False,
    )
    .agg(
        completion_candidates=(
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
        newly_admitted_by_relaxation=(
            "newly_admitted_by_relaxation",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "completion_year",
            "award_type",
        ]
    )
)

by_catalog_year = (
    selected_candidates.groupby(
        [
            "catalog_year",
            "award_type",
        ],
        dropna=False,
    )
    .agg(
        completion_candidates=(
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
        newly_admitted_by_relaxation=(
            "newly_admitted_by_relaxation",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "catalog_year",
            "award_type",
        ]
    )
)

by_credential = (
    selected_candidates.groupby(
        [
            "credential_lineage",
            "award_type",
        ],
        dropna=False,
    )
    .agg(
        completion_candidates=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        completion_years=(
            "completion_year",
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
                ),
        ),
        newly_admitted_by_relaxation=(
            "newly_admitted_by_relaxation",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "completion_candidates",
            "credential_lineage",
        ],
        ascending=[
            False,
            True,
        ],
    )
)

continuity_effect = (
    selected_candidates.groupby(
        [
            "continuity_break_bool",
            "newly_admitted_by_relaxation",
            "award_type",
        ],
        dropna=False,
    )
    .agg(
        completion_candidates=(
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
        [
            "newly_admitted_by_relaxation",
            "award_type",
        ],
        ascending=[
            False,
            True,
        ],
    )
)

degree_only = selected_candidates[
    selected_candidates[
        "award_type"
    ].eq("DEGREE")
].copy()

certificate_only = selected_candidates[
    selected_candidates[
        "award_type"
    ].eq("CERTIFICATE")
].copy()


# =============================================================================
# FERPA-SAFE COPIES
# =============================================================================

safe_funnel = suppress_counts(
    funnel,
    [
        "rows",
        "distinct_students",
        "distinct_credentials_or_lineages",
    ],
)

safe_by_completion_year = suppress_counts(
    by_completion_year,
    [
        "completion_candidates",
        "distinct_students",
        "credential_lineages",
        "newly_admitted_by_relaxation",
    ],
)

safe_by_catalog_year = suppress_counts(
    by_catalog_year,
    [
        "completion_candidates",
        "distinct_students",
        "credential_lineages",
        "newly_admitted_by_relaxation",
    ],
)

safe_by_credential = suppress_counts(
    by_credential,
    [
        "completion_candidates",
        "distinct_students",
        "newly_admitted_by_relaxation",
    ],
)

safe_continuity_effect = suppress_counts(
    continuity_effect,
    [
        "completion_candidates",
        "distinct_students",
        "credential_lineages",
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
                "Eligibility rule",
            "Description":
                (
                    "earned_course_in_catalog_year = True and "
                    "has_activity_after_catalog_life = False. "
                    "continuity_break is ignored."
                ),
        },
        {
            "Item":
                "Selection rule",
            "Description":
                (
                    "One candidate per student × credential lineage, "
                    "using earliest modeled completion term and newest "
                    "relaxed-eligible catalog only to label ties."
                ),
        },
        {
            "Item":
                "Upload status",
            "Description":
                "Do not upload this workbook.",
        },
    ]
)

restricted_columns = [
    "student_id",
    "pseudonymous_id",
    "credential_lineage",
    "credential_id",
    "award_type",
    "catalog_year",
    "completion_year",
    "award_term_sort",
    "award_term_taken",
    "continuity_break_bool",
    "original_catalog_eligible_bool",
    "newly_admitted_by_relaxation",
    "relaxed_eligibility_reason",
    "eligible_complete_versions_in_lineage",
    "collapsed_catalog_versions",
    "selection_reason",
]

with pd.ExcelWriter(
    RESTRICTED_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    restricted_sheets = {
        "Read Me":
            restricted_readme,
        "All Candidate Awards":
            selected_candidates[
                restricted_columns
            ].copy(),
        "Degree Candidates":
            degree_only[
                restricted_columns
            ].copy(),
        "Certificate Candidates":
            certificate_only[
                restricted_columns
            ].copy(),
        "New From Relaxation":
            new_selected_candidates[
                restricted_columns
            ].copy(),
        "All Relaxed Complete Rows":
            relaxed_complete,
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
                    f"Positive counts below {SAFE_THRESHOLD} "
                    f"display as <{SAFE_THRESHOLD}."
                ),
        },
        {
            "Item":
                "Eligibility experiment",
            "Description":
                (
                    "Continuity breaks are ignored. Other eligibility "
                    "conditions remain enforced."
                ),
        },
        {
            "Item":
                "Meaning of candidate",
            "Description":
                (
                    "A student × credential lineage with at least one "
                    "COMPLETE catalog-version row under the relaxed rule."
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
        "Funnel":
            safe_funnel,
        "By Completion Year":
            safe_by_completion_year,
        "By Catalog Year":
            safe_by_catalog_year,
        "By Credential":
            safe_by_credential,
        "Continuity Effect":
            safe_continuity_effect,
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
# FINAL REPORT
# =============================================================================

print()
print("=" * 110)
print("RELAXED CONTINUITY COMPLETION REVIEW")
print("=" * 110)

print(
    f"Raw COMPLETE catalog-version rows:             "
    f"{len(complete):,}"
)

print(
    f"Original eligible COMPLETE rows:               "
    f"{original_eligible_complete_rows:,}"
)

print(
    f"Relaxed eligible COMPLETE rows:                "
    f"{len(relaxed_complete):,}"
)

print(
    f"New COMPLETE rows admitted by relaxation:      "
    f"{new_complete_rows_from_relaxation:,}"
)

print(
    f"Distinct relaxed completion candidates:        "
    f"{len(selected_candidates):,}"
)

print(
    f"Distinct students with relaxed candidates:     "
    f"{selected_candidates['student_id'].nunique():,}"
)

print(
    f"Degree candidates:                             "
    f"{len(degree_only):,}"
)

print(
    f"Certificate candidates:                        "
    f"{len(certificate_only):,}"
)

print(
    f"New distinct candidates from relaxation:       "
    f"{len(new_selected_candidates):,}"
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
