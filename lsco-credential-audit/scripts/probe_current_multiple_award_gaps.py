from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

GOV = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "governed_lineage_relationships_final.csv"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"multiple_award_gap_probe_{STAMP}"
)

SAFE_METRICS = (
    OUT_DIR
    / "FERPA_SAFE_multiple_award_gap_metrics.csv"
)

SAFE_UNGOV = (
    OUT_DIR
    / "FERPA_SAFE_ungoverned_pair_review.csv"
)

SAFE_METADATA = (
    OUT_DIR
    / "FERPA_SAFE_candidate_metadata_gaps.csv"
)

SAFE_ASSOC = (
    OUT_DIR
    / "FERPA_SAFE_associate_degree_code_gaps.csv"
)


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def yes(value: object) -> bool:
    return txt(value).upper() in {
        "TRUE", "T", "YES", "Y", "1",
    }


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
    matches = sorted(
        [
            p
            for p in REPORTING.glob(pattern)
            if (
                p.is_dir()
                and (
                    p
                    / required_name
                ).exists()
            )
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        raise FileNotFoundError(
            f"No {pattern} directory containing {required_name}"
        )

    return matches[0]


def catalog_start_year(
    value: object,
) -> int | None:
    value = txt(value)

    if len(value) < 4:
        return None

    try:
        return int(
            value[:4]
        )
    except ValueError:
        return None


def joined(values) -> str:
    return " | ".join(
        sorted(
            {
                txt(v)
                for v in values
                if txt(v)
            }
        )
    )


def main() -> None:
    screen_dir = latest_dir(
        "current_governed_dependency_screen_*",
        "RESTRICTED_current_governed_dependency_candidates.csv",
    )

    candidate_path = (
        screen_dir
        / "RESTRICTED_current_governed_dependency_candidates.csv"
    )

    pair_path = (
        screen_dir
        / "RESTRICTED_current_candidate_official_governance_pairs.csv"
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

    gov = pd.read_csv(
        GOV,
        dtype=str,
        low_memory=False,
    ).fillna("")

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    gov[
        "_represents"
    ] = gov[
        "awarded_represents_detected"
    ].map(
        yes
    )

    gov[
        "_remains"
    ] = gov[
        "detected_remains_additional_award"
    ].map(
        yes
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

    consuming_count = int(
        gov[
            "_consuming"
        ].sum()
    )

    # --------------------------------------------------------------
    # Ungoverned current cross-lineage pairs.
    # --------------------------------------------------------------
    ungoverned = pairs[
        pairs[
            "governance_pair_status"
        ].eq(
            "REVIEW_UNGOVERNED_PAIR"
        )
    ].copy()

    gov_lookup = {}

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
        gov_lookup[
            (
                txt(detected),
                txt(institutional),
            )
        ] = {
            "relationship_types":
                joined(
                    group[
                        "relationship_type"
                    ]
                ),
            "represents_any":
                bool(
                    group[
                        "_represents"
                    ].any()
                ),
            "remains_any":
                bool(
                    group[
                        "_remains"
                    ].any()
                ),
            "consuming_any":
                bool(
                    group[
                        "_consuming"
                    ].any()
                ),
        }

    pair_rows = []

    if not ungoverned.empty:
        grouped = (
            ungoverned.groupby(
                [
                    "candidate_lineage",
                    "official_family",
                    "official_degree_code",
                ],
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
        )

        for row in grouped.itertuples(
            index=False
        ):
            reverse = gov_lookup.get(
                (
                    txt(
                        row.official_family
                    ),
                    txt(
                        row.candidate_lineage
                    ),
                ),
                {},
            )

            forward = gov_lookup.get(
                (
                    txt(
                        row.candidate_lineage
                    ),
                    txt(
                        row.official_family
                    ),
                ),
                {},
            )

            pair_rows.append(
                {
                    "candidate_lineage":
                        row.candidate_lineage,
                    "official_family":
                        row.official_family,
                    "official_degree_code":
                        row.official_degree_code,
                    "pair_rows":
                        int(
                            row.pair_rows
                        ),
                    "candidate_combinations":
                        int(
                            row.candidate_combinations
                        ),
                    "forward_governance_exists":
                        bool(
                            forward
                        ),
                    "forward_relationship_types":
                        forward.get(
                            "relationship_types",
                            "",
                        ),
                    "forward_consuming_any":
                        forward.get(
                            "consuming_any",
                            False,
                        ),
                    "reverse_governance_exists":
                        bool(
                            reverse
                        ),
                    "reverse_relationship_types":
                        reverse.get(
                            "relationship_types",
                            "",
                        ),
                    "reverse_represents_any":
                        reverse.get(
                            "represents_any",
                            False,
                        ),
                    "reverse_remains_any":
                        reverse.get(
                            "remains_any",
                            False,
                        ),
                    "reverse_consuming_any":
                        reverse.get(
                            "consuming_any",
                            False,
                        ),
                }
            )

    ungoverned_safe = pd.DataFrame(
        pair_rows
    )

    if not ungoverned_safe.empty:
        ungoverned_safe = (
            ungoverned_safe.sort_values(
                [
                    "pair_rows",
                    "candidate_lineage",
                    "official_family",
                ],
                ascending=[
                    False,
                    True,
                    True,
                ],
            )
        )

    ungoverned_safe.to_csv(
        SAFE_UNGOV,
        index=False,
    )

    # --------------------------------------------------------------
    # Candidate CERTIFICATE vs IA metadata gaps.
    # --------------------------------------------------------------
    metadata_gap = candidates[
        candidates[
            "candidate_metadata_status"
        ].eq(
            "REVIEW"
        )
    ].copy()

    metadata_cols = [
        column
        for column in [
            "catalog_year",
            "credential_id",
            "credential_title",
            "awardability_credential_title",
            "candidate_lineage",
            "awardability_program_hours",
            "candidate_crosswalk_degree_codes",
            "candidate_crosswalk_award_levels",
            "candidate_award_category",
            "candidate_award_category_basis",
            "multiple_award_route",
        ]
        if column
        in metadata_gap.columns
    ]

    if metadata_gap.empty:
        metadata_safe = pd.DataFrame()
    else:
        metadata_safe = (
            metadata_gap.groupby(
                metadata_cols,
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
                    "candidate_combinations",
                    "catalog_year",
                    "credential_id",
                ],
                ascending=[
                    False,
                    True,
                    True,
                ],
            )
        )

    metadata_safe.to_csv(
        SAFE_METADATA,
        index=False,
    )

    # --------------------------------------------------------------
    # Associate exact degree-code gaps, split by whether modern rule needs it.
    # --------------------------------------------------------------
    assoc = candidates[
        candidates[
            "candidate_award_category"
        ].eq(
            "ASSOCIATE"
        )
        & ~candidates[
            "candidate_exact_associate_degree_code_resolved"
        ].map(
            yes
        )
    ].copy()

    if not assoc.empty:
        assoc[
            "catalog_start_year"
        ] = assoc[
            "catalog_year"
        ].map(
            catalog_start_year
        )

        assoc[
            "modern_2025plus_rule"
        ] = assoc[
            "catalog_start_year"
        ].ge(
            2025
        )

        assoc_cols = [
            column
            for column in [
                "catalog_year",
                "credential_id",
                "credential_title",
                "awardability_credential_title",
                "candidate_lineage",
                "awardability_program_hours",
                "candidate_crosswalk_degree_codes",
                "multiple_award_route",
                "modern_2025plus_rule",
            ]
            if column
            in assoc.columns
        ]

        assoc_safe = (
            assoc.groupby(
                assoc_cols,
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
                    "modern_2025plus_rule",
                    "candidate_combinations",
                    "catalog_year",
                    "credential_id",
                ],
                ascending=[
                    False,
                    False,
                    True,
                    True,
                ],
            )
        )
    else:
        assoc_safe = pd.DataFrame()

    assoc_safe.to_csv(
        SAFE_ASSOC,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "active_governance_rows",
                "value":
                    len(
                        gov
                    ),
            },
            {
                "metric":
                    "active_cross_lineage_consuming_governance_rows",
                "value":
                    consuming_count,
            },
            {
                "metric":
                    "ungoverned_pair_rows",
                "value":
                    len(
                        ungoverned
                    ),
            },
            {
                "metric":
                    "ungoverned_unique_lineage_degree_pairs",
                "value":
                    len(
                        ungoverned_safe
                    ),
            },
            {
                "metric":
                    "ungoverned_pairs_with_reverse_governance",
                "value":
                    int(
                        ungoverned_safe[
                            "reverse_governance_exists"
                        ].sum()
                    )
                    if not ungoverned_safe.empty
                    else 0,
            },
            {
                "metric":
                    "candidate_metadata_review_combinations",
                "value":
                    len(
                        metadata_gap
                    ),
            },
            {
                "metric":
                    "candidate_metadata_review_unique_credential_years",
                "value":
                    len(
                        metadata_safe
                    ),
            },
            {
                "metric":
                    "associate_exact_degree_code_unresolved_combinations",
                "value":
                    len(
                        assoc
                    ),
            },
            {
                "metric":
                    "associate_exact_degree_code_unresolved_2025plus_combinations",
                "value":
                    int(
                        assoc[
                            "modern_2025plus_rule"
                        ].sum()
                    )
                    if not assoc.empty
                    else 0,
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("MULTIPLE-AWARD GAP PROBE")
    print("=" * 112)
    print(
        f"Active governance rows:                         {len(gov):,}"
    )
    print(
        f"Active cross-lineage CONSUMING rows:            {consuming_count:,}"
    )
    print(
        f"Current ungoverned pair rows:                   {len(ungoverned):,}"
    )
    print(
        "Unique ungoverned lineage/degree pairs:         "
        f"{len(ungoverned_safe):,}"
    )
    print(
        "Ungoverned pairs with reverse governance:       "
        f"{int(ungoverned_safe['reverse_governance_exists'].sum()) if not ungoverned_safe.empty else 0:,}"
    )
    print()
    print(
        f"Candidate metadata REVIEW combinations:         {len(metadata_gap):,}"
    )
    print(
        "Unique candidate credential-year metadata gaps: "
        f"{len(metadata_safe):,}"
    )
    print()
    print(
        "Associate exact-degree-code unresolved:         "
        f"{len(assoc):,}"
    )
    print(
        "Of those in 2025+ catalog rules:                "
        f"{int(assoc['modern_2025plus_rule'].sum()) if not assoc.empty else 0:,}"
    )
    print()

    if not ungoverned_safe.empty:
        print("TOP UNGOVERNED PAIRS")
        print(
            ungoverned_safe.head(
                30
            ).to_string(
                index=False
            )
        )
        print()

    if not metadata_safe.empty:
        print("CANDIDATE METADATA GAPS")
        print(
            metadata_safe.head(
                40
            ).to_string(
                index=False
            )
        )
        print()

    if not assoc_safe.empty:
        print("ASSOCIATE DEGREE-CODE GAPS")
        print(
            assoc_safe.head(
                40
            ).to_string(
                index=False
            )
        )
        print()

    print(
        f"Source governance screen: {screen_dir}"
    )
    print(
        f"Output directory:         {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
