from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd


# ======================================================================================
# MODERN SECOND-ASSOCIATE REVIEW — TARGETED PRIOR-DEGREE RE-AUDIT
# ======================================================================================
#
# Purpose
# -------
# The 25 unresolved modern second-associate combinations all have official first
# associate awards inside the six-year modeled catalog window. The legacy
# full_actual_audit summary does not show those prior lineages COMPLETE.
#
# This script performs a SMALL, TARGETED re-audit:
#   * only the 24 affected students;
#   * only the official prior-degree canonical lineage;
#   * only catalog versions effective on/before the official award term;
#   * transcript truncated at the official first-prior award term;
#   * NO catalog-eligibility filter.
#
# This directly tests whether the earlier zero-COMPLETE result was caused by
# eligibility/version selection rather than curriculum logic.
#
# It does NOT modify any production artifact and does NOT adjudicate the
# 15-additional-resident-hour rule.
#
# Run from repository root:
#   python -u .\scripts\probe_prior_degree_targeted_reaudit_no_eligibility.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lsco_audit import audit_multiyear_sample_path_candidate as eng  # noqa: E402


REQUIREMENTS = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "requirements_master_multiyear.csv"
)

CORE_LOOKUP = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "runtime_support"
    / "core_bucket_lookup_multicatalog.csv"
)

ACADEMIC_CROSSWALK = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "runtime_support"
    / "catalog_academic_course_crosswalk_final.csv"
)

ELECTIVE_RULES = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "semantic_policies"
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

COMPOUND = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "semantic_policies"
    / "compound_requirement_alternatives.csv"
)

PATHS = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "semantic_policies"
    / "alternative_requirement_paths.csv"
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
    / f"prior_degree_targeted_reaudit_no_eligibility_{STAMP}"
)

RESTRICTED_SUMMARY = (
    OUTDIR
    / "RESTRICTED_prior_degree_targeted_reaudit_summary.csv"
)

RESTRICTED_DETAIL = (
    OUTDIR
    / "RESTRICTED_prior_degree_targeted_reaudit_detail.csv"
)

SAFE_STATUS = (
    OUTDIR
    / "FERPA_SAFE_prior_degree_targeted_reaudit_status.csv"
)

SAFE_FAMILY = (
    OUTDIR
    / "FERPA_SAFE_prior_degree_targeted_reaudit_by_family.csv"
)

