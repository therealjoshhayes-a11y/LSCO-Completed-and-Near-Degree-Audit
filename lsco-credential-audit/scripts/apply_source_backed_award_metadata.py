from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


# ======================================================================================
# STEP 5B — APPLY SOURCE-BACKED CATALOG AWARD METADATA
# ======================================================================================
#
# Purpose:
#   Resolve the remaining CERTIFICATE-vs-IA and modern AA/AS identity gaps using
#   direct catalog evidence, WITHOUT changing the canonical catalog staging files
#   or the curated institutional-award crosswalk yet.
#
# Important controls:
#   * Exact credential_id overlay only.
#   * Does not change canonical lineage.
#   * Does not change governance pair disposition.
#   * Does not adjudicate second-associate hours.
#   * Does not adjudicate the 25% additional-certificate rule.
#   * Does not perform latest-catalog lineage selection.
#
# The earlier source probe's SAME-YEAR FILE NAME boolean is NOT used here. That
# probe matched individual endpoint years, so adjacent catalogs could be labeled
# "same year." The exact catalog path / credential year and direct program heading
# are the evidence used below.
#
# Run from repository root:
#   python -u .\scripts\apply_source_backed_award_metadata.py


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"

EXPECTED_ORDINARY_PASS = 1_108

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT_DIR = (
    REPORTING
    / f"source_backed_award_metadata_{STAMP}"
)

RESTRICTED_OUT = (
    OUT_DIR
    / "RESTRICTED_source_backed_award_metadata_candidates.csv"
)

RESTRICTED_REVIEW_OUT = (
    OUT_DIR
    / "RESTRICTED_source_backed_award_metadata_remaining_review.csv"
)

SAFE_OVERLAY_OUT = (
    OUT_DIR
    / "FERPA_SAFE_catalog_award_metadata_overlay.csv"
)

SAFE_ROUTE_OUT = (
    OUT_DIR
    / "FERPA_SAFE_source_backed_route_counts.csv"
)

SAFE_METADATA_OUT = (
    OUT_DIR
    / "FERPA_SAFE_source_backed_metadata_status.csv"
)

SAFE_METRICS_OUT = (
    OUT_DIR
    / "FERPA_SAFE_source_backed_metadata_metrics.csv"
)

KEY = [
    "student_id",
    "catalog_year",
    "credential_id",
]


# ======================================================================================
# SOURCE-BACKED CATALOG METADATA
# ======================================================================================
#
# These rows are catalog facts, not inferred from program hours.
#
# source_strength:
#   DIRECT_PROGRAM_HEADING
#       The exact program heading in the matching catalog explicitly states the
#       award type.
#
#   CATALOG_TOC_GROUPING
#       The matching catalog places the credential in the certificate list
#       immediately before the Institutional Awards section, but the probe did
#       not capture the full program heading. This one row is retained as REVIEW
#       below rather than automatically applied.
#
# 2021-22 Criminal Justice Law Enforcement is intentionally NOT auto-resolved.
# The supplied evidence captured its TOC placement but not the direct credential
# heading. That case remains reviewable rather than being inferred from continuity.


