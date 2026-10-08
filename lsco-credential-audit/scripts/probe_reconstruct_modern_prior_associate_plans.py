from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# MODERN SECOND-ASSOCIATE PRIOR-PLAN RECONSTRUCTION PROBE
# ======================================================================================
#
# Purpose:
#   Reconstruct the FIRST PRIOR associate degree plan for the 39 modern-rule
#   candidates that survived Stage 1, using the VALIDATED six-year audit engine
#   against the student's transcript AS OF the official first-prior award term.
#
# Why:
#   The old Stage-2 implementation compared the candidate's allocated courses
#   against every plausible COMPLETE prior-plan allocation. The historical cache
#   does not contain a COMPLETE modeled prior plan for most current cases, so this
#   probe rebuilds that evidence directly rather than treating missing cache rows
#   as policy failures.
#
# Canonical eligibility:
#   This script imports scripts/build_student_catalog_eligibility_v2.py and applies
#   it to each student's activity history truncated at the first prior award term.
#
# Audit engine:
#   Uses src/lsco_audit/audit_multiyear_sample_path_candidate.py with the validated
#   SIX-YEAR staging support files.
#
# Outputs:
#   Restricted reconstruction evidence for the next Stage-2 adjudicator plus
#   FERPA-safe coverage summaries.
#
# No second-associate Stage-2 PASS/FAIL decision is made here.
#
# Run:
#   python -u .\scripts\probe_reconstruct_modern_prior_associate_plans.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(
        0,
        str(SRC),
    )

from lsco_audit import audit_multiyear_sample_path_candidate as engine  # noqa: E402


EXPECTED_PENDING = 39

STAGING = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
)

REQUIREMENTS = (
    STAGING
    / "requirements_master_multiyear.csv"
)

CORE_LOOKUP = (
    STAGING
    / "runtime_support"
    / "core_bucket_lookup_multicatalog.csv"
)

ACADEMIC_CROSSWALK = (
    STAGING
    / "runtime_support"
    / "catalog_academic_course_crosswalk_final.csv"
)

ELECTIVE_RULES = (
    STAGING
    / "semantic_policies"
    / "ELECTIVE_controlled_semantic_overrides_final.csv"
)

COMPOUND = (
    STAGING
    / "semantic_policies"
    / "compound_requirement_alternatives.csv"
)

ALT_PATHS = (
    STAGING
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

ELIGIBILITY_SCRIPT = (
    ROOT
    / "scripts"
    / "build_student_catalog_eligibility_v2.py"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"modern_second_associate_prior_plan_reconstruction_{STAMP}"
)

RESTRICTED_PLAN_OUT = (
    OUT_DIR
    / "RESTRICTED_reconstructed_prior_plan_candidates.csv"
)

RESTRICTED_DETAIL_OUT = (
    OUT_DIR
    / "RESTRICTED_reconstructed_prior_plan_detail.csv"
)

RESTRICTED_ALLOC_OUT = (
    OUT_DIR
    / "RESTRICTED_reconstructed_prior_plan_allocations.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_prior_plan_reconstruction_metrics.csv"
)

SAFE_FAMILY_OUT = (
    OUT_DIR
    / "FERPA_SAFE_prior_plan_reconstruction_by_family.csv"
)

SAFE_GAPS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_prior_plan_reconstruction_gaps.csv"
)

SAFE_PLAUSIBLE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_plausible_prior_plan_counts.csv"
)


PASSING_GRADES = {
    "A",
    "B",
    "C",
    "D",
    "S",
    "P",
    "CR",
    "T",
    "TA",
    "TB",
    "TC",
    "TD",
    "TS",
}


