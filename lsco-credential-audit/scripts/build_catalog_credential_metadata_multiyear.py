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


OUT = (
    ROOT
    / "data/processed/catalogs/"
    "credential_metadata_multiyear.csv"
)

TARGET = (
    ROOT
    / "data/processed/reporting/"
    "additional_awards_clean_query_20260803/"
    "11_additional_awards_student_detail.csv"
)

REQ = (
    ROOT
    / "data/processed/catalogs/"
    "requirements_master_multiyear.csv"
)


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip()
    )


def normalize_index(value):
    text = clean(value)

    if not text:
        return ""

    try:
        return str(int(float(text)))
    except ValueError:
        return text


def classify_award_type(text):
    raw = clean(text)
    upper = raw.upper()

    if upper.startswith(
        "CERTIFICATE OF COMPLETION"
    ):
        return (
            raw,
            "Certificate of Completion",
            "CERT",
        )

    mapping = {
        "ASSOCIATE OF APPLIED SCIENCE DEGREE": (
            "Associate of Applied Science Degree",
            "AAS",
        ),
        "ASSOCIATE OF SCIENCE DEGREE": (
            "Associate of Science Degree",
            "AS",
        ),
        "ASSOCIATE OF ARTS DEGREE": (
            "Associate of Arts Degree",
            "AA",
        ),
        "ASSOCIATE OF ARTS IN TEACHING DEGREE": (
            "Associate of Arts in Teaching Degree",
            "AAT",
        ),
    }

    if upper in mapping:
        normalized, level = mapping[upper]

        return (
            raw,
            normalized,
            level,
        )

    return ("", "", "")


all_metadata = []


