#!/usr/bin/env python
"""
Build publication-ready reporting extracts for the LSCO President's brief.

READ-ONLY INPUTS
----------------
- data/processed/full_actual_audit/full_actual_credential_summary.csv
- data/processed/full_actual_audit/full_actual_audit_results.csv

WRITES ONLY
-----------
- data/processed/full_actual_audit/president_report/

This script does not modify the audit engine, requirements masters, chunks,
combined audit outputs, or source/ground-truth data.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(".").resolve()
SUMMARY_PATH = ROOT / "data/processed/full_actual_audit/full_actual_credential_summary.csv"
DETAIL_PATH = ROOT / "data/processed/full_actual_audit/full_actual_audit_results.csv"
OUT_DIR = ROOT / "data/processed/full_actual_audit/president_report"

CHUNK_SIZE = 250_000


# ---------------------------------------------------------------------------
# APPROVED REPORTING LINEAGE CROSSWALK
# Unlisted lineages retain their mechanical lineage unchanged.
# ---------------------------------------------------------------------------

APPROVED_LINEAGE_MAP = {
    "PROCESS_TECHNOLOGY": "PROCESS_TECHNOLOGY_AAS",
    "PROCESS_OPERATING_TECHNOLOGY": "PROCESS_TECHNOLOGY_AAS",

    "MEDICAL_ASSISTING": "MEDICAL_ASSISTING_CERTIFICATE",
    "MEDICAL_ASSISTANT": "MEDICAL_ASSISTING_CERTIFICATE",

    "DENTAL_ASSISTING": "DENTAL_ASSISTING_CERTIFICATE",
    "DENTAL_ASSISTING_CERTIFICATE_OF_COMPLETION": "DENTAL_ASSISTING_CERTIFICATE",

    "SAFETY_HEALTH_AND_ENVIRONMENTAL": "SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE",
    "SAFETY_HEALTH_AND_ENVIRONMENT_CERTIFICATE_OF_COMPLETION":
        "SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE",

    "BASIC_PHARMACY_TECHNOLOGY": "PHARMACY_TECHNOLOGY_BASIC",
    "PHARMACY_TECHNOLOGY_BASIC": "PHARMACY_TECHNOLOGY_BASIC",

    "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC":
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC",
    "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_T050":
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC",
    "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_T072":
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC",

    "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE":
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE",
    "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_T051":
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE",
    "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_T073":
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE",

    "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_NETWORKING_SPECIALIST":
        "IT_SUPPORT_ASSISTANT_NETWORKING_SPECIALIST",
    "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTING_NETWORKING_SPECIALIST":
        "IT_SUPPORT_ASSISTANT_NETWORKING_SPECIALIST",

    "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_SOFTWARE_DEVELOPMENT":
        "IT_SUPPORT_ASSISTANT_SOFTWARE_DEVELOPMENT",
    "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTING_SOFTWARE_SPECIALIST_DEVELOPMENT":
        "IT_SUPPORT_ASSISTANT_SOFTWARE_DEVELOPMENT",
}


# ---------------------------------------------------------------------------
# OFFICIAL DEGREE AWARDS, TRANSCRIBED FROM:
# "Degrees and Certificates Awarded by Program,
#  Academic Year 2019 through Academic Year 2024"
#
# Only degree-level awards are included in the President's overlap comparison.
# Blank cells in the source report are represented as zero.
# ---------------------------------------------------------------------------

OFFICIAL_DEGREE_AWARDS = [
    ("Business", "Business - AS", "BUSINESS", 41, 31, 30, 23),
    ("Business", "Business Management - AAS", "BUSINESS_MANAGEMENT", 5, 6, 11, 15),
    ("Communication", "Communication - AA", "COMMUNICATION", 1, 2, 2, 3),
    ("Computer Information Systems", "Computer Information Systems - AS",
     "COMPUTER_INFORMATION_SYSTEMS", 1, 0, 1, 2),
    ("Computer Science", "Computer Science - AS", "COMPUTER_SCIENCE", 1, 4, 5, 7),
    ("Construction Management", "Business Construction Management - AAS",
     "BUSINESS_CONSTRUCTION_MANAGEMENT", 0, 0, 1, 4),
    ("Cosmetology", "Cosmetology Operator - AAS",
     "COSMETOLOGY_OPERATOR", 0, 0, 0, 2),
    ("Court Reporting", "Court Reporting - AAS",
     "COURT_REPORTING_AAS", 0, 6, 9, 8),
    ("Criminal Justice", "Criminal Justice - AS",
     "CRIMINAL_JUSTICE_AAS", 11, 10, 7, 8),
    ("Dental Assisting", "Dental Assisting - AAS",
     "DENTAL_ASSISTING_AAS", 0, 2, 3, 10),
    ("Electromechanical Technology", "Electromechanical Tech - AAS",
     "ELECTROMECHANICAL_TECHNOLOGY", 0, 0, 1, 7),
    ("Industrial Systems", "Industrial Technology - AAS",
     "INDUSTRIAL_TECHNOLOGY", 4, 1, 0, 0),
    ("Industrial Systems", "Instrumentation - AAS",
     "INSTRUMENTATION_AAS", 14, 27, 26, 20),
    ("Industrial Systems", "Process Operating Technology - AAS",
     "PROCESS_TECHNOLOGY_AAS", 32, 34, 30, 48),
    ("Industrial Systems", "Safety, Health, and Environment - AAS",
     "SAFETY_HEALTH_AND_ENVIRONMENT_AAS", 0, 1, 6, 6),
    ("Information Technology", "Info Tech Support Specialist - AAS",
     "INFORMATION_TECHNOLOGY_SUPPORT_SPECIALIST", 6, 6, 2, 3),
    ("Liberal Arts", "Liberal Arts - AA",
     "LIBERAL_ARTS", 66, 60, 44, 100),
    ("Logistics Management", "Logistics Management (Maritime) - AAS",
     "LOGISTICS_MANAGEMENT_MARITIME", 0, 0, 2, 2),
    ("Massage Therapy", "Massage Therapy Management - AAS",
     "MASSAGE_THERAPY_MANAGEMENT", 0, 0, 1, 0),
    ("Nursing", "Registered Nursing - AAS",
     "REGISTERED_NURSING_AAS", 32, 57, 64, 51),
    ("Pharmacy Technology", "Pharmacy Technology Business Management - AAS",
     "PHARMACY_TECHNOLOGY_BUSINESS_MANAGEMENT", 0, 2, 1, 1),
    ("Real Estate", "Business Real Estate Management - AAS",
     "BUSINESS_REAL_ESTATE_MANAGEMENT", 0, 0, 2, 1),
    ("Science", "Environmental Science - AS",
     "ENVIRONMENTAL_SCIENCE", 0, 0, 1, 3),
    ("Science", "Natural Science - AS",
     "NATURAL_SCIENCE", 1, 4, 3, 2),
    ("Science", "Pre-Professional Health Science - AS",
     "BIOLOGY_MEDICAL_PROFESSIONS_EMPHASIS", 5, 3, 6, 6),
    ("Sociology", "Sociology - AA",
     "SOCIOLOGY", 10, 17, 10, 10),
    ("Teaching", "Teaching Grades EC-6, 4-8, Special Ed. EC-12 - AAT 1",
     "TEACHING_AAT1", 11, 15, 8, 6),
    ("Teaching", "Teaching Grades 8-12, EC-12 - AAT 2",
     "TEACHING_AAT2", 6, 7, 17, 34),
    ("Welding", "Welding Technology - AAS",
     "WELDING_TECHNOLOGY_AAS", 0, 0, 1, 0),
]

OVERLAP_YEARS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025"]


def mechanical_lineage(credential_id: str) -> str:
    value = str(credential_id).strip().upper()
    return re.sub(r"_(2021|2022|2023|2024|2025)$", "", value)


def canonical_lineage(credential_id: str) -> str:
    mechanical = mechanical_lineage(credential_id)
    return APPROVED_LINEAGE_MAP.get(mechanical, mechanical)


def completion_academic_year(term_value: str) -> str:
    """
    Convert common Banner-like term codes or year labels to academic years.

    Examples supported:
      202210 -> 2021-2022
      202220 -> 2021-2022
      202230 -> 2021-2022
      2022FA -> 2022-2023
      Fall 2022 -> 2022-2023
      2022-2023 -> 2022-2023

    Unrecognized values return an empty string for explicit review.
    """
    raw = str(term_value).strip()
    if not raw:
        return ""

    if re.fullmatch(r"20\d{2}-20\d{2}", raw):
        return raw

    digits = re.sub(r"\D", "", raw)

    # Standard six-digit Banner term pattern: YYYYxx.
    if len(digits) >= 6:
        year = int(digits[:4])
        suffix = int(digits[4:6])

        # Common convention: 10/20/30 comprise fall/spring/summer academic year.
        # Fall term begins the academic year; spring/summer belong to prior fall.
        if suffix == 10:
            return f"{year}-{year + 1}"
        if suffix in {20, 30, 40}:
            return f"{year - 1}-{year}"

    year_match = re.search(r"(20\d{2})", raw)
    if not year_match:
        return ""

    year = int(year_match.group(1))
    lower = raw.lower()

    if any(token in lower for token in ("fall", "fa", "autumn")):
        return f"{year}-{year + 1}"
    if any(token in lower for token in ("spring", "sp", "summer", "su")):
        return f"{year - 1}-{year}"

    return ""


def load_complete_summary() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    usecols = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "requirements_missing",
        "catalog_eligible",
    ]

    for chunk in pd.read_csv(
        SUMMARY_PATH,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ):
        selected = chunk.loc[
            chunk["audit_status"].str.upper().eq("COMPLETE")
        ].copy()

        if not selected.empty:
            frames.append(selected)

    if not frames:
        raise RuntimeError("No COMPLETE rows found in the summary.")

    complete = pd.concat(frames, ignore_index=True)
    complete["mechanical_lineage"] = complete["credential_id"].map(mechanical_lineage)
    complete["canonical_lineage"] = complete["credential_id"].map(canonical_lineage)

    # Prefer the actual awarded/last-required term; fall back to the sortable term.
    chosen_term = complete["award_term_taken"].where(
        complete["award_term_taken"].ne(""),
        complete["award_term_sort"],
    )
    complete["completion_academic_year"] = chosen_term.map(completion_academic_year)

    return complete


def collapse_completions(complete: pd.DataFrame) -> pd.DataFrame:
    """
    One modeled completion per student + approved canonical lineage.

    Retain the earliest recognized completion term. When term parsing is blank,
    place the record last so a recognized term wins.
    """
    work = complete.copy()
    work["_year_missing"] = work["completion_academic_year"].eq("").astype(int)
    work["_term_sort"] = pd.to_numeric(work["award_term_sort"], errors="coerce")

    work = work.sort_values(
        [
            "student_id",
            "canonical_lineage",
            "_year_missing",
            "_term_sort",
            "catalog_year",
        ],
        na_position="last",
    )

    collapsed = work.drop_duplicates(
        subset=["student_id", "canonical_lineage"],
        keep="first",
    ).drop(columns=["_year_missing", "_term_sort"])

    return collapsed


def official_degree_table() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for program, award, lineage, y21, y22, y23, y24 in OFFICIAL_DEGREE_AWARDS:
        values = [y21, y22, y23, y24]

        for academic_year, count in zip(OVERLAP_YEARS, values):
            rows.append(
                {
                    "program": program,
                    "official_award_title": award,
                    "canonical_lineage": lineage,
                    "academic_year": academic_year,
                    "official_awards": int(count),
                }
            )

    return pd.DataFrame(rows)


def build_official_vs_modeled(
    collapsed: pd.DataFrame,
    official: pd.DataFrame,
) -> pd.DataFrame:
    modeled = (
        collapsed.loc[
            collapsed["completion_academic_year"].isin(OVERLAP_YEARS)
        ]
        .groupby(
            ["canonical_lineage", "completion_academic_year"],
            as_index=False,
        )
        .agg(
            modeled_completions=("student_id", "nunique"),
        )
        .rename(columns={"completion_academic_year": "academic_year"})
    )

    comparison = official.merge(
        modeled,
        on=["canonical_lineage", "academic_year"],
        how="left",
    )

    comparison["modeled_completions"] = (
        comparison["modeled_completions"].fillna(0).astype(int)
    )
    comparison["difference"] = (
        comparison["modeled_completions"] - comparison["official_awards"]
    )

    return comparison.sort_values(
        ["program", "official_award_title", "academic_year"]
    )


def build_lineage_counts(collapsed: pd.DataFrame) -> pd.DataFrame:
    return (
        collapsed.groupby("canonical_lineage", as_index=False)
        .agg(
            modeled_completions=("student_id", "nunique"),
            earliest_completion_year=("completion_academic_year", "min"),
            latest_completion_year=("completion_academic_year", "max"),
            source_credential_ids=("credential_id", "nunique"),
        )
        .sort_values(
            ["modeled_completions", "canonical_lineage"],
            ascending=[False, True],
        )
    )


def build_near_complete_inventory() -> pd.DataFrame:
    """
    Pull summary-level near-complete rows for Process Technology and Welding.

    Exact missing-course labels are added in a second pass from the detail file
    when usable requirement/course columns are present.
    """
    targets = {
        "PROCESS_TECHNOLOGY_AAS",
        "WELDING_TECHNOLOGY",
        "WELDING_TECHNOLOGY_AAS",
    }

    frames: list[pd.DataFrame] = []

    usecols = [
        "student_id",
        "catalog_year",
        "credential_id",
        "requirements_met",
        "requirements_total",
        "requirements_missing",
        "requirements_unresolved",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "catalog_eligible",
        "eligibility_reason",
    ]

    for chunk in pd.read_csv(
        SUMMARY_PATH,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ):
        chunk["canonical_lineage"] = chunk["credential_id"].map(canonical_lineage)

        selected = chunk.loc[
            chunk["audit_status"].str.upper().eq("NEAR_COMPLETE")
            & chunk["canonical_lineage"].isin(targets)
        ].copy()

        if not selected.empty:
            frames.append(selected)

    if not frames:
        return pd.DataFrame(columns=usecols + ["canonical_lineage"])

    near = pd.concat(frames, ignore_index=True)

    # Keep one best row per student + canonical lineage:
    # fewest missing requirements, then latest catalog.
    near["_missing_num"] = pd.to_numeric(
        near["requirements_missing"], errors="coerce"
    )
    near = near.sort_values(
        ["student_id", "canonical_lineage", "_missing_num", "catalog_year"],
        ascending=[True, True, True, False],
        na_position="last",
    )
    near = near.drop_duplicates(
        subset=["student_id", "canonical_lineage"],
        keep="first",
    ).drop(columns="_missing_num")

    return near


def attach_missing_requirement_from_detail(
    near: pd.DataFrame,
) -> pd.DataFrame:
    """
    Best-effort extraction of exact missing requirements from the 8.67 GB detail.

    The function inspects the actual detail schema and uses common column names.
    When no compatible columns exist, it writes the schema separately and leaves
    missing_requirement blank rather than guessing.
    """
    if near.empty:
        near["missing_requirement"] = ""
        return near

    header = pd.read_csv(DETAIL_PATH, nrows=0)
    columns = list(header.columns)

    student_col = next(
        (c for c in ["student_id", "student_pidm", "student_key"] if c in columns),
        None,
    )
    credential_col = next(
        (c for c in ["credential_id", "credential", "program_id"] if c in columns),
        None,
    )
    status_col = next(
        (c for c in ["requirement_status", "status", "result_status"] if c in columns),
        None,
    )
    requirement_col = next(
        (
            c for c in [
                "requirement_label",
                "requirement_name",
                "requirement_id",
                "required_course",
                "course_code",
                "option_value",
            ]
            if c in columns
        ),
        None,
    )

    pd.DataFrame({"detail_column": columns}).to_csv(
        OUT_DIR / "detail_schema.csv",
        index=False,
    )

    if not all([student_col, credential_col, status_col, requirement_col]):
        result = near.copy()
        result["missing_requirement"] = ""
        result["missing_requirement_note"] = (
            "Detail schema did not expose a recognized requirement/status column set. "
            "See detail_schema.csv."
        )
        return result

    keys = set(
        zip(
            near["student_id"].astype(str),
            near["credential_id"].astype(str),
        )
    )

    missing_rows: list[pd.DataFrame] = []
    readcols = [student_col, credential_col, status_col, requirement_col]

    for chunk in pd.read_csv(
        DETAIL_PATH,
        usecols=readcols,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ):
        pair_mask = pd.Series(
            list(zip(chunk[student_col], chunk[credential_col]))
        ).isin(keys).to_numpy()

        status = chunk[status_col].str.upper()
        unmet_mask = status.isin(
            {"UNMET", "MISSING", "NOT_MET", "INCOMPLETE", "NEAR_COMPLETE"}
        )

        selected = chunk.loc[pair_mask & unmet_mask].copy()
        if not selected.empty:
            missing_rows.append(selected)

    result = near.copy()

    if not missing_rows:
        result["missing_requirement"] = ""
        result["missing_requirement_note"] = (
            "No matching unmet detail rows found under recognized status values."
        )
        return result

    missing = pd.concat(missing_rows, ignore_index=True)
    missing = (
        missing.groupby([student_col, credential_col])[requirement_col]
        .apply(lambda s: " | ".join(dict.fromkeys(v for v in s if v)))
        .reset_index(name="missing_requirement")
    )

    result = result.merge(
        missing,
        left_on=["student_id", "credential_id"],
        right_on=[student_col, credential_col],
        how="left",
    )

    result["missing_requirement"] = result["missing_requirement"].fillna("")
    result["missing_requirement_note"] = ""

    drop_cols = [
        c for c in [student_col, credential_col]
        if c in result.columns and c not in {"student_id", "credential_id"}
    ]
    if drop_cols:
        result = result.drop(columns=drop_cols)

    return result


def build_near_complete_summary(near: pd.DataFrame) -> pd.DataFrame:
    if near.empty:
        return pd.DataFrame(
            columns=[
                "canonical_lineage",
                "near_complete_students",
                "students_with_exact_missing_requirement",
            ]
        )

    return (
        near.groupby("canonical_lineage", as_index=False)
        .agg(
            near_complete_students=("student_id", "nunique"),
            students_with_exact_missing_requirement=(
                "missing_requirement",
                lambda s: int(s.ne("").sum()),
            ),
        )
        .sort_values("canonical_lineage")
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading COMPLETE summary rows...")
    complete = load_complete_summary()

    print("Collapsing to approved student + canonical lineage completions...")
    collapsed = collapse_completions(complete)

    print("Building official degree-award table...")
    official = official_degree_table()

    print("Building official-versus-modeled comparison...")
    comparison = build_official_vs_modeled(collapsed, official)

    print("Building canonical lineage counts...")
    lineage_counts = build_lineage_counts(collapsed)

    print("Building Process Technology and Welding near-completer inventory...")
    near = build_near_complete_inventory()

    print("Scanning detail for exact missing requirements...")
    near = attach_missing_requirement_from_detail(near)
    near_summary = build_near_complete_summary(near)

    headline = pd.DataFrame(
        [
            {
                "raw_complete_credential_year_rows": len(complete),
                "unique_students_with_complete": complete["student_id"].nunique(),
                "approved_canonical_student_lineage_completions": len(collapsed),
                "approved_canonical_lineages": collapsed[
                    "canonical_lineage"
                ].nunique(),
                "unparsed_completion_year_rows": int(
                    collapsed["completion_academic_year"].eq("").sum()
                ),
            }
        ]
    )

    official_year_totals = (
        comparison.groupby("academic_year", as_index=False)
        .agg(
            official_degree_awards=("official_awards", "sum"),
            modeled_degree_completions=("modeled_completions", "sum"),
        )
    )
    official_year_totals["difference"] = (
        official_year_totals["modeled_degree_completions"]
        - official_year_totals["official_degree_awards"]
    )

    # Write reporting assets only.
    headline.to_csv(OUT_DIR / "headline_metrics.csv", index=False)
    complete.to_csv(OUT_DIR / "complete_rows_with_canonical_lineage.csv", index=False)
    collapsed.to_csv(OUT_DIR / "collapsed_modeled_completions.csv", index=False)
    lineage_counts.to_csv(OUT_DIR / "modeled_completions_by_lineage.csv", index=False)
    official.to_csv(OUT_DIR / "official_degree_awards_overlap.csv", index=False)
    comparison.to_csv(OUT_DIR / "official_vs_modeled_by_major_year.csv", index=False)
    official_year_totals.to_csv(
        OUT_DIR / "official_vs_modeled_degree_totals_by_year.csv",
        index=False,
    )
    near.to_csv(
        OUT_DIR / "process_welding_near_completers.csv",
        index=False,
    )
    near_summary.to_csv(
        OUT_DIR / "process_welding_near_complete_summary.csv",
        index=False,
    )

    print("\n" + "=" * 112)
    print("PRESIDENT REPORT DATA BUILD")
    print("=" * 112)
    print("\nHEADLINE METRICS")
    print(headline.to_string(index=False))

    print("\nOFFICIAL VS MODELED DEGREE TOTALS")
    print(official_year_totals.to_string(index=False))

    print("\nPROCESS TECHNOLOGY / WELDING NEAR-COMPLETE SUMMARY")
    print(near_summary.to_string(index=False))

    print(f"\nReporting extracts written to:\n{OUT_DIR}")
    print("\nCore audit and ground-truth files were not modified.")


if __name__ == "__main__":
    main()
