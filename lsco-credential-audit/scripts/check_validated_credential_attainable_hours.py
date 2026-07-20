from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIREMENTS = Path(
    "data/processed/catalogs/requirements_master_multiyear.csv"
)

VALIDATION = Path(
    "data/interim/catalogs/requirement_total_validation.csv"
)

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / (
    "validated_attainable_hours_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Validated_Attainable_Hours_KPI.csv"
SAFE_CENSUS = OUTPUT_DIR / "FERPA_SAFE_Validated_Attainable_Hours_Census.csv"
SAFE_ANOMALIES = OUTPUT_DIR / "FERPA_SAFE_Validated_Attainable_Hours_Anomalies.csv"


def first_existing(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def normalize(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def main() -> None:
    for path in (REQUIREMENTS, VALIDATION):
        if not path.exists():
            raise FileNotFoundError(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    val = pd.read_csv(
        VALIDATION,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_req = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "credit_hours",
    }

    missing_req = required_req - set(req.columns)

    if missing_req:
        raise ValueError(
            "Requirements file missing columns: "
            + ", ".join(sorted(missing_req))
        )

    catalog_col = first_existing(
        list(val.columns),
        [
            "catalog_year",
            "catalog",
            "catalog_version",
        ],
    )

    credential_col = first_existing(
        list(val.columns),
        [
            "credential_id",
            "credential_slug",
            "program_id",
            "credential",
        ],
    )

    displayed_total_col = first_existing(
        list(val.columns),
        [
            "displayed_program_total",
            "program_total_hours",
            "catalog_program_total",
            "displayed_total",
            "program_total",
            "catalog_total",
            "expected_hours",
        ],
    )

    status_col = first_existing(
        list(val.columns),
        [
            "validation_status",
            "status",
            "classification",
            "result",
        ],
    )

    missing_val = []

    if catalog_col is None:
        missing_val.append("catalog-year column")

    if credential_col is None:
        missing_val.append("credential identifier column")

    if displayed_total_col is None:
        missing_val.append("displayed program total column")

    if missing_val:
        raise ValueError(
            "Validation file is missing a recognizable "
            + ", ".join(missing_val)
            + ". Columns found: "
            + ", ".join(val.columns)
        )

    req["catalog_key"] = req["catalog_year"].map(normalize)
    req["credential_key"] = req["credential_id"].map(normalize)

    val["catalog_key"] = val[catalog_col].map(normalize)
    val["credential_key"] = val[credential_col].map(normalize)

    req["credit_hours_num"] = pd.to_numeric(
        req["credit_hours"],
        errors="coerce",
    )

    one_per_requirement = (
        req.sort_values(
            [
                "catalog_key",
                "credential_key",
                "requirement_id",
            ],
            kind="mergesort",
        )
        .drop_duplicates(
            [
                "catalog_key",
                "credential_key",
                "requirement_id",
            ],
            keep="first",
        )
        .copy()
    )

    executable = (
        one_per_requirement.groupby(
            ["catalog_key", "credential_key"],
            dropna=False,
        )
        .agg(
            requirement_count=(
                "requirement_id",
                "nunique",
            ),
            executable_minimum_hours=(
                "credit_hours_num",
                "sum",
            ),
            zero_or_missing_hour_requirements=(
                "credit_hours_num",
                lambda s: int(
                    s.isna().sum()
                    + (s.fillna(0) <= 0).sum()
                ),
            ),
        )
        .reset_index()
    )

    validation_rows = val.copy()

    if "validation_level" in validation_rows.columns:
        validation_rows = validation_rows[
            validation_rows["validation_level"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("PROGRAM")
        ].copy()

    validation_rows["displayed_program_total_num"] = pd.to_numeric(
        validation_rows[displayed_total_col],
        errors="coerce",
    )

    keep_cols = [
        "catalog_key",
        "credential_key",
        displayed_total_col,
        "displayed_program_total_num",
    ]

    if status_col is not None:
        keep_cols.append(status_col)

    if "classified_status" in validation_rows.columns:
        keep_cols.append("classified_status")

    validation_rows = validation_rows[keep_cols].copy()

    if status_col is not None:
        validation_rows = validation_rows.rename(
            columns={
                status_col: "source_validation_status",
            }
        )

    validation_rows = (
        validation_rows
        .drop_duplicates(
            ["catalog_key", "credential_key"],
            keep="first",
        )
    )

    merged = executable.merge(
        validation_rows,
        on=["catalog_key", "credential_key"],
        how="left",
        validate="one_to_one",
    )

    merged["difference_hours"] = (
        merged["executable_minimum_hours"]
        - merged["displayed_program_total_num"]
    )

    def classify(row: pd.Series) -> str:
        source_status = str(
            row.get("source_validation_status", "")
        ).strip().upper()

        source_classified_status = str(
            row.get("classified_status", "")
        ).strip().upper()

        if (
            source_classified_status == "OK_OFFICIAL_LOW_HOUR_AAS"
            or source_status == "OK_OFFICIAL_LOW_HOUR_AAS"
        ):
            return "DOCUMENTED_OFFICIAL_LOW_HOUR_AAS"

        if pd.isna(row["displayed_program_total_num"]):
            return "NO_VALIDATED_TOTAL_MATCH"

        if row["zero_or_missing_hour_requirements"] > 0:
            return "REVIEW_ZERO_OR_MISSING_REQUIREMENT_HOURS"

        difference = float(row["difference_hours"])

        if abs(difference) < 0.001:
            return "MATCH"

        if difference < 0:
            return "EXECUTABLE_MINIMUM_BELOW_VALIDATED_TOTAL"

        return "EXECUTABLE_MINIMUM_ABOVE_VALIDATED_TOTAL"

    merged["status"] = merged.apply(
        classify,
        axis=1,
    )

    merged = merged.rename(
        columns={
            "catalog_key": "catalog_year",
            "credential_key": "credential_id",
            displayed_total_col: "validated_program_total_raw",
        }
    )

    anomalies = merged[
        ~merged["status"].eq("MATCH")
    ].copy()

    kpis = (
        merged["status"]
        .value_counts(dropna=False)
        .rename_axis("metric")
        .reset_index(name="value")
    )

    metadata = pd.DataFrame(
        [
            {
                "metric": "Credential-year rows",
                "value": len(merged),
            },
            {
                "metric": "Validation catalog column used",
                "value": catalog_col,
            },
            {
                "metric": "Validation credential column used",
                "value": credential_col,
            },
            {
                "metric": "Validation total column used",
                "value": displayed_total_col,
            },
            {
                "metric": "Validation status column used",
                "value": status_col or "",
            },
        ]
    )

    kpis = pd.concat(
        [metadata, kpis],
        ignore_index=True,
    )

    sort_cols = [
        column
        for column in [
            "status",
            "catalog_year",
            "credential_id",
        ]
        if column in merged.columns
    ]

    merged = merged.sort_values(
        sort_cols,
        kind="mergesort",
    )

    anomalies = anomalies.sort_values(
        sort_cols,
        kind="mergesort",
    )

    kpis.to_csv(SAFE_KPI, index=False)
    merged.to_csv(SAFE_CENSUS, index=False)
    anomalies.to_csv(SAFE_ANOMALIES, index=False)

    print("=" * 100)
    print("VALIDATED MINIMUM ATTAINABLE HOURS CHECK")
    print("=" * 100)
    print(f"Credential-year rows: {len(merged):,}")
    print(f"Validation catalog column: {catalog_col}")
    print(f"Validation credential column: {credential_col}")
    print(f"Validation total column: {displayed_total_col}")
    print(f"Validation status column: {status_col or '[none]'}")
    print()
    print("Status counts:")
    print(
        merged["status"]
        .value_counts()
        .to_string()
    )
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"Census: {SAFE_CENSUS}")
    print(f"Anomalies: {SAFE_ANOMALIES}")
    print()
    print("UPLOAD ALL THREE FERPA-SAFE CSV FILES.")
    print("VALIDATED-HOURS GATE: PASSED")


if __name__ == "__main__":
    main()
