from __future__ import annotations

import ast
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


# ======================================================================================
# CONFIGURATION
# ======================================================================================

ROOT = Path.cwd()

HISTORY_PATH = (
    ROOT
    / "data"
    / "processed"
    / "student_course_history_normalized_FULL_ACTUAL.csv"
)
SUMMARY_PATH = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "full_actual_credential_summary.csv"
)
DETAIL_PATH = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "full_actual_audit_results.csv"
)
REQUIREMENTS_PATH = (
    ROOT
    / "data"
    / "processed"
    / "catalogs"
    / "requirements_master_multiyear.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "reporting"
    / "livingston_2025_2026_advising"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Optional LSCO logo. Place the supplied PNG at R:\assets\LSCO-logo-horizontal-green.png.
# The workbook still renders cleanly when the image is absent.
LOGO_PATH = ROOT / "assets" / "LSCO-logo-horizontal-green.png"

WORKBOOK_PATH = OUTPUT_DIR / "Livingston_2025_2026_Advising_Packet.xlsx"
COURSE_DEMAND_CSV = OUTPUT_DIR / "livingston_course_demand.csv"
STUDENT_PLAN_CSV = OUTPUT_DIR / "livingston_student_plans.csv"
UNMAPPED_CSV = OUTPUT_DIR / "livingston_unmapped_majors.csv"
RUN_LOG = OUTPUT_DIR / "livingston_advising_run_log.txt"

TARGET_CATALOG = "2025-2026"
HIGH_SCHOOL_MATCH = "LIVINGSTON"

# Two semesters of planning. This does not prevent the workbook from showing
# every remaining requirement; it only controls the highlighted next-year set.
NEXT_YEAR_MAX_HOURS = 24

# Restrict the Livingston cohort to students with earned/accepted course activity
# in the most recent academic year represented in the extract.
# Current production extract ends with Summer 2025.
ACTIVE_ACADEMIC_YEAR_LABEL = "2025-2026"
ACTIVE_TERM_CODES = {"202590", "202610"}


COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b", re.I)
INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


# ======================================================================================
# CONTROLLED MAJOR-TO-PROGRAM KEYWORDS
# ======================================================================================
#
# The mapper uses the last declared major to limit the candidate credential family.
# Within that family, the student's 2025-2026 audit progress chooses the strongest
# matching credential. Unmapped majors are preserved for advisor review.
#
# Add or revise entries here as LSCO confirms additional Banner major codes.
# ======================================================================================

MAJOR_MAP = {
    "AALA": {"keywords": ["LIBERAL ARTS"], "prefer_hours": 60},
    "GENS": {"keywords": ["GENERAL STUDIES", "CORE CURRICULUM"], "prefer_hours": 44},
    "ASBU": {"keywords": ["BUSINESS"], "prefer_hours": 60},
    "BAAD": {"keywords": ["BUSINESS ADMINISTRATION"], "prefer_hours": 60},
    "ASCJ": {"keywords": ["CRIMINAL JUSTICE"], "prefer_hours": 60},
    "ASCS": {"keywords": ["COMPUTER SCIENCE"], "prefer_hours": 60},
    "ASES": {"keywords": ["ENGINEERING"], "prefer_hours": 60},
    "ASPM": {"keywords": ["PRE-MEDICINE", "MEDICAL PROFESSIONS", "HEALTH PROFESSIONS"], "prefer_hours": 60},
    "ASPE": {"keywords": ["PHYSICAL EDUCATION", "KINESIOLOGY"], "prefer_hours": 60},
    "ASCI": {"keywords": ["SCIENCE"], "prefer_hours": 60},
    "AAT1": {"keywords": ["TEACHING", "EDUCATION"], "prefer_hours": 60},
    "AAT2": {"keywords": ["TEACHING", "EDUCATION"], "prefer_hours": 60},
    "AATP": {"keywords": ["TEACHING", "EDUCATION"], "prefer_hours": 60},
    "RNSG": {"keywords": ["REGISTERED NURSING", "NURSING"], "prefer_hours": 60},
    "RNAD": {"keywords": ["REGISTERED NURSING", "NURSING"], "prefer_hours": 60},
    "VNSG": {"keywords": ["VOCATIONAL NURSING", "PRACTICAL NURSING", "NURSING"], "prefer_hours": 42},
    "PNUR": {"keywords": ["VOCATIONAL NURSING", "PRACTICAL NURSING", "NURSING"], "prefer_hours": 42},
    "PROC": {"keywords": ["PROCESS TECHNOLOGY"], "prefer_hours": 30},
    "ISTR": {"keywords": ["INSTRUMENTATION"], "prefer_hours": 30},
    "CRTD": {"keywords": ["COURT REPORTING"], "prefer_hours": 21},
    "CRSC": {"keywords": ["COURT REPORTING", "SCOPIST"], "prefer_hours": 21},
    "ITNC": {"keywords": ["NETWORKING", "INFORMATION TECHNOLOGY"], "prefer_hours": 30},
    "ITSS": {"keywords": ["CYBERSECURITY", "INFORMATION TECHNOLOGY"], "prefer_hours": 30},
    "BMCD": {"keywords": ["BUSINESS MANAGEMENT"], "prefer_hours": 30},
    "BSMT": {"keywords": ["BUSINESS"], "prefer_hours": 60},
    "MMMC": {"keywords": ["MARITIME", "MARINE"], "prefer_hours": 42},
    "PTAA": {"keywords": ["PROCESS TECHNOLOGY"], "prefer_hours": 60},
    "CFSD": {"keywords": ["CHILD", "FAMILY"], "prefer_hours": 60},
    "AACM": {"keywords": ["COMMUNICATION"], "prefer_hours": 60},
    "AASO": {"keywords": ["OCCUPATIONAL SAFETY", "SAFETY"], "prefer_hours": 60},

    # Livingston major-code mappings supplied by the user.
    "CJCC": {"keywords": ["CRIMINAL JUSTICE", "LAW ENFORCEMENT"], "prefer_hours": 18},
    "ASMB": {"keywords": ["BUSINESS"], "prefer_hours": 60},
    "COSD": {"keywords": ["COSMETOLOGY", "OPERATOR MANAGEMENT"], "prefer_hours": 60},
    "COSC": {"keywords": ["COMPUTER SCIENCE", "INFORMATION TECHNOLOGY"], "prefer_hours": 60},
    "ASMD": {"keywords": ["ANIMAL SCIENCE", "ANIMAL SCIENCE MANAGEMENT"], "prefer_hours": 60},
    "ASNS": {"keywords": ["NATURAL SCIENCE", "SCIENCE"], "prefer_hours": 60},
    "ACSD": {"keywords": ["ACCOUNTING SERVICES", "ACCOUNTING", "BUSINESS MANAGEMENT"], "prefer_hours": 60},
    "CJCR": {"keywords": ["CRIMINAL JUSTICE", "LAW ENFORCEMENT"], "prefer_hours": 18},
    "ITHC": {"keywords": ["CYBERSECURITY", "HEALTHCARE IT", "INFORMATION TECHNOLOGY"], "prefer_hours": 18},
    "TEPC": {"keywords": ["TEACHER EDUCATION", "EDUCATOR PREPARATION", "TEACHING"], "prefer_hours": 18},
    "BMRD": {"keywords": ["REAL ESTATE MANAGEMENT", "REAL ESTATE", "BUSINESS"], "prefer_hours": 60},
    "WLDB": {"keywords": ["WELDING", "WELDING BASIC"], "prefer_hours": 15},
}


# ======================================================================================
# HELPERS
# ======================================================================================

def text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_course(value: object) -> str:
    match = COURSE_RE.search(text(value).upper())
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def derive_hours(course_code: object) -> float:
    course = normalize_course(course_code)
    if not course:
        return np.nan
    number = course.split()[1]
    hours = int(number[1])
    return float(hours) if hours > 0 else np.nan


def parse_course_options(value: object) -> list[str]:
    raw = text(value)
    if not raw:
        return []

    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, (list, tuple, set)):
            courses = [normalize_course(item) for item in parsed]
            return [course for course in courses if course]
    except Exception:
        pass

    return [
        f"{match.group(1).upper()} {match.group(2)}"
        for match in COURSE_RE.finditer(raw.upper())
    ]


