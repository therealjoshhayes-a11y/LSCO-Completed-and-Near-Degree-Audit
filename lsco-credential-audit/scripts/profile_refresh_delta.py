from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd


# ======================================================================================
# PURPOSE
# ======================================================================================
# READ-ONLY / FERPA-SAFE profiler for the Fall 2026 incremental credential-audit refresh.
#
# This script does NOT:
#   - overwrite raw files
#   - overwrite processed audit files
#   - write student-level output
#   - run the credential audit engine
#
# It DOES:
#   - reconcile the July and October Summer 2026 snapshots for profiling
#   - treat the October Summer snapshot as authoritative for 202660
#   - preserve Fall 2026 as empirical enrollment activity
#   - recompute catalog eligibility only for students whose 2026 activity state changed
#   - size both a conservative and a tighter audit worklist
#   - profile the official-award refresh
#   - estimate work reduction using existing run artifacts when possible
#
# Run from the repository root:
#   python -u .\scripts\profile_refresh_delta.py
#
# All written outputs are aggregate FERPA-safe CSV files.


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_student_catalog_eligibility_v2 as eligibility_v2  # noqa: E402


# ======================================================================================
# DEFAULT LOCAL PATHS
# ======================================================================================

DEFAULT_HISTORICAL_ATTEMPTS = Path(
    "data/raw/student_exports/banner_course_history_actual.csv"
)
DEFAULT_NEW_ATTEMPTS = Path(
    "data/raw/student_exports/Summer 2026 and Fall 2026 Course Attempts_(10.5.26).xlsx"
)
DEFAULT_PRIOR_AWARDS = Path(
    "data/raw/institutional_awards/lsco_awards_sample_20260730.xlsx"
)
DEFAULT_NEW_AWARDS = Path(
    "data/raw/institutional_awards/Summer 2026 Awards_(8.31.26).xlsx"
)
DEFAULT_PRIOR_SUMMARY = Path(
    "data/processed/full_actual_audit/full_actual_credential_summary.csv"
)
DEFAULT_PRIOR_ELIGIBILITY = Path(
    "data/processed/student_catalog_eligibility.csv"
)
DEFAULT_REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/requirements_master_multiyear.csv"
)
DEFAULT_RUN_LOG = Path(
    "data/processed/full_actual_audit/full_actual_audit_run_log.csv"
)

SUMMER_2026 = 202660
FALL_2026 = 202690


# ======================================================================================
# GOVERNED DECISIONS ALREADY AUTHORIZED FOR THIS REFRESH
# ======================================================================================

# GOVERNED HUMAN DECISION
# Authorized by: Joshua Hayes
# Date: 2026-10-07
# Blank FinalGrade values in the Fall 2026 source represent courses in progress.
# They are valid enrollment/activity records and do not represent earned credit.
#
# GOVERNED HUMAN DECISION
# Authorized by: Joshua Hayes
# Date: 2026-10-07
# Any Fall 2026 course attempt establishes membership in the current-enrollment
# population for this refresh.
#
# GOVERNED DATA-HYGIENE DECISION
# Authorized by: Joshua Hayes
# Date: 2026-10-07
# The October 2026 extract is the authoritative Summer 2026 (202660) snapshot.
# The July 202660 rows are superseded for current course-state/eligibility refresh
# purposes. The original July source remains untouched as historical evidence.
#
# GOVERNED DATA-HYGIENE DECISION
# Authorized by: Joshua Hayes
# Date: 2026-10-07
# When multiple source rows share student + term + course and every substantive
# field agrees, with Section as the only difference, they represent linked-section
# expansion of one academic course attempt. Preserve all section codes as provenance
# but count one academic attempt. If substantive fields disagree, STOP and review;
# do not collapse by inference.


# ======================================================================================
# SOURCE SHAPES
# ======================================================================================

HISTORICAL_REQUIRED = [
    "StudenID",
    "FirstName",
    "LastName",
    "StudentMajor",
    "Subject",
    "CrseNumb",
    "Section",
    "FinalGrade",
    "Term",
    "DualCreditIndicator",
    "HighSchool",
    "LastTermDualCredit",
]

NEW_REQUIRED = [
    "Student_Id",
    "First_Name",
    "Last_Name",
    "StudentMajor",
    "Subject_Code",
    "Course_Numb",
    "Section_Numb",
    "Final_Grade",
    "Term_Code",
    "DualCreditIndicator",
    "High School",
    "LastTermDualCredit",
]

AWARD_REQUIRED = [
    "ID",
    "FirstName",
    "LastName",
    "Curr1ProgramCode",
    "Major1Code",
    "MajorDesc",
    "DegreeCode",
    "DegreeDesc",
    "StudGradTerm",
    "GradDate",
    "DegreeStat",
]

CANONICAL_ATTEMPT_COLUMNS = [
    "student_id",
    "first_name",
    "last_name",
    "student_major",
    "subject",
    "course_number",
    "section",
    "grade",
    "term_sort",
    "dual_credit_indicator",
    "high_school",
    "last_term_dual_credit",
    "source_dataset",
    "source_row_number",
]


# ======================================================================================
# CLI
# ======================================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile the 2026 LSCO incremental audit refresh without changing production state."
    )
    parser.add_argument(
        "--historical-attempts",
        default=str(DEFAULT_HISTORICAL_ATTEMPTS),
    )
    parser.add_argument(
        "--new-attempts",
        default=str(DEFAULT_NEW_ATTEMPTS),
    )
    parser.add_argument(
        "--prior-awards",
        default=str(DEFAULT_PRIOR_AWARDS),
    )
    parser.add_argument(
        "--new-awards",
        default=str(DEFAULT_NEW_AWARDS),
    )
    parser.add_argument(
        "--prior-summary",
        default=str(DEFAULT_PRIOR_SUMMARY),
    )
    parser.add_argument(
        "--prior-eligibility",
        default=str(DEFAULT_PRIOR_ELIGIBILITY),
    )
    parser.add_argument(
        "--requirements",
        default=str(DEFAULT_REQUIREMENTS),
    )
    parser.add_argument(
        "--run-log",
        default=str(DEFAULT_RUN_LOG),
    )
    parser.add_argument(
        "--output-dir",
        default="",
    )
    return parser.parse_args()


# ======================================================================================
# BASIC HELPERS
# ======================================================================================