PASSING_GRADES = {
    "A", "B", "C", "D",
    "S", "P", "CR", "E",
    "T", "TA", "TB", "TC", "TD", "TS",
}


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def latest_dir(pattern: str, required_name: str) -> Path:
    matches = sorted(
        [
            p
            for p in REPORTING.glob(pattern)
            if p.is_dir() and (p / required_name).exists()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def catalog_start_term(catalog_year: object) -> int:
    """
    LSCO Banner term convention:
      2021-2022 catalog begins Fall 2021 -> 202210
      2022-2023 catalog begins Fall 2022 -> 202310
      ...
    """
    start_year = int(txt(catalog_year)[:4])
    return (start_year + 1) * 100 + 10


def build_course_lookup(
    attempts: pd.DataFrame,
    award_term: int,
) -> dict[str, dict]:
    student = attempts.copy()

    student["term_sort_num"] = pd.to_numeric(
        student["term_sort"],
        errors="coerce",
    )

    student = student[
        student["term_sort_num"].notna()
        & student["term_sort_num"].le(award_term)
    ].copy()

    if "passed" in student.columns:
        passing = (
            student["passed"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin({"TRUE", "T", "YES", "Y", "1"})
        )
    else:
        grade_col = (
            "grade"
            if "grade" in student.columns
            else "final_grade"
        )

        passing = (
            student[grade_col]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(PASSING_GRADES)
        )

    student = student[passing].copy()

    grade_col = (
        "grade"
        if "grade" in student.columns
        else "final_grade"
    )

    student["course_code"] = (
        student["course_code"]
        .map(eng.normalize_course_code)
    )

    student = student[
        student["course_code"].ne("")
    ].copy()

    student["term_sort_num"] = (
        student["term_sort_num"].astype(int)
    )

    student = student.sort_values(
        ["course_code", "term_sort_num"],
        ascending=[True, False],
        kind="mergesort",
    )

    lookup = {}

    for _, row in student.drop_duplicates(
        "course_code",
        keep="first",
    ).iterrows():
        course = txt(row["course_code"])

        lookup[course] = {
            "course_code": course,
            "term_taken": txt(row.get("term_taken", "")),
            "term_sort": int(row["term_sort_num"]),
            "grade": txt(row.get(grade_col, "")),
        }

    return lookup


def summarize_detail(detail_rows: list[dict]) -> dict:
    df = pd.DataFrame(detail_rows)

    if df.empty:
        raise RuntimeError("Audit returned no detail rows.")

    path_group = (
        df["path_group_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    path_selected = (
        df["path_selected"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    counted = df[
        path_group.eq("")
        | path_selected.eq("TRUE")
    ].copy()

    total = len(counted)
    met = int(counted["status"].eq("MET").sum())

    unresolved = int(
        counted["status"]
        .astype(str)
        .str.startswith("UNRESOLVED")
        .sum()
    )

    missing = total - met - unresolved

    audit_status = eng.get_audit_status(
        missing,
        unresolved,
    )

    award_term_sort, award_term_taken = (
        eng.summarize_award_term(
            counted,
            audit_status,
        )
    )

    unmet = counted[
        ~counted["status"].eq("MET")
    ].copy()

    return {
        "requirements_met": met,
        "requirements_total": total,
        "requirements_missing": missing,
        "requirements_unresolved": unresolved,
        "audit_status": audit_status,
        "modeled_completion_term": award_term_sort,
        "modeled_completion_term_taken": award_term_taken,
        "unmet_requirement_ids": " | ".join(
            unmet["requirement_id"]
            .astype(str)
            .tolist()
        ),
        "unmet_statuses": " | ".join(
            unmet["status"]
            .astype(str)
            .tolist()
        ),
    }


def main() -> None:
    # ------------------------------------------------------------------
    # Sources.
    # ------------------------------------------------------------------
    s1dir = latest_dir(
        "second_associate_stage1_current_*",
        "RESTRICTED_second_associate_stage1_current.csv",
    )

    s2dir = latest_dir(
        "second_associate_stage2_current_*",
        "RESTRICTED_second_associate_stage2_final.csv",
    )

    adir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_current_attempt_state_candidate_students.csv",
    )

    s1 = pd.read_csv(
        s1dir / "RESTRICTED_second_associate_stage1_current.csv",
        dtype=str,
        low_memory=False,
    ).fillna("")

    s2 = pd.read_csv(
        s2dir / "RESTRICTED_second_associate_stage2_final.csv",
        dtype=str,
        low_memory=False,
    ).fillna("")

    attempts = pd.read_csv(
        adir / "RESTRICTED_current_attempt_state_candidate_students.csv",
        dtype=str,
        low_memory=False,
    ).fillna("")

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    # ------------------------------------------------------------------
    # Pull exactly the 25 unresolved combinations.
    # ------------------------------------------------------------------
    reviews = s2[
        s2["final_stage2_decision"].eq(
            "REVIEW_SECOND_ASSOCIATE_2025_RULE"
        )
    ][
        ["student_id", "catalog_year", "credential_id"]
    ].drop_duplicates()

    cases = reviews.merge(
        s1,
        on=["student_id", "catalog_year", "credential_id"],
        how="left",
        validate="one_to_one",
    )

    if len(cases) != 25:
        raise RuntimeError(
            f"Expected 25 review combinations; found {len(cases):,}"
        )

    # ------------------------------------------------------------------
    # Official-program -> canonical lineage from curated crosswalk.
    # ------------------------------------------------------------------
    xw = pd.read_excel(
        CROSSWALK,
        sheet_name="Crosswalk Draft",
        dtype=str,
    ).fillna("")

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

    cases["first_prior_program_code"] = (
        cases["first_prior_program_code"]
        .str.strip()
        .str.upper()
    )

    # Only validate mappings for the official prior program codes actually
    # present in these 25 review combinations. The curated workbook contains
    # unrelated historical codes (for example AAS_BSMT, CERT1_PHRA, ZCONV CERT)
    # that intentionally have more than one curation row and are irrelevant to
    # this targeted prior-degree probe.
    needed_program_codes = set(
        cases["first_prior_program_code"]
    )

    code_map_frame = (
        xw[
            xw["Curr1ProgramCode"].isin(
                needed_program_codes
            )
        ][
            ["Curr1ProgramCode", "canonical_lineage"]
        ]
        .drop_duplicates()
    )

    duplicate_codes = (
        code_map_frame.groupby(
            "Curr1ProgramCode"
        )["canonical_lineage"]
        .nunique()
    )

    bad = duplicate_codes[
        duplicate_codes.gt(1)
    ]

    if not bad.empty:
        raise RuntimeError(
            "A REQUIRED prior program code maps to multiple canonical "
            "lineages in the curated crosswalk:\n"
            + bad.to_string()
        )

    code_map = dict(
        zip(
            code_map_frame["Curr1ProgramCode"],
            code_map_frame["canonical_lineage"],
        )
    )

    cases["expected_prior_lineage"] = (
        cases["first_prior_program_code"]
        .map(code_map)
        .fillna("")
    )

    if cases["expected_prior_lineage"].eq("").any():
        bad_codes = sorted(
            cases.loc[
                cases["expected_prior_lineage"].eq(""),
                "first_prior_program_code",
            ].unique()
        )

        raise RuntimeError(
            "Missing official-program canonical mapping: "
            + ", ".join(bad_codes)
        )

    # ------------------------------------------------------------------
    # Modeled credential -> canonical lineage from the curated workbook.
    # This is preferable to guessing from credential_id text.
    # ------------------------------------------------------------------
    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    needed_modeled = {
        "credential_id",
        "canonical_lineage",
    }

    missing = needed_modeled - set(modeled.columns)

    if missing:
        raise RuntimeError(
            "Modeled Inventory missing columns: "
            + ", ".join(sorted(missing))
        )

    modeled["credential_id"] = (
        modeled["credential_id"]
        .astype(str)
        .str.strip()
    )

    modeled["canonical_lineage"] = (
        modeled["canonical_lineage"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    model_map = (
        modeled[
            ["credential_id", "canonical_lineage"]
        ]
        .drop_duplicates()
    )

    dup_model = (
        model_map.groupby("credential_id")["canonical_lineage"]
        .nunique()
    )

    bad_model = dup_model[dup_model.gt(1)]

    if not bad_model.empty:
        raise RuntimeError(
            "Modeled credential maps to multiple canonical lineages:\n"
            + bad_model.to_string()
        )

    model_map = dict(
        zip(
            model_map["credential_id"],
            model_map["canonical_lineage"],
        )
    )

    req["canonical_lineage"] = (
        req["credential_id"]
        .map(model_map)
        .fillna("")
    )

    # Fail loud if a target family has no modeled credential rows.
    target_lineages = set(cases["expected_prior_lineage"])

    missing_target_lineages = sorted(
        target_lineages
        - set(
            req.loc[
                req["canonical_lineage"].ne(""),
                "canonical_lineage",
            ]
        )
    )

    if missing_target_lineages:
        raise RuntimeError(
            "No modeled requirement rows for target lineage(s): "
            + ", ".join(missing_target_lineages)
        )

    # ------------------------------------------------------------------
    # Point the validated path-aware engine at the six-year staging assets.
    # ------------------------------------------------------------------
    eng.CORE_LOOKUP = CORE_LOOKUP
    eng.ELECTIVE_RULES = ELECTIVE_RULES
    eng.ACADEMIC_COURSE_CROSSWALK = ACADEMIC_CROSSWALK
    eng.COMPOUND_REQUIREMENT_ALTERNATIVES = COMPOUND
    eng.ALTERNATIVE_REQUIREMENT_PATHS = PATHS

    core_lookup = eng.load_core_lookup()
    elective_rules = eng.load_elective_rules()
    academic_lookup = eng.load_academic_course_lookup()
    compound = eng.load_compound_requirement_alternatives()
    alt_paths = eng.load_alternative_requirement_paths()

    eng.validate_alternative_requirement_paths(
        alt_paths,
        req,
    )

    alt_lookup = eng.build_alternative_path_lookup(
        alt_paths
    )

    # ------------------------------------------------------------------
    # Run only unique official prior awards. R80093283 has two current
    # candidate catalogs but one prior award, so don't duplicate engine work.
    # ------------------------------------------------------------------
    prior_key_cols = [
        "student_id",
        "first_prior_program_code",
        "first_prior_grad_term",
        "expected_prior_lineage",
    ]

    prior_awards = (
        cases[prior_key_cols]
        .drop_duplicates()
        .sort_values(prior_key_cols)
    )

    if len(prior_awards) != 24:
        raise RuntimeError(
            f"Expected 24 distinct prior-award cases; found {len(prior_awards):,}"
        )

    summary_rows = []
    detail_rows = []

    for prior in prior_awards.itertuples(index=False):
        student_id = txt(prior.student_id)
        official_term = int(txt(prior.first_prior_grad_term))
        lineage = txt(prior.expected_prior_lineage)

        student_attempts = attempts[
            attempts["student_id"].eq(student_id)
        ].copy()

        if student_attempts.empty:
            raise RuntimeError(
                f"No current attempt-state rows for {student_id}"
            )

        course_lookup = build_course_lookup(
            student_attempts,
            official_term,
        )

        family_req = req[
            req["canonical_lineage"].eq(lineage)
        ].copy()

        versions = (
            family_req[
                ["catalog_year", "credential_id"]
            ]
            .drop_duplicates()
            .assign(
                catalog_start_term=lambda d:
                    d["catalog_year"].map(catalog_start_term)
            )
        )

        versions = versions[
            versions["catalog_start_term"].le(official_term)
        ].copy()

        if versions.empty:
            raise RuntimeError(
                f"No modeled {lineage} catalog version effective by "
                f"official term {official_term} for {student_id}"
            )

        for version in versions.itertuples(index=False):
            catalog_year = txt(version.catalog_year)
            credential_id = txt(version.credential_id)

            credential_req = family_req[
                family_req["catalog_year"].eq(catalog_year)
                & family_req["credential_id"].eq(credential_id)
            ].copy()

            audited = eng.audit_student_credential(
                student_id=student_id,
                catalog_year=catalog_year,
                credential_id=credential_id,
                credential_requirements=credential_req,
                course_lookup=course_lookup,
                core_lookup=core_lookup,
                elective_rules=elective_rules,
                academic_course_lookup=academic_lookup,
                compound_alternatives=compound,
                alternative_path_lookup=alt_lookup,
            )

            summary = summarize_detail(audited)

            summary_rows.append(
                {
                    "student_id": student_id,
                    "first_prior_program_code":
                        txt(prior.first_prior_program_code),
                    "first_prior_grad_term": official_term,
                    "expected_prior_lineage": lineage,
                    "prior_catalog_year": catalog_year,
                    "prior_credential_id": credential_id,
                    **summary,
                }
            )

            for row in audited:
                detail_rows.append(
                    {
                        "official_first_prior_program_code":
                            txt(prior.first_prior_program_code),
                        "official_first_prior_grad_term":
                            official_term,
                        "expected_prior_lineage":
                            lineage,
                        **row,
                    }
                )

    summary_df = pd.DataFrame(summary_rows)
    detail_df = pd.DataFrame(detail_rows)

    # ------------------------------------------------------------------
    # Per-prior-award outcome:
    # 1) COMPLETE on at least one version;
    # 2) otherwise report best modeled distance.
    # ------------------------------------------------------------------
    outcome_rows = []

    for key, group in summary_df.groupby(
        prior_key_cols,
        sort=False,
    ):
        complete = group[
            group["audit_status"].eq("COMPLETE")
        ].copy()

        if not complete.empty:
            outcome = "FOUND_COMPLETE_WITHOUT_ELIGIBILITY_FILTER"
            best = complete.sort_values(
                [
                    "prior_catalog_year",
                    "prior_credential_id",
                ],
                ascending=[False, True],
            ).iloc[0]
        else:
            outcome = "NO_COMPLETE_AFTER_ALL_FAMILY_VERSIONS"
            best = group.sort_values(
                [
                    "requirements_unresolved",
                    "requirements_missing",
                    "requirements_met",
                    "prior_catalog_year",
                ],
                ascending=[True, True, False, False],
            ).iloc[0]

        outcome_rows.append(
            {
                "student_id": key[0],
                "first_prior_program_code": key[1],
                "first_prior_grad_term": key[2],
                "expected_prior_lineage": key[3],
                "targeted_reaudit_outcome": outcome,
                "complete_plan_count": int(
                    group["audit_status"].eq("COMPLETE").sum()
                ),
                "best_catalog_year": best["prior_catalog_year"],
                "best_credential_id": best["prior_credential_id"],
                "best_audit_status": best["audit_status"],
                "best_requirements_met": best["requirements_met"],
                "best_requirements_total": best["requirements_total"],
                "best_requirements_missing":
                    best["requirements_missing"],
                "best_requirements_unresolved":
                    best["requirements_unresolved"],
                "best_unmet_requirement_ids":
                    best["unmet_requirement_ids"],
                "best_unmet_statuses":
                    best["unmet_statuses"],
            }
        )

    outcomes = pd.DataFrame(outcome_rows)

    # Join back to the 25 current candidate combinations for auditability.
    candidate_out = cases[
        [
            "student_id",
            "catalog_year",
            "credential_id",
            "first_prior_program_code",
            "first_prior_grad_term",
            "expected_prior_lineage",
        ]
    ].merge(
        outcomes,
        on=[
            "student_id",
            "first_prior_program_code",
            "first_prior_grad_term",
            "expected_prior_lineage",
        ],
        how="left",
        validate="many_to_one",
    )

    OUTDIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    candidate_out.to_csv(
        RESTRICTED_SUMMARY,
        index=False,
    )

    detail_df.to_csv(
        RESTRICTED_DETAIL,
        index=False,
    )

    safe_status = (
        outcomes.groupby(
            "targeted_reaudit_outcome",
            dropna=False,
        )
        .agg(
            distinct_prior_awards=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
        )
        .reset_index()
    )

    safe_status.to_csv(
        SAFE_STATUS,
        index=False,
    )

    safe_family = (
        outcomes.groupby(
            [
                "expected_prior_lineage",
                "first_prior_program_code",
                "targeted_reaudit_outcome",
            ],
            dropna=False,
        )
        .agg(
            prior_awards=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
            min_best_missing=("best_requirements_missing", "min"),
            max_best_missing=("best_requirements_missing", "max"),
            min_best_unresolved=("best_requirements_unresolved", "min"),
            max_best_unresolved=("best_requirements_unresolved", "max"),
        )
        .reset_index()
        .sort_values(
            [
                "targeted_reaudit_outcome",
                "expected_prior_lineage",
                "first_prior_program_code",
            ]
        )
    )

    safe_family.to_csv(
        SAFE_FAMILY,
        index=False,
    )

    print("=" * 118)
    print("TARGETED PRIOR-DEGREE RE-AUDIT — NO CATALOG ELIGIBILITY FILTER")
    print("=" * 118)
    print()
    print(f"Current review combinations:          {len(cases):,}")
    print(f"Distinct official prior awards:       {len(prior_awards):,}")
    print(f"Distinct students:                    {prior_awards['student_id'].nunique():,}")
    print(f"Prior-family catalog audits executed: {len(summary_df):,}")
    print()
    print("OUTCOMES")
    print("-" * 118)
    print(safe_status.to_string(index=False))
    print()
    print("BY PRIOR FAMILY")
    print("-" * 118)
    print(safe_family.to_string(index=False))
    print()
    print("BEST NON-COMPLETE DISTANCE (if any)")
    print("-" * 118)

    unresolved = outcomes[
        outcomes["targeted_reaudit_outcome"].eq(
            "NO_COMPLETE_AFTER_ALL_FAMILY_VERSIONS"
        )
    ]

    if unresolved.empty:
        print("NONE — every official prior award has at least one modeled COMPLETE plan.")
    else:
        diagnostic = (
            unresolved.groupby(
                [
                    "expected_prior_lineage",
                    "best_audit_status",
                    "best_requirements_missing",
                    "best_requirements_unresolved",
                    "best_unmet_statuses",
                ],
                dropna=False,
            )
            .size()
            .reset_index(name="prior_awards")
            .sort_values(
                [
                    "best_requirements_missing",
                    "best_requirements_unresolved",
                    "prior_awards",
                ],
                ascending=[True, True, False],
            )
        )
        print(diagnostic.to_string(index=False))

    print()
    print("CONTROLS")
    print("  This is a targeted 24-student / prior-family rerun, not a full audit.")
    print("  Transcript state is truncated at the official first-prior award term.")
    print("  Every modeled catalog version effective by that award term is tested.")
    print("  Catalog eligibility is deliberately NOT used.")
    print("  No second-associate PASS/FAIL decision is made here.")
    print("  No upstream artifact is modified.")
    print()
    print(f"Restricted summary: {RESTRICTED_SUMMARY}")
    print(f"Restricted detail:  {RESTRICTED_DETAIL}")
    print(f"Output directory:   {OUTDIR}")


if __name__ == "__main__":
    main()