def safe_sheet_name(value: object, used: set[str]) -> str:
    base = INVALID_SHEET_CHARS.sub("_", text(value))
    base = base[:31] or "Student"
    name = base
    suffix = 1
    while name in used:
        suffix_text = f"_{suffix}"
        name = f"{base[:31-len(suffix_text)]}{suffix_text}"
        suffix += 1
    used.add(name)
    return name


def choose_credential(
    student_id: str,
    major_code: str,
    credential_inventory: pd.DataFrame,
    student_summary: pd.DataFrame,
) -> dict:
    mapping = MAJOR_MAP.get(major_code)

    if mapping is None:
        return {
            "mapping_status": "UNMAPPED_MAJOR",
            "credential_id": "",
            "credential_title": "",
            "requirements_met": np.nan,
            "requirements_total": np.nan,
            "progress_ratio": np.nan,
        }

    keywords = [keyword.upper() for keyword in mapping["keywords"]]
    preferred_hours = mapping.get("prefer_hours")

    candidates = credential_inventory.copy()
    search_text = (
        candidates["credential_id"].fillna("")
        + " "
        + candidates["credential_title"].fillna("")
    ).str.upper()

    keyword_mask = pd.Series(False, index=candidates.index)
    for keyword in keywords:
        keyword_mask |= search_text.str.contains(keyword, regex=False)

    candidates = candidates[keyword_mask].copy()

    if candidates.empty:
        return {
            "mapping_status": "NO_2025_2026_CREDENTIAL_MATCH",
            "credential_id": "",
            "credential_title": "",
            "requirements_met": np.nan,
            "requirements_total": np.nan,
            "progress_ratio": np.nan,
        }

    progress = student_summary[
        student_summary["student_id"].eq(student_id)
        & student_summary["credential_id"].isin(candidates["credential_id"])
    ].copy()

    candidates = candidates.merge(
        progress[
            [
                "credential_id",
                "requirements_met",
                "requirements_total",
                "audit_status",
            ]
        ],
        on="credential_id",
        how="left",
    )

    candidates["requirements_met"] = pd.to_numeric(
        candidates["requirements_met"], errors="coerce"
    ).fillna(0)
    candidates["requirements_total"] = pd.to_numeric(
        candidates["requirements_total"], errors="coerce"
    ).replace(0, np.nan)
    candidates["progress_ratio"] = (
        candidates["requirements_met"] / candidates["requirements_total"]
    ).fillna(0)

    candidates["hours_distance"] = (
        (candidates["program_hours"] - float(preferred_hours)).abs()
        if preferred_hours is not None
        else 0
    )

    candidates = candidates.sort_values(
        ["progress_ratio", "hours_distance", "program_hours", "credential_title"],
        ascending=[False, True, False, True],
    )

    winner = candidates.iloc[0]

    return {
        "mapping_status": "MAPPED",
        "credential_id": winner["credential_id"],
        "credential_title": winner["credential_title"],
        "requirements_met": winner["requirements_met"],
        "requirements_total": winner["requirements_total"],
        "progress_ratio": winner["progress_ratio"],
        "audit_status": winner.get("audit_status", ""),
    }


