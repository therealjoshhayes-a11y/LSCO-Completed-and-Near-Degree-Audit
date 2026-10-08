from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd


# =============================================================================
# CABINET BRIEF — STUDENT-BLIND AGGREGATION
#
# PURPOSE
# -------
# Build presentation-ready aggregate outputs from the frozen LSCO
# additional-award analysis.
#
# FERPA RULE
# ----------
# Student-level source files may be READ locally.
# NO student-level records or identifiers may be WRITTEN to this output folder.
#
# The cabinet output directory contains aggregate institutional intelligence only.
# =============================================================================


ROOT = Path.cwd()

SOURCE_DIR = (
    ROOT
    / "data"
    / "processed"
    / "reporting"
    / "final_additional_award_numbers_20260803"
)

DETAIL_PATH = SOURCE_DIR / "01_final_additional_awards_student_detail.csv"
HEADLINE_PATH = SOURCE_DIR / "00_final_headline_metrics.csv"
YEAR_PATH = SOURCE_DIR / "03_final_additional_awards_by_completion_year.csv"
CATALOG_PATH = SOURCE_DIR / "04_final_additional_awards_by_catalog.csv"

STUDENT_FLOOR_PATH = (
    ROOT
    / "data"
    / "processed"
    / "reporting"
    / "additional_awards_clean_query_20260803"
    / "01_student_catalog_floors.csv"
)

METADATA_CANDIDATES = [
    (
        ROOT
        / "data"
        / "processed"
        / "full_actual_audit"
        / "evidence"
        / "awardability"
        / "selected_awards_awardability_screen_finalized.csv"
    ),
    (
        ROOT
        / "data"
        / "processed"
        / "full_actual_audit"
        / "evidence"
        / "catalog_eligibility_test"
        / "collapsed_modeled_awards_corrected.csv"
    ),
]

OUTPUT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "reporting"
    / "cabinet_brief_20260811"
)

TOP_K = 5


# =============================================================================
# HELPERS
# =============================================================================


def fail(message: str) -> None:
    raise RuntimeError(message)


def first_nonblank(series: pd.Series) -> str:
    for value in series.astype(str):
        value = value.strip()
        if value:
            return value
    return ""


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)

    return h.hexdigest()


def assert_student_blind(df: pd.DataFrame, label: str) -> None:
    """
    Hard gate: cabinet outputs may contain counts and credential/program labels,
    but may not contain student identifiers or student-level personal data.
    """

    forbidden_columns = {
        "student_id",
        "student_pidm",
        "pidm",
        "banner_id",
        "first_name",
        "middle_name",
        "last_name",
        "full_name",
        "student_name",
        "name",
        "email",
        "email_address",
        "dob",
        "birth_date",
        "date_of_birth",
        "ssn",
        "social_security_number",
        "tdcj_number",
        "phone",
        "phone_number",
        "address",
        "street_address",
    }

    actual = {str(c).strip().lower() for c in df.columns}
    bad_columns = sorted(actual & forbidden_columns)

    if bad_columns:
        fail(
            f"FERPA OUTPUT GATE FAILED for {label}: "
            f"forbidden columns detected: {bad_columns}"
        )

    # Value-level safety net.
    patterns = {
        "Banner-style student ID": re.compile(r"\bR\d{8}\b", re.I),
        "SSN-shaped value": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "email address": re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.I,
        ),
    }

    for column in df.select_dtypes(include="object").columns:
        values = df[column].fillna("").astype(str)

        for description, pattern in patterns.items():
            if values.str.contains(pattern, regex=True).any():
                fail(
                    f"FERPA OUTPUT GATE FAILED for {label}: "
                    f"{description} detected in column {column!r}"
                )



# =============================================================================
# CATALOG-DERIVED CREDENTIAL LEVEL OVERRIDES
#
# These lineages appear in the frozen final award package with generic CERT /
# ASSOCIATE labels or missing credential_type metadata.
#
# They are classified here from the published LSCO catalog award lists rather
# than inferred from student data.
# =============================================================================

