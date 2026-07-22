#!/usr/bin/env python
"""
Build corrected President-report data extracts.

This is a READ-ONLY reporting layer. It does not modify:
- catalog requirements
- audit chunks
- combined audit outputs
- source or ground-truth records

Official benchmark:
- full institutional award totals from the LSCO IR publication
- program totals transcribed from the publication
- residual institutional awards carried explicitly so annual totals reconcile
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(".").resolve()
SUMMARY_PATH = ROOT / "data/processed/full_actual_audit/full_actual_credential_summary.csv"
DETAIL_PATH = ROOT / "data/processed/full_actual_audit/full_actual_audit_results.csv"
OUT_DIR = ROOT / "data/processed/full_actual_audit/president_report_corrected"
CHUNK_SIZE = 250_000

OVERLAP_YEARS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025"]

OFFICIAL_GRAND_TOTALS = {
    "2021-2022": 635,
    "2022-2023": 769,
    "2023-2024": 901,
    "2024-2025": 1107,
}

# Program totals visible in the IR publication. A residual category is calculated
# below so each year reconciles exactly to the official grand total.
OFFICIAL_PROGRAM_TOTALS = {
    "Business": [58, 40, 78, 79],
    "Communication": [1, 2, 2, 3],
    "Computer Information Systems": [1, 0, 1, 2],
    "Computer Science": [1, 4, 5, 7],
    "Construction Management": [0, 3, 6, 13],
    "Cosmetology": [0, 0, 33, 95],
    "Court Reporting": [0, 46, 37, 28],
    "Criminal Justice": [14, 13, 18, 40],
    "Dental Assisting": [23, 20, 25, 29],
    "Electromechanical Technology": [0, 0, 13, 16],
    "Emergency Medical Services": [7, 4, 12, 7],
    "Industrial Systems": [99, 139, 175, 187],
    "Information Technology": [31, 29, 23, 20],
    "Liberal Arts": [208, 241, 220, 294],
    "Logistics Management": [0, 0, 4, 5],
    "Maritime": [7, 2, 17, 14],
    "Massage Therapy": [0, 0, 7, 2],
    "Nursing": [128, 149, 149, 117],
    "Pharmacy Technology": [17, 22, 11, 19],
    "Real Estate": [0, 2, 16, 7],
    "Science": [6, 7, 10, 11],
    "Sociology": [10, 17, 10, 10],
    "Teaching": [6, 7, 17, 40],
    "Welding": [7, 7, 12, 62],
}

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


def mechanical_lineage(credential_id: str) -> str:
    return re.sub(
        r"_(2021|2022|2023|2024|2025)$",
        "",
        str(credential_id).strip().upper(),
    )


def canonical_lineage(credential_id: str) -> str:
    mechanical = mechanical_lineage(credential_id)
    return APPROVED_LINEAGE_MAP.get(mechanical, mechanical)


def completion_academic_year(term_value: str) -> str:
    """
    Academic year of the final required course term.

      90, 95 = Fall side: YYYY-(YYYY+1)
      10, 15, 60 = Spring/summer side: (YYYY-1)-YYYY
    """
    raw = str(term_value).strip()
    if not raw:
        return ""

    if re.fullmatch(r"20\d{2}-20\d{2}", raw):
        return raw

    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 6:
        year = int(digits[:4])
        suffix = int(digits[4:6])

        if suffix in {90, 95}:
            return f"{year}-{year + 1}"

        if suffix in {10, 15, 60}:
            return f"{year - 1}-{year}"

    return ""


def program_family(lineage: str) -> str:
    """Explicit reporting-family assignment for current canonical lineages."""
    x = str(lineage).upper()

    rules = [
        ("Business", ("BUSINESS", "ACCOUNTING", "ENTREPRENEURSHIP")),
        ("Communication", ("COMMUNICATION",)),
        ("Computer Information Systems", ("COMPUTER_INFORMATION_SYSTEMS",)),
        ("Computer Science", ("COMPUTER_SCIENCE", "DATA_ANALYTICS")),
        ("Construction Management", ("CONSTRUCTION_MANAGEMENT",)),
        ("Cosmetology", ("COSMETOLOGY",)),
        ("Court Reporting", ("COURT_REPORTING",)),
        ("Criminal Justice", ("CRIMINAL_JUSTICE",)),
        ("Dental Assisting", ("DENTAL",)),
        ("Electromechanical Technology", ("ELECTROMECHANICAL", "HVAC")),
        ("Emergency Medical Services", ("EMERGENCY_MEDICAL",)),
        ("Industrial Systems", (
            "INDUSTRIAL_TECHNOLOGY",
            "INSTRUMENTATION",
            "PROCESS_TECHNOLOGY",
            "PROCESS_OPERATING",
            "SAFETY_HEALTH",
        )),
        ("Information Technology", (
            "INFORMATION_TECHNOLOGY",
            "IT_SUPPORT",
            "CISCO",
            "CYBERSECURITY",
        )),
        ("Liberal Arts", ("GENERAL_STUDIES", "LIBERAL_ARTS")),
        ("Logistics Management", ("LOGISTICS",)),
        ("Maritime", ("ORDINARY_SEAMAN",)),
        ("Massage Therapy", ("MASSAGE",)),
        ("Nursing", (
            "REGISTERED_NURSING",
            "VOCATIONAL_NURSING",
            "PHYSICAL_THERAPY_ASSISTANT",
        )),
        ("Pharmacy Technology", ("PHARMACY",)),
        ("Real Estate", ("REAL_ESTATE",)),
        ("Science", (
            "NATURAL_SCIENCE",
            "BIOLOGY",
            "ENVIRONMENTAL_SCIENCE",
        )),
        ("Sociology", ("SOCIOLOGY",)),
        ("Teaching", ("TEACH",)),
        ("Welding", ("WELDING", "PRODUCTION_WELDER", "PIPE_WELDING", "LAYOUT_AND_FABRICATION")),
    ]

    for family, tokens in rules:
        if any(token in x for token in tokens):
            return family

    return "Other / Unmapped"


def load_complete_rows() -> pd.DataFrame:
    frames = []
    usecols = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
    ]

    for chunk in pd.read_csv(
        SUMMARY_PATH,
        usecols=usecols,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ):
        selected = chunk.loc[chunk["audit_status"].eq("COMPLETE")].copy()
        if not selected.empty:
            frames.append(selected)

    complete = pd.concat(frames, ignore_index=True)
    complete["canonical_lineage"] = complete["credential_id"].map(canonical_lineage)
    complete["program_family"] = complete["canonical_lineage"].map(program_family)

    chosen_term = complete["award_term_taken"].where(
        complete["award_term_taken"].ne(""),
        complete["award_term_sort"],
    )
    complete["completion_academic_year"] = chosen_term.map(completion_academic_year)

    return complete


def collapse_completions(complete: pd.DataFrame) -> pd.DataFrame:
    work = complete.copy()
    work["_term_sort"] = pd.to_numeric(work["award_term_sort"], errors="coerce")

    work = work.sort_values(
        ["student_id", "canonical_lineage", "_term_sort", "catalog_year"],
        na_position="last",
    )

    return (
        work.drop_duplicates(
            subset=["student_id", "canonical_lineage"],
            keep="first",
        )
        .drop(columns="_term_sort")
        .reset_index(drop=True)
    )


def build_official_program_table() -> pd.DataFrame:
    rows = []

    for program, values in OFFICIAL_PROGRAM_TOTALS.items():
        for year, count in zip(OVERLAP_YEARS, values):
            rows.append(
                {
                    "program_family": program,
                    "academic_year": year,
                    "official_awards": int(count),
                    "official_source_status": "Published program total",
                }
            )

    table = pd.DataFrame(rows)

    published = (
        table.groupby("academic_year", as_index=False)["official_awards"]
        .sum()
        .set_index("academic_year")["official_awards"]
        .to_dict()
    )

    residual_rows = []
    for year in OVERLAP_YEARS:
        residual = OFFICIAL_GRAND_TOTALS[year] - int(published.get(year, 0))
        residual_rows.append(
            {
                "program_family": "Other / Institutional Awards",
                "academic_year": year,
                "official_awards": residual,
                "official_source_status": "Residual to published grand total",
            }
        )

    return pd.concat(
        [table, pd.DataFrame(residual_rows)],
        ignore_index=True,
    )


def build_program_comparison(
    collapsed: pd.DataFrame,
    official: pd.DataFrame,
) -> pd.DataFrame:
    modeled = (
        collapsed.loc[
            collapsed["completion_academic_year"].isin(OVERLAP_YEARS)
        ]
        .groupby(
            ["program_family", "completion_academic_year"],
            as_index=False,
        )
        .agg(modeled_completions=("student_id", "size"))
        .rename(columns={"completion_academic_year": "academic_year"})
    )

    programs = sorted(
        set(official["program_family"]) | set(modeled["program_family"])
    )
    grid = pd.MultiIndex.from_product(
        [programs, OVERLAP_YEARS],
        names=["program_family", "academic_year"],
    ).to_frame(index=False)

    comparison = (
        grid.merge(
            official,
            on=["program_family", "academic_year"],
            how="left",
        )
        .merge(
            modeled,
            on=["program_family", "academic_year"],
            how="left",
        )
    )

    comparison["official_awards"] = (
        comparison["official_awards"].fillna(0).astype(int)
    )
    comparison["modeled_completions"] = (
        comparison["modeled_completions"].fillna(0).astype(int)
    )
    comparison["difference"] = (
        comparison["modeled_completions"] - comparison["official_awards"]
    )
    comparison["official_source_status"] = comparison[
        "official_source_status"
    ].fillna("No published matching program row")

    return comparison.sort_values(["program_family", "academic_year"])


def build_near_complete_inventory() -> pd.DataFrame:
    targets = {
        "PROCESS_TECHNOLOGY_AAS",
        "WELDING_TECHNOLOGY",
        "WELDING_TECHNOLOGY_AAS",
    }

    frames = []
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
            chunk["audit_status"].eq("NEAR_COMPLETE")
            & chunk["canonical_lineage"].isin(targets)
        ].copy()
        if not selected.empty:
            frames.append(selected)

    near = pd.concat(frames, ignore_index=True)

    near["_missing"] = pd.to_numeric(
        near["requirements_missing"],
        errors="coerce",
    )
    near = (
        near.sort_values(
            ["student_id", "canonical_lineage", "_missing", "catalog_year"],
            ascending=[True, True, True, False],
        )
        .drop_duplicates(
            subset=["student_id", "canonical_lineage"],
            keep="first",
        )
        .drop(columns="_missing")
    )

    return near


def attach_missing_requirements(near: pd.DataFrame) -> pd.DataFrame:
    header = pd.read_csv(DETAIL_PATH, nrows=0)
    columns = list(header.columns)

    student_col = "student_id" if "student_id" in columns else None
    credential_col = "credential_id" if "credential_id" in columns else None
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

    result = near.copy()
    if not all([student_col, credential_col, status_col, requirement_col]):
        result["missing_requirement"] = ""
        result["missing_requirement_note"] = (
            "Recognized detail columns were not available; see detail_schema.csv."
        )
        return result

    keys = set(zip(near["student_id"], near["credential_id"]))
    found = []

    for chunk in pd.read_csv(
        DETAIL_PATH,
        usecols=[student_col, credential_col, status_col, requirement_col],
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
    ):
        pair_mask = pd.Series(
            list(zip(chunk[student_col], chunk[credential_col]))
        ).isin(keys).to_numpy()

        unmet = chunk[status_col].str.upper().isin(
            {"UNMET", "MISSING", "NOT_MET", "INCOMPLETE", "NEAR_COMPLETE"}
        )

        selected = chunk.loc[pair_mask & unmet].copy()
        if not selected.empty:
            found.append(selected)

    if not found:
        result["missing_requirement"] = ""
        result["missing_requirement_note"] = "No matching unmet detail row found."
        return result

    missing = pd.concat(found, ignore_index=True)
    missing = (
        missing.groupby([student_col, credential_col])[requirement_col]
        .apply(lambda s: " | ".join(dict.fromkeys(v for v in s if v)))
        .reset_index(name="missing_requirement")
    )

    result = result.merge(
        missing,
        on=["student_id", "credential_id"],
        how="left",
    )
    result["missing_requirement"] = result["missing_requirement"].fillna("")
    result["missing_requirement_note"] = ""
    return result


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading COMPLETE rows...")
    complete = load_complete_rows()

    if complete["completion_academic_year"].eq("").any():
        raise RuntimeError(
            "Completion-year parser failed: "
            f"{int(complete['completion_academic_year'].eq('').sum())} rows unparsed."
        )

    print("Collapsing approved canonical completions...")
    collapsed = collapse_completions(complete)

    print("Building full official all-award benchmark...")
    official_program = build_official_program_table()

    # Hard control: official totals must reconcile exactly.
    official_control = (
        official_program.groupby("academic_year")["official_awards"].sum().to_dict()
    )
    if official_control != OFFICIAL_GRAND_TOTALS:
        raise RuntimeError(
            f"Official totals failed reconciliation: {official_control}"
        )

    print("Building all-award modeled comparison...")
    comparison = build_program_comparison(collapsed, official_program)

    annual = (
        comparison.groupby("academic_year", as_index=False)
        .agg(
            official_awards=("official_awards", "sum"),
            modeled_completions=("modeled_completions", "sum"),
        )
    )
    annual["difference"] = (
        annual["modeled_completions"] - annual["official_awards"]
    )

    print("Building near-completer case-study files...")
    near = build_near_complete_inventory()
    near = attach_missing_requirements(near)

    near_summary = (
        near.groupby("canonical_lineage", as_index=False)
        .agg(
            near_complete_students=("student_id", "nunique"),
            students_with_exact_missing_requirement=(
                "missing_requirement",
                lambda s: int(s.ne("").sum()),
            ),
        )
    )

    headline = pd.DataFrame(
        [{
            "raw_complete_credential_year_rows": len(complete),
            "unique_students_with_complete": complete["student_id"].nunique(),
            "approved_canonical_student_lineage_completions": len(collapsed),
            "approved_canonical_lineages": collapsed["canonical_lineage"].nunique(),
            "unparsed_completion_year_rows": 0,
        }]
    )

    lineage = (
        collapsed.groupby(
            ["program_family", "canonical_lineage"],
            as_index=False,
        )
        .agg(
            modeled_completions=("student_id", "size"),
            affected_students=("student_id", "nunique"),
        )
        .sort_values(
            ["program_family", "modeled_completions"],
            ascending=[True, False],
        )
    )

    headline.to_csv(OUT_DIR / "headline_metrics.csv", index=False)
    collapsed.to_csv(OUT_DIR / "collapsed_modeled_completions.csv", index=False)
    lineage.to_csv(OUT_DIR / "modeled_completions_by_program_lineage.csv", index=False)
    official_program.to_csv(OUT_DIR / "official_program_totals_overlap.csv", index=False)
    comparison.to_csv(OUT_DIR / "official_vs_modeled_by_program_year.csv", index=False)
    annual.to_csv(OUT_DIR / "official_vs_modeled_totals_by_year.csv", index=False)
    near.to_csv(OUT_DIR / "process_welding_near_completers.csv", index=False)
    near_summary.to_csv(
        OUT_DIR / "process_welding_near_complete_summary.csv",
        index=False,
    )

    print("\n" + "=" * 112)
    print("CORRECTED PRESIDENT REPORT DATA BUILD")
    print("=" * 112)
    print("\nHEADLINE METRICS")
    print(headline.to_string(index=False))
    print("\nOFFICIAL VS MODELED — ALL AWARD TYPES")
    print(annual.to_string(index=False))
    print("\nPROCESS TECHNOLOGY / WELDING NEAR-COMPLETE SUMMARY")
    print(near_summary.to_string(index=False))
    print(f"\nOutputs written to:\n{OUT_DIR}")
    print("\nCore audit and ground-truth files were not modified.")


if __name__ == "__main__":
    main()