CANONICAL_ALIASES = {
    "GENERAL_STUDIES":
        "GENERAL_STUDIES_CORE_CURRICULUM",
    "ORDINARY_SEAMAN_BASIC_SAFETY_TRAINING":
        "ORDINARY_SEAMAN_I",
    "PHARMACY_TECHNOLOGY":
        "HOSPITAL_PHARMACY_TECHNOLOGY",
    "PHARMACY_TECHNOLOGY_BASIC":
        "RETAIL_PHARMACY_TECHNOLOGY_BASIC",
    "SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE":
        "SAFETY_HEALTH_AND_ENVIRONMENT",
    "WELDING_TECHNOLOGY":
        "WELDING_TECHNOLOGY_CERTIFICATE_OF_COMPLETION",
    "TEACHING_T038":
        "TEACHING_AAT1",
    "TEACHING_T074":
        "TEACHING_AAT1",
    "TEACHING_T039":
        "TEACHING_AAT2",
    "TEACHING_T075":
        "TEACHING_AAT2",
}


# Exact identity repairs already supported by prior curation / catalog evidence.
CREDENTIAL_LINEAGE_OVERRIDES = {
    "TEACHING_T038_2021":
        "TEACHING_AAT1",
    "TEACHING_T074_2021":
        "TEACHING_AAT1",
    "TEACHING_T039_2021":
        "TEACHING_AAT2",
    "TEACHING_T075_2021":
        "TEACHING_AAT2",
    "TEACHING_AAT1_2022":
        "TEACHING_AAT1",
    "TEACHING_AAT2_2022":
        "TEACHING_AAT2",
    "TEACHING_AAT1_2023":
        "TEACHING_AAT1",
    "TEACHING_AAT2_2023":
        "TEACHING_AAT2",
    "TEACHING_AAT1_2024":
        "TEACHING_AAT1",
    "TEACHING_AAT2_2024":
        "TEACHING_AAT2",
    # The six-year staged ID says AAS, but the source catalog heading is
    # Teacher Education — Associate of Arts in Teaching Degree.
    "TEACHER_EDUCATION_AAS_2025":
        "TEACHER_EDUCATION_AAT",
    "TEACHER_EDUCATION_AAS_2026":
        "TEACHER_EDUCATION_AAT",
}


KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm(value: object) -> str:
    return txt(value).upper().replace(
        " ",
        "_",
    )


def canonicalize(value: object) -> str:
    value = norm(value)

    return CANONICAL_ALIASES.get(
        value,
        value,
    )