CATALOG_LEVEL_OVERRIDES = {

    # Associate degrees
    "LIBERAL_ARTS": "AA",
    "INDUSTRIAL_TECHNOLOGY": "AAS",

    # Certificates of Completion
    "ACCOUNTING_SERVICES_BASIC": "Certificate of Completion",
    "AUTOMOTIVE_TECHNOLOGY_BASIC": "Certificate of Completion",
    "BANKING_AND_FINANCIAL_SERVICES_BASIC": "Certificate of Completion",
    "BUSINESS_MANAGEMENT_ACCOUNTING": "Certificate of Completion",
    "BUSINESS_OPERATIONS": "Certificate of Completion",
    "CISCO_NETWORKING_CYBERSECURITY_TECHNICIAN": "Certificate of Completion",
    "CONSTRUCTION_MANAGEMENT": "Certificate of Completion",
    "COURT_REPORTING_MACHINE_SHORTHAND_SCOPIST": "Certificate of Completion",
    "CRIMINAL_JUSTICE_LAW_ENFORCEMENT": "Certificate of Completion",
    "DENTAL_ASSISTING_CERTIFICATE": "Certificate of Completion",
    "DENTAL_FRONT_OFFICE": "Certificate of Completion",
    "ELECTROMECHANICAL_TECHNOLOGY_BASIC": "Certificate of Completion",
    "ENTREPRENEURSHIP": "Certificate of Completion",
    "GENERAL_STUDIES_CORE_CURRICULUM": "Certificate of Completion",
    "INFORMATION_TECHNOLOGY_CYBERSECURITY_BASIC": "Certificate of Completion",
    "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_CYBERSECURITY_SPECIALIST":
        "Certificate of Completion",
    "INSTRUMENTATION_BASIC": "Certificate of Completion",
    "IT_SUPPORT_ASSISTANT_NETWORKING_SPECIALIST": "Certificate of Completion",
    "LAYOUT_AND_FABRICATION_WELDING_CERTIFICATE": "Certificate of Completion",
    "MEDICAL_ASSISTING_CERTIFICATE": "Certificate of Completion",
    "ORDINARY_SEAMAN_BASIC_SAFETY_TRAINING": "Certificate of Completion",
    "ORDINARY_SEAMAN_I": "Certificate of Completion",
    "PHARMACY_TECHNOLOGY_BASIC": "Certificate of Completion",
    "PIPE_WELDING_CERTIFICATE": "Certificate of Completion",
    "PROCESS_TECHNOLOGY_BASIC": "Certificate of Completion",
    "PRODUCTION_WELDER": "Certificate of Completion",
    "REAL_ESTATE": "Certificate of Completion",
    "REAL_ESTATE_MANAGEMENT": "Certificate of Completion",
    "WELDING_TECHNOLOGY": "Certificate of Completion",
}


def normalize_level(
    raw_type: str,
    credential_id: str,
    lineage: str,
) -> str:

    raw = str(raw_type).strip().upper()
    credential_id = str(credential_id).strip().upper()
    lineage_key = str(lineage).strip().upper()

    # First use explicit catalog-grounded lineage classification.
    if lineage_key in CATALOG_LEVEL_OVERRIDES:
        return CATALOG_LEVEL_OVERRIDES[lineage_key]

    key = f"{credential_id} {lineage_key}"

    # Specific associate levels.
    if (
        raw == "AAS"
        or "ASSOCIATE OF APPLIED SCIENCE" in raw
        or re.search(r"(^|_)AAS(_|$)", key)
    ):
        return "AAS"

    if (
        raw == "AAT"
        or "ASSOCIATE OF ARTS IN TEACHING" in raw
        or re.search(r"(^|_)AAT[12]?(_|$)", key)
    ):
        return "AAT"

    if (
        raw == "AA"
        or raw == "ASSOCIATE OF ARTS"
        or re.search(r"(^|_)AA(_|$)", key)
    ):
        return "AA"

    if (
        raw == "AS"
        or raw == "ASSOCIATE OF SCIENCE"
        or re.search(r"(^|_)AS(_|$)", key)
    ):
        return "AS"

    # Source-system aliases for certificates.
    if raw in {
        "CERT",
        "CC",
        "CERTIFICATE",
        "CERTIFICATE OF COMPLETION",
    }:
        return "Certificate of Completion"

    if (
        "CERTIFICATE OF COMPLETION" in raw
        or "CERTIFICATE_OF_COMPLETION" in key
    ):
        return "Certificate of Completion"

    # Institutional awards.
    if raw in {
        "IA",
        "INSTITUTIONAL AWARD",
    }:
        return "Institutional Award"

    if (
        "INSTITUTIONAL AWARD" in raw
        or "INSTITUTIONAL_AWARD" in key
    ):
        return "Institutional Award"

    # Never guess from a generic ASSOCIATE label.
    # If the catalog-derived mapping or identifier cannot establish AA/AS/AAS/AAT,
    # stop and require review.
    return "UNRESOLVED"