def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().upper().split())


def clean_display(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().split())


def clean_course_number(value: object) -> str:
    """Mechanical source normalization only; no academic equivalency inference."""
    text = clean_text(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text


def to_term(value: object) -> int | None:
    text = clean_text(value)
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        return None
    return int(text)


def validate_columns(
    df: pd.DataFrame,
    required: list[str],
    label: str,
) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def first_sheet(path: Path, preferred: str | None = None) -> str:
    book = pd.ExcelFile(path)

    if preferred and preferred in book.sheet_names:
        return preferred

    if len(book.sheet_names) == 1:
        return book.sheet_names[0]

    raise ValueError(
        f"{path} has multiple worksheets and preferred sheet {preferred!r} "
        f"was not found. Sheets: {book.sheet_names}"
    )


def truthy_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.upper()
        .isin({"TRUE", "1", "YES", "Y", "ELIGIBLE"})
    )


# ======================================================================================
# COURSE-ATTEMPT READERS
# ======================================================================================

def read_historical_attempts(path: Path) -> pd.DataFrame:
    require_file(path)

    raw = pd.read_csv(
        path,
        dtype=str,
        low_memory=False,
        encoding="cp1252",
        encoding_errors="replace",
    ).fillna("")

    validate_columns(
        raw,
        HISTORICAL_REQUIRED,
        "Historical course-attempt source",
    )

    out = pd.DataFrame(
        {
            "student_id": raw["StudenID"].map(clean_text),
            "first_name": raw["FirstName"].map(clean_display),
            "last_name": raw["LastName"].map(clean_display),
            "student_major": raw["StudentMajor"].map(clean_text),
            "subject": raw["Subject"].map(clean_text),
            "course_number": raw["CrseNumb"].map(clean_course_number),
            "section": raw["Section"].map(clean_text),
            "grade": raw["FinalGrade"].map(clean_text),
            "term_sort": raw["Term"].map(to_term),
            "dual_credit_indicator": raw["DualCreditIndicator"].map(clean_text),
            "high_school": raw["HighSchool"].map(clean_display),
            "last_term_dual_credit": raw["LastTermDualCredit"].map(clean_text),
            "source_dataset": "HISTORICAL_20260709",
            "source_row_number": range(2, len(raw) + 2),
        }
    )

    return out[CANONICAL_ATTEMPT_COLUMNS]


def read_new_attempts(path: Path) -> tuple[pd.DataFrame, str]:
    require_file(path)

    sheet = first_sheet(path, preferred="202660 Course Attempts")

    raw = pd.read_excel(
        path,
        sheet_name=sheet,
        dtype=str,
    ).fillna("")

    validate_columns(
        raw,
        NEW_REQUIRED,
        "Summer/Fall 2026 course-attempt source",
    )

    out = pd.DataFrame(
        {
            "student_id": raw["Student_Id"].map(clean_text),
            "first_name": raw["First_Name"].map(clean_display),
            "last_name": raw["Last_Name"].map(clean_display),
            "student_major": raw["StudentMajor"].map(clean_text),
            "subject": raw["Subject_Code"].map(clean_text),
            "course_number": raw["Course_Numb"].map(clean_course_number),
            "section": raw["Section_Numb"].map(clean_text),
            "grade": raw["Final_Grade"].map(clean_text),
            "term_sort": raw["Term_Code"].map(to_term),
            "dual_credit_indicator": raw["DualCreditIndicator"].map(clean_text),
            "high_school": raw["High School"].map(clean_display),
            "last_term_dual_credit": raw["LastTermDualCredit"].map(clean_text),
            "source_dataset": "CURRENT_20261005",
            "source_row_number": range(2, len(raw) + 2),
        }
    )

    return out[CANONICAL_ATTEMPT_COLUMNS], sheet


# ======================================================================================
# LINKED-SECTION NORMALIZATION
# ======================================================================================

