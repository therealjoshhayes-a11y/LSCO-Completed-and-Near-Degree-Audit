from pathlib import Path
import re
import pandas as pd

ROOT = Path(".")
SEARCH_ROOT = ROOT / "data/processed"

OUT_DIR = (
    ROOT
    / "data/processed/reporting/"
      "process_technology_2021_repair"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "process_technology_2021_model_inventory.csv"
FILE_PATHS_OUT = OUT_DIR / "source_files_examined.csv"

TARGET_CATALOG = "2021-2022"
TARGET_WORDS = ["PROCESS", "TECHNOLOGY"]

EXCLUDED_PARTS = {
    "full_actual_audit",
    "reporting",
    "integrity_checks",
}

FILENAME_HINTS = (
    "requirement",
    "credential",
    "master",
    "audit",
    "catalog",
)


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    value = clean(value).upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalized_column(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def find_column(columns, candidates):
    lookup = {
        normalized_column(column): column
        for column in columns
    }

    for candidate in candidates:
        key = normalized_column(candidate)
        if key in lookup:
            return lookup[key]

    return None


candidate_files = []

for path in SEARCH_ROOT.rglob("*.csv"):
    relative_parts = {
        part.lower()
        for part in path.relative_to(SEARCH_ROOT).parts
    }

    if relative_parts.intersection(EXCLUDED_PARTS):
        continue

    if not any(
        hint in path.name.lower()
        for hint in FILENAME_HINTS
    ):
        continue

    candidate_files.append(path)

print("=" * 100)
print("PROCESS TECHNOLOGY 2021-2022 MODEL INVENTORY")
print("=" * 100)
print(f"Candidate processed CSV files: {len(candidate_files):,}")

matches = []
files_examined = []

for path in sorted(candidate_files):
    try:
        columns = list(pd.read_csv(path, nrows=0).columns)
    except Exception as exc:
        files_examined.append(
            {
                "file": str(path),
                "status": "HEADER_READ_FAILED",
                "note": str(exc),
            }
        )
        continue

    credential_col = find_column(
        columns,
        [
            "credential_id",
            "credential",
            "credential_name",
            "credential_title",
            "program_name",
            "degree_name",
            "canonical_lineage",
            "detected_lineage",
            "lineage",
        ],
    )

    catalog_col = find_column(
        columns,
        [
            "catalog_year",
            "catalog",
            "catalogyear",
        ],
    )

    if not credential_col:
        files_examined.append(
            {
                "file": str(path),
                "status": "SKIPPED",
                "note": "No credential/program column",
            }
        )
        continue

    file_matches = []

    try:
        for chunk in pd.read_csv(
            path,
            dtype="string",
            low_memory=False,
            chunksize=50_000,
        ):
            credential_text = (
                chunk[credential_col]
                .fillna("")
                .astype(str)
                .map(normalize)
            )

            mask = pd.Series(
                True,
                index=chunk.index,
            )

            for word in TARGET_WORDS:
                mask &= credential_text.str.contains(
                    rf"\b{re.escape(word)}\b",
                    regex=True,
                    na=False,
                )

            if catalog_col:
                catalog_text = (
                    chunk[catalog_col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                )

                catalog_mask = catalog_text.eq(
                    TARGET_CATALOG
                )

                # Retain rows without a catalog field value only when
                # the credential ID itself clearly carries the 2021 marker.
                id_has_2021 = credential_text.str.contains(
                    r"\b2021\b",
                    regex=True,
                    na=False,
                )

                mask &= catalog_mask | (
                    catalog_text.eq("")
                    & id_has_2021
                )

            selected = chunk.loc[mask].copy()

            if not selected.empty:
                selected.insert(
                    0,
                    "_source_file",
                    str(path),
                )
                selected.insert(
                    1,
                    "_credential_column",
                    credential_col,
                )
                selected.insert(
                    2,
                    "_catalog_column",
                    catalog_col or "",
                )

                file_matches.append(selected)

    except Exception as exc:
        files_examined.append(
            {
                "file": str(path),
                "status": "READ_FAILED",
                "note": str(exc),
            }
        )
        continue

    if file_matches:
        combined = pd.concat(
            file_matches,
            ignore_index=True,
        )

        matches.append(combined)

        files_examined.append(
            {
                "file": str(path),
                "status": "MATCH",
                "note": f"{len(combined):,} matching rows",
            }
        )

        print(
            f"MATCH: {path} "
            f"({len(combined):,} rows)"
        )
    else:
        files_examined.append(
            {
                "file": str(path),
                "status": "NO_MATCH",
                "note": "",
            }
        )

pd.DataFrame(files_examined).to_csv(
    FILE_PATHS_OUT,
    index=False,
    encoding="utf-8-sig",
)

if not matches:
    raise RuntimeError(
        "No Process Technology 2021-2022 model rows were found "
        "in the processed requirement-definition files."
    )

inventory = pd.concat(
    matches,
    ignore_index=True,
    sort=False,
).fillna("")

preferred_columns = [
    "_source_file",
    "catalog_year",
    "credential_id",
    "credential_title",
    "credential_name",
    "canonical_lineage",
    "requirement_id",
    "requirement_group",
    "requirement_label",
    "term_label",
    "rule_type",
    "option_type",
    "course_code",
    "required_course",
    "option_course",
    "required_hours",
    "credit_hours",
    "hours",
    "min_required",
    "options_required",
    "display_text",
    "source_text",
]

ordered = [
    column
    for column in preferred_columns
    if column in inventory.columns
]

remaining = [
    column
    for column in inventory.columns
    if column not in ordered
]

inventory = inventory[
    ordered + remaining
].drop_duplicates()

sort_columns = [
    column
    for column in [
        "credential_id",
        "requirement_id",
        "requirement_group",
        "course_code",
        "required_course",
        "option_course",
    ]
    if column in inventory.columns
]

if sort_columns:
    inventory = inventory.sort_values(
        sort_columns,
        na_position="last",
    )

inventory.to_csv(
    OUT_PATH,
    index=False,
    encoding="utf-8-sig",
)

print()
print("=" * 100)
print("MATCHING CREDENTIAL IDS")
print("=" * 100)

credential_columns = [
    column
    for column in [
        "credential_id",
        "credential_title",
        "credential_name",
        "canonical_lineage",
    ]
    if column in inventory.columns
]

if credential_columns:
    print(
        inventory[credential_columns]
        .drop_duplicates()
        .to_string(index=False)
    )

print()
print("=" * 100)
print("COURSE / REQUIREMENT INVENTORY")
print("=" * 100)

display_columns = [
    column
    for column in [
        "credential_id",
        "requirement_id",
        "requirement_group",
        "requirement_label",
        "term_label",
        "rule_type",
        "option_type",
        "course_code",
        "required_course",
        "option_course",
        "required_hours",
        "credit_hours",
        "display_text",
    ]
    if column in inventory.columns
]

if display_columns:
    print(
        inventory[display_columns]
        .drop_duplicates()
        .to_string(index=False)
    )
else:
    print(
        inventory.head(100).to_string(index=False)
    )

print()
print("=" * 100)
print("CETT CHECK")
print("=" * 100)

row_text = (
    inventory
    .astype(str)
    .agg(" | ".join, axis=1)
    .str.upper()
)

cett_rows = inventory.loc[
    row_text.str.contains(
        r"\bCETT\b",
        regex=True,
        na=False,
    )
]

if cett_rows.empty:
    print(
        "NO CETT REQUIREMENT FOUND IN THE PROCESSED "
        "PROCESS TECHNOLOGY MODEL."
    )
else:
    print(
        cett_rows[
            [
                column
                for column in display_columns
                if column in cett_rows.columns
            ]
        ].to_string(index=False)
    )

print()
print(f"Full inventory:\n{OUT_PATH}")
print(f"\nFiles examined:\n{FILE_PATHS_OUT}")
