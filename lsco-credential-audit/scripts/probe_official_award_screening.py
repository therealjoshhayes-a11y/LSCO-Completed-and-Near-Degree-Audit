from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import profile_refresh_delta as refresh  # noqa: E402
import select_maximum_awards as award_select  # noqa: E402


PRIOR_AWARDS = refresh.DEFAULT_PRIOR_AWARDS
NEW_AWARDS = refresh.DEFAULT_NEW_AWARDS

STAGED_REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/requirements_master_multiyear.csv"
)

LOCAL_LINEAGE_CROSSWALK = Path(
    "data/processed/reporting/credential_lineage_crosswalk.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"official_award_screening_probe_{RUN_STAMP}"


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def normalized_join(values) -> str:
    return " | ".join(
        sorted(
            {
                str(value).strip()
                for value in values
                if str(value).strip()
            }
        )
    )


def main() -> None:
    for path in (
        PRIOR_AWARDS,
        NEW_AWARDS,
        STAGED_REQUIREMENTS,
    ):
        require(path)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    prior, prior_sheet = refresh.read_awards(
        PRIOR_AWARDS,
        preferred_sheet="Initial Enr Cohort Awards",
        source_label="PRIOR_OFFICIAL_AWARDS",
    )

    new, new_sheet = refresh.read_awards(
        NEW_AWARDS,
        preferred_sheet="Summer 2026 Awards",
        source_label="SUMMER_2026_OFFICIAL_AWARDS",
    )

    prior_dedup = prior.drop_duplicates(
        subset=[
            column
            for column in prior.columns
            if column != "source_dataset"
        ],
        keep="first",
    ).copy()

    award_key = [
        "ID",
        "Major1Code",
        "DegreeCode",
        "StudGradTerm",
    ]

    old_keys = set(
        map(
            tuple,
            prior_dedup[award_key].values.tolist(),
        )
    )

    new_keys = set(
        map(
            tuple,
            new[award_key].values.tolist(),
        )
    )

    overlap = old_keys & new_keys

    combined = pd.concat(
        [
            prior_dedup,
            new,
        ],
        ignore_index=True,
    )

    expected = {
        "prior_raw": 5284,
        "prior_dedup": 5277,
        "new_rows": 203,
        "overlap": 0,
        "combined": 5480,
    }

    observed = {
        "prior_raw": len(prior),
        "prior_dedup": len(prior_dedup),
        "new_rows": len(new),
        "overlap": len(overlap),
        "combined": len(combined),
    }

    if observed != expected:
        raise RuntimeError(
            "Official-award source reconciliation changed.\n"
            f"Expected: {expected}\n"
            f"Observed: {observed}\n"
            "Stop before building any suppression crosswalk."
        )

    group_columns = [
        "Curr1ProgramCode",
        "Major1Code",
        "MajorDesc",
        "DegreeCode",
        "DegreeDesc",
        "CIPCode",
    ]

    inventory = (
        combined.groupby(
            group_columns,
            dropna=False,
        )
        .agg(
            official_award_rows=(
                "ID",
                "size",
            ),
            first_grad_term=(
                "StudGradTerm",
                "min",
            ),
            last_grad_term=(
                "StudGradTerm",
                "max",
            ),
            degree_status_values=(
                "DegreeStat",
                normalized_join,
            ),
            source_datasets=(
                "source_dataset",
                normalized_join,
            ),
        )
        .reset_index()
        .sort_values(
            [
                "DegreeCode",
                "MajorDesc",
                "Major1Code",
                "Curr1ProgramCode",
            ],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    inventory.insert(
        0,
        "official_award_code_id",
        [
            f"OFFICIAL_{index:04d}"
            for index in range(
                1,
                len(inventory) + 1,
            )
        ],
    )

    inventory.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_official_award_code_inventory.csv",
        index=False,
    )

    requirements = pd.read_csv(
        STAGED_REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "catalog_year",
        "credential_id",
    }

    missing = (
        required_columns
        - set(requirements.columns)
    )

    if missing:
        raise RuntimeError(
            "Staged requirements missing columns: "
            + ", ".join(sorted(missing))
        )

    credential_columns = [
        "catalog_year",
        "credential_id",
    ]

    if "credential_title" in requirements.columns:
        credential_columns.append(
            "credential_title"
        )

    credential_rows = (
        requirements[
            credential_columns
        ]
        .drop_duplicates()
        .copy()
    )

    credential_rows[
        "credential_lineage"
    ] = credential_rows[
        "credential_id"
    ].map(
        award_select.derive_lineage
    )

    lineage_inventory = (
        credential_rows.groupby(
            "credential_lineage",
            dropna=False,
        )
        .agg(
            credential_year_count=(
                "credential_id",
                "size",
            ),
            credential_ids=(
                "credential_id",
                normalized_join,
            ),
            catalog_years=(
                "catalog_year",
                normalized_join,
            ),
        )
        .reset_index()
        .sort_values(
            "credential_lineage",
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    if "credential_title" in credential_rows.columns:
        titles = (
            credential_rows.groupby(
                "credential_lineage",
                dropna=False,
            )["credential_title"]
            .agg(normalized_join)
            .rename("credential_titles")
            .reset_index()
        )

        lineage_inventory = (
            lineage_inventory.merge(
                titles,
                on="credential_lineage",
                how="left",
                validate="one_to_one",
            )
        )

    lineage_inventory.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_audit_lineage_inventory.csv",
        index=False,
    )

    local_crosswalk_status = "ABSENT"

    if LOCAL_LINEAGE_CROSSWALK.exists():
        crosswalk = pd.read_csv(
            LOCAL_LINEAGE_CROSSWALK,
            dtype=str,
            low_memory=False,
        ).fillna("")

        required_crosswalk = {
            "credential_id",
            "credential_lineage",
        }

        missing_crosswalk = (
            required_crosswalk
            - set(crosswalk.columns)
        )

        if missing_crosswalk:
            raise RuntimeError(
                "Local credential-lineage crosswalk exists but is "
                "missing columns: "
                + ", ".join(
                    sorted(missing_crosswalk)
                )
            )

        safe_crosswalk = (
            crosswalk[
                [
                    "credential_id",
                    "credential_lineage",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                [
                    "credential_lineage",
                    "credential_id",
                ],
                kind="mergesort",
            )
        )

        safe_crosswalk.to_csv(
            OUTPUT_DIR
            / "FERPA_SAFE_local_credential_lineage_crosswalk.csv",
            index=False,
        )

        local_crosswalk_status = (
            f"PRESENT ({len(safe_crosswalk):,} rows)"
        )

    metrics = pd.DataFrame(
        [
            {
                "metric": "historical_award_rows_raw",
                "value": len(prior),
            },
            {
                "metric": "historical_award_rows_exact_deduped",
                "value": len(prior_dedup),
            },
            {
                "metric": "new_summer_2026_award_rows",
                "value": len(new),
            },
            {
                "metric": "overlap_new_vs_historical_award_keys",
                "value": len(overlap),
            },
            {
                "metric": "canonical_official_award_rows",
                "value": len(combined),
            },
            {
                "metric": "unique_official_award_code_combinations",
                "value": len(inventory),
            },
            {
                "metric": "audit_credential_lineages",
                "value": len(lineage_inventory),
            },
            {
                "metric": "historical_award_sheet",
                "value": prior_sheet,
            },
            {
                "metric": "new_award_sheet",
                "value": new_sheet,
            },
            {
                "metric": "local_credential_lineage_crosswalk",
                "value": local_crosswalk_status,
            },
        ]
    )

    metrics.to_csv(
        OUTPUT_DIR
        / "FERPA_SAFE_probe_metrics.csv",
        index=False,
    )

    print("=" * 100)
    print("OFFICIAL AWARD SCREENING — FERPA-SAFE PROBE")
    print("=" * 100)
    print(
        f"Historical raw official awards:              {len(prior):,}"
    )
    print(
        f"Historical after exact dedupe:               {len(prior_dedup):,}"
    )
    print(
        f"Summer 2026 official awards:                 {len(new):,}"
    )
    print(
        f"Overlap with historical award keys:          {len(overlap):,}"
    )
    print(
        f"Canonical official-award rows:               {len(combined):,}"
    )
    print()
    print(
        f"Unique official award-code combinations:     {len(inventory):,}"
    )
    print(
        f"Current audit credential lineages:           {len(lineage_inventory):,}"
    )
    print(
        f"Local credential-lineage crosswalk:          {local_crosswalk_status}"
    )
    print()
    print("OFFICIAL AWARD CODE INVENTORY BY DEGREE CODE")
    print(
        inventory.groupby(
            "DegreeCode",
            dropna=False,
        )
        .agg(
            code_combinations=(
                "official_award_code_id",
                "size",
            ),
            official_award_rows=(
                "official_award_rows",
                "sum",
            ),
        )
        .to_string()
    )
    print()
    print(
        f"FERPA-safe output directory: {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
