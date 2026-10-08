from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# SECOND-ASSOCIATE FIRST-PRIOR / PROGRAM-HOURS PREFLIGHT
# ======================================================================================
#
# Why this exists:
#   The historical full-audit cache did NOT reconstruct a prior COMPLETE modeled
#   plan for most official associate awards. Therefore the generalized rule must
#   not depend on prior modeled completion as a universal prerequisite.
#
# This probe answers the narrower questions actually needed next:
#
#   OLD RULE (< 2025):
#     * What is the FIRST prior official associate award?
#     * What degree type / canonical family was it?
#     * Is the prior family's program-hour requirement stable and recoverable
#       from the six-year catalog requirement inventory?
#     * What threshold would therefore be testable:
#           max(candidate program hours, prior program hours) + 15
#
#   NEW RULE (2025+):
#     * Does ANY prior official associate have the same exact degree code as the
#       candidate? (For the current modern universe, candidate = AA.)
#     * If not, what is the FIRST prior associate family whose plan must be used
#       for the 15 unique resident SCH / GPA test?
#     * Is that prior family represented by one or more modeled catalog plans?
#
# This script does NOT adjudicate any student.
# It emits FERPA-safe summaries only.
#
# Run:
#   python -u .\scripts\probe_second_associate_first_prior.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_SECOND_ASSOCIATE = 365

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

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = (
    REPORTING
    / f"second_associate_first_prior_preflight_{STAMP}"
)

SAFE_METRICS = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_first_prior_metrics.csv"
)

SAFE_FIRST_PRIOR = (
    OUT_DIR
    / "FERPA_SAFE_second_associate_first_prior_families.csv"
)

SAFE_OLD_HOURS = (
    OUT_DIR
    / "FERPA_SAFE_old_rule_prior_program_hours.csv"
)

SAFE_MODERN = (
    OUT_DIR
    / "FERPA_SAFE_modern_second_associate_paths.csv"
)

SAFE_TERMS = (
    OUT_DIR
    / "FERPA_SAFE_first_prior_grad_terms.csv"
)

SAFE_UNMAPPED_SEARCH = (
    OUT_DIR
    / "FERPA_SAFE_unmapped_prior_family_catalog_candidates.csv"
)


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


def numeric(value: object):
    value = txt(value)
    if not value:
        return pd.NA

    return pd.to_numeric(
        pd.Series(
            [value]
        ),
        errors="coerce",
    ).iloc[0]


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


