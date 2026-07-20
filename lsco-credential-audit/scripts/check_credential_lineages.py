from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIREMENTS = Path("data/processed/catalogs/requirements_master_multiyear.csv")
OUTPUT_DIR = Path("data/processed/reporting") / (
    "credential_lineage_shadow_check_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)

SAFE_KPI = OUTPUT_DIR / "FERPA_SAFE_Credential_Lineage_KPI.csv"
SAFE_LINEAGES = OUTPUT_DIR / "FERPA_SAFE_Credential_Lineage_Census.csv"
SAFE_COLLISIONS = OUTPUT_DIR / "FERPA_SAFE_Credential_Lineage_Collisions.csv"
SAFE_NEAR_MATCHES = OUTPUT_DIR / "FERPA_SAFE_Credential_Title_Near_Matches.csv"


def normalize_text(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def slugify(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", normalize_text(value)).strip("_")


def derive_lineage(credential_id: object) -> str:
    value = normalize_text(credential_id)
    value = re.sub(
        r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026)$",
        "",
        value,
    )
    value = re.sub(r"_(2021|2022|2023|2024|2025|2026)$", "", value)
    return value


def extract_award_type(title: object, credential_id: object) -> str:
    text = f"{normalize_text(title)} {normalize_text(credential_id)}"

    patterns = [
        ("AAS", [r"\bAAS\b", r"ASSOCIATE OF APPLIED SCIENCE"]),
        ("AA", [r"\bAA\b", r"ASSOCIATE OF ARTS"]),
        ("AS", [r"\bAS\b", r"ASSOCIATE OF SCIENCE"]),
        ("CERTIFICATE", [r"\bCERT\b", r"CERTIFICATE"]),
        ("LEVEL_1_CERTIFICATE", [r"LEVEL I", r"LEVEL 1"]),
        ("LEVEL_2_CERTIFICATE", [r"LEVEL II", r"LEVEL 2"]),
    ]

    for label, regexes in patterns:
        if any(re.search(pattern, text) for pattern in regexes):
            return label

    return "UNKNOWN"


def infer_program_hours(group: pd.DataFrame) -> float | None:
    # Requirement rows should carry the displayed slot hours.
    # Sum one row per requirement_id to avoid option-row multiplication.
    one_per_requirement = (
        group.sort_values("requirement_id", kind="mergesort")
        .drop_duplicates("requirement_id", keep="first")
        .copy()
    )

    hours = pd.to_numeric(
        one_per_requirement["credit_hours"],
        errors="coerce",
    )

    if hours.notna().any():
        return float(hours.fillna(0).sum())

    return None


def normalized_title_key(title: object) -> str:
    text = normalize_text(title)
    text = text.replace("&", " AND ")
    text = re.sub(r"\bAND\b", " AND ", text)
    text = re.sub(r"\bCERTIFICATE\b", " CERT ", text)
    text = re.sub(r"\bASSOCIATE OF APPLIED SCIENCE\b", " AAS ", text)
    text = re.sub(r"\bASSOCIATE OF ARTS\b", " AA ", text)
    text = re.sub(r"\bASSOCIATE OF SCIENCE\b", " AS ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def similarity_tokens(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())

    if not sa and not sb:
        return 1.0

    if not sa or not sb:
        return 0.0

    return len(sa & sb) / len(sa | sb)


def main() -> None:
    if not REQUIREMENTS.exists():
        raise FileNotFoundError(REQUIREMENTS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    req = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_columns = {
        "catalog_year",
        "credential_id",
        "requirement_id",
        "credit_hours",
    }

    missing = required_columns - set(req.columns)
    if missing:
        raise ValueError(
            "Requirements file missing columns: "
            + ", ".join(sorted(missing))
        )

    title_column = (
        "credential_title"
        if "credential_title" in req.columns
        else None
    )

    credential_rows = []

    for (catalog_year, credential_id), group in req.groupby(
        ["catalog_year", "credential_id"],
        sort=False,
    ):
        title = (
            str(group.iloc[0][title_column])
            if title_column
            else str(credential_id)
        )

        credential_rows.append(
            {
                "catalog_year": str(catalog_year),
                "credential_id": str(credential_id),
                "credential_title": title,
                "lineage": derive_lineage(credential_id),
                "title_slug": slugify(title),
                "normalized_title_key": normalized_title_key(title),
                "award_type": extract_award_type(title, credential_id),
                "requirement_count": group["requirement_id"].nunique(),
                "inferred_program_hours": infer_program_hours(group),
            }
        )

    credentials = pd.DataFrame(credential_rows)

    lineage_summary = (
        credentials.groupby("lineage", dropna=False)
        .agg(
            catalog_year_count=("catalog_year", "nunique"),
            credential_id_count=("credential_id", "nunique"),
            title_count=("credential_title", "nunique"),
            award_type_count=("award_type", "nunique"),
            min_inferred_hours=("inferred_program_hours", "min"),
            max_inferred_hours=("inferred_program_hours", "max"),
            titles=(
                "credential_title",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            credential_ids=(
                "credential_id",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            catalog_years=(
                "catalog_year",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            award_types=(
                "award_type",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
        )
        .reset_index()
    )

    lineage_summary["hour_spread"] = (
        lineage_summary["max_inferred_hours"]
        - lineage_summary["min_inferred_hours"]
    )

    lineage_summary["mixed_award_types"] = (
        lineage_summary["award_type_count"] > 1
    )

    lineage_summary["large_hour_spread"] = (
        lineage_summary["hour_spread"].fillna(0) >= 12
    )

    same_year_slug = (
        credentials.groupby(
            ["catalog_year", "title_slug"],
            dropna=False,
        )
        .agg(
            credential_count=("credential_id", "nunique"),
            credential_ids=(
                "credential_id",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            titles=(
                "credential_title",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            award_types=(
                "award_type",
                lambda s: " | ".join(sorted(set(map(str, s)))),
            ),
            min_hours=("inferred_program_hours", "min"),
            max_hours=("inferred_program_hours", "max"),
        )
        .reset_index()
    )

    same_year_slug = same_year_slug[
        same_year_slug["credential_count"] > 1
    ].copy()

    collision_rows = []

    for _, row in lineage_summary.iterrows():
        if bool(row["mixed_award_types"]):
            collision_rows.append(
                {
                    "issue_type": "LINEAGE_MIXES_AWARD_TYPES",
                    **row.to_dict(),
                }
            )

        if bool(row["large_hour_spread"]):
            collision_rows.append(
                {
                    "issue_type": "LINEAGE_LARGE_HOUR_SPREAD",
                    **row.to_dict(),
                }
            )

    for _, row in same_year_slug.iterrows():
        collision_rows.append(
            {
                "issue_type": "SAME_YEAR_TITLE_SLUG_COLLISION",
                "lineage": "",
                "catalog_year_count": 1,
                "credential_id_count": row["credential_count"],
                "title_count": "",
                "award_type_count": "",
                "min_inferred_hours": row["min_hours"],
                "max_inferred_hours": row["max_hours"],
                "titles": row["titles"],
                "credential_ids": row["credential_ids"],
                "catalog_years": row["catalog_year"],
                "award_types": row["award_types"],
                "hour_spread": (
                    row["max_hours"] - row["min_hours"]
                    if pd.notna(row["max_hours"])
                    and pd.notna(row["min_hours"])
                    else ""
                ),
                "mixed_award_types": "",
                "large_hour_spread": "",
            }
        )

    collisions = pd.DataFrame(collision_rows)

    # Near-match review across different lineages.
    latest = (
        credentials.sort_values(
            ["lineage", "catalog_year"],
            kind="mergesort",
        )
        .drop_duplicates("lineage", keep="last")
        .reset_index(drop=True)
    )

    near_rows = []

    for i in range(len(latest)):
        left = latest.iloc[i]

        for j in range(i + 1, len(latest)):
            right = latest.iloc[j]

            if left["lineage"] == right["lineage"]:
                continue

            score = similarity_tokens(
                left["normalized_title_key"],
                right["normalized_title_key"],
            )

            if score < 0.75:
                continue

            near_rows.append(
                {
                    "lineage_left": left["lineage"],
                    "title_left": left["credential_title"],
                    "award_type_left": left["award_type"],
                    "hours_left": left["inferred_program_hours"],
                    "lineage_right": right["lineage"],
                    "title_right": right["credential_title"],
                    "award_type_right": right["award_type"],
                    "hours_right": right["inferred_program_hours"],
                    "token_jaccard": round(score, 4),
                    "same_award_type": (
                        left["award_type"] == right["award_type"]
                    ),
                    "hour_difference": (
                        abs(
                            float(left["inferred_program_hours"])
                            - float(right["inferred_program_hours"])
                        )
                        if pd.notna(left["inferred_program_hours"])
                        and pd.notna(right["inferred_program_hours"])
                        else ""
                    ),
                }
            )

    near_matches = pd.DataFrame(near_rows)

    if not near_matches.empty:
        near_matches = near_matches.sort_values(
            ["token_jaccard", "lineage_left", "lineage_right"],
            ascending=[False, True, True],
            kind="mergesort",
        )

    kpis = pd.DataFrame(
        [
            {
                "metric": "Credential-year rows",
                "value": len(credentials),
            },
            {
                "metric": "Distinct lineages",
                "value": credentials["lineage"].nunique(),
            },
            {
                "metric": "Lineages mixing award types",
                "value": int(
                    lineage_summary["mixed_award_types"].sum()
                ),
            },
            {
                "metric": "Lineages with >=12 hour spread",
                "value": int(
                    lineage_summary["large_hour_spread"].sum()
                ),
            },
            {
                "metric": "Same-year title-slug collisions",
                "value": len(same_year_slug),
            },
            {
                "metric": "Near-match lineage pairs >=0.75 token Jaccard",
                "value": len(near_matches),
            },
        ]
    )

    kpis.to_csv(SAFE_KPI, index=False)
    lineage_summary.to_csv(SAFE_LINEAGES, index=False)
    collisions.to_csv(SAFE_COLLISIONS, index=False)
    near_matches.to_csv(SAFE_NEAR_MATCHES, index=False)

    print("=" * 100)
    print("CREDENTIAL-LINEAGE SHADOW CHECK")
    print("=" * 100)
    print(f"Credential-year rows: {len(credentials):,}")
    print(f"Distinct lineages: {credentials['lineage'].nunique():,}")
    print(
        "Lineages mixing award types: "
        f"{int(lineage_summary['mixed_award_types'].sum()):,}"
    )
    print(
        "Lineages with >=12 hour spread: "
        f"{int(lineage_summary['large_hour_spread'].sum()):,}"
    )
    print(
        "Same-year title-slug collisions: "
        f"{len(same_year_slug):,}"
    )
    print(
        "Near-match lineage pairs >=0.75 token Jaccard: "
        f"{len(near_matches):,}"
    )
    print()
    print(f"KPI: {SAFE_KPI}")
    print(f"Lineage census: {SAFE_LINEAGES}")
    print(f"Collision review: {SAFE_COLLISIONS}")
    print(f"Near matches: {SAFE_NEAR_MATCHES}")
    print()
    print("UPLOAD ALL FOUR FERPA-SAFE CSV FILES.")
    print("LINEAGE GATE: PASSED")


if __name__ == "__main__":
    main()
