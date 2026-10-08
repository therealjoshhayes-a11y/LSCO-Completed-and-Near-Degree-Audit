from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# SECOND-ASSOCIATE GENERALIZATION PREFLIGHT
# ======================================================================================
#
# Purpose:
#   Before generalizing the old Liberal-Arts/AAT1 second-associate scripts to the
#   current 365-candidate universe, verify that the current data products support
#   the same evidence model:
#
#     current candidate
#       -> prior official associate award(s)
#       -> canonical prior lineage
#       -> plausible COMPLETE modeled prior plan(s)
#       -> exact candidate/prior degree-type identity
#       -> plan-hours source for the old rule
#
# This script is FERPA-safe in its console and SAFE outputs. It does not adjudicate
# any second-associate case and emits no student IDs in safe products.
#
# Run from repo root:
#   python -u .\scripts\probe_generalized_second_associate_inputs.py


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
OUT_DIR = REPORTING / f"second_associate_generalization_preflight_{STAMP}"

SAFE_METRICS = OUT_DIR / "FERPA_SAFE_second_associate_preflight_metrics.csv"
SAFE_REGIME = OUT_DIR / "FERPA_SAFE_second_associate_rule_regimes.csv"
SAFE_PRIOR = OUT_DIR / "FERPA_SAFE_second_associate_prior_awards.csv"
SAFE_MAPPING = OUT_DIR / "FERPA_SAFE_second_associate_prior_lineage_mapping.csv"
SAFE_PLAUSIBLE = OUT_DIR / "FERPA_SAFE_second_associate_plausible_prior_audits.csv"
SAFE_HOUR_COLUMNS = OUT_DIR / "FERPA_SAFE_requirement_hour_columns.csv"
SAFE_EXACT_CODES = OUT_DIR / "FERPA_SAFE_modern_second_associate_degree_codes.csv"


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
    return CANONICAL_ALIASES.get(value, value)


def truthy(value: object) -> bool:
    return txt(value).upper() in {
        "TRUE", "T", "YES", "Y", "1", "ELIGIBLE",
    }


def numeric_term(value: object):
    value = txt(value)
    if not value:
        return pd.NA
    return pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]


def catalog_start_year(value: object) -> int | None:
    value = txt(value)
    try:
        return int(value[:4])
    except Exception:
        return None


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


