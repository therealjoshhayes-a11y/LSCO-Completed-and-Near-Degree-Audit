from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# GENERALIZED SECOND-ASSOCIATE — STAGE 1
# ======================================================================================
#
# Current population:
#   365 candidate combinations routed to SECOND_ASSOCIATE_TEST_PENDING.
#
# This stage makes ONLY the decisions that can be made without reconstructing the
# first prior degree's allocated course set.
#
# OLD RULE (< 2025 catalog):
#   Required earned college-level SCH =
#       max(candidate degree hours, first prior associate degree hours) + 15
#
#   Earned SCH follows the recovered old implementation:
#     * passing grades / passed credit only;
#     * college-level 4-digit courses only (exclude 0xxx);
#     * one earned-credit count per student/course;
#     * Texas course-number second digit supplies SCH when no explicit hours exist.
#
# NEW RULE (2025+ catalog):
#   * if the candidate's exact associate degree code has already been awarded
#     (e.g., AA when an AA already exists), FAIL_SAME_DEGREE_TYPE;
#   * otherwise route to Stage 2 for the "15 hours beyond the first degree plan,
#     completed in residence at LSCO with GPA >= 2.0" test.
#
# Source-backed program-hour repairs used ONLY for prior-degree threshold metadata:
#   REGISTERED_NURSING_AAS = 60 SCH
#     - LSCO catalogs identify Registered Nursing AAS / Transition as 60-hour plans.
#   TEACHER_EDUCATION_AAT = 60 SCH
#     - 2025-2026 catalog identifies Teacher Education AAT as 60 hours.
#
# This script does NOT:
#   * reconstruct the prior degree course allocation;
#   * run the Stage-2 unique-resident/GPA test;
#   * adjudicate additional certificates;
#   * perform latest-catalog lineage selection.
#
# Run from repository root:
#   python -u .\scripts\adjudicate_second_associate_stage1_current.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_SECOND_ASSOCIATE = 365

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

COURSE_RE = re.compile(
    r"\b([A-Z]{2,5})\s*[- ]?\s*(\d{4})\b",
    re.I,
)

CROSSWALK = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "award_program_crosswalk_curated.xlsx"
)

REQUIREMENTS = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "staging_six_year"
    / "requirements_master_multiyear.csv"
)

# Source-backed corrections for prior-degree PLAN HOURS only.
PRIOR_PROGRAM_HOUR_OVERRIDES = {
    "REGISTERED_NURSING_AAS": 60.0,
    "TEACHER_EDUCATION_AAT": 60.0,
}

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"second_associate_stage1_current_{STAMP}"
)

DETAIL_OUT = (
    OUT_DIR
    / "RESTRICTED_second_associate_stage1_current.csv"
)

PENDING_OUT = (
    OUT_DIR
    / "RESTRICTED_second_associate_stage2_pending.csv"
)

SAFE_DECISIONS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage1_decisions.csv"
)

SAFE_OLD_OUT = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_old_rule_sch.csv"
)

SAFE_MODERN_OUT = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_modern_stage1.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_stage1_metrics.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


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


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm(value: object) -> str:
    return txt(value).upper().replace(" ", "_")


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


def normalize_course(value: object) -> str:
    match = COURSE_RE.search(
        txt(value).upper()
    )

    if not match:
        return ""

    return (
        f"{match.group(1).upper()} "
        f"{match.group(2)}"
    )


def derive_sch(course_code: object) -> float:
    """
    Port of the recovered old Stage-1 convention:
    Texas 4-digit course numbering => second digit is SCH.
    """
    match = COURSE_RE.search(
        txt(course_code).upper()
    )

    if not match:
        return 0.0

    number = match.group(2)

    try:
        return float(
            number[1]
        )
    except Exception:
        return 0.0


def catalog_start_year(
    value: object,
) -> int | None:
    value = txt(value)

    try:
        return int(
            value[:4]
        )
    except Exception:
        return None


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