def requirement_recommendation(row: pd.Series) -> tuple[str, str, float]:
    rule_type = text(row.get("rule_type")).upper()
    required_options = text(row.get("required_options"))
    source_text = text(row.get("source_requirement_text"))
    group_name = text(row.get("group_name"))
    options = parse_course_options(required_options)

    if rule_type == "EXACT" and len(options) == 1:
        course = options[0]
        return course, "REQUIRED COURSE", derive_hours(course)

    if rule_type == "ANY_N":
        label = group_name or source_text or required_options or "Choose required options"
        hours = pd.to_numeric(pd.Series([row.get("credit_hours")]), errors="coerce").iloc[0]
        return label, "CHOOSE FROM OPTIONS", hours

    if rule_type == "CORE_BUCKET":
        label = group_name or source_text or "Core curriculum bucket"
        hours = pd.to_numeric(pd.Series([row.get("credit_hours")]), errors="coerce").iloc[0]
        return label, "CORE BUCKET", hours

    if rule_type == "ELECTIVE":
        label = group_name or source_text or "Approved elective"
        hours = pd.to_numeric(pd.Series([row.get("credit_hours")]), errors="coerce").iloc[0]
        return label, "ELECTIVE / ADVISOR CHOICE", hours

    if options:
        label = " OR ".join(options)
        hours = pd.to_numeric(pd.Series([row.get("credit_hours")]), errors="coerce").iloc[0]
        return label, "COURSE OPTIONS", hours

    label = group_name or source_text or required_options or "Advisor review"
    hours = pd.to_numeric(pd.Series([row.get("credit_hours")]), errors="coerce").iloc[0]
    return label, "ADVISOR REVIEW", hours


# ======================================================================================
# LOAD AND DEFINE LIVINGSTON COHORT
# ======================================================================================

for path in [HISTORY_PATH, SUMMARY_PATH, DETAIL_PATH, REQUIREMENTS_PATH]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

history = pd.read_csv(HISTORY_PATH, dtype=str, low_memory=False)
history["student_id"] = history["student_id"].astype(str)
history["term_sort_numeric"] = pd.to_numeric(history["term_sort"], errors="coerce")
history["course_code_normalized"] = history["course_code"].map(normalize_course)
history["grade_normalized"] = history["final_grade"].fillna("").str.upper()

livingston_history = history[
    history["high_school"]
    .fillna("")
    .str.upper()
    .str.contains(HIGH_SCHOOL_MATCH, regex=False)
].copy()

# Restrict to students with at least one earned/accepted course in the most
# recent academic year. A row counts as earned/accepted when passed=True.
active_term_mask = (
    livingston_history["term_taken"]
    .fillna("")
    .astype(str)
    .isin(ACTIVE_TERM_CODES)
)

active_earned_rows = livingston_history[
    active_term_mask
    & livingston_history["passed"].fillna("").str.upper().isin(
        {"TRUE", "1", "YES", "Y"}
    )
].copy()

active_student_ids = set(active_earned_rows["student_id"])
livingston_history = livingston_history[
    livingston_history["student_id"].isin(active_student_ids)
].copy()

if livingston_history.empty:
    available = (
        history["high_school"]
        .fillna("")
        .loc[lambda s: s.str.strip().ne("")]
        .value_counts()
        .head(50)
    )
    raise RuntimeError(
        "No Livingston students had earned hours in Banner terms 202590 or 202610. Most common high_school values:\n"
        + available.to_string()
    )

# One latest-major record per student, based on the latest course-stack term.
latest_rows = (
    livingston_history
    .sort_values(
        ["student_id", "term_sort_numeric", "term_taken"],
        ascending=[True, False, False],
    )
    .drop_duplicates("student_id")
)

cohort = latest_rows[
    [
        "student_id",
        "student_major",
        "term_taken",
        "term_sort",
        "high_school",
        "last_term_dual_credit",
    ]
].rename(
    columns={
        "student_major": "last_declared_major",
        "term_taken": "last_course_term",
        "term_sort": "last_course_term_sort",
    }
)

cohort["last_declared_major"] = (
    cohort["last_declared_major"].fillna("").str.strip().str.upper()
)

livingston_students = set(cohort["student_id"])

print("=" * 110)
print("LIVINGSTON 2025-2026 ADVISING PACKET")
print("=" * 110)
print(f"Livingston course-history rows: {len(livingston_history):,}")
print(f"Livingston students with earned hours in {ACTIVE_ACADEMIC_YEAR_LABEL}: {len(cohort):,}")
print("High-school values included:")
print(livingston_history["high_school"].value_counts().to_string())
print()


