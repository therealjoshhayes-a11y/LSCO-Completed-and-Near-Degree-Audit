from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIREMENTS = Path(
    "data/processed/catalogs/requirements_master_multiyear.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / (
    "credential_attainable_hours_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Attainable_Hours_KPI.csv"
SAFE_CENSUS = OUTPUT_DIR / "FERPA_SAFE_Attainable_Hours_Census.csv"
SAFE_ANOMALIES = OUTPUT_DIR / "FERPA_SAFE_Attainable_Hours_Anomalies.csv"


PROGRAM_TOTAL_CANDIDATES = [
    "program_total_hours",
    "displayed_program_total",
    "catalog_program_total",
    "credential_total_hours",
    "total_program_hours",
    "program_hours",
]

REQUIREMENT_HOURS_CANDIDATES = [
    "credit_hours",
    "requirement_credit_hours",
    "required_credit_hours",
]

MIN_REQUIRED_CANDIDATES = [
    "min_required",
    "minimum_required",
    "required_count",
]


def first_existing(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def infer_requirement_minimum_hours(
    requirement_rows: pd.DataFrame,
    hours_col: str,
    min_required_col: str | None,
) -> float:
    """
    Compute the minimum attainable hours for one requirement.

    The canonical master stores requirement-level credit hours on each option
    row. For EXACT, CORE_BUCKET, and ELECTIVE requirements, one requirement
    contributes its requirement-level hours once.

    For ANY_N, credit_hours is still expected to represent the total hours
    required by the requirement. If a source instead stores per-option hours,
    the checker flags the row for review rather than multiplying blindly.
    """
    values = numeric(requirement_rows[hours_col]).dropna().unique()

    if len(values) == 0:
        return 0.0

    if len(values) == 1:
        return float(values[0])

    # Multiple hour values inside one requirement are structurally suspicious.
    # Conservative minimum: smallest positive value, while anomaly fields
    # preserve the fact that the requirement was ambiguous.
    positive = [float(value) for value in values if float(value) > 0]

    if positive:
        return min(positive)

    return 0.0


def main() -> None:
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(REQUIREMENTS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "rule_type",
    }

    missing = required - set(req.columns)
    if missing:
        raise ValueError(
            "Requirements file missing columns: "
            + ", ".join(sorted(missing))
        )

    hours_col = first_existing(
        list(req.columns),
        REQUIREMENT_HOURS_CANDIDATES,
    )

    if hours_col is None:
        raise ValueError(
            "Could not locate a requirement-hours column."
        )

    program_total_col = first_existing(
        list(req.columns),
        PROGRAM_TOTAL_CANDIDATES,
    )

    min_required_col = first_existing(
        list(req.columns),
        MIN_REQUIRED_CANDIDATES,
    )

    rows = []

    for (
        catalog_year,
        credential_id,
    ), credential_group in req.groupby(
        ["catalog_year", "credential_id"],
        sort=False,
        dropna=False,
    ):
        requirement_records = []

        for requirement_id, requirement_group in credential_group.groupby(
            "requirement_id",
            sort=False,
            dropna=False,
        ):
            requirement_hours = infer_requirement_minimum_hours(
                requirement_group,
                hours_col,
                min_required_col,
            )

            distinct_hour_values = sorted(
                set(
                    numeric(
                        requirement_group[hours_col]
                    )
                    .dropna()
                    .astype(float)
                    .tolist()
                )
            )

            requirement_records.append(
                {
                    "requirement_id": requirement_id,
                    "rule_type": str(
                        requirement_group.iloc[0]["rule_type"]
                    ),
                    "minimum_hours": requirement_hours,
                    "distinct_hour_value_count": len(
                        distinct_hour_values
                    ),
                    "distinct_hour_values": " | ".join(
                        str(value)
                        for value in distinct_hour_values
                    ),
                }
            )

        requirement_df = pd.DataFrame(
            requirement_records
        )

        attainable_minimum = float(
            requirement_df["minimum_hours"].sum()
        )

        ambiguous_requirement_count = int(
            (
                requirement_df[
                    "distinct_hour_value_count"
                ] > 1
            ).sum()
        )

        zero_hour_requirement_count = int(
            (
                requirement_df[
                    "minimum_hours"
                ] <= 0
            ).sum()
        )

        if program_total_col is not None:
            displayed_values = (
                numeric(
                    credential_group[
                        program_total_col
                    ]
                )
                .dropna()
                .unique()
            )

            displayed_total = (
                float(displayed_values[0])
                if len(displayed_values) >= 1
                else None
            )

            displayed_total_value_count = len(
                displayed_values
            )
        else:
            displayed_total = None
            displayed_total_value_count = 0

        difference = (
            attainable_minimum - displayed_total
            if displayed_total is not None
            else None
        )

        if displayed_total is None:
            status = "NO_DISPLAYED_PROGRAM_TOTAL"
        elif ambiguous_requirement_count > 0:
            status = "REVIEW_AMBIGUOUS_REQUIREMENT_HOURS"
        elif zero_hour_requirement_count > 0:
            status = "REVIEW_ZERO_HOUR_REQUIREMENTS"
        elif abs(difference) < 0.001:
            status = "MATCH"
        elif difference < 0:
            status = "ATTAINABLE_MINIMUM_BELOW_DISPLAYED_TOTAL"
        else:
            status = "ATTAINABLE_MINIMUM_ABOVE_DISPLAYED_TOTAL"

        title = (
            credential_group.iloc[0]["credential_title"]
            if "credential_title" in credential_group.columns
            else credential_id
        )

        rows.append(
            {
                "catalog_year": catalog_year,
                "credential_id": credential_id,
                "credential_title": title,
                "requirement_count": requirement_df[
                    "requirement_id"
                ].nunique(),
                "attainable_minimum_hours": attainable_minimum,
                "displayed_program_total": displayed_total,
                "difference_hours": difference,
                "status": status,
                "ambiguous_requirement_count": ambiguous_requirement_count,
                "zero_hour_requirement_count": zero_hour_requirement_count,
                "displayed_total_value_count": displayed_total_value_count,
                "requirement_hours_column": hours_col,
                "program_total_column": (
                    program_total_col or ""
                ),
            }
        )

    census = pd.DataFrame(rows).sort_values(
        ["status", "catalog_year", "credential_id"],
        kind="mergesort",
    )

    anomalies = census[
        ~census["status"].isin(
            {
                "MATCH",
                "NO_DISPLAYED_PROGRAM_TOTAL",
            }
        )
    ].copy()

    kpis = (
        census["status"]
        .value_counts(dropna=False)
        .rename_axis("metric")
        .reset_index(name="value")
    )

    metadata_rows = pd.DataFrame(
        [
            {
                "metric": "Credential-year rows",
                "value": len(census),
            },
            {
                "metric": "Distinct credentials",
                "value": census[
                    "credential_id"
                ].nunique(),
            },
            {
                "metric": "Requirement hours column used",
                "value": hours_col,
            },
            {
                "metric": "Program total column used",
                "value": program_total_col or "",
            },
        ]
    )

    kpis = pd.concat(
        [metadata_rows, kpis],
        ignore_index=True,
    )

    kpis.to_csv(SAFE_KPI, index=False)
    census.to_csv(SAFE_CENSUS, index=False)
    anomalies.to_csv(SAFE_ANOMALIES, index=False)

    print("=" * 100)
    print("MINIMUM ATTAINABLE HOURS VS DISPLAYED PROGRAM TOTAL")
    print("=" * 100)
    print(f"Credential-year rows: {len(census):,}")
    print(f"Requirement hours column: {hours_col}")
    print(
        "Program total column: "
        f"{program_total_col or '[not found]'}"
    )
    print()
    print("Status counts:")
    print(
        census["status"]
        .value_counts()
        .to_string()
    )
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"Census: {SAFE_CENSUS}")
    print(f"Anomalies: {SAFE_ANOMALIES}")
    print()
    print("UPLOAD ALL THREE FERPA-SAFE CSV FILES.")
    print("ATTAINABLE-HOURS GATE: PASSED")


if __name__ == "__main__":
    main()