HEALTH_TERMS = {
    "DENTAL",
    "EMERGENCY MEDICAL",
    "EMERGENCY_MEDICAL",
    "PARAMEDIC",
    "MASSAGE",
    "MEDICAL ASSIST",
    "MEDICAL_ASSIST",
    "MEDICAL OFFICE",
    "MEDICAL_OFFICE",
    "NURSING",
    "VOCATIONAL NURS",
    "VOCATIONAL_NURS",
    "REGISTERED NURS",
    "REGISTERED_NURS",
    "PHARMACY",
    "PHYSICAL THERAPY",
    "PHYSICAL_THERAPY",
    "HEALTH SCIENCE",
    "HEALTH_SCIENCE",
}


def classify_cluster(
    credential_level: str,
    credential_title: str,
    credential_lineage: str,
) -> str:
    """
    Executive analytical clusters.

    Health is identified by program family/title.
    AA/AS/AAT programs not already classified as Health are General Academic.
    Remaining applied/certificate/IA programs are grouped as Industry / Workforce.

    This is an executive reporting cluster, not a replacement for the catalog's
    formal pathway taxonomy.
    """

    text = (
        f"{credential_title} {credential_lineage}"
        .upper()
        .replace("-", " ")
    )

    if any(term in text for term in HEALTH_TERMS):
        return "Health"

    if credential_level in {"AA", "AS", "AAT"}:
        return "General Academic / Transfer"

    return "Industry / Workforce"


# =============================================================================
# INPUT VALIDATION
# =============================================================================


print("=" * 100)
print("CABINET BRIEF — STUDENT-BLIND AGGREGATE QUERY")
print("=" * 100)

for required in [
    DETAIL_PATH,
    HEADLINE_PATH,
    YEAR_PATH,
    CATALOG_PATH,
]:
    if not required.exists():
        fail(f"Required frozen input not found: {required}")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Frozen source: {SOURCE_DIR}")
print(f"Cabinet output: {OUTPUT_DIR}")
print()


# =============================================================================
# LOAD FROZEN FINAL DETAIL — LOCAL ONLY
# =============================================================================


work = pd.read_csv(
    DETAIL_PATH,
    dtype=str,
    low_memory=False,
).fillna("")

required_keys = {
    "student_id",
    "credential_id",
    "catalog_year",
}

missing_keys = required_keys - set(work.columns)

if missing_keys:
    fail(
        "Frozen final detail is missing required local keys: "
        + ", ".join(sorted(missing_keys))
    )

lineage_source = next(
    (
        c
        for c in [
            "credential_lineage",
            "detected_lineage",
            "canonical_lineage",
        ]
        if c in work.columns
    ),
    None,
)

if lineage_source is None:
    fail(
        "Could not locate credential lineage in frozen final detail. "
        "Expected credential_lineage, detected_lineage, or canonical_lineage."
    )

work["credential_lineage"] = (
    work[lineage_source]
    .astype(str)
    .str.strip()
)

for column in ["credential_title", "credential_type"]:
    if column not in work.columns:
        work[column] = ""


# =============================================================================
# ATTACH CREDENTIAL METADATA LOCALLY IF NEEDED
# =============================================================================


for metadata_path in METADATA_CANDIDATES:

    still_need_title = work["credential_title"].str.strip().eq("").any()
    still_need_type = work["credential_type"].str.strip().eq("").any()

    if not (still_need_title or still_need_type):
        break

    if not metadata_path.exists():
        continue

    header = pd.read_csv(metadata_path, nrows=0)
    available = set(header.columns)

    keys = ["student_id", "catalog_year", "credential_id"]

    if not set(keys).issubset(available):
        continue

    attrs = [
        c
        for c in [
            "credential_title",
            "credential_type",
        ]
        if c in available
    ]

    if not attrs:
        continue

    meta = pd.read_csv(
        metadata_path,
        usecols=keys + attrs,
        dtype=str,
        low_memory=False,
    ).fillna("")

    # Metadata must be deterministic within local student/catalog/credential key.
    for attr in attrs:
        conflicts = (
            meta.groupby(keys, dropna=False)[attr]
            .apply(
                lambda s: len(
                    {
                        str(v).strip()
                        for v in s
                        if str(v).strip()
                    }
                )
            )
        )

        if (conflicts > 1).any():
            fail(
                f"Metadata conflict detected for {attr} in "
                f"{metadata_path.name}."
            )

    agg_map = {
        attr: first_nonblank
        for attr in attrs
    }

    meta = (
        meta.groupby(keys, as_index=False, dropna=False)
        .agg(agg_map)
    )

    work = work.merge(
        meta,
        on=keys,
        how="left",
        suffixes=("", "_metadata"),
        validate="many_to_one",
    )

    for attr in attrs:
        meta_col = f"{attr}_metadata"

        if meta_col in work.columns:
            work[attr] = work[attr].where(
                work[attr].astype(str).str.strip().ne(""),
                work[meta_col].fillna(""),
            )

            work = work.drop(columns=meta_col)


