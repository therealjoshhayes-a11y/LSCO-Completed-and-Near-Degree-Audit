from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# HISTORICAL PRIOR-PLAN COVERAGE PROBE
# ======================================================================================
#
# Purpose:
#   The current eligible empirical summary is NOT a sufficient source for
#   reconstructing prior official associate degree plans, because expired /
#   currently-ineligible historical catalog audits can be absent from it.
#
#   The recovered old Stage-2 code used:
#       data/processed/full_actual_audit/full_actual_credential_summary.csv
#   or, if absent:
#       data/processed/full_actual_audit/chunks/chunk_*_credential_summary.csv
#
#   This probe measures whether that historical audit cache can recover the
#   prior associate plan coverage needed for the current 365 second-associate
#   candidates.
#
#   It also prints FERPA-safe modeled-inventory rows involving the two currently
#   unmapped official associate families:
#       REGISTERED_NURSING_AAS
#       TEACHER_EDUCATION_AAT
#
# No student decisions are made.
# No files are mutated.
#
# Run from repo root:
#   python -u .\scripts\probe_historical_prior_associate_coverage.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

FULL_ACTUAL = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
)

SUMMARY = (
    FULL_ACTUAL
    / "full_actual_credential_summary.csv"
)

CHUNK_DIR = (
    FULL_ACTUAL
    / "chunks"
)

CROSSWALK = (
    ROOT
    / "data"
    / "interim"
    / "institutional_awards"
    / "award_program_crosswalk_curated.xlsx"
)

EXPECTED_SECOND_ASSOCIATE = 365

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = (
    REPORTING
    / f"historical_prior_associate_coverage_{STAMP}"
)

SAFE_METRICS = (
    OUT_DIR
    / "FERPA_SAFE_historical_prior_associate_coverage_metrics.csv"
)

SAFE_FAMILY = (
    OUT_DIR
    / "FERPA_SAFE_historical_prior_associate_family_coverage.csv"
)

SAFE_SOURCE = (
    OUT_DIR
    / "FERPA_SAFE_historical_audit_source_inventory.csv"
)

