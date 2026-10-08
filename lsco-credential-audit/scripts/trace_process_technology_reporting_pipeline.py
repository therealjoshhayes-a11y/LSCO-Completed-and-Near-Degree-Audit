from pathlib import Path
import pandas as pd

TARGET_ID = "PROCESS_TECHNOLOGY_2021"
TARGET_LINEAGE = "PROCESS_TECHNOLOGY_AAS"

ROOTS = [
    Path(
        "data/processed/reporting/"
        "additional_awards_revised_query_20260803"
    ),
    Path(
        "data/processed/reporting/"
        "additional_awards_clean_query_20260803"
    ),
]

OUT_DIR = Path(
    "data/processed/reporting/"
    "process_technology_2021_repair"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "process_technology_reporting_trace.csv"

parts = []

print("=" * 100)
print("PROCESS TECHNOLOGY REPORTING-PIPELINE TRACE")
print("=" * 100)

for root in ROOTS:
    if not root.exists():
        print(f"MISSING FOLDER: {root}")
        continue

    for path in sorted(root.glob("*.csv")):
        try:
            header = pd.read_csv(path, nrows=0).columns.tolist()
        except Exception:
            continue

        relevant = [
            column
            for column in header
            if any(
                token in column.lower()
                for token in [
                    "student",
                    "credential",
                    "lineage",
                    "title",
                    "award",
                    "degree",
                    "catalog",
                    "status",
                    "completion",
                    "term",
                ]
            )
        ]

        if not relevant:
            continue

        try:
            df = pd.read_csv(
                path,
                usecols=relevant,
                dtype="string",
                low_memory=False,
            ).fillna("")
        except Exception as exc:
            print(f"READ FAILED: {path.name} — {exc}")
            continue

        row_text = df.astype(str).apply(
            lambda row: " | ".join(row.tolist()),
            axis=1,
        )

        mask = (
            row_text.str.contains(
                TARGET_ID,
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
            continue

        selected.insert(0, "_source_file", str(path))
        parts.append(selected)

        print(f"MATCH: {path.name} — {len(selected):,} rows")

        mapping_columns = [
            column
            for column in [
                "credential_id",
                "credential_base_id",
                "credential_title",
                "canonical_lineage",
                "detected_lineage",
                "award_lineage",
                "institutional_lineage",
                "award_level",
                "credential_level",
                "catalog_year",
                "audit_status",
            ]
            if column in selected.columns
        ]

        if mapping_columns:
            print(
                selected[mapping_columns]
                .drop_duplicates()
                .to_string(index=False)
            )
        print()

if not parts:
    raise RuntimeError(
        "No Process Technology rows found in the "
        "additional-awards reporting folders."
    )

combined = pd.concat(
    parts,
    ignore_index=True,
    sort=False,
).fillna("").drop_duplicates()

combined.to_csv(
    OUT_PATH,
    index=False,
    encoding="utf-8-sig",
)

print("=" * 100)
print("REPORTING TRACE COMPLETE")
print("=" * 100)
print(f"Rows saved: {len(combined):,}")
print(f"Output:\n{OUT_PATH}")