# ======================================================================================
# LOAD 2025-2026 REQUIREMENTS AND SUMMARY
# ======================================================================================

requirements = pd.read_csv(REQUIREMENTS_PATH, dtype=str, low_memory=False)
requirements = requirements[
    requirements["catalog_year"].eq(TARGET_CATALOG)
].copy()

requirements["credit_hours_numeric"] = pd.to_numeric(
    requirements["credit_hours"], errors="coerce"
)

requirement_inventory = (
    requirements
    .sort_values(["credential_id", "requirement_id", "sequence"])
    .drop_duplicates(["credential_id", "requirement_id"])
)

credential_inventory = (
    requirement_inventory
    .groupby("credential_id", as_index=False)
    .agg(
        credential_title=("credential_title", "first"),
        program_hours=("credit_hours_numeric", "sum"),
        requirement_count=("requirement_id", "nunique"),
    )
)

summary_parts = []
for chunk in pd.read_csv(
    SUMMARY_PATH,
    dtype=str,
    chunksize=250_000,
    low_memory=False,
):
    filtered = chunk[
        chunk["catalog_year"].eq(TARGET_CATALOG)
        & chunk["student_id"].astype(str).isin(livingston_students)
    ].copy()
    if not filtered.empty:
        summary_parts.append(filtered)

if not summary_parts:
    raise RuntimeError("No 2025-2026 summary rows found for Livingston students.")

student_summary = pd.concat(summary_parts, ignore_index=True)
student_summary["student_id"] = student_summary["student_id"].astype(str)


# ======================================================================================
# MAP LAST MAJOR TO TARGET CREDENTIAL
# ======================================================================================

mapping_rows = []

for student in cohort.itertuples(index=False):
    result = choose_credential(
        student.student_id,
        student.last_declared_major,
        credential_inventory,
        student_summary,
    )

    mapping_rows.append(
        {
            **student._asdict(),
            **result,
        }
    )

student_map = pd.DataFrame(mapping_rows)

mapped = student_map[
    student_map["mapping_status"].eq("MAPPED")
    & student_map["credential_id"].fillna("").ne("")
].copy()

unmapped = student_map[
    ~student_map.index.isin(mapped.index)
].copy()

print("Major mapping status:")
print(student_map["mapping_status"].value_counts(dropna=False).to_string())
print()


# ======================================================================================
# EXTRACT ONLY TARGETED DETAIL ROWS FROM THE 8.3 GB AUDIT FILE
# ======================================================================================

target_keys = set(
    mapped[
        ["student_id", "credential_id"]
    ].itertuples(index=False, name=None)
)

detail_parts = []
rows_read = 0

detail_columns = [
    "student_id",
    "catalog_year",
    "credential_id",
    "requirement_id",
    "rule_type",
    "status",
    "matched_options",
    "matched_terms",
    "matched_grades",
    "required_options",
    "option_types",
    "used_course_count",
]

for chunk_number, chunk in enumerate(
    pd.read_csv(
        DETAIL_PATH,
        dtype=str,
        usecols=detail_columns,
        chunksize=500_000,
        low_memory=False,
    ),
    start=1,
):
    rows_read += len(chunk)

    chunk = chunk[
        chunk["catalog_year"].eq(TARGET_CATALOG)
    ].copy()

    if chunk.empty:
        continue

    keys = list(
        chunk[
            ["student_id", "credential_id"]
        ].itertuples(index=False, name=None)
    )
    mask = [key in target_keys for key in keys]
    filtered = chunk.loc[mask].copy()

    if not filtered.empty:
        detail_parts.append(filtered)

    if chunk_number % 20 == 0:
        selected_count = sum(len(part) for part in detail_parts)
        print(
            f"Read detail chunks: {chunk_number:,} "
            f"| rows: {rows_read:,} "
            f"| Livingston target detail rows: {selected_count:,}"
        )

if not detail_parts:
    raise RuntimeError("No audit-detail rows found for mapped Livingston students.")

target_detail = pd.concat(detail_parts, ignore_index=True)

target_detail = target_detail.merge(
    requirement_inventory[
        [
            "credential_id",
            "requirement_id",
            "sequence",
            "group_name",
            "credit_hours",
            "semester_label",
            "source_requirement_text",
        ]
    ],
    on=["credential_id", "requirement_id"],
    how="left",
    validate="many_to_one",
)

target_detail["sequence_numeric"] = pd.to_numeric(
    target_detail["sequence"], errors="coerce"
)

# Only unmet or unresolved requirements drive recommendations.
remaining_detail = target_detail[
    ~target_detail["status"].fillna("").str.upper().eq("MET")
].copy()

recommendation_rows = []

for row in remaining_detail.itertuples(index=False):
    recommendation, recommendation_type, recommendation_hours = (
        requirement_recommendation(pd.Series(row._asdict()))
    )

    recommendation_rows.append(
        {
            "student_id": row.student_id,
            "credential_id": row.credential_id,
            "requirement_id": row.requirement_id,
            "sequence": row.sequence_numeric,
            "semester_label": row.semester_label,
            "rule_type": row.rule_type,
            "requirement_status": row.status,
            "group_name": row.group_name,
            "source_requirement_text": row.source_requirement_text,
            "required_options": row.required_options,
            "recommendation": recommendation,
            "recommendation_type": recommendation_type,
            "estimated_hours": recommendation_hours,
        }
    )

