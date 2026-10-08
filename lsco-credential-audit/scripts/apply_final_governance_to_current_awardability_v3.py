from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# STEP 5A — APPLY FINAL GOVERNED AWARD RELATIONSHIPS TO CURRENT ORDINARY-PASS UNIVERSE
# ======================================================================================
#
# Purpose:
#   Correct the preliminary multiple-award ledger by applying the ACTUAL final
#   governed relationship table before any second-associate / additional-
#   certificate mathematics.
#
# Prior validated governance semantics:
#   CONSUMING = awarded_represents_detected == TRUE
#               AND detected_remains_additional_award == FALSE
#
# Precedence:
#   1. Any consuming official-award relationship => candidate represented.
#   2. Otherwise governed rows with remains_additional == TRUE are non-consuming.
#   3. IA official awards are mechanically non-consuming.
#   4. Any unmapped official lineage or ungoverned observed pair => REVIEW.
#
# Important:
#   A row with represents==TRUE AND remains_additional==TRUE is NOT consuming.
#   That is how the prior finalized code treated these relationships.
#
# This script does NOT:
#   * adjudicate second-associate hours;
#   * adjudicate the governed 25% additional-certificate rule;
#   * perform latest-catalog lineage selection.
#
# It also preserves official awards with blank suppression_family. Those awards
# still matter for same-level multiple-award routing even though their lineage
# relationship cannot be governed automatically.
#
# Run from repository root:
#   python -u .\scripts\apply_final_governance_to_current_awardability.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_ORDINARY_PASS = 1_108

FINAL_GOVERNANCE = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

CROSSWALK = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "award_program_crosswalk_curated.xlsx"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = (
    REPORTING
    / f"current_governed_dependency_screen_{RUN_STAMP}"
)

PAIR_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_candidate_official_governance_pairs.csv"
)

CANDIDATE_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_governed_dependency_candidates.csv"
)

SURVIVORS_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_governed_dependency_survivors.csv"
)

REPRESENTED_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_governed_dependency_represented.csv"
)

REVIEW_OUT = (
    OUTPUT_DIR
    / "RESTRICTED_current_governed_dependency_review.csv"
)

SAFE_METRICS = (
    OUTPUT_DIR
    / "FERPA_SAFE_current_governed_dependency_metrics.csv"
)

SAFE_ROUTE = (
    OUTPUT_DIR
    / "FERPA_SAFE_current_governed_dependency_routes.csv"
)

SAFE_PAIR_STATUS = (
    OUTPUT_DIR
    / "FERPA_SAFE_governance_pair_status_counts.csv"
)

SAFE_UNRESOLVED = (
    OUTPUT_DIR
    / "FERPA_SAFE_unresolved_governance_pairs.csv"
)

