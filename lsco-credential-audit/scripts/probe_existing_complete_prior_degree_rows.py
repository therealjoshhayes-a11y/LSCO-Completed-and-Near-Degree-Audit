from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

HIST_SUMMARY = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "full_actual_credential_summary.csv"
)

CROSSWALK = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "award_program_crosswalk_curated.xlsx"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTDIR = (
    REPORTING
    / f"modern_second_associate_existing_complete_lookup_{STAMP}"
)

RESTRICTED_OUT = (
    OUTDIR
    / "RESTRICTED_existing_complete_prior_degree_lookup.csv"
)

SAFE_OUT = (
    OUTDIR
    / "FERPA_SAFE_existing_complete_prior_degree_lookup_summary.csv"
)

SAFE_MAPPING_OUT = (
    OUTDIR
    / "FERPA_SAFE_prior_program_code_mapping.csv"
)


LEGACY_MODELED_LINEAGE = {
    "TEACHING_T038": "TEACHING_AAT1",
    "TEACHING_T074": "TEACHING_AAT1",
    "TEACHING_T039": "TEACHING_AAT2",
    "TEACHING_T075": "TEACHING_AAT2",
}


def text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def upper(value: object) -> str:
    return text(value).upper()


def latest_dir(pattern: str, required_file: str) -> Path:
    matches = sorted(
        [
            p
            for p in REPORTING.glob(pattern)
            if p.is_dir() and (p / required_file).exists()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_file}"
        )

    return matches[0]


def canonicalize_modeled_credential(credential_id: object) -> str:
    """
    Convert modeled audit credential IDs to the established canonical family
    identity needed only for this lookup.

    Ordinary modeled IDs are year-suffixed canonical identities.
    Historical Teaching aliases are mapped by the already-established identity
    repair. The 2025+ Teacher Education parser identity is likewise normalized
    to the curated Teacher Education AAT lineage.
    """
    raw = upper(credential_id)

    base = re.sub(r"_20\d{2}$", "", raw)

    if base in LEGACY_MODELED_LINEAGE:
        return LEGACY_MODELED_LINEAGE[base]

    if base.startswith("TEACHER_EDUCATION_AAS"):
        return "TEACHER_EDUCATION_AAT"

    return base


