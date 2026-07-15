from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import sys

import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

SUMMARY_PATH = Path(
    "data/processed/full_actual_audit/"
    "full_actual_credential_summary.csv"
)

ELIGIBILITY_PATH = Path(
    "data/processed/student_catalog_eligibility.csv"
)

LINEAGE_CROSSWALK_PATH = Path(
    "data/processed/reporting/"
    "credential_lineage_crosswalk.csv"
)

PUBLISHED_COUNTS_PATH = Path(
    "data/raw/reference/"
    "lsco_published_credential_counts.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting/"
    f"credential_completion_comparison_{RUN_STAMP}"
)

STUDENT_WORKBOOK = (
    OUTPUT_DIR
    / "Detected_Student_Completions.xlsx"
)

COMPARISON_WORKBOOK = (
    OUTPUT_DIR
    / "LSCO_vs_Audit_Comparison.xlsx"
)


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

def require_file(
    path: Path,
) -> None:
    if not path.exists():
        raise SystemExit(
            f"Required file not found: {path.resolve()}"
        )


def truthy(
    value: object,
) -> bool:
    return str(value).strip().upper() in {
        "TRUE",
        "1",
        "YES",
        "Y",
        "ELIGIBLE",
    }


def normalize_text(
    value: object,
) -> str:
    return " ".join(
        str(value)
        .strip()
        .upper()
        .split()
    )


def derive_lineage(
    credential_id: object,
) -> str:
    """
    Remove only a terminal catalog-year suffix.

    Separate credentials remain separate because the rest of the
    credential ID is preserved.
    """
    value = normalize_text(
        credential_id
    )

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


def display_name_from_lineage(
    lineage: object,
) -> str:
    text = str(
        lineage
    ).strip().replace(
        "_",
        " ",
    )

    replacements = {
        "Aas": "AAS",
        "Aat": "AAT",
        "Aa": "AA",
        "As": "AS",
        "Emt": "EMT",
        "Ems": "EMS",
        "Hvac": "HVAC",
        "It": "IT",
        "Cis": "CIS",
        "Cnc": "CNC",
        "Lvn": "LVN",
        "Rn": "RN",
    }

    words = []

    for word in text.title().split():
        words.append(
            replacements.get(
                word,
                word,
            )
        )

    return " ".join(
        words
    )


def catalog_rank(
    catalog_year: object,
) -> int:
    match = re.match(
        r"^\s*(20\d{2})-(20\d{2})\s*$",
        str(catalog_year),
    )

    if not match:
        return -1

    return int(
        match.group(1)
    )


def numeric_term(
    value: object,
) -> int:
    number = pd.to_numeric(
        pd.Series(
            [value]
        ),
        errors="coerce",
    ).iloc[0]

    if pd.isna(number):
        return -1

    return int(
        number
    )


def completion_year_from_term(
    value: object,
) -> str:
    """
    Convert LSCO six-digit term codes to academic years.

    Fall:
        202190 -> 2021-2022

    Spring:
        202210 -> 2021-2022

    Summer:
        202264 -> 2021-2022
    """
    term = numeric_term(
        value
    )

    if term < 0:
        return ""

    year = term // 100
    suffix = term % 100

    if suffix in FALL_SUFFIXES:
        return (
            f"{year}-{year + 1}"
        )

    if (
        suffix in SPRING_SUFFIXES
        or suffix in SUMMER_SUFFIXES
    ):
        return (
            f"{year - 1}-{year}"
        )

    return ""


def autosize_columns(
    worksheet,
    dataframe: pd.DataFrame,
    max_width: int = 45,
) -> None:
    for column_index, column in enumerate(
        dataframe.columns
    ):
        sample_values = (
            dataframe[column]
            .astype(str)
            .replace(
                "nan",
                "",
            )
            .head(
                5000
            )
            .tolist()
        )

        width = max(
            len(
                str(column)
            )
            + 2,
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
            min(
                width,
                max_width,
            ),
        )