recommendations = pd.DataFrame(recommendation_rows)

if recommendations.empty:
    recommendations = pd.DataFrame(
        columns=[
            "student_id",
            "credential_id",
            "requirement_id",
            "sequence",
            "semester_label",
            "rule_type",
            "requirement_status",
            "group_name",
            "source_requirement_text",
            "required_options",
            "recommendation",
            "recommendation_type",
            "estimated_hours",
        ]
    )

recommendations = recommendations.merge(
    mapped[
        [
            "student_id",
            "last_declared_major",
            "credential_title",
            "progress_ratio",
        ]
    ],
    on="student_id",
    how="left",
    validate="many_to_one",
)

recommendations["estimated_hours"] = pd.to_numeric(
    recommendations["estimated_hours"], errors="coerce"
)

recommendations = recommendations.sort_values(
    ["student_id", "sequence", "requirement_id"],
    na_position="last",
)

# Highlight a next-year planning set, without hiding remaining requirements.
recommendations["cumulative_hours"] = (
    recommendations.groupby("student_id")["estimated_hours"]
    .transform(lambda s: s.fillna(0).cumsum())
)
recommendations["next_year_plan"] = (
    recommendations["cumulative_hours"] <= NEXT_YEAR_MAX_HOURS
)

# Exact courses become aggregate scheduling demand.
course_demand = (
    recommendations[
        recommendations["recommendation_type"].eq("REQUIRED COURSE")
    ]
    .groupby(
        [
            "last_declared_major",
            "credential_id",
            "credential_title",
            "recommendation",
        ],
        dropna=False,
    )
    .agg(
        students_needing_course=("student_id", "nunique"),
        next_year_students=(
            "next_year_plan",
            lambda values: int(pd.Series(values).sum()),
        ),
        estimated_hours=("estimated_hours", "first"),
    )
    .reset_index()
    .rename(columns={"recommendation": "course_code"})
    .sort_values(
        ["next_year_students", "students_needing_course", "course_code"],
        ascending=[False, False, True],
    )
)

bucket_demand = (
    recommendations[
        ~recommendations["recommendation_type"].eq("REQUIRED COURSE")
    ]
    .groupby(
        [
            "last_declared_major",
            "credential_id",
            "credential_title",
            "recommendation_type",
            "recommendation",
        ],
        dropna=False,
    )
    .agg(
        students_needing_requirement=("student_id", "nunique"),
        next_year_students=(
            "next_year_plan",
            lambda values: int(pd.Series(values).sum()),
        ),
    )
    .reset_index()
    .sort_values(
        ["next_year_students", "students_needing_requirement"],
        ascending=[False, False],
    )
)

major_summary = (
    mapped.groupby(
        [
            "last_declared_major",
            "credential_id",
            "credential_title",
        ],
        dropna=False,
    )
    .agg(
        student_count=("student_id", "nunique"),
        average_progress=("progress_ratio", "mean"),
        students_complete=(
            "audit_status",
            lambda values: int(
                pd.Series(values).fillna("").str.upper().eq("COMPLETE").sum()
            ),
        ),
    )
    .reset_index()
    .sort_values("student_count", ascending=False)
)

major_summary["average_progress"] = (
    major_summary["average_progress"] * 100
).round(1)

# Student-level plan inventory.
student_plan = mapped.merge(
    recommendations.groupby("student_id", as_index=False).agg(
        remaining_requirement_count=("requirement_id", "nunique"),
        next_year_recommendation_count=(
            "next_year_plan",
            lambda values: int(pd.Series(values).sum()),
        ),
        next_year_estimated_hours=(
            "estimated_hours",
            lambda values: float(
                recommendations.loc[
                    values.index[
                        recommendations.loc[values.index, "next_year_plan"]
                    ],
                    "estimated_hours",
                ]
                .fillna(0)
                .sum()
            ),
        ),
    ),
    on="student_id",
    how="left",
)

for column in [
    "remaining_requirement_count",
    "next_year_recommendation_count",
    "next_year_estimated_hours",
]:
    student_plan[column] = pd.to_numeric(
        student_plan[column], errors="coerce"
    ).fillna(0)

# Completed course list for each Livingston student.
passed_courses = (
    livingston_history[
        livingston_history["passed"].fillna("").str.upper().isin(
            {"TRUE", "1", "YES", "Y"}
        )
    ]
    .sort_values(["student_id", "term_sort_numeric", "course_code_normalized"])
    .groupby("student_id")["course_code_normalized"]
    .agg(lambda values: " | ".join(sorted(set(v for v in values if v))))
    .reset_index(name="completed_courses")
)

student_plan = student_plan.merge(
    passed_courses,
    on="student_id",
    how="left",
)

course_demand.to_csv(COURSE_DEMAND_CSV, index=False)
student_plan.to_csv(STUDENT_PLAN_CSV, index=False)
unmapped.to_csv(UNMAPPED_CSV, index=False)


# ======================================================================================
# BUILD EXCEL PACKET
# ======================================================================================

