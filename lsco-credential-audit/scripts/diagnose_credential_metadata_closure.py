from pathlib import Path
import sys
import re
import pandas as pd

from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

ROOT = Path.cwd()

sys.path.insert(
    0,
    str((ROOT / "scripts").resolve())
)

import extract_docx_requirements as edr


META = (
    ROOT
    / "data/processed/catalogs/"
    "credential_metadata_multiyear.csv"
)

REQ = (
    ROOT
    / "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)

RESID = (
    ROOT
    / "data/processed/reporting/"
    "additional_awards_clean_query_20260803/"
    "11_additional_awards_student_detail.csv"
)

OVERLAY = (
    ROOT
    / "data/processed/catalogs/"
    "missing_health_credentials_overlay/"
    "missing_health_requirements_overlay.csv"
)

OUT_DIR = (
    ROOT
    / "data/processed/catalogs/"
    "credential_metadata_closure"
)

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUT = (
    OUT_DIR
    / "credential_metadata_31_row_closure_review.csv"
)


def clean(v):
    return re.sub(
        r"\s+",
        " ",
        str(v or "").strip(),
    )


def norm_index(v):
    text = clean(v)

    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


meta = pd.read_csv(
    META,
    dtype=str,
    low_memory=False,
).fillna("")

req = pd.read_csv(
    REQ,
    dtype=str,
    low_memory=False,
).fillna("")

resid = pd.read_csv(
    RESID,
    dtype=str,
    low_memory=False,
).fillna("")


# ------------------------------------------------------------------
# Executable credential universe
# ------------------------------------------------------------------

req_creds = (
    req[
        [
            "catalog_year",
            "credential_id",
            "credential_title",
        ]
    ]
    .drop_duplicates()
)

meta_key = set(
    zip(
        meta["catalog_year"],
        meta["credential_id"],
    )
)

absent = req_creds[
    ~req_creds.apply(
        lambda r: (
            r["catalog_year"],
            r["credential_id"],
        ) in meta_key,
        axis=1,
    )
].copy()

absent["closure_issue"] = (
    "EXECUTABLE_CREDENTIAL_NOT_IN_DOCX_METADATA"
)

absent["pathway"] = ""
absent["source_table_index"] = ""
absent["between_heading_and_plan_table"] = ""
absent["overlay_match"] = ""
absent["overlay_title"] = ""


# ------------------------------------------------------------------
# Check missing executable credentials against approved health overlay
# ------------------------------------------------------------------

if OVERLAY.exists():

    ov = pd.read_csv(
        OVERLAY,
        dtype=str,
        low_memory=False,
    ).fillna("")

    ov_cols = [
        c for c in [
            "catalog_year",
            "credential_id",
            "credential_title",
        ]
        if c in ov.columns
    ]

    ov_cred = (
        ov[ov_cols]
        .drop_duplicates()
    )

    if {
        "catalog_year",
        "credential_id",
    }.issubset(ov_cred.columns):

        ov_lookup = set(
            zip(
                ov_cred["catalog_year"],
                ov_cred["credential_id"],
            )
        )

        absent["overlay_match"] = absent.apply(
            lambda r:
            "YES"
            if (
                r["catalog_year"],
                r["credential_id"],
            ) in ov_lookup
            else "NO",
            axis=1,
        )

        if "credential_title" in ov_cred.columns:

            title_lookup = {
                (
                    r["catalog_year"],
                    r["credential_id"],
                ): r["credential_title"]
                for _, r in ov_cred.iterrows()
            }

            absent["overlay_title"] = absent.apply(
                lambda r: title_lookup.get(
                    (
                        r["catalog_year"],
                        r["credential_id"],
                    ),
                    "",
                ),
                axis=1,
            )


# ------------------------------------------------------------------
# Native DOCX credential rows whose award type was not recognized
# ------------------------------------------------------------------

native_missing = meta[
    meta["award_level"]
    .str.strip()
    .eq("")
].copy()

native_missing["closure_issue"] = (
    "DOCX_PLAN_AWARD_TYPE_UNRECOGNIZED"
)

native_missing[
    "between_heading_and_plan_table"
] = ""


# ------------------------------------------------------------------
# Capture every paragraph between Heading 2 and its plan table
# ------------------------------------------------------------------

context_lookup = {}

for record in edr.load_catalog_registry(
    active_only=True
):

    doc = Document(
        record.source_docx_path
    )

    current_heading_2 = ""
    between = []
    table_index = 0

    for block in edr.iter_block_items(doc):

        if isinstance(block, Paragraph):

            text = clean(block.text)
            style = (
                block.style.name
                if block.style
                else ""
            )

            if text and style == "Heading 2":
                current_heading_2 = text
                between = []
                continue

            if current_heading_2 and text:
                between.append(
                    f"[{style}] {text}"
                )

        elif isinstance(block, Table):

            if (
                edr.is_plan_table(block)
                and current_heading_2
            ):

                context_lookup[
                    (
                        record.catalog_year,
                        norm_index(table_index),
                    )
                ] = " || ".join(
                    between[-12:]
                )

            table_index += 1


native_missing[
    "source_table_index"
] = native_missing[
    "source_table_index"
].map(norm_index)

native_missing[
    "between_heading_and_plan_table"
] = native_missing.apply(
    lambda r: context_lookup.get(
        (
            r["catalog_year"],
            r["source_table_index"],
        ),
        "",
    ),
    axis=1,
)


# ------------------------------------------------------------------
# Residual impact by credential-year
# ------------------------------------------------------------------

lineage_col = (
    "detected_lineage"
    if "detected_lineage" in resid.columns
    else "canonical_lineage"
)

impact = (
    resid.groupby(
        [
            "catalog_year",
            "credential_id",
        ],
        dropna=False,
    )
    .agg(
        residual_rows=(
            "credential_id",
            "size",
        ),
        residual_students=(
            "student_id",
            "nunique",
        ),
        detected_lineage=(
            lineage_col,
            "first",
        ),
    )
    .reset_index()
)


# ------------------------------------------------------------------
# Normalize both issue groups into one closure table
# ------------------------------------------------------------------

native_cols = native_missing[
    [
        "catalog_year",
        "credential_id",
        "credential_title",
        "closure_issue",
        "pathway",
        "source_table_index",
        "between_heading_and_plan_table",
    ]
].copy()

native_cols["overlay_match"] = ""
native_cols["overlay_title"] = ""

absent_cols = absent[
    [
        "catalog_year",
        "credential_id",
        "credential_title",
        "closure_issue",
        "pathway",
        "source_table_index",
        "between_heading_and_plan_table",
        "overlay_match",
        "overlay_title",
    ]
].copy()

review = pd.concat(
    [
        native_cols,
        absent_cols,
    ],
    ignore_index=True,
)

review = review.merge(
    impact,
    on=[
        "catalog_year",
        "credential_id",
    ],
    how="left",
)

review[
    "residual_rows"
] = review[
    "residual_rows"
].fillna(0).astype(int)

review[
    "residual_students"
] = review[
    "residual_students"
].fillna(0).astype(int)

review["human_award_type"] = ""
review["human_award_level"] = ""
review["review_note"] = ""

review = review.sort_values(
    [
        "closure_issue",
        "catalog_year",
        "credential_title",
    ],
    kind="mergesort",
)

review.to_csv(
    OUT,
    index=False,
)


print("=" * 105)
print("CREDENTIAL METADATA CLOSURE")
print("=" * 105)

print(
    "Native DOCX rows with unrecognized type:",
    len(native_missing),
)

print(
    "Executable credentials absent from DOCX metadata:",
    len(absent),
)

print(
    "Total closure rows:",
    len(review),
)

print()

if "overlay_match" in review.columns:
    print("ABSENT EXECUTABLE ROWS — OVERLAY MATCH:")
    print(
        review[
            review["closure_issue"].eq(
                "EXECUTABLE_CREDENTIAL_NOT_IN_DOCX_METADATA"
            )
        ]["overlay_match"]
        .replace("", "<BLANK>")
        .value_counts()
        .to_string()
    )

print()
print("RESIDUAL IMPACT OF THE 31 CREDENTIAL-YEAR HOLES:")
print(
    review[
        [
            "credential_title",
            "catalog_year",
            "closure_issue",
            "overlay_match",
            "residual_rows",
            "residual_students",
        ]
    ]
    .to_string(index=False)
)

print()
print("WROTE:")
print(OUT)