def load_crosswalk_mapping(program_codes: set[str]) -> dict[str, str]:
    if not CROSSWALK.exists():
        raise FileNotFoundError(CROSSWALK)

    xw = pd.read_excel(
        CROSSWALK,
        sheet_name="Crosswalk Draft",
        dtype=str,
    ).fillna("")

    required = {
        "Curr1ProgramCode",
        "canonical_lineage",
    }

    missing = required - set(xw.columns)

    if missing:
        raise RuntimeError(
            "Crosswalk missing columns: "
            + ", ".join(sorted(missing))
        )

    xw["Curr1ProgramCode"] = (
        xw["Curr1ProgramCode"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    xw["canonical_lineage"] = (
        xw["canonical_lineage"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    subset = xw[
        xw["Curr1ProgramCode"].isin(program_codes)
    ][
        [
            "Curr1ProgramCode",
            "canonical_lineage",
        ]
    ].drop_duplicates()

    dupes = (
        subset.groupby("Curr1ProgramCode")["canonical_lineage"]
        .nunique()
    )

    bad = dupes[dupes.gt(1)]

    if not bad.empty:
        raise RuntimeError(
            "Official program code maps to multiple canonical lineages:\n"
            + bad.to_string()
        )

    mapping = dict(
        zip(
            subset["Curr1ProgramCode"],
            subset["canonical_lineage"],
        )
    )

    missing_codes = sorted(program_codes - set(mapping))

    if missing_codes:
        raise RuntimeError(
            "Official prior program code(s) missing from curated crosswalk: "
            + ", ".join(missing_codes)
        )

    blank = sorted(
        code
        for code, lineage in mapping.items()
        if not lineage
    )

    if blank:
        raise RuntimeError(
            "Official prior program code(s) have blank canonical lineage: "
            + ", ".join(blank)
        )

    return mapping


def main() -> None:
    stage1_dir = latest_dir(
        "second_associate_stage1_current_*",
        "RESTRICTED_second_associate_stage1_current.csv",
    )

    stage2_dir = latest_dir(
        "second_associate_stage2_current_*",
        "RESTRICTED_second_associate_stage2_final.csv",
    )

    stage1_path = (
        stage1_dir
        / "RESTRICTED_second_associate_stage1_current.csv"
    )

    stage2_path = (
        stage2_dir
        / "RESTRICTED_second_associate_stage2_final.csv"
    )

    s1 = pd.read_csv(
        stage1_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    s2 = pd.read_csv(
        stage2_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_s1 = {
        "student_id",
        "catalog_year",
        "credential_id",
        "first_prior_program_code",
        "first_prior_grad_term",
        "first_prior_degree_code",
    }

    missing = required_s1 - set(s1.columns)

    if missing:
        raise RuntimeError(
            "Stage-1 file missing columns: "
            + ", ".join(sorted(missing))
        )

    required_s2 = {
        "student_id",
        "catalog_year",
        "credential_id",
        "final_stage2_decision",
    }

    missing = required_s2 - set(s2.columns)

    if missing:
        raise RuntimeError(
            "Stage-2 file missing columns: "
            + ", ".join(sorted(missing))
        )

    reviews = s2[
        s2["final_stage2_decision"].eq(
            "REVIEW_SECOND_ASSOCIATE_2025_RULE"
        )
    ][
        [
            "student_id",
            "catalog_year",
            "credential_id",
        ]
    ].drop_duplicates()

    cases = reviews.merge(
        s1,
        on=[
            "student_id",
            "catalog_year",
            "credential_id",
        ],
        how="left",
        validate="one_to_one",
    )

    if len(cases) != 25:
        raise RuntimeError(
            f"Expected 25 review combinations; found {len(cases):,}"
        )

    if cases["first_prior_program_code"].eq("").any():
        raise RuntimeError(
            "At least one review case has blank first_prior_program_code."
        )

    if cases["first_prior_grad_term"].eq("").any():
        raise RuntimeError(
            "At least one review case has blank first_prior_grad_term."
        )

    cases["first_prior_program_code"] = (
        cases["first_prior_program_code"]
        .str.strip()
        .str.upper()
    )

    program_codes = set(
        cases["first_prior_program_code"]
    )

    mapping = load_crosswalk_mapping(program_codes)

    cases["expected_prior_lineage"] = (
        cases["first_prior_program_code"]
        .map(mapping)
    )

    mapping_safe = (
        cases[
            [
                "first_prior_program_code",
                "first_prior_degree_code",
                "expected_prior_lineage",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "expected_prior_lineage",
                "first_prior_program_code",
            ]
        )
    )

    # ----------------------------------------------------------------------
    # Scan the EXISTING historical all-catalog audit summary.
    #
    # IMPORTANT:
    #   We deliberately DO NOT filter catalog_eligible here.
    #   The official first degree is already known to have been conferred.
    #   This probe asks only whether an existing COMPLETE modeled audit row
    #   exists for the corresponding prior-degree lineage.
    # ----------------------------------------------------------------------
    if not HIST_SUMMARY.exists():
        raise FileNotFoundError(HIST_SUMMARY)

    header = pd.read_csv(
        HIST_SUMMARY,
        nrows=0,
    ).columns.tolist()

    desired = [
        "student_id",
        "catalog_year",
        "credential_id",
        "credential_title",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "catalog_eligible",
    ]

    usecols = [
        c
        for c in desired
        if c in header
    ]

    required_summary = {
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
    }

    missing = required_summary - set(usecols)

    if missing:
        raise RuntimeError(
            "Historical audit summary missing required columns: "
            + ", ".join(sorted(missing))
        )

    target_students = set(
        cases["student_id"]
    )

    parts = []
    rows_read = 0

    for chunk in pd.read_csv(
        HIST_SUMMARY,
        dtype=str,
        usecols=usecols,
        chunksize=250_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        rows_read += len(chunk)

        chunk = chunk[
            chunk["student_id"].isin(target_students)
        ].copy()

        if chunk.empty:
            continue

        chunk = chunk[
            chunk["audit_status"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("COMPLETE")
        ].copy()

        if chunk.empty:
            continue

        chunk["modeled_canonical_lineage"] = (
            chunk["credential_id"]
            .map(canonicalize_modeled_credential)
        )

        parts.append(chunk)

    if parts:
        all_complete = pd.concat(
            parts,
            ignore_index=True,
        )
    else:
        all_complete = pd.DataFrame(
            columns=usecols + ["modeled_canonical_lineage"]
        )

    # Attach candidate-specific prior identity, so a student with two current
    # Liberal Arts candidate catalogs remains two review combinations but uses
    # the same official first-prior award evidence.
    matched = cases[
        [
            "student_id",
            "catalog_year",
            "credential_id",
            "first_prior_program_code",
            "first_prior_grad_term",
            "first_prior_degree_code",
            "expected_prior_lineage",
        ]
    ].merge(
        all_complete,
        on="student_id",
        how="left",
        suffixes=(
            "_candidate",
            "_prior_audit",
        ),
    )

    matched["is_expected_prior_lineage"] = (
        matched["modeled_canonical_lineage"]
        .eq(
            matched["expected_prior_lineage"]
        )
    )

    expected = matched[
        matched["is_expected_prior_lineage"]
    ].copy()

    # Completion-term timing is a descriptive check, not an eligibility gate.
    expected["official_prior_grad_term_num"] = pd.to_numeric(
        expected["first_prior_grad_term"],
        errors="coerce",
    )

    if "award_term_sort" in expected.columns:
        expected["modeled_completion_term_num"] = pd.to_numeric(
            expected["award_term_sort"],
            errors="coerce",
        )

        expected["completion_timing"] = "MODELED_TERM_UNAVAILABLE"

        on_or_before = (
            expected["modeled_completion_term_num"].notna()
            & expected["official_prior_grad_term_num"].notna()
            & expected["modeled_completion_term_num"].le(
                expected["official_prior_grad_term_num"]
            )
        )

        after = (
            expected["modeled_completion_term_num"].notna()
            & expected["official_prior_grad_term_num"].notna()
            & expected["modeled_completion_term_num"].gt(
                expected["official_prior_grad_term_num"]
            )
        )

        expected.loc[
            on_or_before,
            "completion_timing",
        ] = "COMPLETE_ON_OR_BEFORE_OFFICIAL_AWARD_TERM"

        expected.loc[
            after,
            "completion_timing",
        ] = "COMPLETE_AFTER_OFFICIAL_AWARD_TERM"
    else:
        expected["completion_timing"] = "MODELED_TERM_COLUMN_UNAVAILABLE"

    candidate_key = [
        "student_id",
        "catalog_year_candidate",
        "credential_id_candidate",
    ]

    # Summary at the current candidate-combination grain.
    summary_rows = []

    for row in cases.itertuples(index=False):
        student_id = text(row.student_id)
        cand_catalog = text(row.catalog_year)
        cand_credential = text(row.credential_id)

        subset = expected[
            expected["student_id"].eq(student_id)
            & expected["catalog_year_candidate"].eq(cand_catalog)
            & expected["credential_id_candidate"].eq(cand_credential)
        ].copy()

        on_time = subset[
            subset["completion_timing"].eq(
                "COMPLETE_ON_OR_BEFORE_OFFICIAL_AWARD_TERM"
            )
        ].copy()

        if not on_time.empty:
            status = "FOUND_COMPLETE_PRIOR_PLAN_ON_OR_BEFORE_OFFICIAL_AWARD"
        elif not subset.empty:
            status = "FOUND_COMPLETE_PRIOR_PLAN_BUT_ONLY_AFTER_OFFICIAL_AWARD"
        else:
            status = "NO_EXISTING_COMPLETE_PRIOR_PLAN_FOUND"

        summary_rows.append(
            {
                "student_id": student_id,
                "catalog_year": cand_catalog,
                "credential_id": cand_credential,
                "first_prior_program_code":
                    text(row.first_prior_program_code),
                "first_prior_grad_term":
                    text(row.first_prior_grad_term),
                "first_prior_degree_code":
                    text(row.first_prior_degree_code),
                "expected_prior_lineage":
                    text(row.expected_prior_lineage),
                "existing_complete_prior_rows":
                    len(subset),
                "existing_complete_prior_rows_on_or_before_award":
                    len(on_time),
                "lookup_status":
                    status,
                "matching_prior_catalogs":
                    " | ".join(
                        sorted(
                            set(
                                subset.get(
                                    "catalog_year_prior_audit",
                                    pd.Series(dtype=str),
                                ).astype(str)
                            )
                        )
                    ),
                "matching_prior_credentials":
                    " | ".join(
                        sorted(
                            set(
                                subset.get(
                                    "credential_id_prior_audit",
                                    pd.Series(dtype=str),
                                ).astype(str)
                            )
                        )
                    ),
            }
        )

    result = pd.DataFrame(summary_rows)

    OUTDIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    result.to_csv(
        RESTRICTED_OUT,
        index=False,
    )

    safe = (
        result.groupby(
            [
                "first_prior_program_code",
                "first_prior_degree_code",
                "expected_prior_lineage",
                "lookup_status",
            ],
            dropna=False,
        )
        .agg(
            candidate_combinations=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            min_complete_prior_rows=(
                "existing_complete_prior_rows",
                "min",
            ),
            max_complete_prior_rows=(
                "existing_complete_prior_rows",
                "max",
            ),
            min_on_time_rows=(
                "existing_complete_prior_rows_on_or_before_award",
                "min",
            ),
            max_on_time_rows=(
                "existing_complete_prior_rows_on_or_before_award",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "lookup_status",
                "expected_prior_lineage",
                "first_prior_program_code",
            ]
        )
    )

    safe.to_csv(
        SAFE_OUT,
        index=False,
    )

    mapping_safe.to_csv(
        SAFE_MAPPING_OUT,
        index=False,
    )

    status_counts = (
        result["lookup_status"]
        .value_counts(dropna=False)
    )

    print("=" * 118)
    print("MODERN SECOND-ASSOCIATE REVIEWS — EXISTING COMPLETE PRIOR-DEGREE LOOKUP")
    print("=" * 118)
    print()
    print(f"Review combinations:                  {len(result):,}")
    print(f"Distinct students:                    {result['student_id'].nunique():,}")
    print(f"Historical audit summary rows read:   {rows_read:,}")
    print()
    print("LOOKUP STATUS")
    print("-" * 118)
    print(status_counts.to_string())
    print()
    print("BY OFFICIAL PRIOR PROGRAM / MODELED LINEAGE")
    print("-" * 118)
    print(safe.to_string(index=False))
    print()
    print("CONTROL:")
    print("  No curriculum audit was rerun.")
    print("  catalog_eligible was NOT used as a filter.")
    print("  Only pre-existing COMPLETE rows in full_actual_credential_summary.csv were inspected.")
    print("  Official prior award term is used only to label whether modeled completion was on/before the award.")
    print()
    print(f"Restricted lookup: {RESTRICTED_OUT}")
    print(f"FERPA-safe summary: {SAFE_OUT}")
    print(f"Output directory:   {OUTDIR}")


if __name__ == "__main__":
    main()