def main() -> None:
    closed_dir = latest_dir(
        "closed_cross_lineage_governance_*",
        "RESTRICTED_closed_cross_lineage_governance_candidates.csv",
    )

    candidate_path = (
        closed_dir
        / "RESTRICTED_closed_cross_lineage_governance_candidates.csv"
    )

    pair_path = (
        closed_dir
        / "RESTRICTED_closed_cross_lineage_governance_pairs.csv"
    )

    for path in [
        candidate_path,
        pair_path,
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
    # Candidate × official associate award rows.
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
            "No official associate awards found."
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

    # One copy of each official award per student. Candidate rows may repeat the
    # same official award across several candidate catalog versions.
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

    # FIRST prior associate: same deterministic strategy as recovered old stage1.
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
            lambda s: sorted(
                {
                    txt(
                        value
                    ).upper()
                    for value in s
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

    target[
        "same_exact_degree_type_already_awarded"
    ] = [
        (
            txt(
                candidate_code
            ).upper()
            in prior_degree_sets.get(
                student_id,
                [],
            )
        )
        if txt(
            candidate_code
        )
        else False
        for (
            student_id,
            candidate_code,
        )
        in target[
            [
                "student_id",
                "candidate_exact_degree_code",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    # ------------------------------------------------------------------
    # Build catalog program-hour inventory using the SAME requirement-hour
    # calculation convention used by the old awardability screen:
    # one row per requirement_id, then sum credit_hours.
    # ------------------------------------------------------------------
    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "catalog_year",
        "credential_id",
        "credential_title",
        "requirement_id",
        "sequence",
        "credit_hours",
    }

    missing = (
        required_columns
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

    requirement_inventory = (
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
        .copy()
    )

    program_hours = (
        requirement_inventory.groupby(
            [
                "catalog_year",
                "credential_id",
            ],
            as_index=False,
        )
        .agg(
            credential_title=(
                "credential_title",
                "first",
            ),
            program_hours=(
                "credit_hours_numeric",
                "sum",
            ),
        )
    )

    # ------------------------------------------------------------------
    # Modeled Inventory maps credential versions to canonical lineage.
    # ------------------------------------------------------------------
    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    modeled_required = {
        "credential_id",
        "canonical_lineage",
    }

    missing = (
        modeled_required
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

    program_hours[
        "credential_id_norm"
    ] = program_hours[
        "credential_id"
    ].map(
        norm
    )

    program_hours = program_hours.merge(
        modeled[
            [
                "credential_id_norm",
                "canonical_lineage_norm",
            ]
        ].drop_duplicates(
            "credential_id_norm"
        ),
        on="credential_id_norm",
        how="left",
        validate="many_to_one",
    )

    program_hours[
        "canonical_lineage_norm"
    ] = program_hours[
        "canonical_lineage_norm"
    ].fillna("")

    family_hours = (
        program_hours[
            program_hours[
                "canonical_lineage_norm"
            ].ne("")
        ]
        .groupby(
            "canonical_lineage_norm"
        )
        .agg(
            modeled_credential_versions=(
                "credential_id",
                lambda s: joined(
                    s
                ),
            ),
            catalog_years=(
                "catalog_year",
                lambda s: joined(
                    s
                ),
            ),
            program_hour_values=(
                "program_hours",
                lambda s: " | ".join(
                    sorted(
                        {
                            f"{float(value):g}"
                            for value in s
                            if pd.notna(
                                value
                            )
                        }
                    )
                ),
            ),
            program_hour_variant_count=(
                "program_hours",
                lambda s: len(
                    {
                        float(
                            value
                        )
                        for value in s
                        if pd.notna(
                            value
                        )
                    }
                ),
            ),
            stable_program_hours=(
                "program_hours",
                lambda s: (
                    next(
                        iter(
                            {
                                float(
                                    value
                                )
                                for value in s
                                if pd.notna(
                                    value
                                )
                            }
                        )
                    )
                    if len(
                        {
                            float(
                                value
                            )
                            for value in s
                            if pd.notna(
                                value
                            )
                        }
                    ) == 1
                    else pd.NA
                ),
            ),
        )
        .reset_index()
        .rename(
            columns={
                "canonical_lineage_norm":
                    "first_prior_family",
            }
        )
    )

    target = target.merge(
        family_hours,
        on="first_prior_family",
        how="left",
        validate="many_to_one",
    )

    for column in [
        "modeled_credential_versions",
        "catalog_years",
        "program_hour_values",
    ]:
        target[
            column
        ] = target[
            column
        ].fillna("")

    target[
        "program_hour_variant_count"
    ] = pd.to_numeric(
        target[
            "program_hour_variant_count"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    target[
        "stable_program_hours"
    ] = pd.to_numeric(
        target[
            "stable_program_hours"
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
        "old_rule_threshold_if_resolved"
    ] = pd.NA

    old_resolvable = (
        target[
            "rule_regime"
        ].eq(
            "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
        )
        & target[
            "candidate_program_hours_numeric"
        ].notna()
        & target[
            "stable_program_hours"
        ].notna()
    )

    target.loc[
        old_resolvable,
        "old_rule_threshold_if_resolved",
    ] = [
        max(
            candidate_hours,
            prior_hours,
        )
        + 15.0
        for (
            candidate_hours,
            prior_hours,
        )
        in target.loc[
            old_resolvable,
            [
                "candidate_program_hours_numeric",
                "stable_program_hours",
            ],
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    target[
        "old_rule_program_hours_status"
    ] = "NOT_APPLICABLE"

    old_mask = target[
        "rule_regime"
    ].eq(
        "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
    )

    target.loc[
        old_mask
        & target[
            "stable_program_hours"
        ].notna(),
        "old_rule_program_hours_status",
    ] = "RESOLVED_STABLE_SIX_YEAR_FAMILY_HOURS"

    target.loc[
        old_mask
        & target[
            "stable_program_hours"
        ].isna()
        & target[
            "program_hour_variant_count"
        ].gt(
            1
        ),
        "old_rule_program_hours_status",
    ] = "REVIEW_FAMILY_PROGRAM_HOURS_VARY_BY_CATALOG"

    target.loc[
        old_mask
        & target[
            "program_hour_variant_count"
        ].eq(
            0
        ),
        "old_rule_program_hours_status",
    ] = "REVIEW_PRIOR_FAMILY_NOT_IN_MODELED_INVENTORY"

    # ------------------------------------------------------------------
    # FERPA-safe outputs.
    # ------------------------------------------------------------------
    first_prior_safe = (
        target.groupby(
            [
                "rule_regime",
                "first_prior_degree_code",
                "first_prior_family",
                "program_hour_values",
                "program_hour_variant_count",
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

    first_prior_safe.to_csv(
        SAFE_FIRST_PRIOR,
        index=False,
    )

    old_safe = (
        target[
            old_mask
        ]
        .groupby(
            [
                "first_prior_degree_code",
                "first_prior_family",
                "candidate_program_hours_numeric",
                "program_hour_values",
                "old_rule_program_hours_status",
                "old_rule_threshold_if_resolved",
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

    old_safe.to_csv(
        SAFE_OLD_HOURS,
        index=False,
    )

    modern = target[
        target[
            "rule_regime"
        ].eq(
            "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
        )
    ].copy()

    modern[
        "modern_stage1_route"
    ] = "NEEDS_FIRST_PRIOR_PLAN_OVERLAP_TEST"

    modern.loc[
        modern[
            "same_exact_degree_type_already_awarded"
        ],
        "modern_stage1_route",
    ] = "SAME_DEGREE_TYPE_ALREADY_AWARDED"

    modern.loc[
        ~modern[
            "same_exact_degree_type_already_awarded"
        ]
        & modern[
            "first_prior_family"
        ].eq(""),
        "modern_stage1_route",
    ] = "REVIEW_FIRST_PRIOR_ASSOCIATE_UNRESOLVED"

    modern.loc[
        ~modern[
            "same_exact_degree_type_already_awarded"
        ]
        & modern[
            "first_prior_family"
        ].ne("")
        & modern[
            "program_hour_variant_count"
        ].eq(
            0
        ),
        "modern_stage1_route",
    ] = "FIRST_PRIOR_FAMILY_NOT_IN_MODELED_INVENTORY"

    modern_safe = (
        modern.groupby(
            [
                "candidate_exact_degree_code",
                "same_exact_degree_type_already_awarded",
                "first_prior_degree_code",
                "first_prior_family",
                "program_hour_values",
                "modern_stage1_route",
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
        SAFE_MODERN,
        index=False,
    )

    terms_safe = (
        target.groupby(
            [
                "rule_regime",
                "first_prior_grad_term",
                "first_prior_degree_code",
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
                "rule_regime",
                "first_prior_grad_term",
            ]
        )
    )

    terms_safe.to_csv(
        SAFE_TERMS,
        index=False,
    )

    # ------------------------------------------------------------------
    # Search the requirement inventory itself for likely credentials behind
    # currently unmapped prior families. This is source inventory only.
    # ------------------------------------------------------------------
    unmapped_families = sorted(
        {
            family
            for family in target[
                "first_prior_family"
            ]
            if (
                family
                and family
                not in set(
                    family_hours[
                        "first_prior_family"
                    ]
                )
            )
        }
    )

    requirement_credential_inventory = (
        program_hours[
            [
                "catalog_year",
                "credential_id",
                "credential_title",
                "program_hours",
                "canonical_lineage_norm",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    search_mask = pd.Series(
        False,
        index=requirement_credential_inventory.index,
    )

    for column in [
        "credential_id",
        "credential_title",
        "canonical_lineage_norm",
    ]:
        text_col = (
            requirement_credential_inventory[
                column
            ]
            .astype(str)
            .str.upper()
        )

        for token in [
            "NURS",
            "REGISTERED",
            "RN",
            "TEACH",
            "AAT",
            "EDUCATION",
        ]:
            search_mask |= text_col.str.contains(
                token,
                regex=False,
                na=False,
            )

    search_results = (
        requirement_credential_inventory[
            search_mask
        ]
        .sort_values(
            [
                "catalog_year",
                "credential_id",
            ]
        )
    )

    search_results.to_csv(
        SAFE_UNMAPPED_SEARCH,
        index=False,
    )

    old_count = int(
        old_mask.sum()
    )

    old_hours_resolved = int(
        target[
            "old_rule_program_hours_status"
        ].eq(
            "RESOLVED_STABLE_SIX_YEAR_FAMILY_HOURS"
        ).sum()
    )

    modern_same_type = int(
        modern[
            "same_exact_degree_type_already_awarded"
        ].sum()
    )

    modern_overlap_ready = int(
        modern[
            "modern_stage1_route"
        ].eq(
            "NEEDS_FIRST_PRIOR_PLAN_OVERLAP_TEST"
        ).sum()
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "second_associate_candidates",
                "value":
                    len(
                        target
                    ),
            },
            {
                "metric":
                    "old_rule_candidates",
                "value":
                    old_count,
            },
            {
                "metric":
                    "old_rule_program_hours_resolved_from_stable_family",
                "value":
                    old_hours_resolved,
            },
            {
                "metric":
                    "old_rule_program_hours_review",
                "value":
                    old_count
                    - old_hours_resolved,
            },
            {
                "metric":
                    "modern_rule_candidates",
                "value":
                    len(
                        modern
                    ),
            },
            {
                "metric":
                    "modern_same_exact_degree_type_already_awarded",
                "value":
                    modern_same_type,
            },
            {
                "metric":
                    "modern_needs_first_prior_plan_overlap_test",
                "value":
                    modern_overlap_ready,
            },
            {
                "metric":
                    "modern_first_prior_family_not_in_modeled_inventory",
                "value":
                    int(
                        modern[
                            "modern_stage1_route"
                        ].eq(
                            "FIRST_PRIOR_FAMILY_NOT_IN_MODELED_INVENTORY"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "first_prior_family_unmapped_to_program_hours_count",
                "value":
                    len(
                        unmapped_families
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("SECOND-ASSOCIATE FIRST-PRIOR / PROGRAM-HOURS PREFLIGHT")
    print("=" * 112)
    print(
        f"Second-associate candidates:                    {len(target):,}"
    )
    print(
        f"Old-rule candidates:                            {old_count:,}"
    )
    print(
        "Old-rule prior hours resolved (stable family): "
        f"{old_hours_resolved:,}"
    )
    print(
        "Old-rule prior hours still REVIEW:             "
        f"{old_count - old_hours_resolved:,}"
    )
    print()
    print(
        f"Modern-rule candidates:                         {len(modern):,}"
    )
    print(
        "Modern same exact degree type already awarded: "
        f"{modern_same_type:,}"
    )
    print(
        "Modern needing first-plan overlap test:        "
        f"{modern_overlap_ready:,}"
    )
    print(
        "Modern first-prior family absent from model:   "
        f"{int(modern['modern_stage1_route'].eq('FIRST_PRIOR_FAMILY_NOT_IN_MODELED_INVENTORY').sum()):,}"
    )
    print()
    print("FIRST PRIOR FAMILY SUMMARY")
    print(
        first_prior_safe.to_string(
            index=False
        )
    )
    print()
    print("OLD-RULE PROGRAM-HOUR READINESS")
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
    print("FIRST PRIOR GRAD TERMS")
    print(
        terms_safe.to_string(
            index=False
        )
    )
    print()
    print("CATALOG CREDENTIALS RELEVANT TO UNMAPPED PRIOR FAMILIES")
    if search_results.empty:
        print("NONE")
    else:
        print(
            search_results.to_string(
                index=False
            )
        )
    print()
    print(
        "No second-associate decision was made."
    )
    print(
        "This probe intentionally does not require a historical modeled COMPLETE "
        "audit for an official prior award."
    )
    print()
    print(
        f"Source: {closed_dir}"
    )
    print(
        f"Output directory: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
