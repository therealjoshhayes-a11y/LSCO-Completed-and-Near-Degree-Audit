from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


AWARDS_PATH = Path(
    "data/raw/institutional_awards/"
    "lsco_awards_sample_20260730.xlsx"
)

CROSSWALK_PATH = Path(
    "data/interim/institutional_awards/"
    "award_program_crosswalk_curated.xlsx"
)

MODELED_PATH = Path(
    "data/processed/full_actual_audit/"
    "president_report_corrected/"
    "collapsed_modeled_completions.csv"
)

AWARDS_SHEET = "Initial Enr Cohort Awards"
CROSSWALK_SHEET = "Crosswalk Draft"


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def normalize_bool(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.upper()
        .map(
            {
                "TRUE": True,
                "FALSE": False,
                "1": True,
                "0": False,
                "YES": True,
                "NO": False,
            }
        )
    )


def main() -> None:
    for path in (AWARDS_PATH, CROSSWALK_PATH, MODELED_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(
        "data/processed/reporting/"
        f"institutional_award_reconciliation_{run_stamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    # ------------------------------------------------------------------
    # LOAD INSTITUTIONAL AWARDS
    # ------------------------------------------------------------------
    awards = pd.read_excel(
        AWARDS_PATH,
        sheet_name=AWARDS_SHEET,
        dtype=str,
    )

    award_required = [
        "ID",
        "Curr1ProgramCode",
        "Major1Code",
        "MajorDesc",
        "DegreeCode",
        "DegreeDesc",
        "StudGradTerm",
        "GradDate",
        "DegreeStat",
    ]

    missing = sorted(set(award_required) - set(awards.columns))
    if missing:
        raise ValueError(f"Awards file missing columns: {missing}")

    for column in award_required:
        awards[column] = clean_text(awards[column])

    if awards["ID"].isna().any():
        raise ValueError("Institutional awards contain blank student IDs.")

    unexpected_status = sorted(
        set(awards["DegreeStat"].dropna().unique()) - {"AW"}
    )
    if unexpected_status:
        raise ValueError(
            "Unexpected DegreeStat values found: "
            f"{unexpected_status}"
        )

    source_award_rows = len(awards)

    award_dedupe_columns = [
        "ID",
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
        "StudGradTerm",
        "GradDate",
        "DegreeStat",
    ]

    awards = awards.drop_duplicates(
        subset=award_dedupe_columns
    ).copy()

    unique_award_rows = len(awards)

    # ------------------------------------------------------------------
    # LOAD AND VALIDATE GOVERNED CROSSWALK
    # ------------------------------------------------------------------
    crosswalk = pd.read_excel(
        CROSSWALK_PATH,
        sheet_name=CROSSWALK_SHEET,
        dtype=str,
    )

    crosswalk_required = [
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
        "canonical_lineage",
        "match_status",
        "award_level",
        "stack_behavior",
        "consumes_certificate_or_degree_lineage",
        "modeled_lineage_present",
        "reconciliation_key",
    ]

    missing = sorted(set(crosswalk_required) - set(crosswalk.columns))
    if missing:
        raise ValueError(f"Crosswalk missing columns: {missing}")

    for column in crosswalk_required:
        crosswalk[column] = clean_text(crosswalk[column])

    crosswalk["consumes_certificate_or_degree_lineage"] = normalize_bool(
        crosswalk["consumes_certificate_or_degree_lineage"]
    )

    crosswalk["modeled_lineage_present"] = normalize_bool(
        crosswalk["modeled_lineage_present"]
    )

    crosswalk_key = [
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
    ]

    duplicate_crosswalk = crosswalk.duplicated(
        subset=crosswalk_key,
        keep=False,
    )

    if duplicate_crosswalk.any():
        bad = crosswalk.loc[
            duplicate_crosswalk,
            crosswalk_key,
        ]
        raise ValueError(
            "Crosswalk contains duplicate institutional keys:\n"
            + bad.to_string(index=False)
        )

    blank_reconciliation_key = (
        crosswalk["reconciliation_key"].isna()
        | crosswalk["reconciliation_key"].eq("")
    )

    if blank_reconciliation_key.any():
        bad = crosswalk.loc[
            blank_reconciliation_key,
            crosswalk_key,
        ]
        raise ValueError(
            "Crosswalk contains blank reconciliation keys:\n"
            + bad.to_string(index=False)
        )

    # Explicit IA safety gate.
    ia_crosswalk = crosswalk[
        crosswalk["DegreeCode"].eq("IA")
        | crosswalk["award_level"].eq("INSTITUTIONAL_AWARD")
    ].copy()

    bad_ia_stack = ia_crosswalk[
        ~ia_crosswalk["stack_behavior"].eq(
            "INDEPENDENT_NONCONSUMING"
        )
        | ~ia_crosswalk[
            "consumes_certificate_or_degree_lineage"
        ].eq(False)
        | ~ia_crosswalk["reconciliation_key"].str.startswith(
            "IA_",
            na=False,
        )
    ]

    if not bad_ia_stack.empty:
        raise ValueError(
            "IA governance failure. Every IA must be independently "
            "nonconsuming, FALSE for lineage consumption, and use an "
            "IA_* reconciliation key:\n"
            + bad_ia_stack[
                crosswalk_key
                + [
                    "stack_behavior",
                    "consumes_certificate_or_degree_lineage",
                    "reconciliation_key",
                ]
            ].to_string(index=False)
        )

    # ------------------------------------------------------------------
    # CROSSWALK THE INSTITUTIONAL AWARDS
    # ------------------------------------------------------------------
    mapped_awards = awards.merge(
        crosswalk[
            crosswalk_key
            + [
                "canonical_lineage",
                "match_status",
                "award_level",
                "stack_behavior",
                "consumes_certificate_or_degree_lineage",
                "modeled_lineage_present",
                "reconciliation_key",
            ]
        ],
        on=crosswalk_key,
        how="left",
        validate="many_to_one",
        indicator="crosswalk_merge",
    )

    unmapped = mapped_awards[
        mapped_awards["crosswalk_merge"].ne("both")
    ].copy()

    if not unmapped.empty:
        unmapped[
            crosswalk_key
            + ["MajorDesc", "DegreeDesc"]
        ].drop_duplicates().to_csv(
            output_dir / "unmapped_institutional_programs.csv",
            index=False,
        )

        raise ValueError(
            f"{len(unmapped):,} institutional award rows did not map. "
            f"Review {output_dir / 'unmapped_institutional_programs.csv'}"
        )

    mapped_awards = mapped_awards.drop(
        columns="crosswalk_merge"
    )

    mapped_awards["GradDate"] = pd.to_datetime(
        mapped_awards["GradDate"],
        errors="coerce",
    )

    # One governed institutional observation per student + key.
    # Multiple source rows remain countable and their timing range is kept.
    institutional = (
        mapped_awards.groupby(
            ["ID", "reconciliation_key"],
            as_index=False,
            dropna=False,
        )
        .agg(
            institutional_source_rows=("ID", "size"),
            Curr1ProgramCode=(
                "Curr1ProgramCode",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            Major1Code=(
                "Major1Code",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            DegreeCode=(
                "DegreeCode",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            MajorDesc=(
                "MajorDesc",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            DegreeDesc=(
                "DegreeDesc",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            canonical_lineage=(
                "canonical_lineage",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            award_level=(
                "award_level",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            stack_behavior=(
                "stack_behavior",
                lambda s: " | ".join(sorted(set(s.dropna()))),
            ),
            modeled_lineage_present=(
                "modeled_lineage_present",
                "first",
            ),
            first_institutional_grad_term=(
                "StudGradTerm",
                "min",
            ),
            last_institutional_grad_term=(
                "StudGradTerm",
                "max",
            ),
            first_institutional_grad_date=(
                "GradDate",
                "min",
            ),
            last_institutional_grad_date=(
                "GradDate",
                "max",
            ),
        )
        .rename(columns={"ID": "student_id"})
    )

    # ------------------------------------------------------------------
    # LOAD MODELED COMPLETIONS
    # ------------------------------------------------------------------
    modeled = pd.read_csv(
        MODELED_PATH,
        dtype=str,
        low_memory=False,
    )

    modeled_required = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "canonical_lineage",
        "program_family",
        "completion_academic_year",
    ]

    missing = sorted(set(modeled_required) - set(modeled.columns))
    if missing:
        raise ValueError(f"Modeled file missing columns: {missing}")

    for column in modeled_required:
        modeled[column] = clean_text(modeled[column])

    modeled = modeled[
        modeled["audit_status"].eq("COMPLETE")
    ].copy()

    modeled["reconciliation_key"] = modeled[
        "canonical_lineage"
    ]

    modeled_duplicate_key = modeled.duplicated(
        subset=["student_id", "reconciliation_key"],
        keep=False,
    )

    if modeled_duplicate_key.any():
        raise ValueError(
            "Modeled completions are not unique at "
            "student_id + canonical_lineage."
        )

    # No modeled credential is allowed to use an IA key.
    modeled_ia_keys = modeled[
        modeled["reconciliation_key"].str.startswith(
            "IA_",
            na=False,
        )
    ]

    if not modeled_ia_keys.empty:
        raise ValueError(
            "Modeled completion data unexpectedly contains IA_* "
            "lineages. IA awards must remain independent."
        )

    # ------------------------------------------------------------------
    # THREE-WAY RECONCILIATION
    # ------------------------------------------------------------------
    reconciliation = institutional.merge(
        modeled,
        on=["student_id", "reconciliation_key"],
        how="outer",
        indicator=True,
        suffixes=("_institutional", "_modeled"),
        validate="one_to_one",
    )

    bucket_map = {
        "both": "DETECTED_AND_AWARDED",
        "left_only": "AWARDED_NOT_DETECTED",
        "right_only": "DETECTED_NOT_AWARDED",
    }

    reconciliation["reconciliation_bucket"] = (
        reconciliation["_merge"]
        .astype("string")
        .map(bucket_map)
    )

    reconciliation = reconciliation.drop(columns="_merge")

    # IA rows are intentionally incapable of consuming/matching a
    # certificate or degree lineage because their keys remain IA_*.
    ia_reconciliation = reconciliation[
        reconciliation["reconciliation_key"].str.startswith(
            "IA_",
            na=False,
        )
    ]

    invalid_ia_bucket = ia_reconciliation[
        ia_reconciliation["reconciliation_bucket"].eq(
            "DETECTED_AND_AWARDED"
        )
    ]

    if not invalid_ia_bucket.empty:
        raise ValueError(
            "IA safety failure: an IA matched a modeled certificate "
            "or degree completion."
        )

    detected_and_awarded = reconciliation[
        reconciliation["reconciliation_bucket"].eq(
            "DETECTED_AND_AWARDED"
        )
    ].copy()

    awarded_not_detected = reconciliation[
        reconciliation["reconciliation_bucket"].eq(
            "AWARDED_NOT_DETECTED"
        )
    ].copy()

    detected_not_awarded = reconciliation[
        reconciliation["reconciliation_bucket"].eq(
            "DETECTED_NOT_AWARDED"
        )
    ].copy()

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    summary = pd.DataFrame(
        [
            {
                "metric": "institutional_source_rows",
                "value": source_award_rows,
            },
            {
                "metric": "institutional_unique_source_awards",
                "value": unique_award_rows,
            },
            {
                "metric": "institutional_student_lineages",
                "value": len(institutional),
            },
            {
                "metric": "modeled_student_lineages",
                "value": len(modeled),
            },
            {
                "metric": "detected_and_awarded",
                "value": len(detected_and_awarded),
            },
            {
                "metric": "awarded_not_detected",
                "value": len(awarded_not_detected),
            },
            {
                "metric": "detected_not_awarded",
                "value": len(detected_not_awarded),
            },
            {
                "metric": "institutional_ia_student_awards",
                "value": len(ia_reconciliation),
            },
            {
                "metric": "ia_detected_and_awarded",
                "value": len(invalid_ia_bucket),
            },
        ]
    )

    bucket_by_level = (
        reconciliation.groupby(
            [
                "reconciliation_bucket",
                "award_level",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="student_lineages")
    )

    bucket_by_lineage = (
        reconciliation.groupby(
            [
                "reconciliation_bucket",
                "reconciliation_key",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="student_lineages")
        .sort_values(
            ["reconciliation_bucket", "student_lineages"],
            ascending=[True, False],
        )
    )

    # ------------------------------------------------------------------
    # WRITE FERPA-RESTRICTED OUTPUTS
    # Names are deliberately excluded; IDs remain because this is the
    # operational reconciliation layer.
    # ------------------------------------------------------------------
    reconciliation.to_csv(
        output_dir / "all_reconciled_student_lineages.csv",
        index=False,
    )

    detected_and_awarded.to_csv(
        output_dir / "detected_and_awarded.csv",
        index=False,
    )

    awarded_not_detected.to_csv(
        output_dir / "awarded_not_detected.csv",
        index=False,
    )

    detected_not_awarded.to_csv(
        output_dir / "detected_not_awarded.csv",
        index=False,
    )

    summary.to_csv(
        output_dir / "reconciliation_summary.csv",
        index=False,
    )

    bucket_by_level.to_csv(
        output_dir / "reconciliation_by_award_level.csv",
        index=False,
    )

    bucket_by_lineage.to_csv(
        output_dir / "reconciliation_by_lineage.csv",
        index=False,
    )

    workbook_path = output_dir / "LSCO_Award_Reconciliation.xlsx"

    with pd.ExcelWriter(
        workbook_path,
        engine="openpyxl",
        datetime_format="yyyy-mm-dd",
    ) as writer:
        summary.to_excel(
            writer,
            sheet_name="Summary",
            index=False,
        )
        bucket_by_level.to_excel(
            writer,
            sheet_name="By Award Level",
            index=False,
        )
        bucket_by_lineage.to_excel(
            writer,
            sheet_name="By Lineage",
            index=False,
        )
        detected_and_awarded.to_excel(
            writer,
            sheet_name="Detected and Awarded",
            index=False,
        )
        awarded_not_detected.to_excel(
            writer,
            sheet_name="Awarded Not Detected",
            index=False,
        )
        detected_not_awarded.to_excel(
            writer,
            sheet_name="Detected Not Awarded",
            index=False,
        )

    print("=" * 92)
    print("INSTITUTIONAL AWARD RECONCILIATION COMPLETE")
    print("=" * 92)
    print(summary.to_string(index=False))
    print()
    print("IA GOVERNANCE")
    print(f"IA student-award keys: {len(ia_reconciliation):,}")
    print("IA matched to modeled cert/degree lineage: 0")
    print("IA stack behavior: INDEPENDENT_NONCONSUMING")
    print()
    print(f"Output directory: {output_dir}")
    print(f"Workbook: {workbook_path}")


if __name__ == "__main__":
    main()
