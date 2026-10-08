from pathlib import Path
import re
import pandas as pd

ROOT = Path.cwd()

REPORT_DIR = (
    ROOT / "data/processed/reporting/"
    "educ1300_d_certificate_award_check_20260811"
)

DETAIL_PATH = REPORT_DIR / "EDUC1300_D_OFFICIAL_CERTIFICATE_DETAIL.csv"

OUT_PATH = REPORT_DIR / "EDUC1300_D_BY_CERTIFICATE_MAJOR.csv"


def norm(v):
    if pd.isna(v):
        return ""
    return re.sub(
        r"[^A-Z0-9]+",
        "_",
        str(v).strip().upper()
    ).strip("_")


def base_credential_id(v):
    s = norm(v)
    return re.sub(r"_20(?:21|22|23|24|25)$", "", s)


detail = pd.read_csv(
    DETAIL_PATH,
    dtype=str,
    low_memory=False
).fillna("")

# ------------------------------------------------------------------
# Build published program-hour lookup from the five catalog parses.
# We retain every observed catalog total instead of pretending an
# awarded student's catalog entitlement is known from award term.
# ------------------------------------------------------------------

total_frames = []

for year in [
    "2021-2022",
    "2022-2023",
    "2023-2024",
    "2024-2025",
    "2025-2026",
]:
    path = (
        ROOT
        / "data/processed/catalogs"
        / year
        / "requirement_totals_docx_draft.csv"
    )

    if not path.exists():
        continue

    df = pd.read_csv(
        path,
        dtype=str,
        low_memory=False
    ).fillna("")

    df = df[
        df["total_program_hours"]
        .astype(str)
        .str.strip()
        .ne("")
    ].copy()

    df["_base"] = df["credential_id"].map(base_credential_id)

    df["total_program_hours_num"] = pd.to_numeric(
        df["total_program_hours"],
        errors="coerce"
    )

    df = df[
        df["total_program_hours_num"].notna()
    ].copy()

    df["catalog_year_source"] = year

    total_frames.append(
        df[
            [
                "_base",
                "credential_title",
                "catalog_year_source",
                "total_program_hours_num",
            ]
        ]
    )

totals = pd.concat(
    total_frames,
    ignore_index=True
)


# ------------------------------------------------------------------
# Link official award canonical lineage to catalog program totals.
# In this project the canonical lineage normally corresponds to the
# credential ID with the catalog-year suffix removed.
# ------------------------------------------------------------------

detail["_base"] = detail["canonical_lineage"].map(norm)

hours_lookup = (
    totals.groupby("_base")
    .agg(
        published_sch_values=(
            "total_program_hours_num",
            lambda s: " | ".join(
                str(int(x))
                for x in sorted(set(s.dropna()))
            )
        ),
        modeled_catalogs=(
            "catalog_year_source",
            lambda s: " | ".join(sorted(set(s)))
        ),
    )
    .reset_index()
)

detail = detail.merge(
    hours_lookup,
    on="_base",
    how="left",
    validate="many_to_one"
)

detail["published_sch_values"] = (
    detail["published_sch_values"]
    .fillna("")
)

detail["modeled_catalogs"] = (
    detail["modeled_catalogs"]
    .fillna("")
)


# ------------------------------------------------------------------
# The empirical population we actually care about:
# D is the highest EDUC 1300 grade existing when certificate awarded.
# ------------------------------------------------------------------

d_cases = detail[
    detail["educ1300_status"]
    .eq("D_IS_HIGHEST_EDUC_1300_GRADE_AT_AWARD")
].copy()


# ------------------------------------------------------------------
# One row per OFFICIAL CERTIFICATE MAJOR
# ------------------------------------------------------------------

summary = (
    d_cases.groupby(
        [
            "MajorDesc",
            "Major1Code",
            "canonical_lineage",
            "published_sch_values",
            "modeled_catalogs",
        ],
        dropna=False
    )
    .agg(
        certificate_awards_with_educ1300_d=(
            "student_id",
            "size"
        ),
        distinct_students=(
            "student_id",
            "nunique"
        ),
    )
    .reset_index()
    .rename(
        columns={
            "MajorDesc": "Certificate Major",
            "Major1Code": "Major Code",
            "canonical_lineage": "Canonical Lineage",
            "published_sch_values": "Published Total SCH",
            "modeled_catalogs": "Catalogs Observed",
            "certificate_awards_with_educ1300_d":
                "Awards With EDUC 1300 D",
            "distinct_students":
                "Distinct Students",
        }
    )
    .sort_values(
        [
            "Awards With EDUC 1300 D",
            "Certificate Major",
        ],
        ascending=[False, True]
    )
    .reset_index(drop=True)
)

summary.to_csv(
    OUT_PATH,
    index=False
)

print()
print("=" * 120)
print("OFFICIALLY AWARDED CERTIFICATES — EDUC 1300 D AT AWARD")
print("=" * 120)
print()

if summary.empty:
    print("NO CASES")
else:
    print(summary.to_string(index=False))

print()
print(f"Majors represented: {len(summary):,}")
print(
    "Certificate awards represented: "
    f"{summary['Awards With EDUC 1300 D'].sum():,}"
)
print(
    "Distinct students: "
    f"{d_cases['student_id'].nunique():,}"
)

print()
print("WROTE:")
print(OUT_PATH.resolve())
