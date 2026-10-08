from pathlib import Path
import re
import pandas as pd

FILES = [
    Path("data/processed/catalogs/2021-2022/requirements_docx_draft.csv"),
    Path("data/processed/catalogs/requirements_master_multicatalog.csv"),
    Path("data/processed/catalogs/requirements_master_multiyear.csv"),
]

OUT_DIR = Path(
    "data/processed/reporting/process_technology_2021_repair"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "process_technology_2021_authoritative_comparison.csv"


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize(value):
    value = clean(value).upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


parts = []

for path in FILES:
    df = pd.read_csv(
        path,
        dtype="string",
        low_memory=False,
    ).fillna("")

    text_columns = [
        column
        for column in [
            "credential_id",
            "credential_title",
            "credential_name",
            "canonical_lineage",
            "program_name",
            "degree_name",
        ]
        if column in df.columns
    ]

    if not text_columns:
        print(f"SKIPPED: {path} — no credential fields")
        continue

    credential_text = (
        df[text_columns]
        .astype(str)
        .agg(" | ".join, axis=1)
        .map(normalize)
    )

    mask = (
        credential_text.str.contains(
            r"\bPROCESS\b",
            regex=True,
            na=False,
        )
        &
        credential_text.str.contains(
            r"\bTECHNOLOGY\b",
            regex=True,
            na=False,
        )
    )

    if "catalog_year" in df.columns:
        mask &= (
            df["catalog_year"]
            .astype(str)
            .str.strip()
            .eq("2021-2022")
        )

    selected = df.loc[mask].copy()

    if selected.empty:
        print(f"NO MATCH: {path}")
        continue

    selected.insert(0, "_source_file", str(path))
    parts.append(selected)

    print(f"MATCH: {path} — {len(selected):,} rows")

if not parts:
    raise RuntimeError(
        "No authoritative Process Technology 2021-2022 rows found."
    )

inventory = pd.concat(
    parts,
    ignore_index=True,
    sort=False,
).fillna("")

preferred = [
    "_source_file",
    "catalog_year",
    "credential_id",
    "credential_title",
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
    "display_text",
    "source_text",
]

ordered = [
    column
    for column in preferred
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

inventory.to_csv(
    OUT_PATH,
    index=False,
    encoding="utf-8-sig",
)

print()
print("=" * 100)
print("CREDENTIAL IDS")
print("=" * 100)

credential_cols = [
    column
    for column in [
        "_source_file",
        "credential_id",
        "credential_title",
        "canonical_lineage",
    ]
    if column in inventory.columns
]

print(
    inventory[credential_cols]
    .drop_duplicates()
    .to_string(index=False)
)

print()
print("=" * 100)
print("REQUIREMENT / COURSE ROWS")
print("=" * 100)

display_cols = [
    column
    for column in [
        "_source_file",
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

print(
    inventory[display_cols]
    .drop_duplicates()
    .to_string(index=False)
)

print()
print("=" * 100)
print("CETT ROWS")
print("=" * 100)

row_text = (
    inventory
    .astype(str)
    .agg(" | ".join, axis=1)
    .str.upper()
)

cett = inventory.loc[
    row_text.str.contains(
        r"\bCETT\b",
        regex=True,
        na=False,
    )
]

if cettt := len(cett):
    print(cett[display_cols].to_string(index=False))
else:
    print("NO CETT ROW FOUND.")

print()
print(f"Saved:\n{OUT_PATH}")