with pd.ExcelWriter(WORKBOOK_PATH, engine="xlsxwriter") as writer:
    workbook = writer.book

    dark_green = "#1F4E3D"
    medium_green = "#548235"
    light_green = "#D9EAD3"
    pale_green = "#EAF4E4"
    gold = "#D6B656"
    pale_gold = "#FFF2CC"
    pale_red = "#F4CCCC"
    gray = "#E7E6E6"
    white = "#FFFFFF"

    title_fmt = workbook.add_format(
        {
            "bold": True,
            "font_color": white,
            "bg_color": dark_green,
            "font_size": 17,
            "align": "center",
            "valign": "vcenter",
        }
    )
    subtitle_fmt = workbook.add_format(
        {
            "bold": True,
            "font_color": dark_green,
            "font_size": 11,
            "align": "center",
            "valign": "vcenter",
        }
    )
    small_note_fmt = workbook.add_format(
        {
            "font_color": "#666666",
            "font_size": 9,
            "italic": True,
            "align": "left",
            "valign": "top",
            "text_wrap": True,
        }
    )
    section_fmt = workbook.add_format(
        {
            "bold": True,
            "font_color": white,
            "bg_color": medium_green,
            "font_size": 11,
            "align": "left",
            "valign": "vcenter",
            "border": 1,
        }
    )
    header_fmt = workbook.add_format(
        {
            "bold": True,
            "font_color": white,
            "bg_color": dark_green,
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    body_fmt = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    percent_fmt = workbook.add_format(
        {
            "border": 1,
            "num_format": "0.0%",
            "valign": "top",
        }
    )
    integer_fmt = workbook.add_format(
        {"border": 1, "num_format": "0", "valign": "top"}
    )
    note_fmt = workbook.add_format(
        {
            "bg_color": pale_gold,
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    green_fmt = workbook.add_format(
        {
            "bg_color": pale_green,
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    review_fmt = workbook.add_format(
        {
            "bg_color": pale_red,
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )

    # ------------------------------------------------------------------
    # Cover
    # ------------------------------------------------------------------
    cover = workbook.add_worksheet("Cover")
    writer.sheets["Cover"] = cover
    cover.merge_range("A1:H2", "Livingston High School\n2025–2026 College Advising Packet", title_fmt)
    cover.set_row(0, 32)
    cover.set_row(1, 32)
    cover.merge_range("A3:H3", "Lamar State College Orange · Planning & Advising Use", subtitle_fmt)
    if LOGO_PATH.exists():
        cover.insert_image("A1", str(LOGO_PATH), {"x_scale": 0.42, "y_scale": 0.42, "x_offset": 8, "y_offset": 8})
    cover.set_tab_color(dark_green)
    cover.hide_gridlines(2)
    cover.set_header("&L&9LSCO Advising Packet&R&9Livingston High School")
    cover.set_footer("&L&8Planning estimate — Registrar certification required&C&8Page &P of &N&R&8Generated from 2025–2026 catalog rules")

    cover.write("A4", f"Planning population ({ACTIVE_ACADEMIC_YEAR_LABEL} active earned hours)", section_fmt)
    cover.write("B4", len(cohort), body_fmt)
    cover.write("A5", "Students mapped to a 2025–2026 LSCO credential", section_fmt)
    cover.write("B5", len(mapped), body_fmt)
    cover.write("A6", "Students requiring major-code review", section_fmt)
    cover.write("B6", len(unmapped), review_fmt)
    cover.write("A7", "Target catalog", section_fmt)
    cover.write("B7", TARGET_CATALOG, body_fmt)
    cover.write("A8", "Next-year planning window", section_fmt)
    cover.write("B8", f"Up to {NEXT_YEAR_MAX_HOURS} estimated SCH", body_fmt)

    cover.merge_range(
        "A10:H13",
        "Purpose: identify aggregate course demand from each student's last declared major "
        "and provide a printable advising sheet for individual meetings. This is a planning "
        "and advising estimate. Final degree certification remains subject to LSCO Registrar review.",
        note_fmt,
    )

    cover.write("A15", "Workbook guide", section_fmt)
    guide = [
        ["Major Summary", "Students by last declared major and mapped 2025–2026 credential."],
        ["Course Demand", "Exact courses students still need, ranked by next-year demand."],
        ["Bucket Demand", "Core, elective, and choice requirements requiring advisor selection."],
        ["Student Index", "Student-level mapping and progress inventory."],
        ["Unmapped Majors", "Major codes that require a controlled program mapping."],
        ["Student tabs", "One printable advising sheet per mapped student."],
    ]
    cover.write_row("A16", ["Sheet", "Purpose"], header_fmt)
    for row_number, row in enumerate(guide, start=16):
        cover.write_row(row_number, 0, row, body_fmt)

    cover.set_column("A:A", 30)
    cover.set_column("B:H", 18)

    # ------------------------------------------------------------------
    # Aggregate sheets
    # ------------------------------------------------------------------
    def write_dataframe_sheet(
        sheet_name: str,
        frame: pd.DataFrame,
        widths: dict[str, int] | None = None,
    ):
        frame.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
        worksheet = writer.sheets[sheet_name]
        worksheet.merge_range(
            0, 0, 0, max(len(frame.columns) - 1, 0), sheet_name, title_fmt
        )
        worksheet.freeze_panes(2, 0)
        worksheet.set_tab_color(medium_green)
        worksheet.hide_gridlines(2)
        worksheet.set_header(f"&L&9LSCO Advising Packet&C&9{sheet_name}&R&9Livingston High School")
        worksheet.set_footer("&L&8Planning estimate — Registrar certification required&C&8Page &P of &N&R&82025–2026")
        worksheet.set_margins(0.35, 0.35, 0.5, 0.5)

        if len(frame.columns) > 0:
            worksheet.autofilter(
                1,
                0,
                max(len(frame) + 1, 1),
                len(frame.columns) - 1,
            )

        for col_idx, column in enumerate(frame.columns):
            worksheet.write(1, col_idx, column, header_fmt)
            if widths and column in widths:
                width = widths[column]
            else:
                if frame.empty or frame[column].dropna().empty:
                    sample_width = 12
                else:
                    width_quantile = frame[column].dropna().astype(str).str.len().quantile(0.90)
                    sample_width = (
                        int(width_quantile) + 2
                        if pd.notna(width_quantile)
                        else 12
                    )
                width = min(max(len(column) + 2, sample_width), 38)
            worksheet.set_column(col_idx, col_idx, width)

        if not frame.empty and len(frame.columns) > 0:
            worksheet.conditional_format(
                2,
                0,
                len(frame) + 1,
                len(frame.columns) - 1,
                {
                    "type": "formula",
                    "criteria": "=MOD(ROW(),2)=0",
                    "format": workbook.add_format({"bg_color": "#F7FAF5"}),
                },
            )

        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
        worksheet.repeat_rows(0, 1)
        return worksheet

    write_dataframe_sheet(
        "Major Summary",
        major_summary,
        {
            "last_declared_major": 18,
            "credential_id": 40,
            "credential_title": 34,
        },
    )

    demand_sheet = write_dataframe_sheet(
        "Course Demand",
        course_demand,
        {
            "last_declared_major": 18,
            "credential_id": 36,
            "credential_title": 30,
            "course_code": 16,
        },
    )

    if not course_demand.empty:
        demand_sheet.conditional_format(
            2,
            course_demand.columns.get_loc("next_year_students"),
            len(course_demand) + 1,
            course_demand.columns.get_loc("next_year_students"),
            {"type": "data_bar", "bar_color": medium_green},
        )

    write_dataframe_sheet(
        "Bucket Demand",
        bucket_demand,
        {
            "last_declared_major": 18,
            "credential_id": 34,
            "credential_title": 30,
            "recommendation_type": 24,
            "recommendation": 48,
        },
    )

    write_dataframe_sheet(
        "Student Index",
        student_plan,
        {
            "student_id": 16,
            "last_declared_major": 18,
            "credential_id": 36,
            "credential_title": 30,
            "completed_courses": 60,
        },
    )

    write_dataframe_sheet(
        "Unmapped Majors",
        unmapped,
        {
            "student_id": 16,
            "last_declared_major": 20,
            "mapping_status": 30,
        },
    )

    # ------------------------------------------------------------------
    # Student advising sheets
    # ------------------------------------------------------------------
    used_sheet_names = {
        "Cover",
        "Major Summary",
        "Course Demand",
        "Bucket Demand",
        "Student Index",
        "Unmapped Majors",
    }

    for student in student_plan.sort_values(
        ["last_declared_major", "student_id"]
    ).itertuples(index=False):
        sheet_name = safe_sheet_name(
            f"S_{student.student_id}",
            used_sheet_names,
        )
        ws = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = ws

        ws.merge_range(
            "A1:H2",
            f"Livingston High School Advising Sheet — {TARGET_CATALOG}",
            title_fmt,
        )
        ws.set_row(0, 26)
        ws.set_row(1, 26)
        ws.merge_range("A3:H3", "Lamar State College Orange · Individual Planning Worksheet", subtitle_fmt)
        if LOGO_PATH.exists():
            ws.insert_image("A1", str(LOGO_PATH), {"x_scale": 0.28, "y_scale": 0.28, "x_offset": 6, "y_offset": 7})
        ws.set_tab_color(medium_green)
        ws.set_header("&L&9LSCO Advising Sheet&R&9Livingston High School")
        ws.set_footer("&L&8Planning estimate — Registrar certification required&C&8Page &P of &N&R&8Student advising copy")

        student_fields = [
            ("Student ID", student.student_id),
            ("High School", student.high_school),
            ("Last Declared Major", student.last_declared_major),
            ("Target LSCO Credential", student.credential_title),
            ("Credential ID", student.credential_id),
            ("Last Course Term", student.last_course_term),
            ("Requirements Met", student.requirements_met),
            ("Requirements Total", student.requirements_total),
            ("Current Progress", f"{float(student.progress_ratio or 0) * 100:.1f}%"),
        ]

        ws.write_row("A5", ["Student Planning Profile", ""], section_fmt)
        row_cursor = 5
        for label, value in student_fields:
            ws.write(row_cursor, 0, label, section_fmt)
            ws.merge_range(row_cursor, 1, row_cursor, 3, value, body_fmt)
            row_cursor += 1

        ws.write(row_cursor + 1, 0, "Completed / Accepted Courses", section_fmt)
        ws.merge_range(
            row_cursor + 2,
            0,
            row_cursor + 4,
            7,
            text(student.completed_courses) or "No passed course list available.",
            green_fmt,
        )

        plan = recommendations[
            recommendations["student_id"].eq(student.student_id)
        ].copy()

        table_start = row_cursor + 6

        ws.merge_range(
            table_start,
            0,
            table_start,
            7,
            f"Next-Year Recommendations — up to {NEXT_YEAR_MAX_HOURS} estimated SCH",
            section_fmt,
        )

        advising_headers = [
            "Priority",
            "Semester / Sequence",
            "Requirement Type",
            "Recommended Course or Requirement",
            "Estimated SCH",
            "Requirement Status",
            "Advisor Decision",
            "Notes",
        ]
        ws.write_row(table_start + 1, 0, advising_headers, header_fmt)

        next_year_plan = plan[plan["next_year_plan"]].copy()

        if next_year_plan.empty:
            ws.merge_range(
                table_start + 2,
                0,
                table_start + 3,
                7,
                "No remaining 2025–2026 requirements were identified for this mapped credential.",
                green_fmt,
            )
            current_row = table_start + 4
        else:
            for priority, plan_row in enumerate(
                next_year_plan.itertuples(index=False),
                start=1,
            ):
                ws.write_row(
                    table_start + 1 + priority,
                    0,
                    [
                        priority,
                        f"{text(plan_row.semester_label)} / {text(plan_row.sequence)}",
                        plan_row.recommendation_type,
                        plan_row.recommendation,
                        plan_row.estimated_hours,
                        plan_row.requirement_status,
                        "",
                        "",
                    ],
                    body_fmt,
                )
            current_row = table_start + 2 + len(next_year_plan)

        remaining_later = plan[~plan["next_year_plan"]].copy()

        ws.merge_range(
            current_row + 1,
            0,
            current_row + 1,
            7,
            "Remaining Requirements After the Next-Year Planning Set",
            section_fmt,
        )
        ws.write_row(current_row + 2, 0, advising_headers[1:6], header_fmt)

        if remaining_later.empty:
            ws.merge_range(
                current_row + 3,
                0,
                current_row + 4,
                7,
                "No additional remaining requirements identified.",
                green_fmt,
            )
            footer_row = current_row + 6
        else:
            for offset, plan_row in enumerate(
                remaining_later.itertuples(index=False),
                start=1,
            ):
                ws.write_row(
                    current_row + 2 + offset,
                    0,
                    [
                        f"{text(plan_row.semester_label)} / {text(plan_row.sequence)}",
                        plan_row.recommendation_type,
                        plan_row.recommendation,
                        plan_row.estimated_hours,
                        plan_row.requirement_status,
                    ],
                    body_fmt,
                )
            footer_row = current_row + 4 + len(remaining_later)

        ws.merge_range(
            footer_row,
            0,
            footer_row,
            7,
            "Advisor Meeting Notes",
            section_fmt,
        )
        ws.merge_range(
            footer_row + 1,
            0,
            footer_row + 5,
            7,
            "",
            note_fmt,
        )

        ws.write(footer_row + 7, 0, "Advisor Signature", section_fmt)
        ws.merge_range(footer_row + 7, 1, footer_row + 7, 3, "", body_fmt)
        ws.write(footer_row + 7, 4, "Date", section_fmt)
        ws.merge_range(footer_row + 7, 5, footer_row + 7, 7, "", body_fmt)
        ws.merge_range(
            footer_row + 9,
            0,
            footer_row + 10,
            7,
            "Advising estimate only. Course availability, prerequisite sequencing, transfer applicability, and final credential certification must be confirmed by LSCO.",
            small_note_fmt,
        )

        ws.set_column("A:A", 20)
        ws.set_column("B:B", 22)
        ws.set_column("C:C", 24)
        ws.set_column("D:D", 42)
        ws.set_column("E:F", 14)
        ws.set_column("G:H", 20)
        ws.set_landscape()
        ws.fit_to_pages(1, 2)
        ws.set_margins(0.3, 0.3, 0.4, 0.4)
        ws.repeat_rows(0, 2)
        ws.hide_gridlines(2)
        ws.center_horizontally()

print()
print("=" * 110)
print("LIVINGSTON ADVISING PACKET COMPLETE")
print("=" * 110)
print(f"Students in cohort with earned hours in {ACTIVE_ACADEMIC_YEAR_LABEL}: {len(cohort):,}")
print(f"Mapped students: {len(mapped):,}")
print(f"Unmapped students: {len(unmapped):,}")
print(f"Exact course-demand rows: {len(course_demand):,}")
print(f"Bucket/choice-demand rows: {len(bucket_demand):,}")
print(f"Workbook: {WORKBOOK_PATH}")
print(f"Course demand CSV: {COURSE_DEMAND_CSV}")
print(f"Student plans CSV: {STUDENT_PLAN_CSV}")
print(f"Unmapped majors CSV: {UNMAPPED_CSV}")

RUN_LOG.write_text(
    "\n".join(
        [
            "LIVINGSTON 2025-2026 ADVISING PACKET",
            f"Students in cohort with earned hours in {ACTIVE_ACADEMIC_YEAR_LABEL}: {len(cohort):,}",
            f"Mapped students: {len(mapped):,}",
            f"Unmapped students: {len(unmapped):,}",
            f"Exact course-demand rows: {len(course_demand):,}",
            f"Bucket/choice-demand rows: {len(bucket_demand):,}",
            f"Workbook: {WORKBOOK_PATH}",
        ]
    ),
    encoding="utf-8",
)