def collapse_linked_sections(
    attempts: pd.DataFrame,
    *,
    label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse verified linked-section expansion to one academic attempt.

    The grouping key is student + term + subject + course_number.
    Section may vary. Every other substantive source field must agree.
    Any conflicting group is returned in the conflict table and causes
    the caller to stop before using the collapsed state.
    """

    key = [
        "student_id",
        "term_sort",
        "subject",
        "course_number",
    ]

    substantive = [
        "first_name",
        "last_name",
        "student_major",
        "grade",
        "dual_credit_indicator",
        "high_school",
        "last_term_dual_credit",
    ]

    valid = attempts[
        attempts["student_id"].ne("")
        & attempts["term_sort"].notna()
        & attempts["subject"].ne("")
        & attempts["course_number"].ne("")
    ].copy()

    grouped = valid.groupby(key, dropna=False, sort=False)

    conflict_keys: set[tuple] = set()

    for column in substantive:
        varying = grouped[column].nunique(dropna=False)
        conflict_keys.update(varying[varying > 1].index.tolist())

    conflict_rows = pd.DataFrame(columns=valid.columns)

    if conflict_keys:
        conflict_index = pd.MultiIndex.from_tuples(
            conflict_keys,
            names=key,
        )
        indexed = valid.set_index(key)
        conflict_rows = (
            indexed.loc[indexed.index.isin(conflict_index)]
            .reset_index()
        )

    safe = valid.copy()

    if conflict_keys:
        safe_index = pd.MultiIndex.from_frame(safe[key])
        conflict_index = pd.MultiIndex.from_tuples(
            conflict_keys,
            names=key,
        )
        safe = safe.loc[~safe_index.isin(conflict_index)].copy()

    rows: list[dict] = []

    for group_key, group in safe.groupby(
        key,
        dropna=False,
        sort=False,
    ):
        first = group.iloc[0]

        sections = sorted(
            {
                clean_text(value)
                for value in group["section"]
                if clean_text(value)
            }
        )

        row = {
            column: first[column]
            for column in CANONICAL_ATTEMPT_COLUMNS
            if column not in {
                "section",
                "source_row_number",
            }
        }

        row["section"] = ";".join(sections)
        row["source_row_number"] = ";".join(
            str(value)
            for value in sorted(
                group["source_row_number"].astype(int).tolist()
            )
        )
        row["raw_row_count"] = len(group)
        row["linked_section_count"] = len(sections)

        rows.append(row)

    collapsed = pd.DataFrame(rows)

    if not collapsed.empty:
        collapsed = collapsed[
            CANONICAL_ATTEMPT_COLUMNS
            + ["raw_row_count", "linked_section_count"]
        ]

    return collapsed, conflict_rows


# ======================================================================================
# AWARD READERS
# ======================================================================================

def read_awards(
    path: Path,
    *,
    preferred_sheet: str,
    source_label: str,
) -> tuple[pd.DataFrame, str]:
    require_file(path)

    sheet = first_sheet(path, preferred=preferred_sheet)

    raw = pd.read_excel(
        path,
        sheet_name=sheet,
        dtype=str,
    ).fillna("")

    validate_columns(
        raw,
        AWARD_REQUIRED,
        source_label,
    )

    # Preserve CIPCode when available; blank for historical rows that predate
    # that extract column.
    if "CIPCode" not in raw.columns:
        raw["CIPCode"] = ""

    keep = [
        "ID",
        "FirstName",
        "LastName",
        "CIPCode",
        "Curr1ProgramCode",
        "Major1Code",
        "MajorDesc",
        "DegreeCode",
        "DegreeDesc",
        "StudGradTerm",
        "GradDate",
        "DegreeStat",
    ]

    out = raw[keep].copy()

    for column in keep:
        if column in {"FirstName", "LastName", "MajorDesc", "DegreeDesc"}:
            out[column] = out[column].map(clean_display)
        else:
            out[column] = out[column].map(clean_text)

    out["source_dataset"] = source_label
    return out, sheet


# ======================================================================================
# ELIGIBILITY STATE
# ======================================================================================

def activity_state(attempts: pd.DataFrame) -> pd.DataFrame:
    """Compress course rows to the exact state V2 eligibility needs.

    Catalog segmentation is based on terms with any activity.
    earned-term metadata is TRUE if any attempt in that term has a grade
    currently treated as passing by the already-governed V2 function.
    """

    work = attempts[
        attempts["student_id"].ne("")
        & attempts["term_sort"].notna()
    ][
        ["student_id", "term_sort", "grade"]
    ].copy()

    work["term_sort"] = work["term_sort"].astype(int)
    work["is_passing"] = work["grade"].isin(
        eligibility_v2.PASSING_GRADES
    )

    return (
        work.groupby(
            ["student_id", "term_sort"],
            as_index=False,
            sort=True,
        )["is_passing"]
        .any()
    )


def cohort_label(
    student_id: str,
    *,
    pre_summer_ids: set[str],
    current_summer_ids: set[str],
    fall_ids: set[str],
    old_summer_ids: set[str],
) -> str:
    returning = student_id in pre_summer_ids
    summer = student_id in current_summer_ids
    fall = student_id in fall_ids
    stale_summer = (
        student_id in old_summer_ids
        and student_id not in current_summer_ids
    )

    prefix = "RETURNING" if returning else "NEW"

    if summer and fall:
        return f"{prefix}_SUMMER_AND_FALL"
    if summer:
        return f"{prefix}_SUMMER_ONLY"
    if fall:
        return f"{prefix}_FALL_ONLY"
    if stale_summer:
        return f"{prefix}_REMOVED_SUMMER_SNAPSHOT_ONLY"
    return f"{prefix}_OTHER_AFFECTED"


# ======================================================================================
# PRIOR SUMMARY STREAMING
# ======================================================================================

def scan_prior_summary(
    path: Path,
    affected_ids: set[str],
) -> tuple[dict, pd.DataFrame, set[str]]:
    require_file(path)

    total_rows = 0
    affected_rows = 0
    complete_rows = 0
    affected_complete_rows = 0
    student_ids: set[str] = set()
    affected_students_in_summary: set[str] = set()
    rows_by_catalog: Counter[str] = Counter()
    affected_rows_by_catalog: Counter[str] = Counter()

    usecols = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
    ]

    for chunk in pd.read_csv(
        path,
        dtype=str,
        usecols=usecols,
        chunksize=250_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        chunk["student_id"] = chunk["student_id"].map(clean_text)
        chunk["catalog_year"] = chunk["catalog_year"].astype(str).str.strip()
        chunk["audit_status"] = chunk["audit_status"].map(clean_text)

        total_rows += len(chunk)
        student_ids.update(
            chunk.loc[
                chunk["student_id"].ne(""),
                "student_id",
            ].unique().tolist()
        )

        catalog_counts = chunk["catalog_year"].value_counts()
        rows_by_catalog.update(
            {str(k): int(v) for k, v in catalog_counts.items()}
        )

        is_complete = chunk["audit_status"].eq("COMPLETE")
        complete_rows += int(is_complete.sum())

        is_affected = chunk["student_id"].isin(affected_ids)
        affected_students_in_summary.update(
            chunk.loc[
                is_affected,
                "student_id",
            ].unique().tolist()
        )
        affected_rows += int(is_affected.sum())
        affected_complete_rows += int(
            (is_affected & is_complete).sum()
        )

        affected_catalog_counts = (
            chunk.loc[is_affected, "catalog_year"]
            .value_counts()
        )
        affected_rows_by_catalog.update(
            {
                str(k): int(v)
                for k, v in affected_catalog_counts.items()
            }
        )

    by_catalog = pd.DataFrame(
        [
            {
                "catalog_year": catalog,
                "prior_summary_rows": rows_by_catalog[catalog],
                "prior_summary_rows_for_affected_students": (
                    affected_rows_by_catalog[catalog]
                ),
            }
            for catalog in sorted(rows_by_catalog)
        ]
    )

    metrics = {
        "prior_summary_rows": total_rows,
        "prior_summary_unique_students": len(student_ids),
        "prior_summary_complete_rows": complete_rows,
        "prior_summary_rows_for_affected_students": affected_rows,
        "prior_summary_complete_rows_for_affected_students": (
            affected_complete_rows
        ),
    }

    return metrics, by_catalog, affected_students_in_summary


# ======================================================================================
# RUNTIME ESTIMATE
# ======================================================================================

def estimate_runtime(
    run_log_path: Path,
    *,
    prior_unique_students: int,
    prior_catalogs: set[str],
    requirements: pd.DataFrame,
    optimized_requirement_units: int,
    conservative_requirement_units: int,
) -> dict:
    result = {
        "run_log_found": False,
        "run_log_rows": 0,
        "run_log_student_count": 0,
        "run_log_elapsed_seconds": 0.0,
        "run_log_coverage_ratio": "",
        "baseline_requirement_units_estimate": "",
        "seconds_per_requirement_unit_estimate": "",
        "optimized_runtime_minutes_estimate": "",
        "conservative_runtime_minutes_estimate": "",
        "runtime_estimate_usable": False,
    }

    if not run_log_path.exists():
        return result

    run_log = pd.read_csv(
        run_log_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    needed = {
        "student_count",
        "elapsed_seconds",
    }

    if not needed.issubset(run_log.columns):
        return result

    student_count = pd.to_numeric(
        run_log["student_count"],
        errors="coerce",
    ).fillna(0).sum()

    elapsed_seconds = pd.to_numeric(
        run_log["elapsed_seconds"],
        errors="coerce",
    ).fillna(0).sum()

    coverage = (
        float(student_count) / prior_unique_students
        if prior_unique_students
        else 0.0
    )

    prior_req_rows = requirements[
        requirements["catalog_year"].astype(str).isin(prior_catalogs)
    ]

    req_rows_per_student = len(prior_req_rows)
    baseline_units = (
        int(prior_unique_students) * int(req_rows_per_student)
    )

    result.update(
        {
            "run_log_found": True,
            "run_log_rows": len(run_log),
            "run_log_student_count": int(student_count),
            "run_log_elapsed_seconds": round(float(elapsed_seconds), 2),
            "run_log_coverage_ratio": round(coverage, 4),
            "baseline_requirement_units_estimate": baseline_units,
        }
    )

    # Do not issue a runtime estimate from a partial run log.
    if (
        coverage < 0.95
        or elapsed_seconds <= 0
        or baseline_units <= 0
    ):
        return result

    seconds_per_unit = float(elapsed_seconds) / baseline_units

    result.update(
        {
            "seconds_per_requirement_unit_estimate": seconds_per_unit,
            "optimized_runtime_minutes_estimate": round(
                optimized_requirement_units
                * seconds_per_unit
                / 60,
                2,
            ),
            "conservative_runtime_minutes_estimate": round(
                conservative_requirement_units
                * seconds_per_unit
                / 60,
                2,
            ),
            "runtime_estimate_usable": True,
        }
    )

    return result


# ======================================================================================
# MAIN
# ======================================================================================

def main() -> None:
    args = parse_args()

    historical_path = Path(args.historical_attempts)
    new_path = Path(args.new_attempts)
    prior_awards_path = Path(args.prior_awards)
    new_awards_path = Path(args.new_awards)
    prior_summary_path = Path(args.prior_summary)
    prior_eligibility_path = Path(args.prior_eligibility)
    requirements_path = Path(args.requirements)
    run_log_path = Path(args.run_log)

    for path in (
        historical_path,
        new_path,
        prior_awards_path,
        new_awards_path,
        prior_summary_path,
        prior_eligibility_path,
        requirements_path,
    ):
        require_file(path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("data/processed/reporting")
        / f"refresh_delta_profile_{stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------------------
    # 1. Load source attempts
    # ----------------------------------------------------------------------------------

    historical = read_historical_attempts(historical_path)
    current_raw, new_sheet = read_new_attempts(new_path)

    invalid_current_terms = sorted(
        {
            int(value)
            for value in current_raw["term_sort"].dropna()
            if int(value) not in {SUMMER_2026, FALL_2026}
        }
    )

    if invalid_current_terms:
        raise RuntimeError(
            "Current 2026 source contains unexpected term codes: "
            + ", ".join(map(str, invalid_current_terms))
        )

    current, linked_conflicts = collapse_linked_sections(
        current_raw,
        label="CURRENT_2026",
    )

    if not linked_conflicts.empty:
        raise RuntimeError(
            "Current 2026 source contains student/term/course groups that differ "
            "in substantive fields, not just Section. No collapse was performed "
            "for those groups. Review required before continuing. "
            f"Conflicting raw rows: {len(linked_conflicts):,}"
        )

    # ----------------------------------------------------------------------------------
    # 2. Reconcile Summer snapshot
    # ----------------------------------------------------------------------------------

    historical_summer = historical[
        historical["term_sort"].eq(SUMMER_2026)
    ].copy()

    current_summer = current[
        current["term_sort"].eq(SUMMER_2026)
    ].copy()

    current_fall = current[
        current["term_sort"].eq(FALL_2026)
    ].copy()

    pre_summer_history = historical[
        historical["term_sort"].notna()
        & historical["term_sort"].lt(SUMMER_2026)
    ].copy()

    pre_summer_ids = set(
        pre_summer_history["student_id"].unique()
    )
    old_summer_ids = set(
        historical_summer["student_id"].unique()
    )
    current_summer_ids = set(
        current_summer["student_id"].unique()
    )
    fall_ids = set(
        current_fall["student_id"].unique()
    )

    affected_ids = (
        old_summer_ids
        | current_summer_ids
        | fall_ids
    )

    # Authoritative current empirical attempt state:
    # historical evidence excluding the superseded July 202660 snapshot
    # plus the October 202660/202690 snapshot.
    refreshed_attempt_state = pd.concat(
        [
            historical[
                ~historical["term_sort"].eq(SUMMER_2026)
            ],
            current[
                CANONICAL_ATTEMPT_COLUMNS
            ],
        ],
        ignore_index=True,
    )

    affected_attempt_state = refreshed_attempt_state[
        refreshed_attempt_state["student_id"].isin(affected_ids)
    ].copy()

    # Existing V2 eligibility needs only activity terms and whether any passing
    # work occurred in a term.
    affected_activity = activity_state(
        affected_attempt_state
    )

    # ----------------------------------------------------------------------------------
    # 3. Load current catalog master and recompute eligibility for affected students
    # ----------------------------------------------------------------------------------

    requirements = pd.read_csv(
        requirements_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_req_cols = {
        "catalog_year",
        "credential_id",
    }

    if not required_req_cols.issubset(requirements.columns):
        raise ValueError(
            "Requirements master is missing: "
            + ", ".join(
                sorted(
                    required_req_cols - set(requirements.columns)
                )
            )
        )

    requirements["catalog_year"] = (
        requirements["catalog_year"]
        .astype(str)
        .str.strip()
    )
    requirements["credential_id"] = (
        requirements["credential_id"]
        .astype(str)
        .str.strip()
    )

    catalog_years = sorted(
        requirements["catalog_year"]
        .dropna()
        .astype(str)
        .unique()
    )

    refreshed_eligibility = (
        eligibility_v2.build_student_catalog_eligibility(
            activity_history=affected_activity,
            catalog_years=catalog_years,
        )
    )

    refreshed_eligible_pairs = (
        refreshed_eligibility[
            refreshed_eligibility["catalog_eligible"] == True
        ][
            ["student_id", "catalog_year"]
        ]
        .drop_duplicates()
    )

    # ----------------------------------------------------------------------------------
    # 4. Compare old versus refreshed eligibility for affected students
    # ----------------------------------------------------------------------------------

    prior_eligibility = pd.read_csv(
        prior_eligibility_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_elig_cols = {
        "student_id",
        "catalog_year",
        "catalog_eligible",
    }

    if not required_elig_cols.issubset(
        prior_eligibility.columns
    ):
        raise ValueError(
            "Prior eligibility file is missing: "
            + ", ".join(
                sorted(
                    required_elig_cols
                    - set(prior_eligibility.columns)
                )
            )
        )

    prior_eligibility["student_id"] = (
        prior_eligibility["student_id"].map(clean_text)
    )
    prior_eligibility["catalog_year"] = (
        prior_eligibility["catalog_year"]
        .astype(str)
        .str.strip()
    )

    old_eligible_pairs = (
        prior_eligibility[
            prior_eligibility["student_id"].isin(affected_ids)
            & truthy_series(
                prior_eligibility["catalog_eligible"]
            )
        ][
            ["student_id", "catalog_year"]
        ]
        .drop_duplicates()
    )

    old_pair_set = set(
        map(
            tuple,
            old_eligible_pairs[
                ["student_id", "catalog_year"]
            ].values.tolist(),
        )
    )
    new_pair_set = set(
        map(
            tuple,
            refreshed_eligible_pairs[
                ["student_id", "catalog_year"]
            ].values.tolist(),
        )
    )

    retained_pairs = old_pair_set & new_pair_set
    gained_pairs = new_pair_set - old_pair_set
    lost_pairs = old_pair_set - new_pair_set

    eligibility_delta_rows = []

    for catalog_year in sorted(
        set(catalog_years)
        | {
            pair[1]
            for pair in old_pair_set
        }
    ):
        old_students = {
            student
            for student, catalog in old_pair_set
            if catalog == catalog_year
        }
        new_students = {
            student
            for student, catalog in new_pair_set
            if catalog == catalog_year
        }

        eligibility_delta_rows.append(
            {
                "catalog_year": catalog_year,
                "prior_eligible_students_affected": len(old_students),
                "refreshed_eligible_students_affected": len(new_students),
                "gained_eligible_students": len(
                    new_students - old_students
                ),
                "lost_eligible_students": len(
                    old_students - new_students
                ),
                "retained_eligible_students": len(
                    old_students & new_students
                ),
            }
        )

    eligibility_delta = pd.DataFrame(
        eligibility_delta_rows
    )

    # ----------------------------------------------------------------------------------
    # 5. Stream the 4.9M-row prior summary before building the optimized worklist
    # ----------------------------------------------------------------------------------

    (
        prior_summary_metrics,
        prior_summary_by_catalog,
        affected_students_in_prior_summary,
    ) = scan_prior_summary(
        prior_summary_path,
        affected_ids,
    )

    prior_catalogs = set(
        prior_summary_by_catalog["catalog_year"]
        .astype(str)
        .tolist()
    )

    # ----------------------------------------------------------------------------------
    # 6. Cohorts and audit worklists
    # ----------------------------------------------------------------------------------

    current_summer["is_passing"] = (
        current_summer["grade"].isin(
            eligibility_v2.PASSING_GRADES
        )
    )

    summer_pass_ids = set(
        current_summer.loc[
            current_summer["is_passing"],
            "student_id",
        ].unique()
    )

    current_2026_ids = current_summer_ids | fall_ids

    cohort_rows = []

    for student_id in sorted(affected_ids):
        cohort_rows.append(
            {
                "student_id": student_id,
                "cohort": cohort_label(
                    student_id,
                    pre_summer_ids=pre_summer_ids,
                    current_summer_ids=current_summer_ids,
                    fall_ids=fall_ids,
                    old_summer_ids=old_summer_ids,
                ),
                "has_pre_summer_history": (
                    student_id in pre_summer_ids
                ),
                "in_old_july_summer_snapshot": (
                    student_id in old_summer_ids
                ),
                "in_current_summer_snapshot": (
                    student_id in current_summer_ids
                ),
                "has_passing_summer_2026_course": (
                    student_id in summer_pass_ids
                ),
                "has_fall_2026_attempt": (
                    student_id in fall_ids
                ),
            }
        )

    cohort_frame = pd.DataFrame(cohort_rows)

    # Conservative worklist:
    # every affected student x every refreshed eligible catalog x every
    # credential in that catalog.
    credential_pairs = (
        requirements[
            ["catalog_year", "credential_id"]
        ]
        .drop_duplicates()
    )

    conservative_pairs = (
        refreshed_eligible_pairs.copy()
    )
    conservative_pairs["worklist_type"] = (
        "CONSERVATIVE_ALL_AFFECTED_ELIGIBLE"
    )

    # Tighter semantics-preserving worklist:
    #   A. Students with at least one newly earned Summer 2026 course:
    #      rerun every refreshed eligible catalog because completion state can change.
    #   B. Fall students:
    #      audit 2026-2027 because that catalog did not exist in the prior run.
    #   C. Affected students absent from the prior empirical summary:
    #      audit every refreshed eligible catalog because there is no baseline result
    #      available to reuse.
    #
    # Students already represented in the exhaustive prior summary whose Summer grades
    # are entirely nonpassing can change eligibility, but cannot change historical
    # requirement satisfaction. Their historical audit rows can therefore be reused
    # and filtered by refreshed eligibility.
    earned_change_pairs = (
        refreshed_eligible_pairs[
            refreshed_eligible_pairs["student_id"].isin(
                summer_pass_ids
            )
        ].copy()
    )

    fall_new_catalog_pairs = (
        refreshed_eligible_pairs[
            refreshed_eligible_pairs["student_id"].isin(
                fall_ids
            )
            & refreshed_eligible_pairs[
                "catalog_year"
            ].eq("2026-2027")
        ].copy()
    )

    no_baseline_ids = (
        affected_ids
        - affected_students_in_prior_summary
    )

    no_baseline_pairs = (
        refreshed_eligible_pairs[
            refreshed_eligible_pairs["student_id"].isin(
                no_baseline_ids
            )
        ].copy()
    )

    optimized_pairs = (
        pd.concat(
            [
                earned_change_pairs,
                fall_new_catalog_pairs,
                no_baseline_pairs,
            ],
            ignore_index=True,
        )
        .drop_duplicates(
            subset=["student_id", "catalog_year"]
        )
    )
    optimized_pairs["worklist_type"] = (
        "OPTIMIZED_SEMANTICS_PRESERVING"
    )

    def expand_worklist(
        pairs: pd.DataFrame,
    ) -> pd.DataFrame:
        expanded = pairs.merge(
            credential_pairs,
            on="catalog_year",
            how="inner",
            validate="many_to_many",
        )

        expanded = expanded.merge(
            cohort_frame[
                ["student_id", "cohort"]
            ],
            on="student_id",
            how="left",
            validate="many_to_one",
        )

        return expanded

    conservative_worklist = expand_worklist(
        conservative_pairs
    )
    optimized_worklist = expand_worklist(
        optimized_pairs
    )

    requirement_rows_by_catalog = (
        requirements.groupby("catalog_year")
        .size()
        .to_dict()
    )

    conservative_requirement_units = int(
        conservative_pairs["catalog_year"]
        .map(requirement_rows_by_catalog)
        .fillna(0)
        .sum()
    )

    optimized_requirement_units = int(
        optimized_pairs["catalog_year"]
        .map(requirement_rows_by_catalog)
        .fillna(0)
        .sum()
    )

    # ----------------------------------------------------------------------------------
    # 7. Official-award refresh
    # ----------------------------------------------------------------------------------

    prior_awards, prior_awards_sheet = (
        read_awards(
            prior_awards_path,
            preferred_sheet="Initial Enr Cohort Awards",
            source_label="PRIOR_OFFICIAL_AWARDS",
        )
    )

    new_awards, new_awards_sheet = (
        read_awards(
            new_awards_path,
            preferred_sheet="Summer 2026 Awards",
            source_label="SUMMER_2026_OFFICIAL_AWARDS",
        )
    )

    prior_awards_dedup = prior_awards.drop_duplicates(
        subset=[
            column
            for column in prior_awards.columns
            if column != "source_dataset"
        ],
        keep="first",
    ).copy()

    award_key = [
        "ID",
        "Major1Code",
        "DegreeCode",
        "StudGradTerm",
    ]

    old_award_keys = set(
        map(
            tuple,
            prior_awards_dedup[
                award_key
            ].values.tolist(),
        )
    )
    new_award_keys = set(
        map(
            tuple,
            new_awards[
                award_key
            ].values.tolist(),
        )
    )

    combined_awards = pd.concat(
        [
            prior_awards_dedup,
            new_awards,
        ],
        ignore_index=True,
    )

    # ----------------------------------------------------------------------------------
    # 8. FERPA-safe source/profile aggregates
    # ----------------------------------------------------------------------------------

    term_counts = (
        current_raw.assign(
            term=current_raw["term_sort"].astype("Int64")
        )
        .groupby("term")
        .size()
        .rename("raw_rows")
        .reset_index()
    )

    grade_counts = (
        current_raw.assign(
            grade_display=current_raw["grade"].replace(
                {"": "<BLANK>"}
            )
        )
        .groupby(
            ["term_sort", "grade_display"],
            dropna=False,
        )
        .size()
        .rename("raw_rows")
        .reset_index()
        .rename(
            columns={
                "term_sort": "term",
                "grade_display": "grade",
            }
        )
        .sort_values(
            ["term", "grade"],
            kind="mergesort",
        )
    )

    linked_section_profile = (
        current.groupby("term_sort")
        .agg(
            academic_attempts=("student_id", "size"),
            source_rows=("raw_row_count", "sum"),
            linked_section_attempts=(
                "linked_section_count",
                lambda s: int((s > 1).sum()),
            ),
            extra_linked_section_rows=(
                "raw_row_count",
                lambda s: int((s - 1).clip(lower=0).sum()),
            ),
        )
        .reset_index()
        .rename(columns={"term_sort": "term"})
    )

    cohort_summary = (
        cohort_frame.groupby("cohort")
        .agg(
            students=("student_id", "nunique"),
            with_passing_summer_course=(
                "has_passing_summer_2026_course",
                "sum",
            ),
            with_fall_attempt=(
                "has_fall_2026_attempt",
                "sum",
            ),
        )
        .reset_index()
        .sort_values("cohort", kind="mergesort")
    )

    requirements_profile = (
        requirements.groupby("catalog_year")
        .agg(
            credential_count=(
                "credential_id",
                "nunique",
            ),
            requirement_rows=(
                "credential_id",
                "size",
            ),
        )
        .reset_index()
        .sort_values("catalog_year")
    )

    def summarize_worklist(
        worklist: pd.DataFrame,
        label: str,
    ) -> pd.DataFrame:
        if worklist.empty:
            return pd.DataFrame(
                columns=[
                    "worklist_type",
                    "catalog_year",
                    "cohort",
                    "students",
                    "student_credential_audits",
                    "credential_count",
                ]
            )

        result = (
            worklist.groupby(
                ["catalog_year", "cohort"],
                dropna=False,
            )
            .agg(
                students=("student_id", "nunique"),
                student_credential_audits=(
                    "credential_id",
                    "size",
                ),
                credential_count=(
                    "credential_id",
                    "nunique",
                ),
            )
            .reset_index()
        )
        result.insert(0, "worklist_type", label)
        return result

    worklist_summary = pd.concat(
        [
            summarize_worklist(
                conservative_worklist,
                "CONSERVATIVE_ALL_AFFECTED_ELIGIBLE",
            ),
            summarize_worklist(
                optimized_worklist,
                "OPTIMIZED_SEMANTICS_PRESERVING",
            ),
        ],
        ignore_index=True,
    ).sort_values(
        ["worklist_type", "catalog_year", "cohort"],
        kind="mergesort",
    )

    # ----------------------------------------------------------------------------------
    # 9. Runtime estimate, if the old run log covers the prior population
    # ----------------------------------------------------------------------------------

    runtime = estimate_runtime(
        run_log_path,
        prior_unique_students=int(
            prior_summary_metrics[
                "prior_summary_unique_students"
            ]
        ),
        prior_catalogs=prior_catalogs,
        requirements=requirements,
        optimized_requirement_units=(
            optimized_requirement_units
        ),
        conservative_requirement_units=(
            conservative_requirement_units
        ),
    )

    # ----------------------------------------------------------------------------------
    # 10. Top-level KPIs
    # ----------------------------------------------------------------------------------

    kpis = []

    def add_kpi(
        group: str,
        metric: str,
        value: object,
    ) -> None:
        kpis.append(
            {
                "metric_group": group,
                "metric": metric,
                "value": value,
            }
        )

    add_kpi(
        "source",
        "historical_raw_rows",
        len(historical),
    )
    add_kpi(
        "source",
        "current_2026_raw_rows",
        len(current_raw),
    )
    add_kpi(
        "source",
        "current_2026_academic_attempts_after_linked_section_collapse",
        len(current),
    )
    add_kpi(
        "source",
        "current_source_sheet",
        new_sheet,
    )

    add_kpi(
        "summer_reconciliation",
        "july_202660_raw_rows",
        len(historical_summer),
    )
    add_kpi(
        "summer_reconciliation",
        "october_202660_academic_attempts",
        len(current_summer),
    )
    add_kpi(
        "summer_reconciliation",
        "students_in_july_202660_snapshot",
        len(old_summer_ids),
    )
    add_kpi(
        "summer_reconciliation",
        "students_in_october_202660_snapshot",
        len(current_summer_ids),
    )
    add_kpi(
        "summer_reconciliation",
        "students_removed_from_summer_snapshot_entirely",
        len(old_summer_ids - current_summer_ids),
    )
    add_kpi(
        "summer_reconciliation",
        "students_new_to_october_summer_snapshot",
        len(current_summer_ids - old_summer_ids),
    )

    add_kpi(
        "population",
        "affected_students_total",
        len(affected_ids),
    )
    add_kpi(
        "population",
        "students_with_pre_summer_history",
        len(affected_ids & pre_summer_ids),
    )
    add_kpi(
        "population",
        "affected_students_without_pre_summer_history",
        len(affected_ids - pre_summer_ids),
    )
    add_kpi(
        "population",
        "current_summer_students",
        len(current_summer_ids),
    )
    add_kpi(
        "population",
        "summer_students_with_at_least_one_passing_course",
        len(summer_pass_ids),
    )
    add_kpi(
        "population",
        "fall_students",
        len(fall_ids),
    )
    add_kpi(
        "population",
        "summer_and_fall_students",
        len(current_summer_ids & fall_ids),
    )
    add_kpi(
        "population",
        "affected_students_present_in_prior_summary",
        len(affected_students_in_prior_summary),
    )
    add_kpi(
        "population",
        "affected_students_absent_from_prior_summary",
        len(affected_ids - affected_students_in_prior_summary),
    )

    add_kpi(
        "eligibility",
        "prior_eligible_pairs_affected",
        len(old_pair_set),
    )
    add_kpi(
        "eligibility",
        "refreshed_eligible_pairs_affected",
        len(new_pair_set),
    )
    add_kpi(
        "eligibility",
        "retained_eligible_pairs",
        len(retained_pairs),
    )
    add_kpi(
        "eligibility",
        "gained_eligible_pairs",
        len(gained_pairs),
    )
    add_kpi(
        "eligibility",
        "lost_eligible_pairs",
        len(lost_pairs),
    )

    add_kpi(
        "worklist",
        "conservative_student_catalog_pairs",
        len(conservative_pairs),
    )
    add_kpi(
        "worklist",
        "conservative_student_credential_audits",
        len(conservative_worklist),
    )
    add_kpi(
        "worklist",
        "optimized_student_catalog_pairs",
        len(optimized_pairs),
    )
    add_kpi(
        "worklist",
        "optimized_student_credential_audits",
        len(optimized_worklist),
    )
    add_kpi(
        "worklist",
        "conservative_requirement_row_units",
        conservative_requirement_units,
    )
    add_kpi(
        "worklist",
        "optimized_requirement_row_units",
        optimized_requirement_units,
    )

    if conservative_requirement_units:
        add_kpi(
            "worklist",
            "optimized_vs_conservative_requirement_unit_reduction_percent",
            round(
                100
                * (
                    1
                    - optimized_requirement_units
                    / conservative_requirement_units
                ),
                2,
            ),
        )

    for metric, value in prior_summary_metrics.items():
        add_kpi("prior_summary", metric, value)

    add_kpi(
        "requirements",
        "catalog_year_count",
        len(catalog_years),
    )
    add_kpi(
        "requirements",
        "contains_2026_2027",
        int("2026-2027" in set(catalog_years)),
    )
    add_kpi(
        "requirements",
        "catalog_credential_pairs",
        len(credential_pairs),
    )
    add_kpi(
        "requirements",
        "requirement_rows",
        len(requirements),
    )

    add_kpi(
        "official_awards",
        "prior_award_rows_raw",
        len(prior_awards),
    )
    add_kpi(
        "official_awards",
        "prior_award_rows_after_exact_dedupe",
        len(prior_awards_dedup),
    )
    add_kpi(
        "official_awards",
        "new_summer_2026_award_rows",
        len(new_awards),
    )
    add_kpi(
        "official_awards",
        "new_award_keys_already_in_prior",
        len(old_award_keys & new_award_keys),
    )
    add_kpi(
        "official_awards",
        "combined_official_award_rows",
        len(combined_awards),
    )
    add_kpi(
        "official_awards",
        "prior_awards_sheet",
        prior_awards_sheet,
    )
    add_kpi(
        "official_awards",
        "new_awards_sheet",
        new_awards_sheet,
    )

    for metric, value in runtime.items():
        add_kpi("runtime_estimate", metric, value)

    kpi_frame = pd.DataFrame(kpis)

    # ----------------------------------------------------------------------------------
    # 11. Write FERPA-safe aggregate outputs only
    # ----------------------------------------------------------------------------------

    outputs = {
        "FERPA_SAFE_refresh_delta_kpi.csv":
            kpi_frame,
        "FERPA_SAFE_refresh_delta_cohorts.csv":
            cohort_summary,
        "FERPA_SAFE_refresh_delta_eligibility_change.csv":
            eligibility_delta,
        "FERPA_SAFE_refresh_delta_worklist.csv":
            worklist_summary,
        "FERPA_SAFE_refresh_delta_requirements.csv":
            requirements_profile,
        "FERPA_SAFE_refresh_delta_term_counts.csv":
            term_counts,
        "FERPA_SAFE_refresh_delta_grade_counts.csv":
            grade_counts,
        "FERPA_SAFE_refresh_delta_linked_sections.csv":
            linked_section_profile,
        "FERPA_SAFE_refresh_delta_prior_summary_by_catalog.csv":
            prior_summary_by_catalog,
    }

    for filename, frame in outputs.items():
        frame.to_csv(
            output_dir / filename,
            index=False,
        )

    # ----------------------------------------------------------------------------------
    # 12. Console report
    # ----------------------------------------------------------------------------------

    print("=" * 100)
    print("LSCO FALL 2026 DELTA-AUDIT PROFILER")
    print("=" * 100)
    print("READ-ONLY: source and production audit files were not modified.")
    print()

    print("SOURCE RECONCILIATION")
    print(
        f"Historical raw rows:                         {len(historical):,}"
    )
    print(
        f"Current 2026 raw rows:                       {len(current_raw):,}"
    )
    print(
        "Current academic attempts after linked "
        f"sections: {len(current):,}"
    )
    print(
        f"  Summer 2026 academic attempts:             {len(current_summer):,}"
    )
    print(
        f"  Fall 2026 academic attempts:               {len(current_fall):,}"
    )
    print()

    print("AFFECTED POPULATION")
    print(
        f"Students affected by Summer snapshot/Fall:   {len(affected_ids):,}"
    )
    print(
        f"Students with pre-Summer history:             {len(affected_ids & pre_summer_ids):,}"
    )
    print(
        f"Students without pre-Summer history:          {len(affected_ids - pre_summer_ids):,}"
    )
    print(
        f"Current Summer students:                      {len(current_summer_ids):,}"
    )
    print(
        f"Summer students with passing work:            {len(summer_pass_ids):,}"
    )
    print(
        f"Fall students:                                {len(fall_ids):,}"
    )
    print(
        "Affected students already in prior summary:   "
        f"{len(affected_students_in_prior_summary):,}"
    )
    print(
        "Affected students absent from prior summary:   "
        f"{len(affected_ids - affected_students_in_prior_summary):,}"
    )
    print()

    print("ELIGIBILITY CHANGE")
    print(
        f"Prior eligible student/catalog pairs:         {len(old_pair_set):,}"
    )
    print(
        f"Refreshed eligible student/catalog pairs:     {len(new_pair_set):,}"
    )
    print(
        f"  Gained:                                     {len(gained_pairs):,}"
    )
    print(
        f"  Lost:                                       {len(lost_pairs):,}"
    )
    print(
        f"  Retained:                                   {len(retained_pairs):,}"
    )
    print()

    print("AUDIT WORKLIST SIZE")
    print(
        "Conservative (all affected eligible):"
    )
    print(
        f"  student/catalog pairs:                      {len(conservative_pairs):,}"
    )
    print(
        f"  student/credential audits:                  {len(conservative_worklist):,}"
    )
    print(
        f"  requirement-row work units:                 {conservative_requirement_units:,}"
    )
    print()
    print(
        "Optimized (Summer earned changes + 2026-27 Fall):"
    )
    print(
        f"  student/catalog pairs:                      {len(optimized_pairs):,}"
    )
    print(
        f"  student/credential audits:                  {len(optimized_worklist):,}"
    )
    print(
        f"  requirement-row work units:                 {optimized_requirement_units:,}"
    )

    if conservative_requirement_units:
        reduction = (
            100
            * (
                1
                - optimized_requirement_units
                / conservative_requirement_units
            )
        )
        print(
            f"  reduction vs conservative:                  {reduction:.2f}%"
        )
    print()

    print("CURRENT REQUIREMENTS MASTER")
    print(
        f"Catalog years:                                {len(catalog_years):,}"
    )
    print(
        "2026-2027 present:                           "
        f"{'YES' if '2026-2027' in set(catalog_years) else 'NO'}"
    )
    print(
        f"Catalog/credential pairs:                     {len(credential_pairs):,}"
    )
    print(
        f"Requirement rows:                             {len(requirements):,}"
    )
    print()

    print("OFFICIAL AWARDS")
    print(
        f"Historical raw rows:                          {len(prior_awards):,}"
    )
    print(
        f"Historical after exact dedupe:                {len(prior_awards_dedup):,}"
    )
    print(
        f"New Summer 2026 awards:                       {len(new_awards):,}"
    )
    print(
        f"Overlap with prior award keys:                {len(old_award_keys & new_award_keys):,}"
    )
    print(
        f"Combined official award rows:                 {len(combined_awards):,}"
    )
    print()

    print("PRIOR EMPIRICAL SUMMARY")
    print(
        f"Rows:                                         {prior_summary_metrics['prior_summary_rows']:,}"
    )
    print(
        f"Unique students:                              {prior_summary_metrics['prior_summary_unique_students']:,}"
    )
    print(
        f"Rows belonging to affected students:          {prior_summary_metrics['prior_summary_rows_for_affected_students']:,}"
    )
    print()

    if runtime["runtime_estimate_usable"]:
        print("ROUGH RUNTIME ESTIMATE FROM PRIOR RUN LOG")
        print(
            "Optimized worklist:                          "
            f"{runtime['optimized_runtime_minutes_estimate']:,} minutes"
        )
        print(
            "Conservative worklist:                       "
            f"{runtime['conservative_runtime_minutes_estimate']:,} minutes"
        )
        print()
    elif runtime["run_log_found"]:
        print("RUNTIME ESTIMATE")
        print(
            "Prior run log exists but does not cover enough of the prior "
            "population for a trustworthy estimate."
        )
        print()

    print(f"FERPA-safe output directory: {output_dir}")
    print()
    print("NEXT: paste this terminal report back into ChatGPT.")
    print("No student-level output was written.")


if __name__ == "__main__":
    main()