SOURCE_OVERLAY = [
    # Criminal Justice Law Enforcement — direct Certificate of Completion headings.
    {
        "catalog_year": "2022-2023",
        "credential_id": "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2022",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2022-2023\2022-2023_Catalog.docx",
        "source_basis": "Criminal Justice Law Enforcement — Certificate of Completion",
    },
    {
        "catalog_year": "2023-2024",
        "credential_id": "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2023",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2023-2024\2023-2024_Catalog.docx",
        "source_basis": "Criminal Justice Law Enforcement — Certificate of Completion",
    },
    {
        "catalog_year": "2024-2025",
        "credential_id": "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2024",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2024-2025\2024-2025_Catalog.docx",
        "source_basis": "Criminal Justice Law Enforcement — Certificate of Completion",
    },
    {
        "catalog_year": "2025-2026",
        "credential_id": "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2025",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2025-2026\2025-2026_Catalog.docx",
        "source_basis": "Criminal Justice Law Enforcement — Certificate of Completion",
    },
    {
        "catalog_year": "2026-2027",
        "credential_id": "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2026",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": "Criminal Justice Law Enforcement — Certificate of Completion",
    },

    # Medical Assisting — Certificate of Completion.
    {
        "catalog_year": "2022-2023",
        "credential_id": "MEDICAL_ASSISTING_2022",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2022-2023\2022-2023_Catalog.docx",
        "source_basis": "Medical Assisting — Certificate of Completion",
    },
    {
        "catalog_year": "2024-2025",
        "credential_id": "MEDICAL_ASSISTING_2024",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2024-2025\2024-2025_Catalog.docx",
        "source_basis": "Medical Assisting — Certificate of Completion",
    },

    # Robotics transition credential — Advanced Technical Certificate of Completion.
    {
        "catalog_year": "2026-2027",
        "credential_id": "ROBOTICS_AND_AUTOMATION_AAS_TO_ELECTROMECHANICAL_TECHNOLOGY_2026",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": (
            "Robotics and Automation AAS to Electromechanical Technology — "
            "Advanced Technical Certificate of Completion"
        ),
    },

    # Process Technology — Basic Certificate.
    {
        "catalog_year": "2022-2023",
        "credential_id": "PROCESS_TECHNOLOGY_2022",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2022-2023\2022-2023_Catalog.docx",
        "source_basis": "Process Technology — Basic Certificate",
    },
    {
        "catalog_year": "2023-2024",
        "credential_id": "PROCESS_TECHNOLOGY_2023",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2023-2024\2023-2024_Catalog.docx",
        "source_basis": "Process Technology — Basic Certificate",
    },
    {
        "catalog_year": "2024-2025",
        "credential_id": "PROCESS_TECHNOLOGY_2024",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2024-2025\2024-2025_Catalog.docx",
        "source_basis": "Process Technology — Basic Certificate",
    },
    {
        "catalog_year": "2025-2026",
        "credential_id": "PROCESS_TECHNOLOGY_2025",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\2025-2026 Catalog.pdf",
        "source_basis": "Process Technology — Basic Certificate",
    },
    {
        "catalog_year": "2026-2027",
        "credential_id": "PROCESS_TECHNOLOGY_2026",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": "Process Technology — Basic Certificate",
    },

    # IT Cybersecurity Basic — Certificate of Completion.
    {
        "catalog_year": "2026-2027",
        "credential_id": "IT_CYBERSECURITY_BASIC_2026",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": "IT Cybersecurity Basic — Certificate of Completion",
    },

    # Real Estate — Certificate of Completion.
    {
        "catalog_year": "2025-2026",
        "credential_id": "REAL_ESTATE_2025",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\2025-2026 Catalog.pdf",
        "source_basis": "Real Estate — Certificate of Completion",
    },
    {
        "catalog_year": "2026-2027",
        "credential_id": "REAL_ESTATE_2026",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": "Real Estate — Certificate of Completion",
    },

    # Dental Assisting — Certificate of Completion.
    {
        "catalog_year": "2024-2025",
        "credential_id": "DENTAL_ASSISTING_CERTIFICATE_OF_COMPLETION_2024",
        "award_category": "CERTIFICATE",
        "exact_degree_code": "",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2024-2025\2024-2025_Catalog.docx",
        "source_basis": "Dental Assisting — Certificate of Completion",
    },

    # Modern Liberal Arts — exact degree identity required for 2025+ same-degree-type rule.
    {
        "catalog_year": "2025-2026",
        "credential_id": "LIBERAL_ARTS_2025",
        "award_category": "ASSOCIATE",
        "exact_degree_code": "AA",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\2025-2026 Catalog.pdf",
        "source_basis": "Liberal Arts — Associate of Arts Degree",
    },
    {
        "catalog_year": "2026-2027",
        "credential_id": "LIBERAL_ARTS_2026",
        "award_category": "ASSOCIATE",
        "exact_degree_code": "AA",
        "source_strength": "DIRECT_PROGRAM_HEADING",
        "source_file": r"data\raw\catalogs\2026-2027\2026-2027_Catalog.docx",
        "source_basis": "Liberal Arts — Associate of Arts Degree",
    },
]


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def as_int(value: object) -> int:
    value = txt(value)
    if not value:
        return 0
    return int(float(value))


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