def locate_empirical_summary() -> Path:
    exact = list(
        (ROOT / "data" / "processed").rglob(
            "RESTRICTED_current_eligible_empirical_credential_summary.csv"
        )
    )

    if exact:
        exact = sorted(
            exact,
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return exact[0]

    raise FileNotFoundError(
        "Could not find RESTRICTED_current_eligible_empirical_credential_summary.csv"
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

    empirical_path = locate_empirical_summary()

    for path in [
        candidate_path,
        pair_path,
        empirical_path,
        CROSSWALK,
        REQUIREMENTS,
    ]:
        if not path.exists():
            raise FileNotFoundError(path)

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

    if len(target) != EXPECTED_SECOND_ASSOCIATE:
        raise RuntimeError(
            "Second-associate universe changed: "
            f"{len(target):,} != {EXPECTED_SECOND_ASSOCIATE:,}"
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
        lambda y: (
            "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
            if y is not None and y < 2025
            else (
                "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
                if y is not None and y >= 2025
                else "REVIEW_CATALOG_RULE"
            )
        )
    )

    # ------------------------------------------------------------------
    # Current candidate x official associate awards
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

    prior = pairs[
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

    if prior.empty:
        raise RuntimeError(
            "No official associate awards found for second-associate targets."
        )

    prior[
        "official_family"
    ] = prior[
        "official_family"
    ].map(
        canonicalize
    )

    # ------------------------------------------------------------------
    # Modeled Inventory: canonical lineage -> modeled credential IDs
    # ------------------------------------------------------------------
    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    required_modeled = {
        "credential_id",
        "canonical_lineage",
    }

    missing = required_modeled - set(
        modeled.columns
    )

    if missing:
        raise RuntimeError(
            "Modeled Inventory missing: "
            + ", ".join(
                sorted(missing)
            )
        )

    modeled[
        "canonical_lineage"
    ] = modeled[
        "canonical_lineage"
    ].map(
        canonicalize
    )

    modeled[
        "credential_id"
    ] = modeled[
        "credential_id"
    ].map(
        norm
    )

    modeled = modeled[
        modeled[
            "canonical_lineage"
        ].ne("")
        & modeled[
            "credential_id"
        ].ne("")
    ].copy()

    family_to_credentials = (
        modeled.groupby(
            "canonical_lineage"
        )[
            "credential_id"
        ]
        .agg(
            lambda s: sorted(
                set(
                    x
                    for x in s
                    if x
                )
            )
        )
        .to_dict()
    )

    prior[
        "mapped_modeled_credential_ids"
    ] = prior[
        "official_family"
    ].map(
        lambda family: " | ".join(
            family_to_credentials.get(
                family,
                [],
            )
        )
    )

    prior[
        "modeled_lineage_mapping_status"
    ] = prior[
        "mapped_modeled_credential_ids"
    ].map(
        lambda value: (
            "MAPPED"
            if txt(value)
            else "UNMAPPED"
        )
    )

    # ------------------------------------------------------------------
    # Current empirical summary coverage for plausible prior plans.
    # ------------------------------------------------------------------
    empirical_header = pd.read_csv(
        empirical_path,
        nrows=0,
    ).columns.tolist()

    required_empirical = {
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
    }

    missing = required_empirical - set(
        empirical_header
    )

    if missing:
        raise RuntimeError(
            "Empirical summary missing: "
            + ", ".join(
                sorted(missing)
            )
        )

    empirical_usecols = [
        c
        for c in [
            "student_id",
            "catalog_year",
            "credential_id",
            "audit_status",
            "award_term_sort",
            "award_term_taken",
            "catalog_eligible",
            "result_provenance",
        ]
        if c in empirical_header
    ]

    target_students = set(
        target[
            "student_id"
        ].astype(str)
    )

    parts = []

    for chunk in pd.read_csv(
        empirical_path,
        dtype=str,
        usecols=empirical_usecols,
        chunksize=500_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        subset = chunk[
            chunk[
                "student_id"
            ].astype(str).isin(
                target_students
            )
        ].copy()

        if not subset.empty:
            parts.append(
                subset
            )

    empirical = (
        pd.concat(
            parts,
            ignore_index=True,
        )
        if parts
        else pd.DataFrame(
            columns=empirical_usecols
        )
    )

    empirical[
        "credential_id_norm"
    ] = empirical[
        "credential_id"
    ].map(
        norm
    )

    modeled_lookup = (
        modeled[
            [
                "credential_id",
                "canonical_lineage",
            ]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "credential_id":
                    "credential_id_norm",
                "canonical_lineage":
                    "empirical_lineage",
            }
        )
    )

    empirical = empirical.merge(
        modeled_lookup,
        on="credential_id_norm",
        how="left",
        validate="many_to_one",
    )

    empirical[
        "empirical_lineage"
    ] = empirical[
        "empirical_lineage"
    ].fillna("")

    if "catalog_eligible" in empirical.columns:
        eligible_text_present = (
            empirical[
                "catalog_eligible"
            ]
            .astype(str)
            .str.strip()
            .ne("")
            .any()
        )

        if eligible_text_present:
            empirical = empirical[
                empirical[
                    "catalog_eligible"
                ].map(
                    truthy
                )
            ].copy()

    empirical = empirical[
        empirical[
            "audit_status"
        ].astype(str).str.upper().eq(
            "COMPLETE"
        )
    ].copy()

    # ------------------------------------------------------------------
    # Pair-by-pair plausible-plan counts.
    # ------------------------------------------------------------------
    pair_rows = []

    for row in prior.itertuples(
        index=False
    ):
        student_id = txt(
            row.student_id
        )

        family = txt(
            row.official_family
        )

        official_term = numeric_term(
            getattr(
                row,
                "official_grad_term",
                "",
            )
        )

        possible = empirical[
            empirical[
                "student_id"
            ].eq(
                student_id
            )
            & empirical[
                "empirical_lineage"
            ].eq(
                family
            )
        ].copy()

        all_complete_count = len(
            possible
        )

        if (
            not possible.empty
            and "award_term_sort"
            in possible.columns
            and pd.notna(
                official_term
            )
        ):
            possible[
                "_award_term_num"
            ] = pd.to_numeric(
                possible[
                    "award_term_sort"
                ],
                errors="coerce",
            )

            on_time = possible[
                possible[
                    "_award_term_num"
                ].notna()
                & possible[
                    "_award_term_num"
                ].le(
                    official_term
                )
            ].copy()

            if not on_time.empty:
                possible = on_time
                timing_basis = (
                    "COMPLETE_MODELED_NO_LATER_THAN_OFFICIAL_AWARD_TERM"
                )
            else:
                timing_basis = (
                    "COMPLETE_MODELED_FOUND_BUT_NONE_NO_LATER_THAN_OFFICIAL_TERM"
                )
        else:
            timing_basis = (
                "OFFICIAL_OR_MODELED_AWARD_TERM_UNAVAILABLE"
            )

        pair_rows.append(
            {
                "candidate_catalog_year":
                    txt(
                        row.catalog_year
                    ),
                "candidate_credential_id":
                    txt(
                        row.credential_id
                    ),
                "candidate_exact_degree_code":
                    txt(
                        getattr(
                            row,
                            "candidate_exact_degree_code",
                            "",
                        )
                    ),
                "official_family":
                    family,
                "official_degree_code":
                    txt(
                        row.official_degree_code
                    ),
                "modeled_lineage_mapping_status":
                    txt(
                        row.modeled_lineage_mapping_status
                    ),
                "mapped_modeled_credential_ids":
                    txt(
                        row.mapped_modeled_credential_ids
                    ),
                "all_complete_modeled_prior_rows":
                    all_complete_count,
                "plausible_prior_rows_after_term_filter":
                    len(
                        possible
                    ),
                "plausible_prior_catalogs":
                    " | ".join(
                        sorted(
                            set(
                                txt(x)
                                for x in possible[
                                    "catalog_year"
                                ]
                                if txt(x)
                            )
                        )
                    ),
                "plausible_prior_credentials":
                    " | ".join(
                        sorted(
                            set(
                                txt(x)
                                for x in possible[
                                    "credential_id"
                                ]
                                if txt(x)
                            )
                        )
                    ),
                "prior_plan_timing_basis":
                    timing_basis,
            }
        )

    pair_eval = pd.DataFrame(
        pair_rows
    )

    # ------------------------------------------------------------------
    # Requirement schema probe for old-rule plan-hour source.
    # ------------------------------------------------------------------
    requirement_header = pd.read_csv(
        REQUIREMENTS,
        nrows=0,
    ).columns.tolist()

    hour_like = [
        col
        for col in requirement_header
        if any(
            token in col.lower()
            for token in [
                "hour",
                "sch",
                "credit",
                "total",
            ]
        )
    ]

    hour_frame = pd.DataFrame(
        {
            "column": hour_like,
        }
    )

    hour_frame.to_csv(
        SAFE_HOUR_COLUMNS,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe summaries.
    # ------------------------------------------------------------------
    regime = (
        target.groupby(
            [
                "catalog_year",
                "rule_regime",
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
    )

    regime.to_csv(
        SAFE_REGIME,
        index=False,
    )

    prior_safe = (
        prior.groupby(
            [
                "official_degree_code",
                "official_family",
                "modeled_lineage_mapping_status",
            ],
            dropna=False,
        )
        .agg(
            pair_rows=(
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
            "pair_rows",
            ascending=False,
        )
    )

    prior_safe.to_csv(
        SAFE_PRIOR,
        index=False,
    )

    mapping_safe = (
        pair_eval.groupby(
            [
                "official_family",
                "official_degree_code",
                "modeled_lineage_mapping_status",
                "mapped_modeled_credential_ids",
            ],
            dropna=False,
        )
        .agg(
            pair_rows=(
                "candidate_credential_id",
                "size",
            ),
            min_plausible_prior_rows=(
                "plausible_prior_rows_after_term_filter",
                "min",
            ),
            max_plausible_prior_rows=(
                "plausible_prior_rows_after_term_filter",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            "pair_rows",
            ascending=False,
        )
    )

    mapping_safe.to_csv(
        SAFE_MAPPING,
        index=False,
    )

    plausible_safe = (
        pair_eval.groupby(
            [
                "modeled_lineage_mapping_status",
                "prior_plan_timing_basis",
            ],
            dropna=False,
        )
        .agg(
            pair_rows=(
                "candidate_credential_id",
                "size",
            ),
            zero_plausible_prior_rows=(
                "plausible_prior_rows_after_term_filter",
                lambda s: int(
                    (
                        pd.to_numeric(
                            s,
                            errors="coerce",
                        ).fillna(0)
                        == 0
                    ).sum()
                ),
            ),
        )
        .reset_index()
    )

    plausible_safe.to_csv(
        SAFE_PLAUSIBLE,
        index=False,
    )

    modern = target[
        target[
            "rule_regime"
        ].eq(
            "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
        )
    ].copy()

    modern_safe = (
        modern.groupby(
            [
                "candidate_exact_degree_code",
                "candidate_exact_associate_degree_code_resolved",
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
    )

    modern_safe.to_csv(
        SAFE_EXACT_CODES,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "second_associate_candidates",
                "value": len(
                    target
                ),
            },
            {
                "metric": "old_rule_candidates",
                "value": int(
                    target[
                        "rule_regime"
                    ].eq(
                        "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
                    ).sum()
                ),
            },
            {
                "metric": "new_rule_candidates",
                "value": int(
                    target[
                        "rule_regime"
                    ].eq(
                        "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
                    ).sum()
                ),
            },
            {
                "metric": "official_associate_pair_rows",
                "value": len(
                    prior
                ),
            },
            {
                "metric": "unmapped_prior_official_family_pair_rows",
                "value": int(
                    prior[
                        "modeled_lineage_mapping_status"
                    ].eq(
                        "UNMAPPED"
                    ).sum()
                ),
            },
            {
                "metric": "prior_pairs_with_zero_plausible_complete_modeled_plan",
                "value": int(
                    (
                        pd.to_numeric(
                            pair_eval[
                                "plausible_prior_rows_after_term_filter"
                            ],
                            errors="coerce",
                        ).fillna(0)
                        == 0
                    ).sum()
                ),
            },
            {
                "metric": "modern_candidate_exact_degree_code_unresolved",
                "value": int(
                    (
                        modern[
                            "candidate_exact_degree_code"
                        ].eq("")
                    ).sum()
                ),
            },
            {
                "metric": "requirement_hour_like_column_count",
                "value": len(
                    hour_like
                ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("GENERALIZED SECOND-ASSOCIATE INPUT PREFLIGHT")
    print("=" * 112)
    print(
        f"Second-associate candidate combinations:       {len(target):,}"
    )
    print(
        "Old-rule candidates (<2025):                 "
        f"{int(target['rule_regime'].eq('OLD_15_ABOVE_GREATER_DEGREE_HOURS').sum()):,}"
    )
    print(
        "New-rule candidates (2025+):                 "
        f"{int(target['rule_regime'].eq('NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE').sum()):,}"
    )
    print(
        f"Official associate pair rows:                 {len(prior):,}"
    )
    print(
        "Unmapped prior official-family pair rows:     "
        f"{int(prior['modeled_lineage_mapping_status'].eq('UNMAPPED').sum()):,}"
    )
    print(
        "Prior pairs with zero plausible COMPLETE plan:"
        f" {int((pd.to_numeric(pair_eval['plausible_prior_rows_after_term_filter'], errors='coerce').fillna(0) == 0).sum()):,}"
    )
    print(
        "Modern candidate exact degree code unresolved:"
        f" {int(modern['candidate_exact_degree_code'].eq('').sum()):,}"
    )
    print()
    print("RULE REGIMES")
    print(
        regime.to_string(
            index=False
        )
    )
    print()
    print("PRIOR ASSOCIATE FAMILIES / MAPPING")
    print(
        prior_safe.to_string(
            index=False
        )
    )
    print()
    print("PLAUSIBLE PRIOR-AUDIT COVERAGE")
    print(
        plausible_safe.to_string(
            index=False
        )
    )
    print()
    print("MODERN CANDIDATE DEGREE CODES")
    if modern_safe.empty:
        print("NONE")
    else:
        print(
            modern_safe.to_string(
                index=False
            )
        )
    print()
    print("REQUIREMENTS HOUR-LIKE COLUMNS")
    if hour_like:
        for col in hour_like:
            print(f"  {col}")
    else:
        print("  NONE")
    print()
    print(
        "No second-associate decision was made."
    )
    print(
        "Next step after this preflight: port the old earned-SCH rule for "
        "pre-2025 candidates and the old every-plausible-prior-plan "
        "unique-resident/GPA test for 2025+ candidates."
    )
    print()
    print(
        f"Candidate source: {closed_dir}"
    )
    print(
        f"Empirical summary: {empirical_path}"
    )
    print(
        f"Output directory: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