# =============================================================================
# CREDENTIAL LEVEL
# =============================================================================


work["credential_level"] = [
    normalize_level(raw_type, credential_id, lineage)
    for raw_type, credential_id, lineage in zip(
        work["credential_type"],
        work["credential_id"],
        work["credential_lineage"],
    )
]

unresolved = work[
    work["credential_level"].eq("UNRESOLVED")
][
    [
        "credential_id",
        "credential_lineage",
        "credential_title",
        "credential_type",
    ]
].drop_duplicates()

if not unresolved.empty:

    unresolved["affected_awards"] = [
        int(
            (
                work["credential_id"]
                .eq(row["credential_id"])
            ).sum()
        )
        for _, row in unresolved.iterrows()
    ]

    assert_student_blind(
        unresolved,
        "unresolved credential levels",
    )

    unresolved_path = (
        OUTPUT_DIR
        / "98_unresolved_credential_levels.csv"
    )

    unresolved.to_csv(
        unresolved_path,
        index=False,
    )

    fail(
        "Credential-level classification is incomplete. "
        f"Student-blind review written to: {unresolved_path}"
    )


# =============================================================================
# DISPLAY TITLES + EXECUTIVE CLUSTERS
# =============================================================================


work["credential_display"] = (
    work["credential_title"]
    .astype(str)
    .str.strip()
)

missing_title = work["credential_display"].eq("")

work.loc[
    missing_title,
    "credential_display",
] = (
    work.loc[
        missing_title,
        "credential_lineage",
    ]
    .str.replace("_", " ", regex=False)
    .str.title()
)

work["pathway_cluster"] = [
    classify_cluster(level, title, lineage)
    for level, title, lineage in zip(
        work["credential_level"],
        work["credential_display"],
        work["credential_lineage"],
    )
]


# =============================================================================
# RECONCILIATION AGAINST FROZEN HEADLINE NUMBERS
# =============================================================================


frozen_headline = pd.read_csv(
    HEADLINE_PATH,
    dtype=str,
).fillna("")

if not {"metric", "value"}.issubset(frozen_headline.columns):
    fail(
        "Frozen headline file does not contain metric/value columns."
    )

metric_map = {
    str(row["metric"]).strip():
    int(float(str(row["value"]).strip()))
    for _, row in frozen_headline.iterrows()
    if str(row["value"]).strip()
}

expected_awards = metric_map.get(
    "Final additional awards"
)

expected_students = metric_map.get(
    "Students receiving additional awards"
)

if expected_awards is not None and len(work) != expected_awards:
    fail(
        f"Frozen reconciliation failed: detail has {len(work):,} rows "
        f"but headline metric reports {expected_awards:,} awards."
    )

actual_students = work["student_id"].nunique()

if (
    expected_students is not None
    and actual_students != expected_students
):
    fail(
        f"Frozen reconciliation failed: detail contains "
        f"{actual_students:,} distinct students but headline reports "
        f"{expected_students:,}."
    )


# =============================================================================
# PROJECT-SCALE HEADLINE METRICS
# =============================================================================


headline = frozen_headline[["metric", "value"]].copy()
headline["source"] = "Frozen final award package"

if STUDENT_FLOOR_PATH.exists():

    floor_header = pd.read_csv(
        STUDENT_FLOOR_PATH,
        nrows=0,
    )

    if "student_id" in floor_header.columns:

        floors = pd.read_csv(
            STUDENT_FLOOR_PATH,
            usecols=["student_id"],
            dtype=str,
        )

        students_audited = floors["student_id"].nunique()

        headline = pd.concat(
            [
                pd.DataFrame(
                    [
                        {
                            "metric": "Students audited",
                            "value": students_audited,
                            "source": "Local catalog-floor population",
                        }
                    ]
                ),
                headline,
            ],
            ignore_index=True,
        )