for record in edr.load_catalog_registry(
    active_only=True
):
    doc = Document(
        record.source_docx_path
    )

    current_heading_1 = ""
    current_heading_2 = ""

    award_type_raw = ""
    award_type = ""
    award_level = ""

    table_index = 0

    plan_rows = []

    for block in edr.iter_block_items(doc):

        if isinstance(block, Paragraph):

            text = clean(block.text)

            style = (
                block.style.name
                if block.style
                else ""
            )

            if text and style == "Heading 1":
                current_heading_1 = text

            if text and style == "Heading 2":
                current_heading_2 = text

                award_type_raw = ""
                award_type = ""
                award_level = ""

                continue

            if current_heading_2 and text:

                raw, normalized, level = (
                    classify_award_type(text)
                )

                if level:
                    award_type_raw = raw
                    award_type = normalized
                    award_level = level

        elif isinstance(block, Table):

            if (
                edr.is_plan_table(block)
                and current_heading_2
            ):
                plan_rows.append(
                    {
                        "catalog_year":
                            record.catalog_year,
                        "source_table_index":
                            str(table_index),
                        "credential_title_from_docx":
                            current_heading_2,
                        "pathway":
                            current_heading_1,
                        "award_type_raw":
                            award_type_raw,
                        "award_type":
                            award_type,
                        "award_level":
                            award_level,
                    }
                )

            # Must advance for EVERY table,
            # exactly as production parser does.
            table_index += 1

    plan_df = pd.DataFrame(plan_rows)

    plan_df[
        "source_table_index"
    ] = plan_df[
        "source_table_index"
    ].map(normalize_index)

    table_map_path = (
        ROOT
        / "data/processed/catalogs"
        / record.catalog_year
        / "credential_table_map_docx_draft.csv"
    )

    if not table_map_path.exists():
        raise FileNotFoundError(
            table_map_path
        )

    table_map = pd.read_csv(
        table_map_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    table_map[
        "source_table_index"
    ] = table_map[
        "source_table_index"
    ].map(normalize_index)

    joined = table_map.merge(
        plan_df,
        on=[
            "catalog_year",
            "source_table_index",
        ],
        how="left",
        validate="one_to_one",
    )

    joined[
        "title_match"
    ] = (
        joined["credential_title"]
        .map(clean)
        .str.upper()
        ==
        joined[
            "credential_title_from_docx"
        ]
        .map(clean)
        .str.upper()
    )

    bad_title = joined[
        ~joined["title_match"]
    ]

    if not bad_title.empty:
        raise RuntimeError(
            f"{record.catalog_year}: "
            f"{len(bad_title)} table-map "
            "title mismatches."
        )

    all_metadata.append(
        joined[
            [
                "catalog_year",
                "credential_id",
                "credential_title",
                "source_table_index",
                "pathway",
                "award_type_raw",
                "award_type",
                "award_level",
            ]
        ].copy()
    )


meta = pd.concat(
    all_metadata,
    ignore_index=True,
)

dupes = meta.duplicated(
    [
        "catalog_year",
        "credential_id",
    ],
    keep=False,
)

if dupes.any():
    raise RuntimeError(
        "Duplicate catalog-year × credential_id "
        "metadata rows found."
    )

meta = meta.sort_values(
    [
        "catalog_year",
        "award_level",
        "credential_title",
    ],
    kind="mergesort",
).reset_index(drop=True)

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

meta.to_csv(
    OUT,
    index=False,
)


# -------------------------------------------------
# Compare against executable credential universe
# -------------------------------------------------

req = pd.read_csv(
    REQ,
    dtype=str,
    low_memory=False,
).fillna("")

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

req_check = req_creds.merge(
    meta[
        [
            "catalog_year",
            "credential_id",
            "award_level",
        ]
    ],
    on=[
        "catalog_year",
        "credential_id",
    ],
    how="left",
    validate="one_to_one",
)

req_missing = req_check[
    req_check["award_level"]
    .fillna("")
    .eq("")
]


# -------------------------------------------------
# Current 564-row residual coverage
# -------------------------------------------------

target = pd.read_csv(
    TARGET,
    dtype=str,
    low_memory=False,
).fillna("")

target_check = target.merge(
    meta[
        [
            "catalog_year",
            "credential_id",
            "award_type",
            "award_level",
            "pathway",
        ]
    ],
    on=[
        "catalog_year",
        "credential_id",
    ],
    how="left",
    validate="many_to_one",
)

target_missing = target_check[
    target_check["award_level"]
    .fillna("")
    .eq("")
]

associate_levels = {
    "AA",
    "AS",
    "AAS",
    "AAT",
}

assoc = target_check[
    target_check[
        "award_level"
    ].isin(associate_levels)
]

lineage_col = (
    "detected_lineage"
    if "detected_lineage"
    in target_check.columns
    else "canonical_lineage"
)

assoc_summary = (
    assoc[
        [
            lineage_col,
            "catalog_year",
            "credential_id",
            "award_level",
        ]
    ]
    .drop_duplicates()
    .sort_values(
        [
            lineage_col,
            "catalog_year",
        ]
    )
)

assoc_out = (
    OUT.parent
    / "associate_targets_in_current_residual.csv"
)

assoc_summary.to_csv(
    assoc_out,
    index=False,
)


print("=" * 100)
print("CATALOG CREDENTIAL METADATA — AUTHORITATIVE DOCX PLAN TYPE")
print("=" * 100)

print(
    "Credential metadata rows:",
    f"{len(meta):,}"
)

print("\nBy award level:")
print(
    meta["award_level"]
    .replace("", "<MISSING>")
    .value_counts()
    .to_string()
)

print(
    "\nExecutable credential-years:",
    f"{len(req_creds):,}"
)

print(
    "Executable credential-years without metadata:",
    f"{len(req_missing):,}"
)

print(
    "\nCurrent downstream residual rows:",
    f"{len(target_check):,}"
)

print(
    "Residual rows without award metadata:",
    f"{len(target_missing):,}"
)

print(
    "Associate-level rows in residual:",
    f"{len(assoc):,}"
)

print(
    "Associate lineages in residual:",
    f"{assoc[lineage_col].nunique():,}"
)

if not assoc_summary.empty:
    print("\nASSOCIATE LINEAGES TO SET ASIDE:")
    print(
        assoc_summary[
            [
                lineage_col,
                "award_level",
            ]
        ]
        .drop_duplicates()
        .to_string(index=False)
    )

print("\nWROTE:")
print(OUT)
print(assoc_out)

if len(target_missing):
    print(
        "\nWARNING: residual metadata coverage "
        "is incomplete. Do not filter yet."
    )
else:
    print(
        "\nPASS: current residual has complete "
        "catalog award-level coverage."
    )