SAFE_UNMAPPED = (
    OUT_DIR
    / "FERPA_SAFE_unmapped_associate_modeled_inventory_candidates.csv"
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


def latest_dir(
    pattern: str,
    required_name: str,
) -> Path:
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


def summary_files() -> list[Path]:
    if SUMMARY.exists():
        return [SUMMARY]

    chunks = sorted(
        CHUNK_DIR.glob(
            "chunk_*_credential_summary.csv"
        )
    )

    if chunks:
        return chunks

    return []


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

    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    if not pair_path.exists():
        raise FileNotFoundError(pair_path)

    if not CROSSWALK.exists():
        raise FileNotFoundError(CROSSWALK)

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

    targets = candidates[
        candidates[
            "multiple_award_route"
        ].eq(
            "SECOND_ASSOCIATE_TEST_PENDING"
        )
    ].copy()

    if len(targets) != EXPECTED_SECOND_ASSOCIATE:
        raise RuntimeError(
            "Second-associate universe changed: "
            f"{len(targets):,} != {EXPECTED_SECOND_ASSOCIATE:,}"
        )

    target_keys = set(
        targets[
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

    prior[
        "official_family"
    ] = prior[
        "official_family"
    ].map(
        canonicalize
    )

    if prior.empty:
        raise RuntimeError(
            "No official associate pairs found."
        )

    # ------------------------------------------------------------------
    # Modeled inventory
    # ------------------------------------------------------------------
    modeled = pd.read_excel(
        CROSSWALK,
        sheet_name="Modeled Inventory",
        dtype=str,
    ).fillna("")

    required = {
        "credential_id",
        "canonical_lineage",
    }

    missing = required - set(
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

    modeled_clean = modeled[
        modeled[
            "credential_id_norm"
        ].ne("")
        & modeled[
            "canonical_lineage_norm"
        ].ne("")
    ].copy()

    cred_to_lineage = (
        modeled_clean[
            [
                "credential_id_norm",
                "canonical_lineage_norm",
            ]
        ]
        .drop_duplicates()
    )

    ambiguity = (
        cred_to_lineage.groupby(
            "credential_id_norm"
        )[
            "canonical_lineage_norm"
        ]
        .nunique()
    )

    bad = ambiguity[
        ambiguity > 1
    ]

    if not bad.empty:
        raise RuntimeError(
            "Modeled Inventory credential_id maps to multiple lineages."
        )

    cred_to_lineage = cred_to_lineage.drop_duplicates(
        "credential_id_norm"
    )

    modeled_families = set(
        modeled_clean[
            "canonical_lineage_norm"
        ]
    )

    prior[
        "modeled_family_present"
    ] = prior[
        "official_family"
    ].isin(
        modeled_families
    )

    # ------------------------------------------------------------------
    # Historical summary source inventory
    # ------------------------------------------------------------------
    files = summary_files()

    source_rows = []

    for path in files:
        header = pd.read_csv(
            path,
            nrows=0,
        ).columns.tolist()

        source_rows.append(
            {
                "path":
                    str(
                        path.relative_to(ROOT)
                    ),
                "size_bytes":
                    path.stat().st_size,
                "columns":
                    " | ".join(
                        header
                    ),
            }
        )

    source_df = pd.DataFrame(
        source_rows
    )

    source_df.to_csv(
        SAFE_SOURCE,
        index=False,
    )

    if not files:
        print("=" * 112)
        print("HISTORICAL PRIOR-ASSOCIATE COVERAGE PROBE")
        print("=" * 112)
        print("Historical full_actual_audit summary source: NOT FOUND")
        print()
        print("Expected either:")
        print(f"  {SUMMARY}")
        print("or chunk files:")
        print(f"  {CHUNK_DIR}\\chunk_*_credential_summary.csv")
        print()
        print(f"Output directory: {OUT_DIR}")
        return

    # ------------------------------------------------------------------
    # Read only candidate students from historical full-audit summary.
    # ------------------------------------------------------------------
    target_students = set(
        targets[
            "student_id"
        ].astype(str)
    )

    historical_parts = []
    total_rows_read = 0

    needed = [
        "student_id",
        "catalog_year",
        "credential_id",
        "audit_status",
        "award_term_sort",
        "award_term_taken",
        "catalog_eligible",
    ]

    for file_index, path in enumerate(
        files,
        start=1,
    ):
        header = pd.read_csv(
            path,
            nrows=0,
        ).columns.tolist()

        required_summary = {
            "student_id",
            "catalog_year",
            "credential_id",
            "audit_status",
        }

        missing = (
            required_summary
            - set(
                header
            )
        )

        if missing:
            raise RuntimeError(
                f"{path.name} missing historical summary columns: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        usecols = [
            col
            for col in needed
            if col in header
        ]

        for chunk in pd.read_csv(
            path,
            dtype=str,
            usecols=usecols,
            chunksize=500_000,
            low_memory=False,
        ):
            total_rows_read += len(
                chunk
            )

            chunk = chunk.fillna("")

            subset = chunk[
                chunk[
                    "student_id"
                ].astype(str).isin(
                    target_students
                )
            ].copy()

            if not subset.empty:
                historical_parts.append(
                    subset
                )

        if len(files) > 1 and (
            file_index % 100 == 0
            or file_index == len(files)
        ):
            print(
                f"Read historical summary files: "
                f"{file_index:,}/{len(files):,}"
            )

    historical = (
        pd.concat(
            historical_parts,
            ignore_index=True,
        )
        if historical_parts
        else pd.DataFrame(
            columns=needed
        )
    )

    historical[
        "credential_id_norm"
    ] = historical[
        "credential_id"
    ].map(
        norm
    )

    historical = historical.merge(
        cred_to_lineage.rename(
            columns={
                "canonical_lineage_norm":
                    "historical_lineage",
            }
        ),
        on="credential_id_norm",
        how="left",
        validate="many_to_one",
    )

    historical[
        "historical_lineage"
    ] = historical[
        "historical_lineage"
    ].fillna("")

    historical_complete = historical[
        historical[
            "audit_status"
        ].astype(str).str.upper().eq(
            "COMPLETE"
        )
    ].copy()

    # IMPORTANT:
    # Do NOT filter historical prior-plan candidates by CURRENT catalog
    # eligibility. The old Stage-2 used its historical full audit specifically
    # to recover the plan that could have existed when the prior award was made.
    #
    # If catalog_eligible exists, preserve it only as a diagnostic.
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

        possible = historical_complete[
            historical_complete[
                "student_id"
            ].eq(
                student_id
            )
            & historical_complete[
                "historical_lineage"
            ].eq(
                family
            )
        ].copy()

        before_term_count = len(
            possible
        )

        timing_basis = ""

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
                    "HISTORICAL_COMPLETE_NO_LATER_THAN_OFFICIAL_TERM"
                )
            else:
                timing_basis = (
                    "HISTORICAL_COMPLETE_FOUND_NONE_NO_LATER_THAN_OFFICIAL_TERM"
                )

        elif possible.empty:
            timing_basis = (
                "NO_HISTORICAL_COMPLETE_MODELED_PRIOR_PLAN"
            )

        else:
            timing_basis = (
                "OFFICIAL_OR_MODELED_TERM_UNAVAILABLE"
            )

        pair_rows.append(
            {
                "official_family":
                    family,
                "official_degree_code":
                    txt(
                        row.official_degree_code
                    ),
                "modeled_family_present":
                    bool(
                        getattr(
                            row,
                            "modeled_family_present",
                            False,
                        )
                    ),
                "historical_complete_rows_before_term_filter":
                    before_term_count,
                "historical_plausible_rows_after_term_filter":
                    len(
                        possible
                    ),
                "timing_basis":
                    timing_basis,
                "historical_catalogs":
                    " | ".join(
                        sorted(
                            {
                                txt(x)
                                for x in possible[
                                    "catalog_year"
                                ]
                                if txt(x)
                            }
                        )
                    ),
                "historical_credentials":
                    " | ".join(
                        sorted(
                            {
                                txt(x)
                                for x in possible[
                                    "credential_id"
                                ]
                                if txt(x)
                            }
                        )
                    ),
            }
        )

    coverage = pd.DataFrame(
        pair_rows
    )

    family_safe = (
        coverage.groupby(
            [
                "official_family",
                "official_degree_code",
                "modeled_family_present",
                "timing_basis",
            ],
            dropna=False,
        )
        .agg(
            pair_rows=(
                "official_family",
                "size",
            ),
            zero_historical_complete=(
                "historical_complete_rows_before_term_filter",
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
            zero_historical_plausible=(
                "historical_plausible_rows_after_term_filter",
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
            min_plausible_rows=(
                "historical_plausible_rows_after_term_filter",
                "min",
            ),
            max_plausible_rows=(
                "historical_plausible_rows_after_term_filter",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "zero_historical_plausible",
                "pair_rows",
            ],
            ascending=[
                False,
                False,
            ],
        )
    )

    family_safe.to_csv(
        SAFE_FAMILY,
        index=False,
    )

    # ------------------------------------------------------------------
    # Unmapped-family modeled-inventory diagnostics — no student rows.
    # ------------------------------------------------------------------
    unresolved_families = sorted(
        set(
            prior.loc[
                ~prior[
                    "modeled_family_present"
                ],
                "official_family",
            ]
        )
    )

    candidate_modeled = modeled.copy()

    search_tokens = [
        "NURS",
        "RN",
        "TEACH",
        "AAT",
    ]

    if unresolved_families:
        mask = pd.Series(
            False,
            index=candidate_modeled.index,
        )

        searchable_columns = [
            col
            for col in [
                "credential_id",
                "credential_title",
                "canonical_lineage",
                "program_family",
            ]
            if col
            in candidate_modeled.columns
        ]

        for col in searchable_columns:
            text_col = (
                candidate_modeled[
                    col
                ]
                .astype(str)
                .str.upper()
            )

            for token in search_tokens:
                mask |= text_col.str.contains(
                    token,
                    regex=False,
                    na=False,
                )

        unresolved_inventory = candidate_modeled.loc[
            mask,
            searchable_columns,
        ].drop_duplicates()
    else:
        unresolved_inventory = pd.DataFrame()

    unresolved_inventory.to_csv(
        SAFE_UNMAPPED,
        index=False,
    )

    zero_before = int(
        (
            pd.to_numeric(
                coverage[
                    "historical_complete_rows_before_term_filter"
                ],
                errors="coerce",
            ).fillna(0)
            == 0
        ).sum()
    )

    zero_after = int(
        (
            pd.to_numeric(
                coverage[
                    "historical_plausible_rows_after_term_filter"
                ],
                errors="coerce",
            ).fillna(0)
            == 0
        ).sum()
    )

    metrics = pd.DataFrame(
        [
            {
                "metric":
                    "second_associate_candidates",
                "value":
                    len(
                        targets
                    ),
            },
            {
                "metric":
                    "official_associate_pair_rows",
                "value":
                    len(
                        prior
                    ),
            },
            {
                "metric":
                    "historical_summary_source_files",
                "value":
                    len(
                        files
                    ),
            },
            {
                "metric":
                    "historical_summary_rows_read",
                "value":
                    total_rows_read,
            },
            {
                "metric":
                    "historical_rows_for_target_students",
                "value":
                    len(
                        historical
                    ),
            },
            {
                "metric":
                    "historical_complete_rows_for_target_students",
                "value":
                    len(
                        historical_complete
                    ),
            },
            {
                "metric":
                    "prior_pairs_zero_historical_complete_before_term_filter",
                "value":
                    zero_before,
            },
            {
                "metric":
                    "prior_pairs_zero_historical_plausible_after_term_filter",
                "value":
                    zero_after,
            },
            {
                "metric":
                    "unmapped_official_associate_families",
                "value":
                    len(
                        unresolved_families
                    ),
            },
        ]
    )

    metrics.to_csv(
        SAFE_METRICS,
        index=False,
    )

    print("=" * 112)
    print("HISTORICAL PRIOR-ASSOCIATE COVERAGE PROBE")
    print("=" * 112)
    print(
        f"Second-associate candidate combinations:      {len(targets):,}"
    )
    print(
        f"Official associate pair rows:                 {len(prior):,}"
    )
    print(
        f"Historical summary source files:              {len(files):,}"
    )
    print(
        f"Historical rows read:                         {total_rows_read:,}"
    )
    print(
        "Historical rows for target students:          "
        f"{len(historical):,}"
    )
    print(
        "Historical COMPLETE rows for target students: "
        f"{len(historical_complete):,}"
    )
    print(
        "Prior pairs with zero historical COMPLETE:    "
        f"{zero_before:,}"
    )
    print(
        "Prior pairs with zero plausible prior plan:   "
        f"{zero_after:,}"
    )
    print(
        "Unmapped official associate families:        "
        f"{len(unresolved_families):,}"
    )

    if unresolved_families:
        print(
            "  "
            + " | ".join(
                unresolved_families
            )
        )

    print()
    print("FAMILY COVERAGE")
    print(
        family_safe.to_string(
            index=False
        )
    )

    print()
    print("MODELED INVENTORY CANDIDATES FOR UNMAPPED FAMILIES")
    if unresolved_inventory.empty:
        print("NONE")
    else:
        print(
            unresolved_inventory.to_string(
                index=False
            )
        )

    print()
    print(
        "No second-associate decision was made."
    )
    print(
        "If historical coverage collapses the 286 missing prior plans, "
        "the generalized adjudicator should use full_actual_audit for prior-plan "
        "reconstruction while retaining the current refresh for candidate-state "
        "and current attempt evidence."
    )
    print()
    print(
        f"Historical summary source: {FULL_ACTUAL}"
    )
    print(
        f"Output directory:          {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