def joined(values) -> str:
    return " | ".join(
        sorted(
            {
                txt(value)
                for value in values
                if txt(value)
            }
        )
    )


def build_prior_program_hours() -> pd.DataFrame:
    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    needed = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "sequence",
        "credit_hours",
    }

    missing = (
        needed
        - set(
            requirements.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Requirements missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    requirements[
        "credit_hours_numeric"
    ] = pd.to_numeric(
        requirements[
            "credit_hours"
        ],
        errors="coerce",
    )

    inventory = (
        requirements.sort_values(
            [
                "catalog_year",
                "credential_id",
                "requirement_id",
                "sequence",
            ]
        )
        .drop_duplicates(
            [
                "catalog_year",
                "credential_id",
                "requirement_id",
            ]
        )
        .groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            as_index=False,
        )
        .agg(
            program_hours=(
                "credit_hours_numeric",
                "sum",
            ),
        )
    )

    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    required_modeled = {
        "credential_id",
        "canonical_lineage",
    }

    missing = (
        required_modeled
        - set(
            modeled.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Modeled Inventory missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
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

    inventory[
        "credential_id_norm"
    ] = inventory[
        "credential_id"
    ].map(
        norm
    )

    inventory = inventory.merge(
        modeled[
            [
                "credential_id_norm",
                "canonical_lineage_norm",
            ]
        ]
        .drop_duplicates(
            "credential_id_norm"
        ),
        on="credential_id_norm",
        how="left",
        validate="many_to_one",
    )

    inventory[
        "canonical_lineage_norm"
    ] = inventory[
        "canonical_lineage_norm"
    ].fillna("")

    rows = []

    for lineage, group in inventory[
        inventory[
            "canonical_lineage_norm"
        ].ne("")
    ].groupby(
        "canonical_lineage_norm",
        sort=False,
    ):
        values = sorted(
            {
                float(
                    value
                )
                for value in group[
                    "program_hours"
                ]
                if pd.notna(
                    value
                )
            }
        )

        rows.append(
            {
                "first_prior_family":
                    lineage,
                "prior_program_hour_values":
                    " | ".join(
                        f"{value:g}"
                        for value in values
                    ),
                "prior_program_hour_variant_count":
                    len(
                        values
                    ),
                "prior_program_hours":
                    (
                        values[0]
                        if len(
                            values
                        ) == 1
                        else pd.NA
                    ),
                "prior_program_hours_basis":
                    (
                        "STABLE_SIX_YEAR_FAMILY_HOURS"
                        if len(
                            values
                        ) == 1
                        else (
                            "FAMILY_HOURS_VARY_BY_CATALOG"
                            if values
                            else "NO_MODELED_HOURS"
                        )
                    ),
            }
        )

    result = pd.DataFrame(
        rows
    )

    # Source-backed repairs.
    for lineage, hours in (
        PRIOR_PROGRAM_HOUR_OVERRIDES.items()
    ):
        mask = result[
            "first_prior_family"
        ].eq(
            lineage
        )

        if mask.any():
            result.loc[
                mask,
                "prior_program_hours",
            ] = hours

            result.loc[
                mask,
                "prior_program_hours_basis",
            ] = (
                "DIRECT_CATALOG_SOURCE_OVERRIDE"
            )

            result.loc[
                mask,
                "prior_program_hour_values",
            ] = f"{hours:g}"

            result.loc[
                mask,
                "prior_program_hour_variant_count",
            ] = 1

        else:
            result = pd.concat(
                [
                    result,
                    pd.DataFrame(
                        [
                            {
                                "first_prior_family":
                                    lineage,
                                "prior_program_hour_values":
                                    f"{hours:g}",
                                "prior_program_hour_variant_count":
                                    1,
                                "prior_program_hours":
                                    hours,
                                "prior_program_hours_basis":
                                    "DIRECT_CATALOG_SOURCE_OVERRIDE",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    return result


def main() -> None:
    closed_dir = latest_dir(
        "closed_cross_lineage_governance_*",
        "RESTRICTED_closed_cross_lineage_governance_candidates.csv",
    )

    pair_dir = closed_dir

    current_awardability_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_current_attempt_state_candidate_students.csv",
    )

    candidate_path = (
        closed_dir
        / "RESTRICTED_closed_cross_lineage_governance_candidates.csv"
    )

    pair_path = (
        pair_dir
        / "RESTRICTED_closed_cross_lineage_governance_pairs.csv"
    )

    attempts_path = (
        current_awardability_dir
        / "RESTRICTED_current_attempt_state_candidate_students.csv"
    )

    for path in [
        candidate_path,
        pair_path,
        attempts_path,
        CROSSWALK,
        REQUIREMENTS,
    ]:
        if not path.exists():
            raise FileNotFoundError(
                path
            )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    candidates = pd.read_csv(
        candidate_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    pairs = pd.read_csv(
        pair_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    attempts = pd.read_csv(
        attempts_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    target = candidates[
        candidates[
            "multiple_award_route"
        ].eq(
            "SECOND_ASSOCIATE_TEST_PENDING"
        )
    ].copy()

    if len(
        target
    ) != EXPECTED_SECOND_ASSOCIATE:
        raise RuntimeError(
            "Second-associate universe changed: "
            f"{len(target):,} != "
            f"{EXPECTED_SECOND_ASSOCIATE:,}"
        )

    if target.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Second-associate universe is not unique at candidate key."
        )

    target[
        "catalog_start_year"
    ] = target[
        "catalog_year"
    ].map(
        catalog_start_year
    )

    target[
        "rule_regime"
    ] = target[
        "catalog_start_year"
    ].map(
        lambda year: (
            "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
            if (
                year is not None
                and year < 2025
            )
            else (
                "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
                if (
                    year is not None
                    and year >= 2025
                )
                else "REVIEW_CATALOG_RULE"
            )
        )
    )

    # ------------------------------------------------------------------
    # Official associate inventory and FIRST prior associate.
    # ------------------------------------------------------------------
    target_keys = set(
        target[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    pair_keys = list(
        pairs[
            KEY
        ].itertuples(
            index=False,
            name=None,
        )
    )

    pairs[
        "_is_target"
    ] = [
        key in target_keys
        for key in pair_keys
    ]

    assoc = pairs[
        pairs[
            "_is_target"
        ]
        & pairs[
            "has_official_award"
        ].map(
            truthy
        )
        & pairs[
            "official_award_category"
        ].eq(
            "ASSOCIATE"
        )
    ].copy()

    if assoc.empty:
        raise RuntimeError(
            "No official associate awards found for second-associate universe."
        )

    assoc[
        "official_family"
    ] = assoc[
        "official_family"
    ].map(
        canonicalize
    )

    assoc[
        "_term_num"
    ] = pd.to_numeric(
        assoc[
            "official_grad_term"
        ],
        errors="coerce",
    )

    assoc[
        "_program_sort"
    ] = assoc[
        "official_program_code"
    ].astype(
        str
    )

    official_awards = (
        assoc[
            [
                "student_id",
                "official_family",
                "official_degree_code",
                "official_program_code",
                "official_major_code",
                "official_grad_term",
                "_term_num",
                "_program_sort",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    first_prior = (
        official_awards.sort_values(
            [
                "student_id",
                "_term_num",
                "_program_sort",
            ],
            kind="mergesort",
            na_position="last",
        )
        .drop_duplicates(
            "student_id",
            keep="first",
        )
        .rename(
            columns={
                "official_family":
                    "first_prior_family",
                "official_degree_code":
                    "first_prior_degree_code",
                "official_program_code":
                    "first_prior_program_code",
                "official_major_code":
                    "first_prior_major_code",
                "official_grad_term":
                    "first_prior_grad_term",
            }
        )
    )

    prior_degree_sets = (
        official_awards.groupby(
            "student_id"
        )[
            "official_degree_code"
        ]
        .agg(
            lambda values: sorted(
                {
                    txt(
                        value
                    ).upper()
                    for value in values
                    if txt(
                        value
                    )
                }
            )
        )
        .to_dict()
    )

    target = target.merge(
        first_prior[
            [
                "student_id",
                "first_prior_family",
                "first_prior_degree_code",
                "first_prior_program_code",
                "first_prior_major_code",
                "first_prior_grad_term",
            ]
        ],
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    for column in [
        "first_prior_family",
        "first_prior_degree_code",
        "first_prior_program_code",
        "first_prior_major_code",
        "first_prior_grad_term",
    ]:
        target[
            column
        ] = target[
            column
        ].fillna("")

    target[
        "all_prior_associate_degree_codes"
    ] = target[
        "student_id"
    ].map(
        lambda student_id: " | ".join(
            prior_degree_sets.get(
                student_id,
                [],
            )
        )
    )

    # Preserve the recovered Stage-1 semantics: compare the candidate's exact
    # degree code to the FIRST prior associate award. Do not broaden this policy
    # test here without separate catalog/governance review.
    target[
        "same_exact_degree_type_already_awarded"
    ] = [
        (
            txt(
                candidate_code
            ).upper()
            == txt(
                first_prior_code
            ).upper()
        )
        if txt(
            candidate_code
        )
        else False
        for (
            candidate_code,
            first_prior_code,
        )
        in target[
            [
                "candidate_exact_degree_code",
                "first_prior_degree_code",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    # ------------------------------------------------------------------
    # Current total PASSED COLLEGE-LEVEL SCH.
    # ------------------------------------------------------------------
    required_attempt_columns = {
        "student_id",
        "course_code",
        "final_grade",
    }

    missing = (
        required_attempt_columns
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
        "_course"
    ] = attempts[
        "course_code"
    ].map(
        normalize_course
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

    attempts[
        "_passed"
    ] = attempts[
        "_grade"
    ].isin(
        PASSING_GRADES
    )

    attempts[
        "_course_number"
    ] = (
        attempts[
            "_course"
        ]
        .str.extract(
            r"(\d{4})$",
            expand=False,
        )
        .fillna("")
    )

    attempts[
        "_college_level"
    ] = (
        attempts[
            "_course_number"
        ].str.len().eq(
            4
        )
        & ~attempts[
            "_course_number"
        ].str.startswith(
            "0"
        )
    )

    explicit_hours_col = next(
        (
            column
            for column in [
                "earned_hours",
                "credit_hours",
                "semester_hours",
                "sch",
            ]
            if column in attempts.columns
        ),
        None,
    )

    if explicit_hours_col:
        attempts[
            "_hours"
        ] = pd.to_numeric(
            attempts[
                explicit_hours_col
            ],
            errors="coerce",
        )
    else:
        attempts[
            "_hours"
        ] = pd.NA

    attempts[
        "_hours"
    ] = attempts[
        "_hours"
    ].fillna(
        attempts[
            "_course"
        ].map(
            derive_sch
        )
    )

    target_students = set(
        target[
            "student_id"
        ].astype(str)
    )

    passed = attempts[
        attempts[
            "student_id"
        ].astype(str).isin(
            target_students
        )
        & attempts[
            "_passed"
        ]
        & attempts[
            "_college_level"
        ]
        & attempts[
            "_course"
        ].ne("")
    ].copy()

    earned_by_course = (
        passed.groupby(
            [
                "student_id",
                "_course",
            ],
            dropna=False,
        )[
            "_hours"
        ]
        .max()
        .reset_index()
    )

    earned_totals = (
        earned_by_course.groupby(
            "student_id"
        )[
            "_hours"
        ]
        .sum()
        .rename(
            "total_passed_college_sch"
        )
        .reset_index()
    )

    target = target.merge(
        earned_totals,
        on="student_id",
        how="left",
        validate="many_to_one",
    )

    target[
        "total_passed_college_sch"
    ] = pd.to_numeric(
        target[
            "total_passed_college_sch"
        ],
        errors="coerce",
    ).fillna(
        0.0
    )

    # ------------------------------------------------------------------
    # Prior degree program-hour evidence.
    # ------------------------------------------------------------------
    prior_hours = (
        build_prior_program_hours()
    )

    target = target.merge(
        prior_hours,
        on="first_prior_family",
        how="left",
        validate="many_to_one",
    )

    for column in [
        "prior_program_hour_values",
        "prior_program_hours_basis",
    ]:
        target[
            column
        ] = target[
            column
        ].fillna("")

    target[
        "prior_program_hours"
    ] = pd.to_numeric(
        target[
            "prior_program_hours"
        ],
        errors="coerce",
    )

    target[
        "candidate_program_hours_numeric"
    ] = pd.to_numeric(
        target[
            "awardability_program_hours"
        ],
        errors="coerce",
    )

    target[
        "old_rule_required_total_sch"
    ] = pd.NA

    old_mask = target[
        "rule_regime"
    ].eq(
        "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
    )

    old_resolved = (
        old_mask
        & target[
            "candidate_program_hours_numeric"
        ].notna()
        & target[
            "prior_program_hours"
        ].notna()
    )

    target.loc[
        old_resolved,
        "old_rule_required_total_sch",
    ] = [
        max(
            float(
                candidate_hours
            ),
            float(
                prior_hours_value
            ),
        )
        + 15.0
        for (
            candidate_hours,
            prior_hours_value,
        )
        in target.loc[
            old_resolved,
            [
                "candidate_program_hours_numeric",
                "prior_program_hours",
            ],
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    target[
        "old_rule_required_total_sch"
    ] = pd.to_numeric(
        target[
            "old_rule_required_total_sch"
        ],
        errors="coerce",
    )

    # ------------------------------------------------------------------
    # Stage-1 decisions.
    # ------------------------------------------------------------------
    target[
        "stage1_decision"
    ] = "REVIEW"

    target[
        "stage1_reason"
    ] = ""

    target[
        "stage1_evidence_basis"
    ] = ""

    # Old rule.
    unresolved_old = (
        old_mask
        & target[
            "old_rule_required_total_sch"
        ].isna()
    )

    if unresolved_old.any():
        bad = target.loc[
            unresolved_old,
            [
                "catalog_year",
                "credential_id",
                "first_prior_family",
                "first_prior_degree_code",
                "prior_program_hour_values",
                "prior_program_hours_basis",
            ],
        ].drop_duplicates()

        raise RuntimeError(
            "Old-rule program-hour threshold remains unresolved after "
            "source-backed overrides:\n"
            + bad.to_string(
                index=False
            )
        )

    old_pass = (
        old_mask
        & target[
            "total_passed_college_sch"
        ].ge(
            target[
                "old_rule_required_total_sch"
            ]
        )
    )

    old_fail = (
        old_mask
        & ~old_pass
    )

    target.loc[
        old_pass,
        "stage1_decision",
    ] = "PASS_SECOND_ASSOCIATE_RULE"

    target.loc[
        old_pass,
        "stage1_reason",
    ] = (
        "Completed at least 15 college-level SCH above the greater "
        "of the candidate and first-prior associate degree requirements."
    )

    target.loc[
        old_pass,
        "stage1_evidence_basis",
    ] = (
        "CURRENT_PASSED_COLLEGE_SCH_PLUS_SOURCE_BACKED_PROGRAM_HOURS"
    )

    target.loc[
        old_fail,
        "stage1_decision",
    ] = "FAIL_SECOND_ASSOCIATE_RULE"

    target.loc[
        old_fail,
        "stage1_reason",
    ] = (
        "Fewer than 15 college-level SCH above the greater "
        "of the candidate and first-prior associate degree requirements."
    )

    target.loc[
        old_fail,
        "stage1_evidence_basis",
    ] = (
        "CURRENT_PASSED_COLLEGE_SCH_PLUS_SOURCE_BACKED_PROGRAM_HOURS"
    )

    # New rule.
    new_mask = target[
        "rule_regime"
    ].eq(
        "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
    )

    unresolved_new_code = (
        new_mask
        & target[
            "candidate_exact_degree_code"
        ].eq("")
    )

    if unresolved_new_code.any():
        raise RuntimeError(
            "Modern second-associate candidate has unresolved exact degree code."
        )

    same_type = (
        new_mask
        & target[
            "same_exact_degree_type_already_awarded"
        ]
    )

    different_type = (
        new_mask
        & ~target[
            "same_exact_degree_type_already_awarded"
        ]
    )

    target.loc[
        same_type,
        "stage1_decision",
    ] = "FAIL_SAME_DEGREE_TYPE"

    target.loc[
        same_type,
        "stage1_reason",
    ] = (
        "The candidate's exact associate degree type has already been awarded."
    )

    target.loc[
        same_type,
        "stage1_evidence_basis",
    ] = (
        "OFFICIAL_ASSOCIATE_AWARD_HISTORY"
    )

    target.loc[
        different_type,
        "stage1_decision",
    ] = (
        "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
    )

    target.loc[
        different_type,
        "stage1_reason",
    ] = (
        "Different associate type; must test at least 15 additional "
        "resident LSCO SCH beyond the first associate degree plan with "
        "GPA >= 2.0."
    )

    target.loc[
        different_type,
        "stage1_evidence_basis",
    ] = (
        "OFFICIAL_FIRST_ASSOCIATE_PLUS_STAGE2_REQUIRED"
    )

    if target[
        "stage1_decision"
    ].eq(
        "REVIEW"
    ).any():
        review = target[
            target[
                "stage1_decision"
            ].eq(
                "REVIEW"
            )
        ]

        raise RuntimeError(
            "Stage-1 left unresolved cases:\n"
            + review[
                [
                    "catalog_year",
                    "credential_id",
                    "rule_regime",
                    "first_prior_family",
                    "first_prior_degree_code",
                ]
            ]
            .drop_duplicates()
            .to_string(
                index=False
            )
        )

    # ------------------------------------------------------------------
    # Outputs.
    # ------------------------------------------------------------------
    target.to_csv(
        DETAIL_OUT,
        index=False,
    )

    pending = target[
        target[
            "stage1_decision"
        ].eq(
            "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"
        )
    ].copy()

    pending.to_csv(
        PENDING_OUT,
        index=False,
    )

    decisions = (
        target.groupby(
            [
                "catalog_year",
                "rule_regime",
                "stage1_decision",
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
                "catalog_year",
                "stage1_decision",
            ]
        )
    )

    decisions.to_csv(
        SAFE_DECISIONS_OUT,
        index=False,
    )

    old_safe = (
        target[
            old_mask
        ]
        .groupby(
            [
                "stage1_decision",
                "old_rule_required_total_sch",
                "prior_program_hours_basis",
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
            min_total_passed_college_sch=(
                "total_passed_college_sch",
                "min",
            ),
            median_total_passed_college_sch=(
                "total_passed_college_sch",
                "median",
            ),
            max_total_passed_college_sch=(
                "total_passed_college_sch",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "candidate_combinations",
            ascending=False,
        )
    )

    old_safe.to_csv(
        SAFE_OLD_OUT,
        index=False,
    )

    modern_safe = (
        target[
            new_mask
        ]
        .groupby(
            [
                "candidate_exact_degree_code",
                "all_prior_associate_degree_codes",
                "first_prior_degree_code",
                "first_prior_family",
                "stage1_decision",
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
            "candidate_combinations",
            ascending=False,
        )
    )

    modern_safe.to_csv(
        SAFE_MODERN_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "second_associate_stage1_candidates",
                "value":
                    len(
                        target
                    ),
            },
            {
                "metric":
                    "old_rule_candidates",
                "value":
                    int(
                        old_mask.sum()
                    ),
            },
            {
                "metric":
                    "old_rule_pass",
                "value":
                    int(
                        (
                            old_mask
                            & target[
                                "stage1_decision"
                            ].eq(
                                "PASS_SECOND_ASSOCIATE_RULE"
                            )
                        ).sum()
                    ),
            },
            {
                "metric":
                    "old_rule_fail",
                "value":
                    int(
                        (
                            old_mask
                            & target[
                                "stage1_decision"
                            ].eq(
                                "FAIL_SECOND_ASSOCIATE_RULE"
                            )
                        ).sum()
                    ),
            },
            {
                "metric":
                    "modern_rule_candidates",
                "value":
                    int(
                        new_mask.sum()
                    ),
            },
            {
                "metric":
                    "modern_same_degree_type_fail",
                "value":
                    int(
                        target[
                            "stage1_decision"
                        ].eq(
                            "FAIL_SAME_DEGREE_TYPE"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "modern_stage2_pending",
                "value":
                    len(
                        pending
                    ),
            },
            {
                "metric":
                    "old_rule_source_backed_prior_hour_override_rows",
                "value":
                    int(
                        (
                            old_mask
                            & target[
                                "prior_program_hours_basis"
                            ].eq(
                                "DIRECT_CATALOG_SOURCE_OVERRIDE"
                            )
                        ).sum()
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS_OUT,
        index=False,
    )

    print("=" * 112)
    print("GENERALIZED SECOND-ASSOCIATE — STAGE 1 COMPLETE")
    print("=" * 112)
    print(
        f"Candidate combinations:                 {len(target):,}"
    )
    print()
    print("OLD RULE")
    print(
        f"  Candidates:                           {int(old_mask.sum()):,}"
    )
    print(
        "  PASS_SECOND_ASSOCIATE_RULE:            "
        f"{int((old_mask & target['stage1_decision'].eq('PASS_SECOND_ASSOCIATE_RULE')).sum()):,}"
    )
    print(
        "  FAIL_SECOND_ASSOCIATE_RULE:            "
        f"{int((old_mask & target['stage1_decision'].eq('FAIL_SECOND_ASSOCIATE_RULE')).sum()):,}"
    )
    print(
        "  Source-backed prior-hour overrides:    "
        f"{int((old_mask & target['prior_program_hours_basis'].eq('DIRECT_CATALOG_SOURCE_OVERRIDE')).sum()):,}"
    )
    print()
    print("2025+ RULE")
    print(
        f"  Candidates:                           {int(new_mask.sum()):,}"
    )
    print(
        "  FAIL_SAME_DEGREE_TYPE:                 "
        f"{int(target['stage1_decision'].eq('FAIL_SAME_DEGREE_TYPE').sum()):,}"
    )
    print(
        "  NEEDS_15_UNIQUE_RESIDENT_SCH_TEST:     "
        f"{len(pending):,}"
    )
    print()
    print("DECISIONS BY CATALOG")
    print(
        decisions.to_string(
            index=False
        )
    )
    print()
    print("OLD-RULE SCH DISTRIBUTION")
    print(
        old_safe.to_string(
            index=False
        )
    )
    print()
    print("MODERN STAGE-1 ROUTES")
    print(
        modern_safe.to_string(
            index=False
        )
    )
    print()
    print(
        "Control: no Stage-2 prior-plan overlap test was performed."
    )
    print(
        "Control: Fall 2026 blank grades remain non-passing because this stage "
        "uses the already-normalized current attempt state from ordinary awardability."
    )
    print()
    print(
        f"Candidate source:       {closed_dir}"
    )
    print(
        f"Current attempt source: {current_awardability_dir}"
    )
    print(
        f"Output directory:       {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