def route_row(row: pd.Series) -> str:
    governed = txt(
        row.get(
            "governed_dependency_disposition",
            "",
        )
    )

    if governed == "REPRESENTED_BY_OFFICIAL_AWARD":
        return "STOP_REPRESENTED_BY_OFFICIAL_AWARD"

    if governed == "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING":
        return "REVIEW_BEFORE_MULTIPLE_AWARD_TEST"

    if txt(
        row.get(
            "candidate_metadata_status",
            "",
        )
    ) == "REVIEW":
        return "REVIEW_CANDIDATE_AWARD_METADATA"

    category = txt(
        row.get(
            "candidate_award_category",
            "",
        )
    )

    if category == "ASSOCIATE":
        if as_int(
            row.get(
                "official_associate_award_count",
                0,
            )
        ) > 0:
            return "SECOND_ASSOCIATE_TEST_PENDING"

        return "NO_SECOND_ASSOCIATE_RULE"

    if category == "CERTIFICATE":
        if as_int(
            row.get(
                "official_certificate_award_count",
                0,
            )
        ) > 0:
            return "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"

        return "NO_ADDITIONAL_CERTIFICATE_RULE"

    if category == "INSTITUTIONAL_AWARD":
        return "INSTITUTIONAL_AWARD_MULTIPLE_POLICY_REVIEW"

    return "REVIEW_CANDIDATE_AWARD_METADATA"


