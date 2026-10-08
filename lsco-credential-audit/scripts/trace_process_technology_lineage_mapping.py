from pathlib import Path
import pandas as pd
import re

TARGET_CREDENTIAL = "PROCESS_TECHNOLOGY_2021"
TARGET_LINEAGE = "PROCESS_TECHNOLOGY_AAS"

FILES = [
    Path("data/processed/all_complete_rows_multiyear.csv"),
    Path("data/processed/award_term_vs_last_required_course_validation.csv"),
]

OUT_DIR = Path(
    "data/processed/reporting/process_technology_2021_repair"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "process_technology_bad_lineage_rows.csv"


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_row_text(df):
    # Explicit apply avoids the pandas 3.0 agg behavior that caused
    # the prior DataFrame-versus-Series failure.
    return df.astype(str).apply(
        lambda row: " | ".join(row.tolist()),
        axis=1,
    )


parts = []

print("=" * 100)
print("PROCESS TECHNOLOGY LINEAGE TRACE")
print("=" * 100)

for path in FILES:
    if not path.exists():
        print(f"MISSING: {path}")
        continue

    df = pd.read_csv(
        path,
        dtype="string",
        low_memory=False,
    ).fillna("")

    relevant_columns = [
        column
        for column in df.columns
        if any(
            word in column.lower()
            for word in [
                "student",
                "credential",
                "lineage",
                "title",
                "award",
                "degree",
                "catalog",
                "status",
                "term",
                "completion",
            ]
        )
    ]

    search_frame = df[relevant_columns].copy()
    row_text = build_row_text(search_frame)

    mask = (
        row_text.str.contains(
            TARGET_CREDENTIAL,
            case=False,
            regex=False,
            na=False,
        )
        |
        row_text.str.contains(
            TARGET_LINEAGE,
            case=False,
            regex=False,
            na=False,
        )
    )

    selected = df.loc[mask].copy()

    if selected.empty:
        print(f"NO MATCH: {path}")
        continue

    selected.insert(0, "_source_file", str(path))
    parts.append(selected)

    print(f"MATCH: {path} — {len(selected):,} rows")

    print()
    print(f"COLUMNS IN {path.name}")
    print("-" * 100)

    for column in relevant_columns:
        values = (
            selected[column]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .drop_duplicates()
        )

        matching_values = values[
            values.str.contains(
                r"PROCESS|TECHNOLOGY|AAS|CERT",
                case=False,
                regex=True,
                na=False,
            )
        ]

        if not matching_values.empty:
            print(f"\n{column}:")
            for value in matching_values.head(50):
                print(f"  {value}")

    print()
    print("DISTINCT MAPPING COMBINATIONS")
    print("-" * 100)

    mapping_columns = [
        column
        for column in [
            "catalog_year",
            "credential_id",
            "credential_title",
            "credential_name",
            "canonical_lineage",
            "detected_lineage",
            "award_lineage",
            "credential_lineage",
            "award_level",
            "credential_level",
            "audit_status",
            "completion_academic_year",
            "modeled_completion_term_numeric",
        ]
        if column in selected.columns
    ]

    if mapping_columns:
        print(
            selected[mapping_columns]
            .drop_duplicates()
            .to_string(index=False)
        )
    else:
        print(selected.head(10).to_string(index=False))

    print()


if not parts:
    raise RuntimeError(
        "No Process Technology mapping rows found in the "
        "two primary completion datasets."
    )

combined = pd.concat(
    parts,
    ignore_index=True,
    sort=False,
).fillna("")

combined.to_csv(
    OUT_PATH,
    index=False,
    encoding="utf-8-sig",
)

print("=" * 100)
print("BAD-MAPPING ROWS SAVED")
print("=" * 100)
print(f"Rows: {len(combined):,}")
print(f"File:\n{OUT_PATH}")
