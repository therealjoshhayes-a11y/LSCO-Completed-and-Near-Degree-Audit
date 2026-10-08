from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/requirements_master_multiyear.csv"
)

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"audit_lineage_type_probe_{RUN_STAMP}"

CENSUS = OUTPUT_DIR / "FERPA_SAFE_audit_lineage_type_census.csv"
CREDENTIALS = OUTPUT_DIR / "FERPA_SAFE_audit_credential_year_types.csv"
COLLISIONS = OUTPUT_DIR / "FERPA_SAFE_same_title_type_collisions.csv"


def normalize_text(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def derive_lineage(credential_id: object) -> str:
    value = normalize_text(credential_id)
    value = re.sub(
        r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026|2026_2027)$",
        "",
        value,
    )
    value = re.sub(
        r"_(2021|2022|2023|2024|2025|2026)$",
        "",
        value,
    )

    # Existing governed override already used by the award selector.
    if value == "REAL_ESTATE_MANAGEMENT_2025":
        return "BUSINESS_REAL_ESTATE_MANAGEMENT"

    return value


def infer_program_hours(group: pd.DataFrame) -> float | None:
    one_per_requirement = (
        group.sort_values("requirement_id", kind="mergesort")
        .drop_duplicates("requirement_id", keep="first")
        .copy()
    )

    hours = pd.to_numeric(
        one_per_requirement["credit_hours"],
        errors="coerce",
    )

    if not hours.notna().any():
        return None

    return float(hours.fillna(0).sum())


def infer_award_type(
    title: object,
    credential_id: object,
    program_hours: float | None,
) -> str:
    text = f"{normalize_text(title)} {normalize_text(credential_id)}"

    explicit = [
        ("AAT", [r"\bAAT\b", r"ASSOCIATE OF ARTS TEACHING"]),
        ("AAS", [r"\bAAS\b", r"ASSOCIATE OF APPLIED SCIENCE"]),
        ("AA", [r"\bAA\b", r"ASSOCIATE OF ARTS"]),
        ("AS", [r"\bAS\b", r"ASSOCIATE OF SCIENCE"]),
        ("CERTIFICATE", [r"\bCERT\b", r"CERTIFICATE"]),
        ("IA", [r"\bIA\b", r"INSTITUTIONAL AWARD"]),
    ]

    for label, patterns in explicit:
        if any(re.search(pattern, text) for pattern in patterns):
            return label

    # Hours are only a diagnostic fallback, never a governed award-type decision.
    if program_hours is not None:
        if program_hours >= 55:
            return "UNKNOWN_HIGH_HOURS"
        if program_hours <= 45:
            return "UNKNOWN_LOW_HOURS"

    return "UNKNOWN"


def normalized_title(value: object) -> str:
    text = normalize_text(value).replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def joined(values) -> str:
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
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(REQUIREMENTS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "credit_hours",
    }

    missing = required - set(req.columns)

    if missing:
        raise RuntimeError(
            "Requirements master missing columns: "
            + ", ".join(sorted(missing))
        )

    title_col = (
        "credential_title"
        if "credential_title" in req.columns
        else None
    )

    rows = []

    for (catalog_year, credential_id), group in req.groupby(
        ["catalog_year", "credential_id"],
        sort=False,
    ):
        title = (
            str(group.iloc[0][title_col])
            if title_col
            else str(credential_id)
        )

        hours = infer_program_hours(group)

        rows.append(
            {
                "catalog_year": str(catalog_year),
                "credential_id": str(credential_id),
                "credential_title": title,
                "credential_lineage": derive_lineage(credential_id),
                "inferred_program_hours": (
                    "" if hours is None else hours
                ),
                "inferred_award_type": infer_award_type(
                    title,
                    credential_id,
                    hours,
                ),
                "requirement_count": group["requirement_id"].nunique(),
                "normalized_title": normalized_title(title),
            }
        )

    credentials = pd.DataFrame(rows)

    credentials.to_csv(
        CREDENTIALS,
        index=False,
    )

    census = (
        credentials.groupby(
            "credential_lineage",
            dropna=False,
        )
        .agg(
            catalog_year_count=("catalog_year", "nunique"),
            credential_year_count=("credential_id", "size"),
            min_program_hours=("inferred_program_hours", "min"),
            max_program_hours=("inferred_program_hours", "max"),
            award_types=("inferred_award_type", joined),
            credential_titles=("credential_title", joined),
            credential_ids=("credential_id", joined),
            catalog_years=("catalog_year", joined),
        )
        .reset_index()
        .sort_values(
            "credential_lineage",
            kind="mergesort",
        )
    )

    census.to_csv(
        CENSUS,
        index=False,
    )

    collision_rows = []

    for (catalog_year, title_key), group in credentials.groupby(
        ["catalog_year", "normalized_title"],
        sort=False,
    ):
        if len(group) <= 1:
            continue

        collision_rows.append(
            {
                "catalog_year": catalog_year,
                "normalized_title": title_key,
                "credential_count": len(group),
                "credential_ids": joined(group["credential_id"]),
                "lineages": joined(group["credential_lineage"]),
                "award_types": joined(group["inferred_award_type"]),
                "program_hours": joined(group["inferred_program_hours"]),
            }
        )

    collisions = pd.DataFrame(collision_rows)

    if collisions.empty:
        collisions = pd.DataFrame(
            columns=[
                "catalog_year",
                "normalized_title",
                "credential_count",
                "credential_ids",
                "lineages",
                "award_types",
                "program_hours",
            ]
        )

    collisions.to_csv(
        COLLISIONS,
        index=False,
    )

    print("=" * 100)
    print("AUDIT LINEAGE TYPE / HOURS PROBE")
    print("=" * 100)
    print(f"Credential-years:                       {len(credentials):,}")
    print(f"Distinct lineages:                      {credentials['credential_lineage'].nunique():,}")
    print(f"Same-title same-year collisions:        {len(collisions):,}")
    print()
    print("INFERRED AWARD TYPES")
    print(
        credentials[
            "inferred_award_type"
        ].value_counts(
            dropna=False
        ).to_string()
    )
    print()
    print(f"FERPA-safe census: {CENSUS}")
    print(f"FERPA-safe credential-year detail: {CREDENTIALS}")
    print(f"FERPA-safe collisions: {COLLISIONS}")


if __name__ == "__main__":
    main()