def main() -> None:
    source_dir = latest_dir(
        "current_governed_dependency_screen_*",
        "RESTRICTED_current_governed_dependency_candidates.csv",
    )

    candidate_path = (
        source_dir
        / "RESTRICTED_current_governed_dependency_candidates.csv"
    )

    candidates = pd.read_csv(
        candidate_path,
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
            "Candidate universe is not unique at student/catalog/credential."
        )

    overlay = pd.DataFrame(
        SOURCE_OVERLAY
    )

    if overlay.duplicated(
        [
            "catalog_year",
            "credential_id",
        ]
    ).any():
        raise RuntimeError(
            "Source overlay contains duplicate credential-year keys."
        )

    OUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    overlay.to_csv(
        SAFE_OVERLAY_OUT,
        index=False,
    )

    work = candidates.copy()

    work[
        "source_metadata_overlay_applied"
    ] = False

    work[
        "source_metadata_source_file"
    ] = ""

    work[
        "source_metadata_source_basis"
    ] = ""

    work[
        "source_metadata_source_strength"
    ] = ""

    overlay_lookup = {
        (
            row.catalog_year,
            row.credential_id,
        ): row
        for row in overlay.itertuples(
            index=False
        )
    }

    current_keys = set(
        work[
            [
                "catalog_year",
                "credential_id",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    )

    overlay_missing_from_current = [
        key
        for key in overlay_lookup
        if key not in current_keys
    ]

    if overlay_missing_from_current:
        raise RuntimeError(
            "Source overlay contains credential-years absent from current "
            f"candidate universe: {overlay_missing_from_current}"
        )

    for index, row in work.iterrows():
        key = (
            txt(
                row[
                    "catalog_year"
                ]
            ),
            txt(
                row[
                    "credential_id"
                ]
            ),
        )

        source = overlay_lookup.get(
            key
        )

        if source is None:
            continue

        old_category = txt(
            row.get(
                "candidate_award_category",
                "",
            )
        )

        old_exact = txt(
            row.get(
                "candidate_exact_degree_code",
                "",
            )
        )

        # The overlay is allowed to resolve an ambiguity or sharpen exact
        # associate identity. It must not silently contradict already-resolved
        # metadata.
        if (
            old_category
            and old_category
            not in {
                "CERTIFICATE_OR_IA",
                "UNRESOLVED",
                source.award_category,
            }
        ):
            raise RuntimeError(
                "Source overlay contradicts current resolved award category: "
                f"{key} current={old_category} source={source.award_category}"
            )

        if (
            source.exact_degree_code
            and old_exact
            and source.exact_degree_code != old_exact
        ):
            # AA|AS ambiguity is represented as blank exact code in the current
            # layer. A genuinely resolved conflicting code is a hard stop.
            raise RuntimeError(
                "Source overlay contradicts current exact degree code: "
                f"{key} current={old_exact} source={source.exact_degree_code}"
            )

        work.at[
            index,
            "candidate_award_category",
        ] = source.award_category

        work.at[
            index,
            "candidate_metadata_status",
        ] = "RESOLVED"

        work.at[
            index,
            "candidate_award_category_basis",
        ] = "DIRECT_CATALOG_SOURCE_OVERLAY"

        if source.exact_degree_code:
            work.at[
                index,
                "candidate_exact_degree_code",
            ] = source.exact_degree_code

        if source.award_category == "ASSOCIATE":
            work.at[
                index,
                "candidate_exact_associate_degree_code_resolved",
            ] = bool(
                source.exact_degree_code
            )

        work.at[
            index,
            "source_metadata_overlay_applied",
        ] = True

        work.at[
            index,
            "source_metadata_source_file",
        ] = source.source_file

        work.at[
            index,
            "source_metadata_source_basis",
        ] = source.source_basis

        work.at[
            index,
            "source_metadata_source_strength",
        ] = source.source_strength

    # Re-route ONLY from already-computed governance disposition + corrected
    # candidate metadata. No governance relationships are changed here.
    work[
        "multiple_award_route_before_source_metadata"
    ] = work[
        "multiple_award_route"
    ]

    work[
        "multiple_award_route"
    ] = work.apply(
        route_row,
        axis=1,
    )

    work[
        "source_metadata_route_changed"
    ] = (
        work[
            "multiple_award_route"
        ]
        != work[
            "multiple_award_route_before_source_metadata"
        ]
    )

    # ------------------------------------------------------------------
    # Safety checks.
    # ------------------------------------------------------------------
    if len(
        work
    ) != EXPECTED_ORDINARY_PASS:
        raise RuntimeError(
            "Candidate row count changed after source metadata overlay."
        )

    if work.duplicated(
        KEY
    ).any():
        raise RuntimeError(
            "Candidate keys duplicated after source metadata overlay."
        )

    # The source layer must not alter governance disposition.
    if (
        work[
            "governed_dependency_disposition"
        ].isna().any()
    ):
        raise RuntimeError(
            "Governance disposition was lost."
        )

    # Every modern Liberal Arts row in this candidate universe must now resolve
    # exactly to AA.
    modern_la = work[
        work[
            "credential_id"
        ].isin(
            [
                "LIBERAL_ARTS_2025",
                "LIBERAL_ARTS_2026",
            ]
        )
    ]

    if not modern_la.empty:
        if not modern_la[
            "candidate_exact_degree_code"
        ].eq(
            "AA"
        ).all():
            raise RuntimeError(
                "Modern Liberal Arts exact degree code did not resolve to AA."
            )

        if not modern_la[
            "candidate_exact_associate_degree_code_resolved"
        ].astype(
            bool
        ).all():
            raise RuntimeError(
                "Modern Liberal Arts exact associate identity remains unresolved."
            )

    # Any remaining metadata REVIEW must be surfaced. Do not guess.
    remaining_metadata_review = work[
        work[
            "candidate_metadata_status"
        ].eq(
            "REVIEW"
        )
    ].copy()

    work.to_csv(
        RESTRICTED_OUT,
        index=False,
    )

    remaining_metadata_review.to_csv(
        RESTRICTED_REVIEW_OUT,
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe output.
    # ------------------------------------------------------------------
    route_summary = (
        work.groupby(
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
        SAFE_ROUTE_OUT,
        index=False,
    )

    metadata_summary = (
        work.groupby(
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

    metadata_summary.to_csv(
        SAFE_METADATA_OUT,
        index=False,
    )

    metrics = pd.DataFrame(
        [
            {
                "metric": "ordinary_awardability_pass_combinations",
                "value": len(
                    work
                ),
            },
            {
                "metric": "source_metadata_overlay_candidate_rows",
                "value": int(
                    work[
                        "source_metadata_overlay_applied"
                    ].astype(
                        bool
                    ).sum()
                ),
            },
            {
                "metric": "source_metadata_route_changes",
                "value": int(
                    work[
                        "source_metadata_route_changed"
                    ].astype(
                        bool
                    ).sum()
                ),
            },
            {
                "metric": "remaining_candidate_metadata_review",
                "value": len(
                    remaining_metadata_review
                ),
            },
            {
                "metric": "modern_liberal_arts_exact_aa_rows",
                "value": len(
                    modern_la
                ),
            },
            {
                "metric": "governance_review_candidates_unchanged",
                "value": int(
                    work[
                        "governed_dependency_disposition"
                    ].eq(
                        "REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING"
                    ).sum()
                ),
            },
            {
                "metric": "second_associate_test_pending",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "SECOND_ASSOCIATE_TEST_PENDING"
                    ).sum()
                ),
            },
            {
                "metric": "additional_certificate_25_percent_test_pending",
                "value": int(
                    work[
                        "multiple_award_route"
                    ].eq(
                        "ADDITIONAL_CERTIFICATE_25_PERCENT_TEST_PENDING"
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
    print("SOURCE-BACKED CATALOG AWARD METADATA — APPLIED")
    print("=" * 112)
    print(
        f"Ordinary awardability PASS combinations:      {len(work):,}"
    )
    print(
        "Candidate rows touched by source overlay:     "
        f"{int(work['source_metadata_overlay_applied'].astype(bool).sum()):,}"
    )
    print(
        "Routes changed by source metadata:           "
        f"{int(work['source_metadata_route_changed'].astype(bool).sum()):,}"
    )
    print(
        "Remaining candidate metadata REVIEW:         "
        f"{len(remaining_metadata_review):,}"
    )
    print(
        "Governance-review candidates (unchanged):    "
        f"{int(work['governed_dependency_disposition'].eq('REVIEW_GOVERNANCE_OR_OFFICIAL_MAPPING').sum()):,}"
    )
    print()
    print("ROUTES")
    print(
        route_summary.to_string(
            index=False
        )
    )
    print()
    print("METADATA STATUS")
    print(
        metadata_summary.to_string(
            index=False
        )
    )
    print()
    if remaining_metadata_review.empty:
        print("REMAINING METADATA REVIEW: 0")
    else:
        safe_remaining = (
            remaining_metadata_review.groupby(
                [
                    "catalog_year",
                    "credential_id",
                    "credential_title",
                    "candidate_lineage",
                    "candidate_award_category",
                    "multiple_award_route",
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

        print("REMAINING METADATA REVIEW")
        print(
            safe_remaining.to_string(
                index=False
            )
        )
    print()
    print(
        "Control: governance dispositions were NOT changed."
    )
    print(
        "Control: no second-associate or additional-certificate arithmetic "
        "was performed."
    )
    print(
        "Control: 2021-22 Criminal Justice Law Enforcement remains unresolved "
        "because the captured local evidence is TOC-level rather than a direct "
        "program heading."
    )
    print()
    print(
        f"Source governance screen: {source_dir}"
    )
    print(
        f"Output directory:         {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