def format_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    dataframe: pd.DataFrame,
) -> None:
    worksheet = writer.sheets[
        sheet_name
    ]

    worksheet.freeze_panes(
        1,
        0,
    )

    if len(
        dataframe.columns
    ) > 0:
        worksheet.autofilter(
            0,
            0,
            max(
                len(dataframe),
                1,
            ),
            len(
                dataframe.columns
            )
            - 1,
        )

    autosize_columns(
        worksheet,
        dataframe,
    )


# =============================================================================
# VALIDATE INPUTS
# =============================================================================

require_file(
    SUMMARY_PATH
)

require_file(
    ELIGIBILITY_PATH
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =============================================================================
# LOAD SUMMARY
# =============================================================================

summary = pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

required_summary_columns = {
    "student_id",
    "credential_id",
    "catalog_year",
    "audit_status",
    "award_term_sort",
    "award_term_taken",
}

missing_summary_columns = (
    required_summary_columns
    - set(
        summary.columns
    )
)

if missing_summary_columns:
    raise SystemExit(
        "Summary file is missing columns: "
        + ", ".join(
            sorted(
                missing_summary_columns
            )
        )
    )

complete = summary[
    summary[
        "audit_status"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
    .eq(
        "COMPLETE"
    )
].copy()

if complete.empty:
    raise SystemExit(
        "No COMPLETE rows found in the audit summary."
    )


# =============================================================================
# LOAD ELIGIBILITY
# =============================================================================

eligibility = pd.read_csv(
    ELIGIBILITY_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

required_eligibility_columns = {
    "student_id",
    "catalog_year",
    "catalog_eligible",
    "eligibility_reason",
}

missing_eligibility_columns = (
    required_eligibility_columns
    - set(
        eligibility.columns
    )
)

if missing_eligibility_columns:
    raise SystemExit(
        "Eligibility file is missing columns: "
        + ", ".join(
            sorted(
                missing_eligibility_columns
            )
        )
    )

eligibility[
    "is_catalog_eligible"
] = eligibility[
    "catalog_eligible"
].map(
    truthy
)

eligible = eligibility[
    eligibility[
        "is_catalog_eligible"
    ]
].copy()

eligible = eligible.drop_duplicates(
    subset=[
        "student_id",
        "catalog_year",
    ]
)

if eligible.empty:
    raise SystemExit(
        "Eligibility file contains no eligible student/catalog rows."
    )

eligible_for_merge = eligible[
    [
        "student_id",
        "catalog_year",
        "eligibility_reason",
        "first_earned_term_sort",
        "latest_earned_term_sort",
        "latest_activity_term_sort",
    ]
].rename(
    columns={
        "eligibility_reason":
            "catalog_eligibility_reason",
        "first_earned_term_sort":
            "eligibility_first_earned_term",
        "latest_earned_term_sort":
            "eligibility_latest_earned_term",
        "latest_activity_term_sort":
            "eligibility_latest_activity_term",
    }
)


# =============================================================================
# APPLY ELIGIBILITY
# =============================================================================

eligible_complete = complete.merge(
    eligible_for_merge,
    on=[
        "student_id",
        "catalog_year",
    ],
    how="inner",
    validate="many_to_one",
)

if eligible_complete.empty:
    raise SystemExit(
        "No COMPLETE rows matched an eligible student/catalog record."
    )


# =============================================================================
# BUILD CREDENTIAL LINEAGES
# =============================================================================

eligible_complete[
    "derived_credential_lineage"
] = eligible_complete[
    "credential_id"
].map(
    derive_lineage
)

if LINEAGE_CROSSWALK_PATH.exists():
    lineage_crosswalk = pd.read_csv(
        LINEAGE_CROSSWALK_PATH,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_crosswalk_columns = {
        "credential_id",
        "credential_lineage",
    }

    missing_crosswalk_columns = (
        required_crosswalk_columns
        - set(
            lineage_crosswalk.columns
        )
    )

    if missing_crosswalk_columns:
        raise SystemExit(
            "Lineage crosswalk is missing columns: "
            + ", ".join(
                sorted(
                    missing_crosswalk_columns
                )
            )
        )

    lineage_crosswalk = (
        lineage_crosswalk[
            [
                "credential_id",
                "credential_lineage",
            ]
        ]
        .drop_duplicates(
            subset=[
                "credential_id",
            ]
        )
    )

    eligible_complete = eligible_complete.merge(
        lineage_crosswalk,
        on="credential_id",
        how="left",
        validate="many_to_one",
    )

    eligible_complete[
        "credential_lineage"
    ] = eligible_complete[
        "credential_lineage"
    ].where(
        eligible_complete[
            "credential_lineage"
        ]
        .astype(str)
        .str.strip()
        .ne(""),
        eligible_complete[
            "derived_credential_lineage"
        ],
    )

else:
    lineage_crosswalk = pd.DataFrame(
        columns=[
            "credential_id",
            "credential_lineage",
        ]
    )

    eligible_complete[
        "credential_lineage"
    ] = eligible_complete[
        "derived_credential_lineage"
    ]


# =============================================================================
# SELECT LATEST ELIGIBLE COMPLETED CATALOG WITHIN EACH LINEAGE
# =============================================================================

eligible_complete[
    "catalog_rank"
] = eligible_complete[
    "catalog_year"
].map(
    catalog_rank
)

eligible_complete[
    "award_term_rank"
] = eligible_complete[
    "award_term_sort"
].map(
    numeric_term
)

eligible_complete = eligible_complete.sort_values(
    [
        "student_id",
        "credential_lineage",
        "catalog_rank",
        "award_term_rank",
        "credential_id",
    ],
    ascending=[
        True,
        True,
        False,
        False,
        False,
    ],
    kind="mergesort",
)

eligible_complete[
    "lineage_candidate_rank"
] = (
    eligible_complete.groupby(
        [
            "student_id",
            "credential_lineage",
        ],
        sort=False,
    )
    .cumcount()
    + 1
)

eligible_complete[
    "complete_versions_in_lineage"
] = eligible_complete.groupby(
    [
        "student_id",
        "credential_lineage",
    ]
)[
    "credential_id"
].transform(
    "size"
)

selected = eligible_complete[
    eligible_complete[
        "lineage_candidate_rank"
    ].eq(
        1
    )
].copy()

selected[
    "major"
] = selected[
    "credential_lineage"
].map(
    display_name_from_lineage
)

selected[
    "completion_year"
] = selected[
    "award_term_sort"
].map(
    completion_year_from_term
)

selected[
    "other_complete_versions"
] = (
    selected[
        "complete_versions_in_lineage"
    ]
    - 1
)

selected[
    "selection_reason"
] = (
    "Latest eligible completed catalog within credential lineage"
)


# =============================================================================
# STUDENT-LEVEL OUTPUT
# =============================================================================

student_output = selected[
    [
        "student_id",
        "credential_lineage",
        "major",
        "credential_id",
        "catalog_year",
        "award_term_sort",
        "award_term_taken",
        "completion_year",
        "other_complete_versions",
        "catalog_eligibility_reason",
        "eligibility_first_earned_term",
        "eligibility_latest_earned_term",
        "eligibility_latest_activity_term",
        "selection_reason",
    ]
].copy()

student_output = student_output.rename(
    columns={
        "credential_id":
            "selected_credential_id",
        "catalog_year":
            "selected_catalog_year",
        "award_term_sort":
            "completion_term_sort",
        "award_term_taken":
            "completion_term",
    }
)

student_output = student_output.sort_values(
    [
        "completion_year",
        "major",
        "selected_catalog_year",
        "student_id",
    ],
    kind="mergesort",
).reset_index(
    drop=True
)


# =============================================================================
# QUALITY CHECKS
# =============================================================================

duplicate_student_lineages = (
    student_output.duplicated(
        subset=[
            "student_id",
            "credential_lineage",
        ],
        keep=False,
    )
)

if duplicate_student_lineages.any():
    duplicate_count = int(
        duplicate_student_lineages.sum()
    )

    raise SystemExit(
        "Duplicate student-lineage selections found: "
        f"{duplicate_count:,}"
    )

missing_completion_year = student_output[
    student_output[
        "completion_year"
    ]
    .astype(str)
    .str.strip()
    .eq("")
].copy()


# =============================================================================
# COUNTS
# =============================================================================

counts_by_year_major_catalog = (
    student_output.groupby(
        [
            "completion_year",
            "credential_lineage",
            "major",
            "selected_catalog_year",
        ],
        dropna=False,
    )
    .agg(
        audit_detected_count=(
            "student_id",
            "nunique",
        )
    )
    .reset_index()
    .sort_values(
        [
            "completion_year",
            "major",
            "selected_catalog_year",
        ],
        kind="mergesort",
    )
)

counts_by_year_major = (
    student_output.groupby(
        [
            "completion_year",
            "credential_lineage",
            "major",
        ],
        dropna=False,
    )
    .agg(
        audit_detected_count=(
            "student_id",
            "nunique",
        )
    )
    .reset_index()
    .sort_values(
        [
            "completion_year",
            "major",
        ],
        kind="mergesort",
    )
)

year_totals = (
    student_output.groupby(
        "completion_year",
        dropna=False,
    )
    .agg(
        audit_detected_count=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        distinct_credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "completion_year",
        kind="mergesort",
    )
)


# =============================================================================
# SELECTION AUDIT
# =============================================================================

selection_audit = eligible_complete[
    [
        "student_id",
        "credential_lineage",
        "credential_id",
        "catalog_year",
        "award_term_sort",
        "award_term_taken",
        "catalog_rank",
        "award_term_rank",
        "lineage_candidate_rank",
        "complete_versions_in_lineage",
        "catalog_eligibility_reason",
    ]
].copy()

selection_audit = selection_audit.sort_values(
    [
        "student_id",
        "credential_lineage",
        "lineage_candidate_rank",
    ],
    kind="mergesort",
).reset_index(
    drop=True
)


# =============================================================================
# LINEAGE REVIEW
# =============================================================================

lineage_review = (
    eligible_complete.groupby(
        [
            "credential_lineage",
            "credential_id",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        eligible_complete_rows=(
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
            "catalog_year",
            "credential_id",
        ],
        kind="mergesort",
    )
)


# =============================================================================
# PUBLISHED COUNTS
# =============================================================================

published_template_columns = [
    "completion_year",
    "credential_lineage",
    "published_credential_name",
    "lsco_published_count",
    "source_note",
]

if PUBLISHED_COUNTS_PATH.exists():
    published = pd.read_csv(
        PUBLISHED_COUNTS_PATH,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_published_columns = {
        "completion_year",
        "credential_lineage",
        "lsco_published_count",
    }

    missing_published_columns = (
        required_published_columns
        - set(
            published.columns
        )
    )

    if missing_published_columns:
        raise SystemExit(
            "Published-count file is missing columns: "
            + ", ".join(
                sorted(
                    missing_published_columns
                )
            )
        )

    for column in published_template_columns:
        if column not in published.columns:
            published[column] = ""

    published = published[
        published_template_columns
    ].copy()

else:
    published = counts_by_year_major[
        [
            "completion_year",
            "credential_lineage",
            "major",
        ]
    ].drop_duplicates().rename(
        columns={
            "major":
                "published_credential_name"
        }
    )

    published[
        "lsco_published_count"
    ] = ""

    published[
        "source_note"
    ] = (
        "ENTER LSCO PUBLISHED COUNT"
    )


# =============================================================================
# COMPARISON
# =============================================================================

comparison = counts_by_year_major.merge(
    published,
    on=[
        "completion_year",
        "credential_lineage",
    ],
    how="outer",
)

comparison[
    "credential_display_name"
] = comparison[
    "major"
].where(
    comparison[
        "major"
    ]
    .astype(str)
    .str.strip()
    .ne(""),
    comparison[
        "published_credential_name"
    ],
)

comparison[
    "audit_detected_count"
] = pd.to_numeric(
    comparison[
        "audit_detected_count"
    ],
    errors="coerce",
).fillna(
    0
).astype(
    int
)

comparison[
    "lsco_published_count_numeric"
] = pd.to_numeric(
    comparison[
        "lsco_published_count"
    ],
    errors="coerce",
)

comparison[
    "difference"
] = (
    comparison[
        "audit_detected_count"
    ]
    - comparison[
        "lsco_published_count_numeric"
    ]
)

comparison[
    "percent_difference"
] = (
    comparison[
        "difference"
    ]
    / comparison[
        "lsco_published_count_numeric"
    ]
)

comparison_output = comparison[
    [
        "completion_year",
        "credential_lineage",
        "credential_display_name",
        "audit_detected_count",
        "lsco_published_count",
        "difference",
        "percent_difference",
        "source_note",
    ]
].sort_values(
    [
        "completion_year",
        "credential_display_name",
    ],
    kind="mergesort",
)


# =============================================================================
# YEAR COMPARISON
# =============================================================================

detected_year_totals = (
    comparison_output.groupby(
        "completion_year",
        dropna=False,
    )[
        "audit_detected_count"
    ]
    .sum()
    .reset_index()
)

published_year_totals = (
    comparison_output.assign(
        published_numeric=pd.to_numeric(
            comparison_output[
                "lsco_published_count"
            ],
            errors="coerce",
        )
    )
    .groupby(
        "completion_year",
        dropna=False,
    )[
        "published_numeric"
    ]
    .sum(
        min_count=1
    )
    .reset_index()
)

year_comparison = detected_year_totals.merge(
    published_year_totals,
    on="completion_year",
    how="outer",
)

year_comparison = year_comparison.rename(
    columns={
        "published_numeric":
            "lsco_published_count"
    }
)

year_comparison[
    "difference"
] = (
    year_comparison[
        "audit_detected_count"
    ]
    - year_comparison[
        "lsco_published_count"
    ]
)

year_comparison = year_comparison.sort_values(
    "completion_year",
    kind="mergesort",
)


# =============================================================================
# WRITE SUPPORTING CSV FILES
# =============================================================================

student_output.to_csv(
    OUTPUT_DIR
    / "detected_student_completions.csv",
    index=False,
)

counts_by_year_major_catalog.to_csv(
    OUTPUT_DIR
    / "detected_counts_by_year_major_catalog.csv",
    index=False,
)

counts_by_year_major.to_csv(
    OUTPUT_DIR
    / "detected_counts_by_year_major.csv",
    index=False,
)

selection_audit.to_csv(
    OUTPUT_DIR
    / "catalog_selection_audit.csv",
    index=False,
)

lineage_review.to_csv(
    OUTPUT_DIR
    / "credential_lineage_review.csv",
    index=False,
)

published.to_csv(
    OUTPUT_DIR
    / "lsco_published_counts_template.csv",
    index=False,
)

missing_completion_year.to_csv(
    OUTPUT_DIR
    / "missing_completion_year_review.csv",
    index=False,
)


# =============================================================================
# WRITE STUDENT WORKBOOK
# =============================================================================

with pd.ExcelWriter(
    STUDENT_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    student_sheets = {
        "All Detected Completions":
            student_output,
        "Counts Year Major Catalog":
            counts_by_year_major_catalog,
        "Counts by Year Major":
            counts_by_year_major,
        "Counts by Year":
            year_totals,
        "Selection Audit":
            selection_audit,
        "Lineage Review":
            lineage_review,
        "Lineage Crosswalk":
            lineage_crosswalk,
        "Completion Year Review":
            missing_completion_year,
    }

    for sheet_name, dataframe in student_sheets.items():
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
# WRITE COMPARISON WORKBOOK
# =============================================================================

with pd.ExcelWriter(
    COMPARISON_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    comparison_sheets = {
        "Year Comparison":
            year_comparison,
        "Credential Comparison":
            comparison_output,
        "Published Counts Input":
            published,
        "Detected Counts":
            counts_by_year_major,
        "Selected Students":
            student_output,
        "Lineage Review":
            lineage_review,
    }

    for sheet_name, dataframe in comparison_sheets.items():
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

    if not year_comparison.empty:
        workbook = writer.book
        worksheet = writer.sheets[
            "Year Comparison"
        ]

        chart = workbook.add_chart(
            {
                "type":
                    "column"
            }
        )

        last_row = len(
            year_comparison
        )

        chart.add_series(
            {
                "name":
                    "Audit detected",
                "categories":
                    [
                        "Year Comparison",
                        1,
                        0,
                        last_row,
                        0,
                    ],
                "values":
                    [
                        "Year Comparison",
                        1,
                        1,
                        last_row,
                        1,
                    ],
            }
        )

        chart.add_series(
            {
                "name":
                    "LSCO published",
                "categories":
                    [
                        "Year Comparison",
                        1,
                        0,
                        last_row,
                        0,
                    ],
                "values":
                    [
                        "Year Comparison",
                        1,
                        2,
                        last_row,
                        2,
                    ],
            }
        )

        chart.set_title(
            {
                "name":
                    "Detected vs. LSCO Published Credentials"
            }
        )

        chart.set_x_axis(
            {
                "name":
                    "Completion year"
            }
        )

        chart.set_y_axis(
            {
                "name":
                    "Credential count",
                "major_gridlines":
                    {
                        "visible":
                            False
                    },
            }
        )

        chart.set_legend(
            {
                "position":
                    "bottom"
            }
        )

        worksheet.insert_chart(
            "F2",
            chart,
            {
                "x_scale":
                    1.4,
                "y_scale":
                    1.4,
            },
        )


# =============================================================================
# FINAL REPORT
# =============================================================================

print("=" * 110)
print("CREDENTIAL COMPLETION REPORT PACKAGE")
print("=" * 110)

print(
    f"Raw COMPLETE rows:              "
    f"{len(complete):,}"
)

print(
    f"Eligible COMPLETE rows:         "
    f"{len(eligible_complete):,}"
)

print(
    f"Selected student-lineages:      "
    f"{len(student_output):,}"
)

print(
    f"Distinct students:              "
    f"{student_output['student_id'].nunique():,}"
)

print(
    f"Credential lineages:            "
    f"{student_output['credential_lineage'].nunique():,}"
)

print(
    f"Completion years represented:   "
    f"{student_output['completion_year'].nunique():,}"
)

print(
    f"Missing completion years:       "
    f"{len(missing_completion_year):,}"
)

print(
    f"Published counts loaded:        "
    f"{PUBLISHED_COUNTS_PATH.exists()}"
)

print()
print(
    f"Student workbook:               "
    f"{STUDENT_WORKBOOK}"
)

print(
    f"Comparison workbook:            "
    f"{COMPARISON_WORKBOOK}"
)

print(
    f"Output directory:               "
    f"{OUTPUT_DIR}"
)

print()
print("=" * 110)
print("REPORT GATE")
print("=" * 110)

if student_output.empty:
    print("FAILED")
    raise SystemExit(
        "No selected student-lineage records were produced."
    )

if not missing_completion_year.empty:
    print(
        "PASSED WITH COMPLETION-YEAR REVIEW"
    )
else:
    print(
        "PASSED"
    )

if not PUBLISHED_COUNTS_PATH.exists():
    print()
    print(
        "LSCO published counts were not loaded."
    )

    print(
        "A populated input template was created at:"
    )

    print(
        OUTPUT_DIR
        / "lsco_published_counts_template.csv"
    )
