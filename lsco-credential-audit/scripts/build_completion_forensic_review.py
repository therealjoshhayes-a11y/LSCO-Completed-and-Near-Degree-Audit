from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

REPORTING_ROOT = Path("data/processed/reporting")

SUMMARY_PATH = Path(
    "data/processed/full_actual_audit/"
    "full_actual_credential_summary.csv"
)

ELIGIBILITY_PATH = Path(
    "data/processed/student_catalog_eligibility.csv"
)

HISTORY_PATH = Path(
    "data/processed/normalized_actual_student_course_history.csv"
)

PUBLISHED_YEARS = [
    "2019-2020",
    "2020-2021",
    "2021-2022",
    "2022-2023",
    "2023-2024",
    "2024-2025",
]

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = (
    REPORTING_ROOT
    / f"completion_forensic_review_{RUN_STAMP}"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_WORKBOOK = (
    OUTPUT_DIR
    / "LSCO_Completion_Forensic_Review.xlsx"
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


def numeric_term(
    value: object,
) -> int | None:
    number = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(number):
        return None

    return int(number)


def academic_year_from_term(
    value: object,
) -> str:
    term = numeric_term(
        value
    )

    if term is None:
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


def classify_window(
    academic_year: object,
) -> str:
    value = str(
        academic_year
    ).strip()

    if value in PUBLISHED_YEARS:
        return "IN_PUBLISHED_WINDOW"

    match = re.match(
        r"^(20\d{2})-(20\d{2})$",
        value,
    )

    if not match:
        return "UNMAPPED_YEAR"

    start_year = int(
        match.group(1)
    )

    if start_year < 2019:
        return "BEFORE_PUBLISHED_WINDOW"

    if start_year > 2024:
        return "AFTER_PUBLISHED_WINDOW"

    return "UNMAPPED_YEAR"


def find_latest_reporting_inputs() -> tuple[Path, Path]:
    selection_candidates = list(
        REPORTING_ROOT.glob(
            "credential_completion_comparison_*/"
            "catalog_selection_audit.csv"
        )
    )

    student_candidates = list(
        REPORTING_ROOT.glob(
            "credential_completion_comparison_*/"
            "detected_student_completions.csv"
        )
    )

    if not selection_candidates:
        raise SystemExit(
            "No catalog_selection_audit.csv found "
            "under data/processed/reporting."
        )

    selection_path = max(
        selection_candidates,
        key=lambda path:
            path.stat().st_mtime,
    )

    preferred_student = (
        selection_path.parent
        / "detected_student_completions.csv"
    )

    if preferred_student.exists():
        student_path = preferred_student

    elif student_candidates:
        student_path = max(
            student_candidates,
            key=lambda path:
                path.stat().st_mtime,
        )

    else:
        raise SystemExit(
            "No detected_student_completions.csv found "
            "under data/processed/reporting."
        )

    return (
        selection_path,
        student_path,
    )


def format_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    dataframe: pd.DataFrame,
    freeze_row: int = 1,
) -> None:
    worksheet = writer.sheets[
        sheet_name
    ]

    workbook = writer.book

    header_format = workbook.add_format(
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
            header_format,
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
            min(
                width,
                45,
            ),
        )

    worksheet.freeze_panes(
        freeze_row,
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


# =============================================================================
# LOAD INPUTS
# =============================================================================

for required_path in [
    SUMMARY_PATH,
    ELIGIBILITY_PATH,
    HISTORY_PATH,
]:
    require_file(
        required_path
    )

selection_path, prior_student_path = (
    find_latest_reporting_inputs()
)

print(
    f"Selection audit: {selection_path}"
)

print(
    f"Prior selected students: {prior_student_path}"
)

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

selection = pd.read_csv(
    selection_path,
    dtype=str,
    low_memory=False,
).fillna("")

prior_students = pd.read_csv(
    prior_student_path,
    dtype=str,
    low_memory=False,
).fillna("")


# =============================================================================
# VALIDATE INPUT SCHEMAS
# =============================================================================

required_summary = {
    "student_id",
    "credential_id",
    "catalog_year",
    "audit_status",
    "award_term_sort",
    "award_term_taken",
}

required_eligibility = {
    "student_id",
    "catalog_year",
    "catalog_eligible",
    "eligibility_reason",
}

required_history = {
    "student_id",
    "term_sort",
    "passed",
}

required_selection = {
    "student_id",
    "credential_lineage",
    "credential_id",
    "catalog_year",
    "award_term_sort",
    "award_term_taken",
}

for label, dataframe, required_columns in [
    (
        "summary",
        summary,
        required_summary,
    ),
    (
        "eligibility",
        eligibility,
        required_eligibility,
    ),
    (
        "history",
        history,
        required_history,
    ),
    (
        "selection audit",
        selection,
        required_selection,
    ),
]:
    missing = (
        required_columns
        - set(
            dataframe.columns
        )
    )

    if missing:
        raise SystemExit(
            f"{label} is missing columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )


# =============================================================================
# REBUILD THE REPORTING FUNNEL
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

eligibility[
    "catalog_eligible_bool"
] = eligibility[
    "catalog_eligible"
].map(
    truthy
)

eligible_keys = eligibility[
    eligibility[
        "catalog_eligible_bool"
    ]
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
)

eligible_complete = complete.merge(
    eligible_keys.rename(
        columns={
            "eligibility_reason":
                "catalog_eligibility_reason"
        }
    ),
    on=[
        "student_id",
        "catalog_year",
    ],
    how="inner",
    validate="many_to_one",
)

selection[
    "award_term_numeric"
] = pd.to_numeric(
    selection[
        "award_term_sort"
    ],
    errors="coerce",
)

selection[
    "catalog_rank_numeric"
] = pd.to_numeric(
    selection[
        "catalog_year"
    ]
    .astype(str)
    .str.extract(
        r"^(20\d{2})",
        expand=False,
    ),
    errors="coerce",
).fillna(-1)

selection = selection[
    selection[
        "award_term_numeric"
    ].notna()
].copy()

selection = selection.sort_values(
    [
        "student_id",
        "credential_lineage",
        "award_term_numeric",
        "catalog_rank_numeric",
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

selection[
    "eligible_complete_versions_in_lineage"
] = selection.groupby(
    [
        "student_id",
        "credential_lineage",
    ]
)[
    "credential_id"
].transform(
    "size"
)

first_completion = selection.drop_duplicates(
    subset=[
        "student_id",
        "credential_lineage",
    ],
    keep="first",
).copy()

first_completion[
    "completion_year"
] = first_completion[
    "award_term_numeric"
].map(
    academic_year_from_term
)

first_completion[
    "window_status"
] = first_completion[
    "completion_year"
].map(
    classify_window
)

first_completion[
    "collapsed_catalog_versions"
] = (
    first_completion[
        "eligible_complete_versions_in_lineage"
    ]
    - 1
)

major_map = pd.DataFrame(
    columns=[
        "credential_lineage",
        "major",
    ]
)

if {
    "credential_lineage",
    "major",
}.issubset(
    prior_students.columns
):
    major_map = prior_students[
        [
            "credential_lineage",
            "major",
        ]
    ].drop_duplicates(
        subset=[
            "credential_lineage",
        ]
    )

first_completion = first_completion.merge(
    major_map,
    on="credential_lineage",
    how="left",
    validate="many_to_one",
)

first_completion[
    "major"
] = first_completion[
    "major"
].where(
    first_completion[
        "major"
    ]
    .astype(str)
    .str.strip()
    .ne(""),
    first_completion[
        "credential_lineage"
    ],
)

in_window = first_completion[
    first_completion[
        "window_status"
    ].eq(
        "IN_PUBLISHED_WINDOW"
    )
].copy()

outside_window = first_completion[
    ~first_completion[
        "window_status"
    ].eq(
        "IN_PUBLISHED_WINDOW"
    )
].copy()


# =============================================================================
# OUTSIDE-WINDOW FORENSICS
# =============================================================================

outside_by_status = (
    outside_window.groupby(
        "window_status",
        dropna=False,
    )
    .agg(
        completion_count=(
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
        "completion_count",
        ascending=False,
    )
)

outside_by_year = (
    outside_window.groupby(
        [
            "window_status",
            "completion_year",
        ],
        dropna=False,
    )
    .agg(
        completion_count=(
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
            "window_status",
            "completion_year",
        ]
    )
)

outside_by_credential = (
    outside_window.groupby(
        [
            "window_status",
            "completion_year",
            "credential_lineage",
            "major",
        ],
        dropna=False,
    )
    .agg(
        completion_count=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        selected_catalog_years=(
            "catalog_year",
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
            "completion_count",
            "completion_year",
            "major",
        ],
        ascending=[
            False,
            True,
            True,
        ],
    )
)

outside_by_catalog = (
    outside_window.groupby(
        [
            "window_status",
            "completion_year",
            "catalog_year",
        ],
        dropna=False,
    )
    .agg(
        completion_count=(
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
            "completion_year",
            "catalog_year",
        ]
    )
)


# =============================================================================
# SOURCE POPULATION COVERAGE
# =============================================================================

history[
    "term_numeric"
] = pd.to_numeric(
    history[
        "term_sort"
    ],
    errors="coerce",
)

history[
    "activity_year"
] = history[
    "term_numeric"
].map(
    academic_year_from_term
)

history[
    "passed_bool"
] = history[
    "passed"
].map(
    truthy
)

activity_by_year = (
    history[
        history[
            "activity_year"
        ].ne("")
    ]
    .groupby(
        "activity_year",
        dropna=False,
    )
    .agg(
        course_rows=(
            "student_id",
            "size",
        ),
        students_with_activity=(
            "student_id",
            "nunique",
        ),
        passed_course_rows=(
            "passed_bool",
            "sum",
        ),
    )
    .reset_index()
    .sort_values(
        "activity_year"
    )
)

student_activity_span = (
    history[
        history[
            "term_numeric"
        ].notna()
    ]
    .groupby(
        "student_id",
        dropna=False,
    )
    .agg(
        first_activity_term=(
            "term_numeric",
            "min",
        ),
        latest_activity_term=(
            "term_numeric",
            "max",
        ),
        course_rows=(
            "term_numeric",
            "size",
        ),
        distinct_activity_terms=(
            "term_numeric",
            "nunique",
        ),
    )
    .reset_index()
)

student_activity_span[
    "first_activity_year"
] = student_activity_span[
    "first_activity_term"
].map(
    academic_year_from_term
)

student_activity_span[
    "latest_activity_year"
] = student_activity_span[
    "latest_activity_term"
].map(
    academic_year_from_term
)

latest_activity_distribution = (
    student_activity_span.groupby(
        "latest_activity_year",
        dropna=False,
    )
    .agg(
        students=(
            "student_id",
            "nunique",
        )
    )
    .reset_index()
    .sort_values(
        "latest_activity_year"
    )
)


# =============================================================================
# ELIGIBILITY FORENSICS
# =============================================================================

eligibility_reason_counts = (
    eligibility.groupby(
        [
            "catalog_year",
            "catalog_eligible_bool",
            "eligibility_reason",
        ],
        dropna=False,
    )
    .agg(
        student_catalog_rows=(
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
            "catalog_year",
            "catalog_eligible_bool",
            "student_catalog_rows",
        ],
        ascending=[
            True,
            False,
            False,
        ],
    )
)

eligibility_disposition_for_merge = eligibility[
    [
        "student_id",
        "catalog_year",
        "catalog_eligible_bool",
        "eligibility_reason",
    ]
].rename(
    columns={
        "eligibility_reason":
            "catalog_eligibility_reason"
    }
)

complete_eligibility_disposition = complete.merge(
    eligibility_disposition_for_merge,
    on=[
        "student_id",
        "catalog_year",
    ],
    how="left",
    validate="many_to_one",
)

complete_eligibility_disposition[
    "eligibility_disposition"
] = (
    complete_eligibility_disposition[
        "catalog_eligible_bool"
    ]
    .map(
        {
            True:
                "ELIGIBLE_COMPLETE",
            False:
                "INELIGIBLE_COMPLETE",
        }
    )
    .fillna(
        "NO_ELIGIBILITY_RECORD"
    )
)

complete_eligibility_summary = (
    complete_eligibility_disposition.groupby(
        [
            "catalog_year",
            "eligibility_disposition",
            "catalog_eligibility_reason",
        ],
        dropna=False,
    )
    .agg(
        complete_rows=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        distinct_credentials=(
            "credential_id",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        [
            "catalog_year",
            "eligibility_disposition",
            "complete_rows",
        ],
        ascending=[
            True,
            True,
            False,
        ],
    )
)


# =============================================================================
# CATALOG-VERSION COLLAPSE FORENSICS
# =============================================================================

collapse_distribution = (
    first_completion.groupby(
        [
            "eligible_complete_versions_in_lineage",
            "collapsed_catalog_versions",
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
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "eligible_complete_versions_in_lineage"
    )
)

collapse_detail = selection[
    [
        "student_id",
        "credential_lineage",
        "credential_id",
        "catalog_year",
        "award_term_sort",
        "award_term_taken",
        "award_term_numeric",
        "eligible_complete_versions_in_lineage",
    ]
].copy()

collapse_detail[
    "completion_year"
] = collapse_detail[
    "award_term_numeric"
].map(
    academic_year_from_term
)

collapse_detail[
    "candidate_order"
] = (
    collapse_detail.groupby(
        [
            "student_id",
            "credential_lineage",
        ]
    )
    .cumcount()
    + 1
)

collapse_detail[
    "selected_as_first_completion"
] = collapse_detail[
    "candidate_order"
].eq(1)


# =============================================================================
# COMPLETION-TERM DISTRIBUTION
# =============================================================================

completion_term_distribution = (
    first_completion.groupby(
        [
            "completion_year",
            "award_term_sort",
            "award_term_taken",
            "window_status",
        ],
        dropna=False,
    )
    .agg(
        completion_count=(
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
            "completion_year",
            "award_term_sort",
        ]
    )
)


# =============================================================================
# FULL FUNNEL
# =============================================================================

funnel = pd.DataFrame(
    [
        {
            "stage_order":
                1,
            "stage":
                "Raw COMPLETE catalog-version rows",
            "rows":
                len(complete),
            "distinct_students":
                complete[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                complete[
                    "credential_id"
                ].nunique(),
            "rows_removed_from_prior_stage":
                0,
            "explanation":
                (
                    "Every COMPLETE student × credential × catalog-year row "
                    "in the audit summary."
                ),
        },
        {
            "stage_order":
                2,
            "stage":
                "Eligible COMPLETE catalog-version rows",
            "rows":
                len(eligible_complete),
            "distinct_students":
                eligible_complete[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                eligible_complete[
                    "credential_id"
                ].nunique(),
            "rows_removed_from_prior_stage":
                len(complete)
                - len(eligible_complete),
            "explanation":
                (
                    "COMPLETE rows whose student/catalog-year record "
                    "passed the catalog eligibility rule."
                ),
        },
        {
            "stage_order":
                3,
            "stage":
                "Distinct first-completion student-lineages",
            "rows":
                len(first_completion),
            "distinct_students":
                first_completion[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                first_completion[
                    "credential_lineage"
                ].nunique(),
            "rows_removed_from_prior_stage":
                len(eligible_complete)
                - len(first_completion),
            "explanation":
                (
                    "Multiple eligible catalog versions collapsed within "
                    "student × credential lineage; earliest modeled "
                    "completion term retained."
                ),
        },
        {
            "stage_order":
                4,
            "stage":
                "Inside LSCO published six-year window",
            "rows":
                len(in_window),
            "distinct_students":
                in_window[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                in_window[
                    "credential_lineage"
                ].nunique(),
            "rows_removed_from_prior_stage":
                len(first_completion)
                - len(in_window),
            "explanation":
                (
                    "First modeled completion year is 2019-2020 through "
                    "2024-2025."
                ),
        },
        {
            "stage_order":
                5,
            "stage":
                "Outside LSCO published six-year window",
            "rows":
                len(outside_window),
            "distinct_students":
                outside_window[
                    "student_id"
                ].nunique(),
            "distinct_credentials_or_lineages":
                outside_window[
                    "credential_lineage"
                ].nunique(),
            "rows_removed_from_prior_stage":
                0,
            "explanation":
                (
                    "First modeled completion year is before 2019-2020, "
                    "after 2024-2025, or could not be mapped."
                ),
        },
    ]
)


# =============================================================================
# WRITE SUPPORTING CSV FILES
# =============================================================================

outside_window.to_csv(
    OUTPUT_DIR
    / "outside_published_window_detail.csv",
    index=False,
)

outside_by_year.to_csv(
    OUTPUT_DIR
    / "outside_published_window_by_year.csv",
    index=False,
)

funnel.to_csv(
    OUTPUT_DIR
    / "completion_funnel.csv",
    index=False,
)

complete_eligibility_disposition.to_csv(
    OUTPUT_DIR
    / "complete_eligibility_disposition_detail.csv",
    index=False,
)

collapse_detail.to_csv(
    OUTPUT_DIR
    / "catalog_version_collapse_detail.csv",
    index=False,
)


# =============================================================================
# WRITE FORENSIC WORKBOOK
# =============================================================================

with pd.ExcelWriter(
    OUTPUT_WORKBOOK,
    engine="xlsxwriter",
) as writer:

    sheets = {
        "Read Me":
            pd.DataFrame(
                [
                    {
                        "Item":
                            "Purpose",
                        "Description":
                            (
                                "Forensic reconciliation of modeled completion "
                                "counts before any further comparison with "
                                "LSCO published awards."
                            ),
                    },
                    {
                        "Item":
                            "Published comparison window",
                        "Description":
                            (
                                "2019-2020 through 2024-2025."
                            ),
                    },
                    {
                        "Item":
                            "First-completion rule",
                        "Description":
                            (
                                "For each student × credential lineage, retain "
                                "the earliest modeled completion term among "
                                "eligible COMPLETE catalog-version rows. "
                                "When tied, the latest eligible catalog is "
                                "used only as the catalog label."
                            ),
                    },
                    {
                        "Item":
                            "FERPA",
                        "Description":
                            (
                                "Workbook is generated locally and contains "
                                "student-level records. Do not upload or share "
                                "outside authorized institutional channels."
                            ),
                    },
                    {
                        "Item":
                            "Selection audit source",
                        "Description":
                            str(
                                selection_path
                            ),
                    },
                    {
                        "Item":
                            "Audit summary source",
                        "Description":
                            str(
                                SUMMARY_PATH
                            ),
                    },
                    {
                        "Item":
                            "Eligibility source",
                        "Description":
                            str(
                                ELIGIBILITY_PATH
                            ),
                    },
                    {
                        "Item":
                            "Course history source",
                        "Description":
                            str(
                                HISTORY_PATH
                            ),
                    },
                ]
            ),
        "Full Funnel Counts":
            funnel,
        "537 Outside Detail":
            outside_window,
        "Outside by Status":
            outside_by_status,
        "Outside by Year":
            outside_by_year,
        "Outside by Credential":
            outside_by_credential,
        "Outside by Catalog":
            outside_by_catalog,
        "Eligibility Summary":
            eligibility_reason_counts,
        "Complete Eligibility":
            complete_eligibility_summary,
        "Complete Eligibility Detail":
            complete_eligibility_disposition,
        "Collapse Distribution":
            collapse_distribution,
        "Catalog Collapse Detail":
            collapse_detail,
        "Activity by Year":
            activity_by_year,
        "Student Activity Span":
            student_activity_span,
        "Latest Activity Year":
            latest_activity_distribution,
        "Completion Term Dist":
            completion_term_distribution,
        "First Completion Detail":
            first_completion,
        "In Published Window":
            in_window,
    }

    for sheet_name, dataframe in sheets.items():
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

    # Funnel chart
    funnel_sheet = writer.sheets[
        "Full Funnel Counts"
    ]

    funnel_chart = workbook.add_chart(
        {
            "type":
                "column"
        }
    )

    funnel_chart.add_series(
        {
            "name":
                "Rows",
            "categories":
                [
                    "Full Funnel Counts",
                    1,
                    1,
                    len(funnel),
                    1,
                ],
            "values":
                [
                    "Full Funnel Counts",
                    1,
                    2,
                    len(funnel),
                    2,
                ],
            "data_labels":
                {
                    "value":
                        True
                },
        }
    )

    funnel_chart.set_title(
        {
            "name":
                "Completion Population Funnel"
        }
    )

    funnel_chart.set_y_axis(
        {
            "name":
                "Rows"
        }
    )

    funnel_chart.set_legend(
        {
            "none":
                True
        }
    )

    funnel_chart.set_style(
        10
    )

    funnel_sheet.insert_chart(
        "J2",
        funnel_chart,
        {
            "x_scale":
                1.35,
            "y_scale":
                1.25,
        },
    )

    # Outside year chart
    outside_year_sheet = writer.sheets[
        "Outside by Year"
    ]

    if not outside_by_year.empty:
        outside_chart = workbook.add_chart(
            {
                "type":
                    "column"
            }
        )

        outside_chart.add_series(
            {
                "name":
                    "Outside-window completions",
                "categories":
                    [
                        "Outside by Year",
                        1,
                        1,
                        len(outside_by_year),
                        1,
                    ],
                "values":
                    [
                        "Outside by Year",
                        1,
                        2,
                        len(outside_by_year),
                        2,
                    ],
                "data_labels":
                    {
                        "value":
                            True
                    },
            }
        )

        outside_chart.set_title(
            {
                "name":
                    "Outside-Window Completions by Year"
            }
        )

        outside_chart.set_y_axis(
            {
                "name":
                    "Completions"
            }
        )

        outside_chart.set_legend(
            {
                "none":
                    True
            }
        )

        outside_chart.set_style(
            10
        )

        outside_year_sheet.insert_chart(
            "H2",
            outside_chart,
            {
                "x_scale":
                    1.35,
                "y_scale":
                    1.25,
            },
        )


# =============================================================================
# FINAL VALIDATION AND REPORT
# =============================================================================

if len(
    first_completion
) != (
    len(in_window)
    + len(outside_window)
):
    raise SystemExit(
        "FAILED: in-window plus outside-window rows "
        "do not equal first-completion rows."
    )

if len(
    outside_window
) != 537:
    print(
        "WARNING: Outside-window count is not 537. "
        "This may reflect a newer reporting input."
    )

print()
print("=" * 110)
print("LSCO COMPLETION FORENSIC REVIEW")
print("=" * 110)

print(
    f"Raw COMPLETE catalog-version rows:       "
    f"{len(complete):,}"
)

print(
    f"Eligible COMPLETE catalog-version rows:  "
    f"{len(eligible_complete):,}"
)

print(
    f"Distinct first-completion lineages:      "
    f"{len(first_completion):,}"
)

print(
    f"Inside published six-year window:        "
    f"{len(in_window):,}"
)

print(
    f"Outside published six-year window:       "
    f"{len(outside_window):,}"
)

print()
print(
    f"Workbook: {OUTPUT_WORKBOOK}"
)

print(
    f"Output directory: {OUTPUT_DIR}"
)

print()
print("FORENSIC REPORT GATE: PASSED")