SAFE_METADATA = (
    OUTPUT_DIR
    / "FERPA_SAFE_candidate_award_metadata_status.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


# Canonical identity repairs recovered from the prior finalized local source.
# These are not inferred here.
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
    return (
        txt(value)
        .upper()
        .replace(" ", "_")
    )


def canonicalize_lineage(value: object) -> str:
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
    candidates = sorted(
        [
            path
            for path in REPORTING.glob(pattern)
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

    if not candidates:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return candidates[0]


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def official_category(
    degree_code: object,
) -> str:
    code = txt(
        degree_code
    ).upper()

    if code in {
        "AA",
        "AS",
        "AAS",
        "AAT",
    }:
        return "ASSOCIATE"

    if code.startswith(
        "CERT"
    ):
        return "CERTIFICATE"

    if code == "IA":
        return "INSTITUTIONAL_AWARD"

    if not code:
        return "UNRESOLVED"

    return "OTHER_OR_REVIEW"


def current_type_fallback(
    value: object,
) -> str:
    value = txt(
        value
    ).upper()

    if value == "ASSOCIATE":
        return "ASSOCIATE"

    if value == "CERT":
        return "CERTIFICATE_OR_IA"

    return "UNRESOLVED"


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


def build_candidate_metadata(
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resolve current modeled credential identity and award category.

    Prior architecture recovered from the local source:
      * modeled credentials are attached to canonical lineage;
      * official awards are separately mapped by
        Curr1ProgramCode + Major1Code + DegreeCode;
      * governance operates on canonical lineage.

    Therefore:
      1. use Modeled Inventory credential_id -> canonical_lineage when present;
      2. otherwise use the current credential_lineage after the exact historical
         alias repairs recovered from prior source;
      3. use Crosswalk Draft canonical-lineage rows only to infer award category
         and exact AA/AS/AAS/AAT code where unambiguous.
    """
    require(
        CROSSWALK
    )

    crosswalk = pd.read_excel(
        CROSSWALK,
        sheet_name="Crosswalk Draft",
        dtype=str,
    ).fillna("")

    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    required_crosswalk = {
        "canonical_lineage",
        "DegreeCode",
        "award_level",
    }

    missing = (
        required_crosswalk
        - set(
            crosswalk.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Crosswalk Draft missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

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

    # --------------------------------------------------------------
    # Modeled credential_id -> canonical lineage
    # --------------------------------------------------------------
    modeled = modeled.copy()

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
        canonicalize_lineage
    )

    modeled = modeled[
        modeled[
            "credential_id_norm"
        ].ne("")
        & modeled[
            "canonical_lineage_norm"
        ].ne("")
    ].copy()

    modeled_ambiguity = (
        modeled.groupby(
            "credential_id_norm"
        )[
            "canonical_lineage_norm"
        ]
        .nunique()
    )

    bad = modeled_ambiguity[
        modeled_ambiguity
        > 1
    ]

    if not bad.empty:
        raise RuntimeError(
            "Modeled Inventory maps credential_id to multiple canonical "
            f"lineages: {list(bad.index[:20])}"
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
    )

    # --------------------------------------------------------------
    # Crosswalk canonical lineage -> award category / degree code
    # --------------------------------------------------------------
    cw = crosswalk.copy()

    cw[
        "canonical_lineage_norm"
    ] = cw[
        "canonical_lineage"
    ].map(
        canonicalize_lineage
    )

    cw[
        "DegreeCode"
    ] = (
        cw[
            "DegreeCode"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    cw[
        "award_level"
    ] = (
        cw[
            "award_level"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    cw = cw[
        cw[
            "canonical_lineage_norm"
        ].ne("")
    ].copy()

    lineage_rows = []

    for lineage, group in cw.groupby(
        "canonical_lineage_norm",
        sort=False,
    ):
        degree_codes = sorted(
            {
                txt(value).upper()
                for value in group[
                    "DegreeCode"
                ]
                if txt(value)
            }
        )

        award_levels = sorted(
            {
                txt(value).upper()
                for value in group[
                    "award_level"
                ]
                if txt(value)
            }
        )

        categories = {
            official_category(
                code
            )
            for code in degree_codes
        }

        categories.discard(
            "UNRESOLVED"
        )

        categories.discard(
            "OTHER_OR_REVIEW"
        )

        if len(
            categories
        ) == 1:
            category = next(
                iter(
                    categories
                )
            )
            category_basis = (
                "CROSSWALK_CANONICAL_LINEAGE_DEGREE_CODE"
            )
        else:
            level_text = " | ".join(
                award_levels
            )

            if "ASSOCIATE" in level_text:
                category = "ASSOCIATE"
                category_basis = (
                    "CROSSWALK_CANONICAL_LINEAGE_AWARD_LEVEL"
                )

            elif (
                "CERT" in level_text
                and "INSTITUTIONAL" not in level_text
                and level_text != "IA"
            ):
                category = "CERTIFICATE"
                category_basis = (
                    "CROSSWALK_CANONICAL_LINEAGE_AWARD_LEVEL"
                )

            elif (
                "INSTITUTIONAL"
                in level_text
                or level_text == "IA"
            ):
                category = "INSTITUTIONAL_AWARD"
                category_basis = (
                    "CROSSWALK_CANONICAL_LINEAGE_AWARD_LEVEL"
                )

            else:
                category = "UNRESOLVED"
                category_basis = (
                    "CROSSWALK_CANONICAL_LINEAGE_AMBIGUOUS"
                )

        exact_degree_code = (
            degree_codes[0]
            if len(
                degree_codes
            ) == 1
            else ""
        )

        lineage_rows.append(
            {
                "candidate_lineage":
                    lineage,
                "candidate_crosswalk_degree_codes":
                    " | ".join(
                        degree_codes
                    ),
                "candidate_crosswalk_award_levels":
                    " | ".join(
                        award_levels
                    ),
                "candidate_exact_degree_code":
                    exact_degree_code,
                "candidate_award_category_crosswalk":
                    category,
                "candidate_award_category_basis":
                    category_basis,
                "candidate_degree_code_variant_count":
                    len(
                        degree_codes
                    ),
            }
        )

    lineage_metadata = pd.DataFrame(
        lineage_rows
    )

    result = candidates[
        KEY
        + [
            "credential_lineage",
            "suppression_family",
            "awardability_credential_type",
        ]
    ].copy()

    result[
        "credential_id_norm"
    ] = result[
        "credential_id"
    ].map(
        norm
    )

    result[
        "current_credential_lineage_norm"
    ] = result[
        "credential_lineage"
    ].map(
        canonicalize_lineage
    )

    result[
        "current_suppression_family_norm"
    ] = result[
        "suppression_family"
    ].map(
        canonicalize_lineage
    )

    result = result.merge(
        modeled_map,
        on="credential_id_norm",
        how="left",
        validate="many_to_one",
    )

    result[
        "canonical_lineage_norm"
    ] = result[
        "canonical_lineage_norm"
    ].fillna("")

    result[
        "candidate_lineage"
    ] = result[
        "canonical_lineage_norm"
    ]

    result[
        "candidate_lineage_basis"
    ] = ""

    modeled_hit = result[
        "candidate_lineage"
    ].ne("")

    result.loc[
        modeled_hit,
        "candidate_lineage_basis",
    ] = "MODELED_INVENTORY_CREDENTIAL_ID"

    # First fallback: current engine lineage, after the exact historical alias
    # repairs recovered from the old canonicalization scripts.
    fallback = result[
        "candidate_lineage"
    ].eq("")

    result.loc[
        fallback,
        "candidate_lineage",
    ] = result.loc[
        fallback,
        "current_credential_lineage_norm",
    ]

    result.loc[
        fallback
        & result[
            "candidate_lineage"
        ].ne(""),
        "candidate_lineage_basis",
    ] = "CURRENT_CREDENTIAL_LINEAGE_CANONICALIZED"

    # Second fallback is diagnostic only. suppression_family is an award
    # suppression identity, not automatically equivalent to canonical lineage,
    # but it is preferable to a blank identity and will still be forced through
    # governed-pair validation below.
    fallback = result[
        "candidate_lineage"
    ].eq("")

    result.loc[
        fallback,
        "candidate_lineage",
    ] = result.loc[
        fallback,
        "current_suppression_family_norm",
    ]

    result.loc[
        fallback
        & result[
            "candidate_lineage"
        ].ne(""),
        "candidate_lineage_basis",
    ] = "SUPPRESSION_FAMILY_FALLBACK_REQUIRES_GOVERNANCE"

    result = result.merge(
        lineage_metadata,
        on="candidate_lineage",
        how="left",
        validate="many_to_one",
    )

    for column in [
        "candidate_crosswalk_degree_codes",
        "candidate_crosswalk_award_levels",
        "candidate_exact_degree_code",
        "candidate_award_category_crosswalk",
        "candidate_award_category_basis",
    ]:
        result[
            column
        ] = result[
            column
        ].fillna("")

    result[
        "candidate_degree_code_variant_count"
    ] = pd.to_numeric(
        result[
            "candidate_degree_code_variant_count"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    result[
        "candidate_award_category"
    ] = result[
        "candidate_award_category_crosswalk"
    ]

    unresolved_category = (
        result[
            "candidate_award_category"
        ].eq("")
        | result[
            "candidate_award_category"
        ].eq(
            "UNRESOLVED"
        )
    )

    result.loc[
        unresolved_category,
        "candidate_award_category",
    ] = result.loc[
        unresolved_category,
        "awardability_credential_type",
    ].map(
        current_type_fallback
    )

    result.loc[
        unresolved_category,
        "candidate_award_category_basis",
    ] = (
        "CURRENT_AWARDABILITY_TYPE_FALLBACK"
    )

    result[
        "candidate_metadata_status"
    ] = "RESOLVED"

    result.loc[
        result[
            "candidate_lineage"
        ].eq("")
        | result[
            "candidate_award_category"
        ].isin(
            [
                "UNRESOLVED",
                "CERTIFICATE_OR_IA",
            ]
        ),
        "candidate_metadata_status",
    ] = "REVIEW"

    result[
        "candidate_exact_associate_degree_code_resolved"
    ] = True

    assoc = result[
        "candidate_award_category"
    ].eq(
        "ASSOCIATE"
    )

    result.loc[
        assoc
        & ~result[
            "candidate_exact_degree_code"
        ].isin(
            [
                "AA",
                "AS",
                "AAS",
                "AAT",
            ]
        ),
        "candidate_exact_associate_degree_code_resolved",
    ] = False

    return result.drop(
        columns=[
            "credential_id_norm",
            "canonical_lineage_norm",
            "current_credential_lineage_norm",
            "current_suppression_family_norm",
            "credential_lineage",
            "suppression_family",
        ]
    )


def main() -> None:
    current_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_awardability_pass_combinations.csv",
    )

    official_dir = latest_dir(
        "official_award_screening_final_*",
        "RESTRICTED_canonical_official_awards_final_mapping.csv",
    )

    candidate_path = (
        current_dir
        / "RESTRICTED_awardability_pass_combinations.csv"
    )

    official_path = (
        official_dir
        / "RESTRICTED_canonical_official_awards_final_mapping.csv"
    )

    for path in [
        candidate_path,
        official_path,
        FINAL_GOVERNANCE,
        CROSSWALK,
    ]:
        require(
            path
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    candidates = pd.read_csv(
        candidate_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    official = pd.read_csv(
        official_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    governance = pd.read_csv(
        FINAL_GOVERNANCE,
        dtype=str,
        low_memory=False,
    ).fillna("")

    if len(
        candidates
    ) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Ordinary PASS universe changed: "
            f"{len(candidates):,} != "
            f"{EXPECTED_ORDINARY_PASS:,}"
        )

    if candidates.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Ordinary PASS universe is not unique at candidate key."
        )

    required_candidate = {
        *KEY,
        "credential_lineage",
        "suppression_family",
        "awardability_credential_type",
    }

    missing = (
        required_candidate
        - set(
            candidates.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Candidate file missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    required_official = {
        "ID",
        "DegreeCode",
        "suppression_family",
    }

    missing = (
        required_official
        - set(
            official.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Official file missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    required_governance = {
        "detected_lineage",
        "institutional_lineage",
        "relationship_type",
        "awarded_represents_detected",
        "detected_remains_additional_award",
        "governance_status",
    }

    missing = (
        required_governance
        - set(
            governance.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Governance file missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ------------------------------------------------------------------
    # Candidate metadata
    # ------------------------------------------------------------------
    metadata = build_candidate_metadata(
        candidates
    )

    candidates = candidates.merge(
        metadata.drop(
            columns=[
                "awardability_credential_type",
            ]
        ),
        on=KEY,
        how="left",
        validate="one_to_one",
    )

    candidates[
        "candidate_suppression_family"
    ] = candidates[
        "suppression_family"
    ].map(
        canonicalize_lineage
    )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Official awards — normalize through the curated official-award crosswalk.
    #
    # This ports the prior validated architecture exactly:
    #   Curr1ProgramCode + Major1Code + DegreeCode -> canonical_lineage
    #
    # Do NOT use the current suppression_family as the governance lineage.
    # suppression_family is retained as a diagnostic because it was built for
    # same-family award suppression, not cross-lineage dependency governance.
    # ------------------------------------------------------------------
    off = official.copy()

    official_crosswalk = pd.read_excel(
        CROSSWALK,
        sheet_name="Crosswalk Draft",
        dtype=str,
    ).fillna("")

    key_columns = [
        "Curr1ProgramCode",
        "Major1Code",
        "DegreeCode",
    ]

    for column in key_columns:
        if column not in off.columns:
            raise RuntimeError(
                f"Official award file missing {column}"
            )

        if column not in official_crosswalk.columns:
            raise RuntimeError(
                f"Crosswalk Draft missing {column}"
            )

        off[
            column
        ] = (
            off[
                column
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        official_crosswalk[
            column
        ] = (
            official_crosswalk[
                column
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

    if "canonical_lineage" not in official_crosswalk.columns:
        raise RuntimeError(
            "Crosswalk Draft missing canonical_lineage."
        )

    official_crosswalk[
        "canonical_lineage"
    ] = official_crosswalk[
        "canonical_lineage"
    ].map(
        canonicalize_lineage
    )

    crosswalk_columns = key_columns + [
        "canonical_lineage",
    ]

    for optional in [
        "award_level",
        "stack_behavior",
        "reconciliation_key",
        "credential_id",
        "match_status",
    ]:
        if optional in official_crosswalk.columns:
            crosswalk_columns.append(
                optional
            )

    crosswalk_clean = (
        official_crosswalk[
            crosswalk_columns
        ]
        .drop_duplicates()
    )

    ambiguity = (
        crosswalk_clean.groupby(
            key_columns
        )[
            "canonical_lineage"
        ]
        .nunique()
    )

    bad = ambiguity[
        ambiguity
        > 1
    ]

    if not bad.empty:
        raise RuntimeError(
            "Official award crosswalk has ambiguous code combinations."
        )

    off = off.merge(
        crosswalk_clean,
        on=key_columns,
        how="left",
        validate="many_to_one",
        suffixes=(
            "",
            "_crosswalk",
        ),
    )

    off[
        "student_id"
    ] = (
        off[
            "ID"
        ]
        .astype(str)
        .str.strip()
    )

    off[
        "official_family"
    ] = off[
        "canonical_lineage"
    ].fillna("").map(
        canonicalize_lineage
    )

    off[
        "official_suppression_family"
    ] = off[
        "suppression_family"
    ].map(
        canonicalize_lineage
    )

    off[
        "official_degree_code"
    ] = (
        off[
            "DegreeCode"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    off[
        "official_award_category"
    ] = off[
        "official_degree_code"
    ].map(
        official_category
    )

    for source, target in [
        (
            "Curr1ProgramCode",
            "official_program_code",
        ),
        (
            "Major1Code",
            "official_major_code",
        ),
        (
            "StudGradTerm",
            "official_grad_term",
        ),
        (
            "mapping_status",
            "official_mapping_status",
        ),
        (
            "mapping_note",
            "official_mapping_note",
        ),
    ]:
        off[
            target
        ] = (
            off[
                source
            ].astype(str).str.strip()
            if source
            in off.columns
            else ""
        )

    # Crosswalk mapping status is useful context where available.
    off[
        "official_crosswalk_match_status"
    ] = (
        off[
            "match_status"
        ].astype(str).str.strip()
        if "match_status"
        in off.columns
        else ""
    )

    off = off[
        off[
            "student_id"
        ].ne("")
    ].copy()

    off = off.drop_duplicates(
        [
            "student_id",
            "official_family",
            "official_degree_code",
            "official_program_code",
            "official_major_code",
            "official_grad_term",
        ]
    ).copy()

    # ------------------------------------------------------------------
    # Effective governance table.
    #
    # Duplicates may exist for the same lineage pair. Collapse according to
    # the PRIOR FINALIZED PRECEDENCE, not relationship_type labels.
    # ------------------------------------------------------------------
    gov = governance.copy()

    gov[
        "detected_lineage"
    ] = gov[
        "detected_lineage"
    ].map(
        canonicalize_lineage
    )

    gov[
        "institutional_lineage"
    ] = gov[
        "institutional_lineage"
    ].map(
        canonicalize_lineage
    )

    gov[
        "_represents"
    ] = gov[
        "awarded_represents_detected"
    ].map(
        truthy
    )

    gov[
        "_remains"
    ] = gov[
        "detected_remains_additional_award"
    ].map(
        truthy
    )

    gov[
        "_consuming"
    ] = (
        gov[
            "_represents"
        ]
        & ~gov[
            "_remains"
        ]
    )

    effective_rows = []

    for (
        detected,
        institutional,
    ), group in gov.groupby(
        [
            "detected_lineage",
            "institutional_lineage",
        ],
        dropna=False,
        sort=False,
    ):
        consuming = bool(
            group[
                "_consuming"
            ].any()
        )

        remains = bool(
            group[
                "_remains"
            ].any()
        )

        if consuming:
            disposition = (
                "CONSUMING_GOVERNED"
            )

        elif remains:
            disposition = (
                "NONCONSUMING_GOVERNED"
            )

        else:
            disposition = (
                "REVIEW_NO_FINAL_DISPOSITION"
            )

        effective_rows.append(
            {
                "candidate_lineage":
                    detected,
                "official_family":
                    institutional,
                "governance_pair_disposition":
                    disposition,
                "governance_relationship_types":
                    joined(
                        group[
                            "relationship_type"
                        ]
                    ),
                "governance_sources":
                    joined(
                        group[
                            "governance_source"
                        ]
                    )
                    if "governance_source"
                    in group.columns
                    else "",
                "governance_row_count":
                    len(
                        group
                    ),
            }
        )

    effective = pd.DataFrame(
        effective_rows
    )

    # ------------------------------------------------------------------
    # Candidate × all official awards.
    # ------------------------------------------------------------------
    candidate_core = candidates[
        KEY
        + [
            "candidate_lineage",
            "candidate_suppression_family",
            "candidate_award_category",
            "candidate_exact_degree_code",
            "candidate_metadata_status",
            "candidate_exact_associate_degree_code_resolved",
        ]
    ].copy()

    pairs = candidate_core.merge(
        off[
            [
                "student_id",
                "official_family",
                "official_degree_code",
                "official_award_category",
                "official_program_code",
                "official_major_code",
                "official_grad_term",
                "official_mapping_status",
                "official_mapping_note",
                "official_suppression_family",
                "official_crosswalk_match_status",
            ]
        ],
        on="student_id",
        how="left",
        validate="many_to_many",
    ).fillna("")

    pairs[
        "has_official_award"
    ] = pairs[
        "official_degree_code"
    ].ne("")

    pairs = pairs.merge(
        effective,
        on=[
            "candidate_lineage",
            "official_family",
        ],
        how="left",
        validate="many_to_one",
    )

    pairs[
        "governance_pair_status"
    ] = ""

    no_award = ~pairs[
        "has_official_award"
    ]

    pairs.loc[
        no_award,
        "governance_pair_status",
    ] = "NO_OFFICIAL_AWARD"

    ia = (
        pairs[
            "has_official_award"
        ]
        & (
            pairs[
                "official_award_category"
            ].eq(
                "INSTITUTIONAL_AWARD"
            )
            | pairs[
                "official_family"
            ].str.startswith(
                "IA_",
                na=False,
            )
        )
    )

    pairs.loc[
        ia,
        "governance_pair_status",
    ] = (
        "NONCONSUMING_IA_MECHANICAL"
    )

    blank_family = (
        pairs[
            "has_official_award"
        ]
        & pairs[
            "official_family"
        ].eq("")
        & ~ia
    )

    pairs.loc[
        blank_family,
        "governance_pair_status",
    ] = (
        "REVIEW_UNMAPPED_OFFICIAL_LINEAGE"
    )

    exact = (
        pairs[
            "has_official_award"
        ]
        & pairs[
            "candidate_lineage"
        ].ne("")
        & pairs[
            "candidate_lineage"
        ].eq(
            pairs[
                "official_family"
            ]
        )
        & ~ia
    )

    pairs.loc[
        exact,
        "governance_pair_status",
    ] = "CONSUMING_EXACT_LINEAGE"

    undecided = pairs[
        "governance_pair_status"
    ].eq("")

    pairs.loc[
        undecided
        & pairs[
            "governance_pair_disposition"
        ].eq(
            "CONSUMING_GOVERNED"
        ),
        "governance_pair_status",
    ] = "CONSUMING_GOVERNED"

    undecided = pairs[
        "governance_pair_status"
    ].eq("")

    pairs.loc[
        undecided
        & pairs[
            "governance_pair_disposition"
        ].eq(
            "NONCONSUMING_GOVERNED"
        ),
        "governance_pair_status",
    ] = "NONCONSUMING_GOVERNED"

    undecided = pairs[
        "governance_pair_status"
    ].eq("")

    pairs.loc[
        undecided
        & pairs[
            "governance_pair_disposition"
        ].eq(
            "REVIEW_NO_FINAL_DISPOSITION"
        ),
        "governance_pair_status",
    ] = "REVIEW_GOVERNED_PAIR_WITHOUT_DISPOSITION"

    undecided = pairs[
        "governance_pair_status"
    ].eq("")

    pairs.loc[
        undecided
        & pairs[
            "has_official_award"
        ],
        "governance_pair_status",
    ] = "REVIEW_UNGOVERNED_PAIR"

    if pairs[
        "governance_pair_status"
    ].eq("").any():
        raise RuntimeError(
            "At least one candidate-official pair received no governance status."
        )

    pairs.to_csv(
        PAIR_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # Collapse to one candidate disposition.
    # ------------------------------------------------------------------
    candidate_rows = []

    pair_by_candidate = {
        key: group.copy()
        for key, group
        in pairs.groupby(
            KEY,
            sort=False,
        )
    }

    for candidate in candidates.itertuples(
        index=False
    ):
        key = (
            candidate.student_id,
            candidate.catalog_year,
            candidate.credential_id,
        )

        group = pair_by_candidate[
            key
        ]

        consuming = group[
            group[
                "governance_pair_status"
            ].str.startswith(
                "CONSUMING_",
                na=False,
            )
        ]

        review_pairs = group[
            group[
                "governance_pair_status"
            ].str.startswith(
                "REVIEW_",
                na=False,
            )
        ]

        official_rows = group[
            group[
                "has_official_award"
            ]
        ]

        prior_assoc = official_rows[
            official_rows[
                "official_award_category"
            ].eq(
                "ASSOCIATE"
            )
        ]

        prior_cert = official_rows[
            official_rows[
                "official_award_category"
            ].eq(
                "CERTIFICATE"
            )
        ]

        prior_ia = official_rows[
            official_rows[
                "official_award_category"
            ].eq(
                "INSTITUTIONAL_AWARD"
            )
        ]

        if not consuming.empty:
            governed_disposition = (
                "REPRESENTED_BY_OFFICIAL_AWARD"
            )

        elif not review_pairs.empty:
            governed_disposition = (
                "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
            )

        else:
            governed_disposition = (
                "REMAINS_ADDITIONAL_CANDIDATE"
            )

        if governed_disposition == (
            "REPRESENTED_BY_OFFICIAL_AWARD"
        ):
            route = (
                "STOP_REPRESENTED_BY_OFFICIAL_AWARD"
            )

        elif governed_disposition == (
            "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
        ):
            route = (
                "REVIEW_BEFORE_MULTIPLE_AWARD_TEST"
            )

        elif (
            candidate.candidate_metadata_status
            == "REVIEW"
        ):
            route = (
                "REVIEW_CANDIDATE_AWARD_METADATA"
            )

        elif (
            candidate.candidate_award_category
            == "ASSOCIATE"
        ):
            if len(
                prior_assoc
            ):
                route = (
                    "SECOND_ASSOCIATE_TEST_PENDING"
                )
            else:
                route = (
                    "NO_SECOND_ASSOCIATE_RULE"
                )

        elif (
            candidate.candidate_award_category
            == "CERTIFICATE"
        ):
            if len(
                prior_cert
            ):
                route = (
                    "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
                )
            else:
                route = (
                    "NO_ADDITIONAL_CERTIFICATE_RULE"
                )

        elif (
            candidate.candidate_award_category
            == "INSTITUTIONAL_AWARD"
        ):
            route = (
                "INSTITUTIONAL_AWARD_MULTIPLE_POLICY_REVIEW"
            )

        else:
            route = (
                "REVIEW_CANDIDATE_AWARD_METADATA"
            )

        candidate_rows.append(
            {
                **candidate._asdict(),
                "governed_dependency_disposition":
                    governed_disposition,
                "governing_consuming_official_families":
                    joined(
                        consuming[
                            "official_family"
                        ]
                    ),
                "governing_consuming_relationship_types":
                    joined(
                        consuming[
                            "governance_relationship_types"
                        ]
                    ),
                "governance_review_pair_count":
                    len(
                        review_pairs
                    ),
                "official_associate_award_count":
                    len(
                        prior_assoc
                    ),
                "official_certificate_award_count":
                    len(
                        prior_cert
                    ),
                "official_institutional_award_count":
                    len(
                        prior_ia
                    ),
                "official_other_or_review_award_count":
                    int(
                        official_rows[
                            "official_award_category"
                        ].isin(
                            [
                                "OTHER_OR_REVIEW",
                                "UNRESOLVED",
                            ]
                        ).sum()
                    ),
                "official_associate_degree_codes":
                    joined(
                        prior_assoc[
                            "official_degree_code"
                        ]
                    ),
                "multiple_award_route":
                    route,
            }
        )

    result = pd.DataFrame(
        candidate_rows
    )

    if len(
        result
    ) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Candidate count changed during governance screen."
        )

    if result.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Governance screen is not unique at candidate key."
        )

    result.to_csv(
        CANDIDATE_OUT,
        index=False,
    )

    result[
        result[
            "governed_dependency_disposition"
        ].eq(
            "REMAINS_ADDITIONAL_CANDIDATE"
        )
    ].to_csv(
        SURVIVORS_OUT,
        index=False,
    )

    result[
        result[
            "governed_dependency_disposition"
        ].eq(
            "REPRESENTED_BY_OFFICIAL_AWARD"
        )
    ].to_csv(
        REPRESENTED_OUT,
        index=False,
    )

    result[
        result[
            "governed_dependency_disposition"
        ].eq(
            "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
        )
        | result[
            "multiple_award_route"
        ].str.startswith(
            "REVIEW_",
            na=False,
        )
    ].to_csv(
        REVIEW_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe outputs.
    # ------------------------------------------------------------------
    route_summary = (
        result.groupby(
            [
                "candidate_award_category",
                "governed_dependency_disposition",
                "multiple_award_route",
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

    route_summary.to_csv(
        SAFE_ROUTE,
        index=False,
    )

    pair_status = (
        pairs.groupby(
            "governance_pair_status",
            dropna=False,
        )
        .agg(
            pair_rows=(
                "student_id",
                "size",
            ),
            candidate_combinations=(
                "credential_id",
                "size",
            ),
        )
        .reset_index()
        .sort_values(
            "pair_rows",
            ascending=False,
        )
    )

    pair_status.to_csv(
        SAFE_PAIR_STATUS,
        index=False,
    )

    unresolved = pairs[
        pairs[
            "governance_pair_status"
        ].str.startswith(
            "REVIEW_",
            na=False,
        )
    ].copy()

    if unresolved.empty:
        unresolved_safe = pd.DataFrame(
            columns=[
                "candidate_lineage",
                "official_family",
                "official_degree_code",
                "governance_pair_status",
                "pair_rows",
            ]
        )
    else:
        unresolved_safe = (
            unresolved.groupby(
                [
                    "candidate_lineage",
                    "official_family",
                    "official_degree_code",
                    "governance_pair_status",
                ],
                dropna=False,
            )
            .size()
            .reset_index(
                name="pair_rows"
            )
            .sort_values(
                "pair_rows",
                ascending=False,
            )
        )

    unresolved_safe.to_csv(
        SAFE_UNRESOLVED,
        index=False,
    )

    metadata_safe = (
        result.groupby(
            [
                "candidate_award_category",
                "candidate_metadata_status",
                "candidate_exact_associate_degree_code_resolved",
                "candidate_award_category_basis",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="candidate_combinations"
        )
        .sort_values(
            "candidate_combinations",
            ascending=False,
        )
    )

    metadata_safe.to_csv(
        SAFE_METADATA,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "ordinary_awardability_pass_combinations",
                "value":
                    len(
                        result
                    ),
            },
            {
                "metric":
                    "represented_by_official_award_after_final_governance",
                "value":
                    int(
                        result[
                            "governed_dependency_disposition"
                        ].eq(
                            "REPRESENTED_BY_OFFICIAL_AWARD"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "governance_or_official_mapping_review",
                "value":
                    int(
                        result[
                            "governed_dependency_disposition"
                        ].eq(
                            "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "remains_additional_candidate",
                "value":
                    int(
                        result[
                            "governed_dependency_disposition"
                        ].eq(
                            "REMAINS_ADDITIONAL_CANDIDATE"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "second_associate_test_pending",
                "value":
                    int(
                        result[
                            "multiple_award_route"
                        ].eq(
                            "SECOND_ASSOCIATE_TEST_PENDING"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "additional_certificate_25_percent_test_pending",
                "value":
                    int(
                        result[
                            "multiple_award_route"
                        ].eq(
                            "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "institutional_award_multiple_policy_review",
                "value":
                    int(
                        result[
                            "multiple_award_route"
                        ].eq(
                            "INSTITUTIONAL_AWARD_MULTIPLE_POLICY_REVIEW"
                        ).sum()
                    ),
            },
            {
                "metric":
                    "unresolved_governance_pair_rows",
                "value":
                    len(
                        unresolved
                    ),
            },
            {
                "metric":
                    "associate_candidates_without_exact_degree_code",
                "value":
                    int(
                        (
                            result[
                                "candidate_award_category"
                            ].eq(
                                "ASSOCIATE"
                            )
                            & ~result[
                                "candidate_exact_associate_degree_code_resolved"
                            ].astype(
                                bool
                            )
                        ).sum()
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("CURRENT FINAL-GOVERNANCE DEPENDENCY SCREEN")
    print("=" * 112)
    print(
        f"Ordinary awardability PASS combinations:      {len(result):,}"
    )
    print(
        "Represented after final governance:          "
        f"{int(result['governed_dependency_disposition'].eq('REPRESENTED_BY_OFFICIAL_AWARD').sum()):,}"
    )
    print(
        "Governance / official-mapping REVIEW:        "
        f"{int(result['governed_dependency_disposition'].eq('REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING').sum()):,}"
    )
    print(
        "Remaining additional-award candidates:       "
        f"{int(result['governed_dependency_disposition'].eq('REMAINS_ADDITIONAL_CANDIDATE').sum()):,}"
    )
    print()
    print("ROUTES")
    print(
        route_summary.to_string(
            index=False
        )
    )
    print()
    print("GOVERNANCE PAIR STATUS")
    print(
        pair_status.to_string(
            index=False
        )
    )
    print()
    print("CANDIDATE AWARD METADATA")
    print(
        metadata_safe.to_string(
            index=False
        )
    )
    print()
    if unresolved_safe.empty:
        print("UNRESOLVED GOVERNANCE PAIRS: 0")
    else:
        print("UNRESOLVED GOVERNANCE PAIRS")
        print(
            unresolved_safe.head(
                40
            ).to_string(
                index=False
            )
        )
    print()
    print(
        "Control: official awards were canonicalized through the curated "
        "three-code crosswalk before governance."
    )
    print(
        "Control: left-join no-award rows were normalized to blanks before "
        "has_official_award classification."
    )
    print(
        "Control: represents=TRUE/remains=TRUE is NON-CONSUMING, "
        "matching the prior finalized governance code."
    )
    print(
        "No second-associate or additional-certificate arithmetic "
        "was performed."
    )
    print()
    print(
        f"Current awardability source: {current_dir}"
    )
    print(
        f"Official-award source:       {official_dir}"
    )
    print(
        f"Output directory:            {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