catalog_root = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
)

catalog_years = []

if catalog_root.exists():
    catalog_years = sorted(
        p.name
        for p in catalog_root.iterdir()
        if p.is_dir()
        and re.fullmatch(r"20\d{2}-20\d{2}", p.name)
    )

if catalog_years:
    headline = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "metric": "Catalog years modeled",
                        "value": len(catalog_years),
                        "source": "Processed catalog directories",
                    }
                ]
            ),
            headline,
        ],
        ignore_index=True,
    )


# =============================================================================
# AWARDS BY CREDENTIAL LEVEL
# =============================================================================


awards_by_level = (
    work.groupby(
        "credential_level",
        dropna=False,
    )
    .agg(
        additional_awards=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
)

awards_by_level["share_of_awards_pct"] = (
    awards_by_level["additional_awards"]
    / len(work)
    * 100
).round(1)

level_order = {
    "AA": 1,
    "AS": 2,
    "AAT": 3,
    "AAS": 4,
    "Certificate of Completion": 5,
    "Institutional Award": 6,
}

awards_by_level["_sort"] = (
    awards_by_level["credential_level"]
    .map(level_order)
    .fillna(99)
)

awards_by_level = (
    awards_by_level
    .sort_values(
        ["_sort", "additional_awards"],
        ascending=[True, False],
    )
    .drop(columns="_sort")
    .reset_index(drop=True)
)


# =============================================================================
# AWARDS BY EXECUTIVE PATHWAY CLUSTER
# =============================================================================


awards_by_cluster = (
    work.groupby(
        "pathway_cluster",
        dropna=False,
    )
    .agg(
        additional_awards=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
        credential_lineages=(
            "credential_lineage",
            "nunique",
        ),
    )
    .reset_index()
    .sort_values(
        "additional_awards",
        ascending=False,
    )
    .reset_index(drop=True)
)

awards_by_cluster["share_of_awards_pct"] = (
    awards_by_cluster["additional_awards"]
    / len(work)
    * 100
).round(1)


# =============================================================================
# ONE STUDENT-BLIND ROW PER CREDENTIAL LINEAGE
# =============================================================================


level_conflicts = (
    work.groupby("credential_lineage")["credential_level"]
    .nunique()
)

if (level_conflicts > 1).any():
    bad_lineages = sorted(
        level_conflicts[
            level_conflicts > 1
        ].index.tolist()
    )

    fail(
        "Credential lineage maps to multiple credential levels: "
        + ", ".join(bad_lineages)
    )

work["_catalog_start"] = pd.to_numeric(
    work["catalog_year"]
    .str.extract(r"^(20\d{2})", expand=False),
    errors="coerce",
).fillna(-1)

latest_labels = (
    work.sort_values(
        [
            "credential_lineage",
            "_catalog_start",
            "credential_display",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )
    .drop_duplicates(
        subset=["credential_lineage"],
        keep="first",
    )
    [
        [
            "credential_lineage",
            "credential_display",
            "credential_level",
            "pathway_cluster",
        ]
    ]
)

lineage_counts = (
    work.groupby(
        "credential_lineage",
        dropna=False,
    )
    .agg(
        additional_awards=(
            "student_id",
            "size",
        ),
        distinct_students=(
            "student_id",
            "nunique",
        ),
    )
    .reset_index()
)

lineage_summary = (
    latest_labels
    .merge(
        lineage_counts,
        on="credential_lineage",
        how="inner",
        validate="one_to_one",
    )
    .rename(
        columns={
            "credential_display":
                "credential_title",
        }
    )
)

lineage_summary = lineage_summary[
    [
        "pathway_cluster",
        "credential_level",
        "credential_title",
        "credential_lineage",
        "additional_awards",
        "distinct_students",
    ]
].sort_values(
    [
        "pathway_cluster",
        "additional_awards",
        "credential_title",
    ],
    ascending=[
        True,
        False,
        True,
    ],
).reset_index(drop=True)


# =============================================================================
# TOP K WITHIN EACH CLUSTER
# =============================================================================


top_k = (
    lineage_summary
    .sort_values(
        [
            "pathway_cluster",
            "additional_awards",
            "credential_title",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )
    .groupby(
        "pathway_cluster",
        group_keys=False,
    )
    .head(TOP_K)
    .copy()
)

top_k["rank"] = (
    top_k.groupby("pathway_cluster")
    .cumcount()
    + 1
)

top_k = top_k[
    [
        "pathway_cluster",
        "rank",
        "credential_title",
        "credential_level",
        "additional_awards",
        "distinct_students",
    ]
]


# =============================================================================
# EXISTING FROZEN AGGREGATES
# =============================================================================


by_year = pd.read_csv(
    YEAR_PATH,
    dtype=str,
).fillna("")

by_catalog = pd.read_csv(
    CATALOG_PATH,
    dtype=str,
).fillna("")


# =============================================================================
# RELATED ANALYTICS PROJECTS — SLIDE-READY TEXT
# =============================================================================


related_projects = pd.DataFrame(
    [
        {
            "project":
                "Multi-catalog credential completion audit",
            "status":
                "Complete",
            "purpose":
                "Audit each student against eligible credentials across five catalog years.",
        },
        {
            "project":
                "Unawarded credential reclamation",
            "status":
                "Complete / frozen",
            "purpose":
                "Reconcile modeled completions against official LSCO awards.",
        },
        {
            "project":
                "Near-completer detection",
            "status":
                "Built",
            "purpose":
                "Identify credentials with only a small number of requirements remaining.",
        },
        {
            "project":
                "Catalog eligibility and award-term simulation",
            "status":
                "Complete",
            "purpose":
                "Apply catalog activity, catalog-life and modeled completion-term rules.",
        },
        {
            "project":
                "Credential lineage and version reconciliation",
            "status":
                "Complete",
            "purpose":
                "Collapse equivalent catalog generations without double counting awards.",
        },
        {
            "project":
                "Stackable credential analysis",
            "status":
                "Built",
            "purpose":
                "Detect legitimate parent-child credential stacks and separate them from duplicates.",
        },
        {
            "project":
                "Requirement bottleneck analysis",
            "status":
                "Ready",
            "purpose":
                "Measure which remaining requirements most frequently block completion.",
        },
        {
            "project":
                "Excess-hours / no-degree analysis",
            "status":
                "Next query",
            "purpose":
                "Find students with substantial earned hours but no completed credential.",
        },
        {
            "project":
                "Antikythera substitution candidate ranking",
            "status":
                "Next stage",
            "purpose":
                "Rank unused coursework against unmet requirements for human substitution review.",
        },
        {
            "project":
                "Historical cohort credential reclamation",
            "status":
                "Reusable architecture",
            "purpose":
                "Rerun the same deterministic audit against archived Argos populations.",
        },
    ]
)


# =============================================================================
# AIR-GAP METHOD — SLIDE-READY TEXT
# =============================================================================


airgap = pd.DataFrame(
    [
        {
            "stage": 1,
            "location": "ChatGPT / repository-visible code",
            "activity":
                "Review architecture, rules, schemas and non-FERPA source code.",
            "data_boundary":
                "No student records required.",
        },
        {
            "stage": 2,
            "location": "ChatGPT",
            "activity":
                "Draft Python queries, reporting logic and validation gates.",
            "data_boundary":
                "Code and structure only.",
        },
        {
            "stage": 3,
            "location": "LSCO secure local environment",
            "activity":
                "Human runs the generated code against Banner/Argos-derived files.",
            "data_boundary":
                "FERPA data enter the process here and remain local.",
        },
        {
            "stage": 4,
            "location": "LSCO secure local environment",
            "activity":
                "Python aggregates results and strips all student-level identifiers.",
            "data_boundary":
                "Only student-blind institutional aggregates are written for cabinet.",
        },
        {
            "stage": 5,
            "location": "ChatGPT / executive reporting",
            "activity":
                "Aggregate counts, program labels and non-identifying diagnostics may be reviewed.",
            "data_boundary":
                "No FERPA record crosses the boundary.",
        },
    ]
)


# =============================================================================
# OUTPUT FERPA GATE
# =============================================================================


outputs = {
    "00_headline_metrics.csv":
        headline,
    "01_additional_awards_by_level.csv":
        awards_by_level,
    "02_additional_awards_by_cluster.csv":
        awards_by_cluster,
    "03_top5_credentials_by_cluster.csv":
        top_k,
    "04_credential_classification_review.csv":
        lineage_summary,
    "05_additional_awards_by_completion_year.csv":
        by_year,
    "06_additional_awards_by_catalog.csv":
        by_catalog,
    "07_related_data_projects.csv":
        related_projects,
    "08_airgap_method.csv":
        airgap,
}

for filename, dataframe in outputs.items():

    assert_student_blind(
        dataframe,
        filename,
    )

    dataframe.to_csv(
        OUTPUT_DIR / filename,
        index=False,
    )


# =============================================================================
# EXCEL WORKBOOK — ALSO STUDENT BLIND
# =============================================================================


workbook_path = (
    OUTPUT_DIR
    / "CABINET_BRIEF_STUDENT_BLIND.xlsx"
)

sheet_map = {
    "Headline":
        headline,
    "Awards by Level":
        awards_by_level,
    "Awards by Cluster":
        awards_by_cluster,
    "Top 5 by Cluster":
        top_k,
    "Credential Review":
        lineage_summary,
    "Completion Year":
        by_year,
    "Catalog Year":
        by_catalog,
    "Related Projects":
        related_projects,
    "Airgap Method":
        airgap,
}

try:

    with pd.ExcelWriter(
        workbook_path,
        engine="openpyxl",
    ) as writer:

        for sheet_name, dataframe in sheet_map.items():

            assert_student_blind(
                dataframe,
                sheet_name,
            )

            dataframe.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

except ImportError:
    print(
        "WARNING: openpyxl not installed; "
        "CSV outputs were still created."
    )


# =============================================================================
# README / PROVENANCE
# =============================================================================


provenance = [
    "LSCO CABINET BRIEF — STUDENT-BLIND DATA PACKAGE",
    "=" * 72,
    "",
    "Purpose:",
    "  Aggregate executive reporting from the frozen credential-audit results.",
    "",
    "FERPA boundary:",
    "  Student-level inputs were read only inside the local LSCO environment.",
    "  No student-level rows or identifiers are written to this directory.",
    "  Every cabinet dataframe passed an identifier/value safety gate before write.",
    "",
    "Frozen source package:",
    f"  {SOURCE_DIR}",
    "",
    "Frozen detail SHA256:",
    f"  {file_sha256(DETAIL_PATH)}",
    "",
    "Headline reconciliation:",
    f"  Final additional awards: {len(work):,}",
    f"  Distinct recipient students: {actual_students:,}",
    f"  Credential lineages represented: {work['credential_lineage'].nunique():,}",
    "",
    "Executive cluster rule:",
    "  Health = health-related program title/family.",
    "  General Academic / Transfer = AA, AS, or AAT not already classified as Health.",
    "  Industry / Workforce = remaining applied, certificate, and institutional award programs.",
    "  This is a cabinet-reporting cluster, not a replacement for catalog pathway taxonomy.",
    "",
    "Outputs:",
]

for filename in outputs:
    provenance.append(f"  {filename}")

if workbook_path.exists():
    provenance.append(f"  {workbook_path.name}")

provenance.extend(
    [
        "",
        "NOTE:",
        "  Registrar and DegreeWorks remain authoritative for graduation determination.",
    ]
)

readme_path = OUTPUT_DIR / "README.txt"

readme_path.write_text(
    "\n".join(provenance),
    encoding="utf-8",
)


# =============================================================================
# CONSOLE — AGGREGATES ONLY
# =============================================================================


print()
print("=" * 100)
print("HEADLINE METRICS")
print("=" * 100)
print(
    headline.to_string(
        index=False,
    )
)

print()
print("=" * 100)
print("ADDITIONAL AWARDS BY LEVEL")
print("=" * 100)
print(
    awards_by_level.to_string(
        index=False,
    )
)

print()
print("=" * 100)
print("ADDITIONAL AWARDS BY EXECUTIVE CLUSTER")
print("=" * 100)
print(
    awards_by_cluster.to_string(
        index=False,
    )
)

print()
print("=" * 100)
print(f"TOP {TOP_K} CREDENTIALS WITHIN EACH CLUSTER")
print("=" * 100)
print(
    top_k.to_string(
        index=False,
    )
)

print()
print("=" * 100)
print("FERPA OUTPUT GATE: PASSED")
print("=" * 100)
print("No student-level rows were written.")
print(f"Output directory: {OUTPUT_DIR.resolve()}")
print()