def truthy(value: object) -> bool:
    return txt(value).upper() in {
        "TRUE",
        "T",
        "YES",
        "Y",
        "1",
    }


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    matches = sorted(
        [
            path
            for path in REPORTING.glob(
                pattern
            )
            if (
                path.is_dir()
                and (
                    path
                    / required_name
                ).exists()
            )
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def load_eligibility_module():
    spec = importlib.util.spec_from_file_location(
        "lsco_catalog_eligibility_v2",
        ELIGIBILITY_SCRIPT,
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load build_student_catalog_eligibility_v2.py"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


def detail_counted_rows(
    detail: pd.DataFrame,
) -> pd.DataFrame:
    if detail.empty:
        return detail.copy()

    path_group = (
        detail[
            "path_group_id"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        if "path_group_id"
        in detail.columns
        else pd.Series(
            "",
            index=detail.index,
        )
    )

    path_selected = (
        detail[
            "path_selected"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        if "path_selected"
        in detail.columns
        else pd.Series(
            "",
            index=detail.index,
        )
    )

    return detail[
        path_group.eq("")
        | path_selected.eq(
            "TRUE"
        )
    ].copy()


def summarize_detail(
    detail: pd.DataFrame,
) -> dict[str, object]:
    counted = detail_counted_rows(
        detail
    )

    if counted.empty:
        return {
            "audit_status":
                "NO_DETAIL",
            "requirements_total":
                0,
            "requirements_met":
                0,
            "requirements_missing":
                0,
            "requirements_unresolved":
                0,
            "modeled_completion_term":
                "",
        }

    statuses = (
        counted[
            "status"
        ]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    total = len(
        counted
    )

    met = int(
        statuses.eq(
            "MET"
        ).sum()
    )

    unresolved = int(
        statuses.str.startswith(
            "UNRESOLVED"
        ).sum()
    )

    missing = (
        total
        - met
        - unresolved
    )

    if unresolved > 0:
        audit_status = (
            "REVIEW_UNRESOLVED"
        )
    elif missing == 0:
        audit_status = "COMPLETE"
    elif missing <= 2:
        audit_status = "NEAR_COMPLETE"
    else:
        audit_status = "INCOMPLETE"

    completion_terms = pd.to_numeric(
        counted.loc[
            statuses.eq(
                "MET"
            ),
            "latest_matched_term_sort",
        ],
        errors="coerce",
    )

    completion_term = (
        str(
            int(
                completion_terms.max()
            )
        )
        if completion_terms.notna().any()
        else ""
    )

    return {
        "audit_status":
            audit_status,
        "requirements_total":
            total,
        "requirements_met":
            met,
        "requirements_missing":
            missing,
        "requirements_unresolved":
            unresolved,
        "modeled_completion_term":
            completion_term,
    }


def split_semicolon(
    value: object,
) -> list[str]:
    raw = txt(
        value
    )

    if not raw:
        return []

    return [
        part.strip()
        for part in raw.split(
            ";"
        )
        if part.strip()
    ]


def extract_allocations(
    detail: pd.DataFrame,
) -> pd.DataFrame:
    counted = detail_counted_rows(
        detail
    )

    counted = counted[
        counted[
            "status"
        ]
        .fillna("")
        .astype(str)
        .str.upper()
        .eq(
            "MET"
        )
    ].copy()

    rows = []

    for row in counted.itertuples(
        index=False
    ):
        courses = [
            engine.normalize_course_code(
                value
            )
            for value in split_semicolon(
                getattr(
                    row,
                    "matched_options",
                    "",
                )
            )
        ]

        courses = [
            course
            for course in courses
            if course
        ]

        grades = [
            txt(
                value
            ).upper()
            for value in split_semicolon(
                getattr(
                    row,
                    "matched_grades",
                    "",
                )
            )
        ]

        terms = split_semicolon(
            getattr(
                row,
                "matched_terms",
                "",
            )
        )

        term_sorts = split_semicolon(
            getattr(
                row,
                "matched_term_sorts",
                "",
            )
        )

        for index, course in enumerate(
            courses
        ):
            rows.append(
                {
                    "student_id":
                        txt(
                            getattr(
                                row,
                                "student_id",
                                "",
                            )
                        ),
                    "catalog_year":
                        txt(
                            getattr(
                                row,
                                "catalog_year",
                                "",
                            )
                        ),
                    "credential_id":
                        txt(
                            getattr(
                                row,
                                "credential_id",
                                "",
                            )
                        ),
                    "requirement_id":
                        txt(
                            getattr(
                                row,
                                "requirement_id",
                                "",
                            )
                        ),
                    "course":
                        course,
                    "matched_grade":
                        (
                            grades[
                                index
                            ]
                            if index
                            < len(
                                grades
                            )
                            else ""
                        ),
                    "matched_term":
                        (
                            terms[
                                index
                            ]
                            if index
                            < len(
                                terms
                            )
                            else ""
                        ),
                    "matched_term_sort":
                        (
                            term_sorts[
                                index
                            ]
                            if index
                            < len(
                                term_sorts
                            )
                            else ""
                        ),
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "student_id",
                "catalog_year",
                "credential_id",
                "requirement_id",
                "course",
                "matched_grade",
                "matched_term",
                "matched_term_sort",
            ]
        )

    return (
        pd.DataFrame(
            rows
        )
        .sort_values(
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "course",
                "requirement_id",
            ]
        )
        .drop_duplicates(
            [
                "student_id",
                "catalog_year",
                "credential_id",
                "course",
            ],
            keep="first",
        )
    )


def main() -> None:
    stage1_dir = latest_dir(
        "second_associate_stage1_current_*",
        "RESTRICTED_second_associate_stage2_pending.csv",
    )

    awardability_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_current_attempt_state_candidate_students.csv",
    )

    stage1_path = (
        stage1_dir
        / "RESTRICTED_second_associate_stage2_pending.csv"
    )

    attempts_path = (
        awardability_dir
        / "RESTRICTED_current_attempt_state_candidate_students.csv"
    )

    for path in [
        stage1_path,
        attempts_path,
        REQUIREMENTS,
        CORE_LOOKUP,
        ACADEMIC_CROSSWALK,
        ELECTIVE_RULES,
        COMPOUND,
        ALT_PATHS,
        CROSSWALK,
        ELIGIBILITY_SCRIPT,
    ]:
        if not path.exists():
            raise FileNotFoundError(
                path
            )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    pending = pd.read_csv(
        stage1_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    if len(
        pending
    ) != EXPECTED_PENDING:
        raise RuntimeError(
            "Stage-2 pending universe changed: "
            f"{len(pending):,} != "
            f"{EXPECTED_PENDING:,}"
        )

    if not pending[
        "stage1_decision"
    ].eq(
        "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
    ).all():
        raise RuntimeError(
            "Pending file contains a non-pending Stage-1 decision."
        )

    if pending.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Pending universe is not unique at candidate key."
        )

    attempts = pd.read_csv(
        attempts_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_attempts = {
        "student_id",
        "course_code",
        "final_grade",
        "term_sort",
        "term_taken",
    }

    missing = (
        required_attempts
        - set(
            attempts.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Current attempt state missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    attempts[
        "term_sort"
    ] = pd.to_numeric(
        attempts[
            "term_sort"
        ],
        errors="coerce",
    )

    attempts = attempts[
        attempts[
            "term_sort"
        ].notna()
    ].copy()

    attempts[
        "term_sort"
    ] = attempts[
        "term_sort"
    ].astype(
        int
    )

    attempts[
        "course_code"
    ] = attempts[
        "course_code"
    ].map(
        engine.normalize_course_code
    )

    attempts[
        "_grade"
    ] = (
        attempts[
            "final_grade"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # ------------------------------------------------------------------
    # Configure the committed path-aware engine to the validated six-year
    # staging package instead of its older default support paths.
    # ------------------------------------------------------------------
    engine.CORE_LOOKUP = (
        CORE_LOOKUP
    )

    engine.ACADEMIC_COURSE_CROSSWALK = (
        ACADEMIC_CROSSWALK
    )

    engine.ELECTIVE_RULES = (
        ELECTIVE_RULES
    )

    engine.COMPOUND_REQUIREMENT_ALTERNATIVES = (
        COMPOUND
    )

    engine.ALTERNATIVE_REQUIREMENT_PATHS = (
        ALT_PATHS
    )

    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    core_lookup = (
        engine.load_core_lookup()
    )

    elective_rules = (
        engine.load_elective_rules()
    )

    academic_course_lookup = (
        engine.load_academic_course_lookup()
    )

    compound_alternatives = (
        engine.load_compound_requirement_alternatives()
    )

    alternative_paths = (
        engine.load_alternative_requirement_paths()
    )

    engine.validate_alternative_requirement_paths(
        alternative_paths,
        requirements,
    )

    alternative_path_lookup = (
        engine.build_alternative_path_lookup(
            alternative_paths
        )
    )

    eligibility_module = (
        load_eligibility_module()
    )

    catalog_years = sorted(
        requirements[
            "catalog_year"
        ]
        .astype(str)
        .unique()
    )

    # ------------------------------------------------------------------
    # Build credential_id -> canonical lineage for every six-year plan.
    # ------------------------------------------------------------------
    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    if not {
        "credential_id",
        "canonical_lineage",
    }.issubset(
        modeled.columns
    ):
        raise RuntimeError(
            "Modeled Inventory missing credential_id/canonical_lineage."
        )

    modeled[
        "credential_id_norm"
    ] = modeled[
        "credential_id"
    ].map(
        norm
    )

    modeled[
        "canonical_lineage_norm"
    ] = modeled[
        "canonical_lineage"
    ].map(
        canonicalize
    )

    modeled_map = (
        modeled[
            [
                "credential_id_norm",
                "canonical_lineage_norm",
            ]
        ]
        .drop_duplicates(
            "credential_id_norm"
        )
        .set_index(
            "credential_id_norm"
        )[
            "canonical_lineage_norm"
        ]
        .to_dict()
    )

    credential_inventory = (
        requirements[
            [
                "catalog_year",
                "credential_id",
                "credential_title",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    credential_inventory[
        "credential_id_norm"
    ] = credential_inventory[
        "credential_id"
    ].map(
        norm
    )

    credential_inventory[
        "canonical_lineage"
    ] = [
        CREDENTIAL_LINEAGE_OVERRIDES.get(
            credential_id,
            modeled_map.get(
                credential_id,
                "",
            ),
        )
        for credential_id in credential_inventory[
            "credential_id_norm"
        ]
    ]

    credential_inventory[
        "canonical_lineage"
    ] = credential_inventory[
        "canonical_lineage"
    ].map(
        canonicalize
    )

    # Every first-prior family in the pending universe must have at least
    # one modeled credential version after explicit identity repairs.
    pending_families = sorted(
        set(
            pending[
                "first_prior_family"
            ].map(
                canonicalize
            )
        )
    )

    missing_families = [
        family
        for family in pending_families
        if not credential_inventory[
            "canonical_lineage"
        ].eq(
            family
        ).any()
    ]

    if missing_families:
        raise RuntimeError(
            "No modeled six-year credential found for first-prior families: "
            + " | ".join(
                missing_families
            )
        )

    plan_rows = []
    detail_parts = []
    allocation_parts = []

    target_students = sorted(
        set(
            pending[
                "student_id"
            ].astype(str)
        )
    )

    print(
        f"Pending candidate combinations: {len(pending):,}"
    )
    print(
        f"Unique students:                {len(target_students):,}"
    )

    for case_number, case in enumerate(
        pending.itertuples(
            index=False
        ),
        start=1,
    ):
        student_id = txt(
            case.student_id
        )

        prior_family = canonicalize(
            case.first_prior_family
        )

        prior_term = pd.to_numeric(
            pd.Series(
                [
                    case.first_prior_grad_term
                ]
            ),
            errors="coerce",
        ).iloc[
            0
        ]

        if pd.isna(
            prior_term
        ):
            raise RuntimeError(
                "Modern Stage-2 case has blank/non-numeric first prior "
                "graduation term."
            )

        prior_term = int(
            prior_term
        )

        student_attempts = attempts[
            attempts[
                "student_id"
            ].astype(str).eq(
                student_id
            )
            & attempts[
                "term_sort"
            ].le(
                prior_term
            )
        ].copy()

        if student_attempts.empty:
            raise RuntimeError(
                "No attempt history exists through first prior award term "
                f"for one Stage-2 candidate."
            )

        # Canonical V2 eligibility on history truncated at the award term.
        activity = student_attempts[
            [
                "student_id",
                "term_sort",
                "final_grade",
            ]
        ].copy()

        activity[
            "is_passing"
        ] = (
            activity[
                "final_grade"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(
                PASSING_GRADES
            )
        )

        eligibility = (
            eligibility_module.build_student_catalog_eligibility(
                activity_history=activity,
                catalog_years=catalog_years,
            )
        )

        eligible_catalogs = set(
            eligibility.loc[
                eligibility[
                    "catalog_eligible"
                ].astype(
                    bool
                ),
                "catalog_year",
            ].astype(str)
        )

        candidate_plans = credential_inventory[
            credential_inventory[
                "canonical_lineage"
            ].eq(
                prior_family
            )
            & credential_inventory[
                "catalog_year"
            ].astype(str).isin(
                eligible_catalogs
            )
        ].copy()

        if candidate_plans.empty:
            plan_rows.append(
                {
                    "student_id":
                        student_id,
                    "target_catalog_year":
                        txt(
                            case.catalog_year
                        ),
                    "target_credential_id":
                        txt(
                            case.credential_id
                        ),
                    "first_prior_family":
                        prior_family,
                    "first_prior_degree_code":
                        txt(
                            case.first_prior_degree_code
                        ),
                    "first_prior_grad_term":
                        prior_term,
                    "prior_catalog_year":
                        "",
                    "prior_credential_id":
                        "",
                    "prior_credential_title":
                        "",
                    "eligibility_basis":
                        "NO_ELIGIBLE_PRIOR_FAMILY_PLAN",
                    "audit_status":
                        "NO_PLAN",
                    "requirements_total":
                        0,
                    "requirements_met":
                        0,
                    "requirements_missing":
                        0,
                    "requirements_unresolved":
                        0,
                    "modeled_completion_term":
                        "",
                }
            )

            continue

        # Build successful-course view AS OF prior award term.
        course_state = student_attempts[
            [
                "course_code",
                "term_taken",
                "term_sort",
                "final_grade",
            ]
        ].copy()

        course_state[
            "grade"
        ] = course_state[
            "final_grade"
        ]

        course_state[
            "passed"
        ] = (
            course_state[
                "final_grade"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(
                PASSING_GRADES
            )
            .map(
                {
                    True:
                        "TRUE",
                    False:
                        "FALSE",
                }
            )
        )

        course_lookup = (
            engine.completed_course_lookup(
                course_state[
                    [
                        "course_code",
                        "term_taken",
                        "term_sort",
                        "grade",
                        "passed",
                    ]
                ]
            )
        )

        for plan in candidate_plans.itertuples(
            index=False
        ):
            catalog_year = txt(
                plan.catalog_year
            )

            credential_id = txt(
                plan.credential_id
            )

            credential_requirements = requirements[
                requirements[
                    "catalog_year"
                ].astype(str).eq(
                    catalog_year
                )
                & requirements[
                    "credential_id"
                ].astype(str).eq(
                    credential_id
                )
            ].copy()

            if credential_requirements.empty:
                raise RuntimeError(
                    "Candidate prior plan has no requirements rows."
                )

            detail_rows = (
                engine.audit_student_credential(
                    student_id=student_id,
                    catalog_year=catalog_year,
                    credential_id=credential_id,
                    credential_requirements=credential_requirements,
                    course_lookup=course_lookup,
                    core_lookup=core_lookup,
                    elective_rules=elective_rules,
                    academic_course_lookup=academic_course_lookup,
                    compound_alternatives=compound_alternatives,
                    alternative_path_lookup=alternative_path_lookup,
                )
            )

            detail = pd.DataFrame(
                detail_rows
            )

            summary = summarize_detail(
                detail
            )

            plan_rows.append(
                {
                    "student_id":
                        student_id,
                    "target_catalog_year":
                        txt(
                            case.catalog_year
                        ),
                    "target_credential_id":
                        txt(
                            case.credential_id
                        ),
                    "first_prior_family":
                        prior_family,
                    "first_prior_degree_code":
                        txt(
                            case.first_prior_degree_code
                        ),
                    "first_prior_grad_term":
                        prior_term,
                    "prior_catalog_year":
                        catalog_year,
                    "prior_credential_id":
                        credential_id,
                    "prior_credential_title":
                        txt(
                            plan.credential_title
                        ),
                    "eligibility_basis":
                        "CANONICAL_V2_AS_OF_FIRST_PRIOR_AWARD_TERM",
                    **summary,
                }
            )

            detail[
                "target_catalog_year"
            ] = txt(
                case.catalog_year
            )

            detail[
                "target_credential_id"
            ] = txt(
                case.credential_id
            )

            detail[
                "first_prior_family"
            ] = prior_family

            detail[
                "first_prior_grad_term"
            ] = prior_term

            detail_parts.append(
                detail
            )

            if summary[
                "audit_status"
            ] == "COMPLETE":
                allocated = extract_allocations(
                    detail
                )

                if not allocated.empty:
                    allocated[
                        "target_catalog_year"
                    ] = txt(
                        case.catalog_year
                    )

                    allocated[
                        "target_credential_id"
                    ] = txt(
                        case.credential_id
                    )

                    allocated[
                        "first_prior_family"
                    ] = prior_family

                    allocated[
                        "first_prior_grad_term"
                    ] = prior_term

                    allocation_parts.append(
                        allocated
                    )

        if (
            case_number % 10 == 0
            or case_number
            == len(
                pending
            )
        ):
            print(
                "Reconstructed cases: "
                f"{case_number:,}/{len(pending):,}"
            )

    plans = pd.DataFrame(
        plan_rows
    )

    detail_out = (
        pd.concat(
            detail_parts,
            ignore_index=True,
        )
        if detail_parts
        else pd.DataFrame()
    )

    alloc_out = (
        pd.concat(
            allocation_parts,
            ignore_index=True,
        )
        if allocation_parts
        else pd.DataFrame()
    )

    plans.to_csv(
        RESTRICTED_PLAN_OUT,
        index=False,
    )

    detail_out.to_csv(
        RESTRICTED_DETAIL_OUT,
        index=False,
    )

    alloc_out.to_csv(
        RESTRICTED_ALLOC_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # Coverage by original candidate key.
    # ------------------------------------------------------------------
    complete = plans[
        plans[
            "audit_status"
        ].eq(
            "COMPLETE"
        )
    ].copy()

    candidate_key_columns = [
        "student_id",
        "target_catalog_year",
        "target_credential_id",
    ]

    complete_counts = (
        complete.groupby(
            candidate_key_columns
        )
        .size()
        .rename(
            "complete_prior_plan_count"
        )
        .reset_index()
    )

    coverage = pending[
        [
            "student_id",
            "catalog_year",
            "credential_id",
            "first_prior_family",
            "first_prior_degree_code",
            "first_prior_grad_term",
        ]
    ].rename(
        columns={
            "catalog_year":
                "target_catalog_year",
            "credential_id":
                "target_credential_id",
        }
    )

    coverage = coverage.merge(
        complete_counts,
        on=candidate_key_columns,
        how="left",
        validate="one_to_one",
    )

    coverage[
        "complete_prior_plan_count"
    ] = pd.to_numeric(
        coverage[
            "complete_prior_plan_count"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    covered = int(
        coverage[
            "complete_prior_plan_count"
        ].gt(
            0
        ).sum()
    )

    uncovered = (
        len(
            coverage
        )
        - covered
    )

    multi = int(
        coverage[
            "complete_prior_plan_count"
        ].gt(
            1
        ).sum()
    )

    plausible_safe = (
        coverage.groupby(
            [
                "first_prior_family",
                "first_prior_degree_code",
                "complete_prior_plan_count",
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
        )
        .reset_index()
        .sort_values(
            [
                "complete_prior_plan_count",
                "candidate_combinations",
            ],
            ascending=[
                True,
                False,
            ],
        )
    )

    plausible_safe.to_csv(
        SAFE_PLAUSIBLE_OUT,
        index=False,
    )

    family_safe = (
        plans.groupby(
            [
                "first_prior_family",
                "first_prior_degree_code",
                "prior_catalog_year",
                "prior_credential_id",
                "audit_status",
            ],
            dropna=False,
        )
        .agg(
            plan_tests=(
                "student_id",
                "size",
            ),
            distinct_students=(
                "student_id",
                "nunique",
            ),
            min_requirements_missing=(
                "requirements_missing",
                "min",
            ),
            max_requirements_missing=(
                "requirements_missing",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "first_prior_family",
                "prior_catalog_year",
                "prior_credential_id",
                "audit_status",
            ]
        )
    )

    family_safe.to_csv(
        SAFE_FAMILY_OUT,
        index=False,
    )

    gap_keys = set(
        coverage.loc[
            coverage[
                "complete_prior_plan_count"
            ].eq(
                0
            ),
            candidate_key_columns,
        ].itertuples(
            index=False,
            name=None,
        )
    )

    if gap_keys:
        plan_key_tuples = list(
            plans[
                candidate_key_columns
            ].itertuples(
                index=False,
                name=None,
            )
        )

        gap_mask = [
            key in gap_keys
            for key in plan_key_tuples
        ]

        gaps = plans.loc[
            gap_mask
        ].copy()

        if not gaps.empty:
            gaps[
                "requirements_missing"
            ] = pd.to_numeric(
                gaps[
                    "requirements_missing"
                ],
                errors="coerce",
            )

            min_missing = (
                gaps.groupby(
                    candidate_key_columns
                )[
                    "requirements_missing"
                ]
                .transform(
                    "min"
                )
            )

            gaps = gaps[
                gaps[
                    "requirements_missing"
                ].eq(
                    min_missing
                )
            ].copy()

            gaps_safe = (
                gaps.groupby(
                    [
                        "first_prior_family",
                        "first_prior_degree_code",
                        "prior_catalog_year",
                        "prior_credential_id",
                        "audit_status",
                        "requirements_missing",
                        "requirements_unresolved",
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
                )
                .reset_index()
                .sort_values(
                    [
                        "requirements_missing",
                        "candidate_combinations",
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )
            )
        else:
            gaps_safe = pd.DataFrame()
    else:
        gaps_safe = pd.DataFrame()

    gaps_safe.to_csv(
        SAFE_GAPS_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "modern_stage2_pending_candidates",
                "value":
                    len(
                        pending
                    ),
            },
            {
                "metric":
                    "prior_plan_tests_executed",
                "value":
                    len(
                        plans
                    ),
            },
            {
                "metric":
                    "complete_prior_plan_tests",
                "value":
                    len(
                        complete
                    ),
            },
            {
                "metric":
                    "candidates_with_at_least_one_complete_prior_plan",
                "value":
                    covered,
            },
            {
                "metric":
                    "candidates_with_zero_complete_prior_plan",
                "value":
                    uncovered,
            },
            {
                "metric":
                    "candidates_with_multiple_complete_prior_plans",
                "value":
                    multi,
            },
            {
                "metric":
                    "reconstructed_complete_prior_allocation_rows",
                "value":
                    len(
                        alloc_out
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 112)
    print("MODERN SECOND-ASSOCIATE PRIOR-PLAN RECONSTRUCTION")
    print("=" * 112)
    print(
        f"Stage-2 pending candidates:                    {len(pending):,}"
    )
    print(
        f"Prior-plan audits executed:                    {len(plans):,}"
    )
    print(
        f"COMPLETE prior-plan audits:                    {len(complete):,}"
    )
    print(
        "Candidates with >=1 COMPLETE prior plan:      "
        f"{covered:,}"
    )
    print(
        "Candidates with zero COMPLETE prior plan:     "
        f"{uncovered:,}"
    )
    print(
        "Candidates with multiple COMPLETE prior plans:"
        f" {multi:,}"
    )
    print(
        "COMPLETE prior-plan allocated course rows:    "
        f"{len(alloc_out):,}"
    )
    print()
    print("PLAUSIBLE PRIOR-PLAN COUNTS")
    print(
        plausible_safe.to_string(
            index=False
        )
    )
    print()
    if gaps_safe.empty:
        print("RECONSTRUCTION GAPS: 0")
    else:
        print("BEST AVAILABLE NON-COMPLETE PRIOR PLAN(S) FOR GAPS")
        print(
            gaps_safe.to_string(
                index=False
            )
        )
    print()
    print(
        "Control: transcript was truncated at the first official "
        "associate award term before eligibility and audit reconstruction."
    )
    print(
        "Control: catalog eligibility used the canonical V2 segmentation "
        "implementation."
    )
    print(
        "Control: no Stage-2 second-associate PASS/FAIL decision was made."
    )
    print()
    print(
        f"Stage-1 source:        {stage1_dir}"
    )
    print(
        f"Current attempt source:{awardability_dir}"
    )
    print(
        f"Output directory:      {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
