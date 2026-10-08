from pathlib import Path
import re
import pandas as pd

ROOT = Path.cwd()

REPORT = (
    ROOT
    / "data/processed/reporting"
    / "additional_awards_clean_query_20260803"
)

RESID = REPORT / "11_additional_awards_student_detail.csv"
AWARDS = REPORT / "08_official_awards_normalized.csv"
COURSES = ROOT / "data/processed/normalized_actual_student_course_history.csv"
RAW_AWARDS = ROOT / "data/raw/institutional_awards/lsco_awards_sample_20260730.xlsx"
CROSSWALK = ROOT / "data/interim/institutional_awards/award_program_crosswalk_curated.xlsx"

OUTDIR = REPORT / "second_associate_review_20260811"
OUTDIR.mkdir(parents=True, exist_ok=True)

DETAIL_OUT = OUTDIR / "RESTRICTED_SECOND_ASSOCIATE_STAGE1.csv"
SAFE_OUT = OUTDIR / "FERPA_SAFE_SECOND_ASSOCIATE_STAGE1_SUMMARY.csv"

TARGET_LINEAGE = "LIBERAL_ARTS"
OLD_RULE_CATALOGS = {"2022-2023", "2023-2024", "2024-2025"}
NEW_RULE_CATALOG = "2025-2026"

# All prior associate awards seen in the 13-person universe are academic
# AA/AS/AAT degrees. The catalog describes those as 60-SCH programs.
PRIOR_ACADEMIC_ASSOCIATE_HOURS = 60
LIBERAL_ARTS_HOURS = 60
OLD_RULE_THRESHOLD = max(
    PRIOR_ACADEMIC_ASSOCIATE_HOURS,
    LIBERAL_ARTS_HOURS,
) + 15

COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b", re.I)


def norm_text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def truthy(value) -> bool:
    return norm_text(value).upper() in {
        "TRUE", "T", "YES", "Y", "1", "PASSED"
    }


def normalize_course(value) -> str:
    m = COURSE_RE.search(norm_text(value).upper())
    if not m:
        return ""
    return f"{m.group(1).upper()} {m.group(2)}"


def derive_sch(course_code: str) -> float:
    """
    Texas 4-digit course numbering: second digit is SCH.
    Example: ENGL 1301 -> 3 SCH; BIOL 1406 -> 4 SCH.
    Developmental 0xxx courses are excluded elsewhere.
    """
    m = COURSE_RE.search(norm_text(course_code).upper())
    if not m:
        return 0.0
    number = m.group(2)
    try:
        return float(number[1])
    except Exception:
        return 0.0


def find_col(columns, candidates, required=True):
    lower = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower:
            return lower[key]
    if required:
        raise RuntimeError(
            "Could not find any of these columns: "
            + ", ".join(candidates)
        )
    return None


def catalog_start(catalog_year: str) -> int:
    try:
        return int(str(catalog_year).split("-")[0])
    except Exception:
        return -1


# =============================================================================
# LOAD
# =============================================================================

for path in [RESID, AWARDS, COURSES, RAW_AWARDS, CROSSWALK]:
    if not path.exists():
        raise FileNotFoundError(path)

resid = pd.read_csv(
    RESID,
    dtype=str,
    low_memory=False,
).fillna("")

awards = pd.read_csv(
    AWARDS,
    dtype=str,
    low_memory=False,
).fillna("")

courses = pd.read_csv(
    COURSES,
    dtype=str,
    low_memory=False,
).fillna("")

raw_awards = pd.read_excel(
    RAW_AWARDS,
    dtype=str,
).fillna("")

cw = pd.read_excel(
    CROSSWALK,
    sheet_name="Crosswalk Draft",
    dtype=str,
).fillna("")


# =============================================================================
# RESOLVE KEYS / ASSOCIATE CODES
# =============================================================================

student_col = find_col(
    resid.columns,
    ["student_id", "RNUM", "rnum", "student_key"],
)

awards_student_col = find_col(
    awards.columns,
    [student_col, "student_id", "RNUM", "rnum", "student_key"],
)

course_student_col = find_col(
    courses.columns,
    [student_col, "student_id", "RNUM", "rnum", "student_key"],
)

raw_student_col = find_col(
    raw_awards.columns,
    [student_col, "student_id", "RNUM", "rnum", "student_key", "ID", "StudentID"],
)

lineage_col = find_col(
    resid.columns,
    ["detected_lineage", "canonical_lineage"],
)

cw["award_level_norm"] = (
    cw["award_level"].astype(str).str.strip().str.upper()
)

associate_program_codes = set(
    cw.loc[
        cw["award_level_norm"].eq("ASSOCIATE"),
        "Curr1ProgramCode",
    ].astype(str)
)

# Program -> degree type from crosswalk.
program_to_degree = (
    cw.loc[
        cw["Curr1ProgramCode"].isin(associate_program_codes),
        ["Curr1ProgramCode", "DegreeCode", "canonical_lineage"],
    ]
    .drop_duplicates("Curr1ProgramCode")
    .set_index("Curr1ProgramCode")
    .to_dict("index")
)


# =============================================================================
# 13 LIBERAL ARTS SECOND-ASSOCIATE CANDIDATES
# =============================================================================

targets = resid[
    resid[lineage_col].eq(TARGET_LINEAGE)
].copy()

if len(targets) != 13:
    print(
        "WARNING: expected 13 Liberal Arts residual rows from current checkpoint; "
        f"found {len(targets)}."
    )

candidate_students = set(targets[student_col])

official_assoc = awards[
    awards["Curr1ProgramCode"].isin(associate_program_codes)
    & awards[awards_student_col].isin(candidate_students)
].copy()

if set(targets[student_col]) - set(official_assoc[awards_student_col]):
    raise RuntimeError(
        "At least one Liberal Arts candidate has no prior associate award "
        "in the normalized official-award file."
    )


# =============================================================================
# RAW AWARD TERMS: identify FIRST prior associate award
# =============================================================================

raw_program_col = find_col(
    raw_awards.columns,
    ["Curr1ProgramCode", "ProgramCode", "program_code"],
)

raw_term_col = find_col(
    raw_awards.columns,
    ["StudGradTerm", "GradTerm", "grad_term", "graduation_term", "term_code"],
)

raw_assoc = raw_awards[
    raw_awards[raw_program_col].isin(associate_program_codes)
    & raw_awards[raw_student_col].isin(candidate_students)
].copy()

raw_assoc["_term_num"] = pd.to_numeric(
    raw_assoc[raw_term_col],
    errors="coerce",
)

raw_assoc = raw_assoc.sort_values(
    [raw_student_col, "_term_num", raw_program_col],
    kind="mergesort",
)

first_prior = (
    raw_assoc.drop_duplicates(
        raw_student_col,
        keep="first",
    )
    [[
        raw_student_col,
        raw_program_col,
        raw_term_col,
    ]]
    .rename(
        columns={
            raw_student_col: student_col,
            raw_program_col: "first_prior_program_code",
            raw_term_col: "first_prior_grad_term",
        }
    )
)

first_prior["first_prior_degree_code"] = (
    first_prior["first_prior_program_code"]
    .map(
        lambda code: program_to_degree.get(code, {}).get("DegreeCode", "")
    )
)

first_prior["first_prior_lineage"] = (
    first_prior["first_prior_program_code"]
    .map(
        lambda code: program_to_degree.get(code, {}).get("canonical_lineage", "")
    )
)


# =============================================================================
# PASSED COLLEGE-LEVEL HOURS FOR OLD RULE
# =============================================================================

course_code_col = find_col(
    courses.columns,
    ["course_code", "course", "normalized_course_code"],
)

passed_col = find_col(
    courses.columns,
    ["passed", "earned_for_catalog", "course_passed"],
    required=False,
)

grade_col = find_col(
    courses.columns,
    ["final_grade", "grade"],
    required=False,
)

hours_col = find_col(
    courses.columns,
    ["earned_hours", "credit_hours", "semester_hours", "sch"],
    required=False,
)

courses["_student"] = courses[course_student_col].astype(str).str.strip()
courses["_course"] = courses[course_code_col].map(normalize_course)

if passed_col:
    courses["_passed"] = courses[passed_col].map(truthy)
else:
    passing_grades = {
        "A", "B", "C", "D", "S", "P", "CR", "T",
        "TA", "TB", "TC", "TD", "TS",
    }
    courses["_passed"] = (
        courses[grade_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(passing_grades)
    )

courses["_course_number"] = (
    courses["_course"]
    .str.extract(r"(\d{4})$", expand=False)
    .fillna("")
)

courses["_college_level"] = (
    courses["_course_number"].str.len().eq(4)
    & ~courses["_course_number"].str.startswith("0")
)

if hours_col:
    courses["_hours"] = pd.to_numeric(
        courses[hours_col],
        errors="coerce",
    )
else:
    courses["_hours"] = pd.NA

courses["_hours"] = courses["_hours"].fillna(
    courses["_course"].map(derive_sch)
)

passed = courses[
    courses["_student"].isin(candidate_students)
    & courses["_passed"]
    & courses["_college_level"]
    & courses["_course"].ne("")
].copy()

# One earned-credit count per student/course. If the same course was passed
# more than once, do not inflate earned SCH for the old second-degree floor.
earned_by_course = (
    passed.groupby(
        ["_student", "_course"],
        dropna=False,
    )["_hours"]
    .max()
    .reset_index()
)

earned_totals = (
    earned_by_course.groupby("_student")["_hours"]
    .sum()
    .rename("total_passed_college_sch")
    .reset_index()
    .rename(columns={"_student": student_col})
)


# =============================================================================
# PRIOR ASSOCIATE INVENTORY PER CANDIDATE
# =============================================================================

prior_inventory = (
    official_assoc.groupby(awards_student_col)
    .agg(
        prior_associate_award_count=("Curr1ProgramCode", "size"),
        prior_associate_programs=(
            "Curr1ProgramCode",
            lambda s: " | ".join(sorted(set(map(str, s)))),
        ),
        prior_associate_lineages=(
            "institutional_lineage",
            lambda s: " | ".join(sorted(set(x for x in map(str, s) if x))),
        ),
    )
    .reset_index()
    .rename(columns={awards_student_col: student_col})
)


# =============================================================================
# ADJUDICATE STAGE 1
# =============================================================================

detail = (
    targets
    .merge(
        first_prior,
        on=student_col,
        how="left",
        validate="m:1",
    )
    .merge(
        earned_totals,
        on=student_col,
        how="left",
        validate="m:1",
    )
    .merge(
        prior_inventory,
        on=student_col,
        how="left",
        validate="m:1",
    )
)

detail["total_passed_college_sch"] = pd.to_numeric(
    detail["total_passed_college_sch"],
    errors="coerce",
).fillna(0.0)

detail["rule_regime"] = detail["catalog_year"].map(
    lambda y: (
        "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
        if y in OLD_RULE_CATALOGS
        else (
            "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
            if y == NEW_RULE_CATALOG
            else "REVIEW_CATALOG_RULE"
        )
    )
)

detail["stage1_decision"] = "REVIEW"
detail["stage1_reason"] = ""

# Old rule: both the first associate and Liberal Arts are 60-SCH academic
# associate degrees in this 13-student universe, so threshold is 75 earned SCH.
old_mask = detail["rule_regime"].eq(
    "OLD_15_ABOVE_GREATER_DEGREE_HOURS"
)

detail.loc[
    old_mask
    & detail["total_passed_college_sch"].ge(OLD_RULE_THRESHOLD),
    "stage1_decision",
] = "PASS_SECOND_ASSOCIATE_RULE"

detail.loc[
    old_mask
    & detail["total_passed_college_sch"].ge(OLD_RULE_THRESHOLD),
    "stage1_reason",
] = (
    f"Completed at least {OLD_RULE_THRESHOLD} college-level SCH "
    f"(60-SCH greater degree requirement + 15)."
)

detail.loc[
    old_mask
    & detail["total_passed_college_sch"].lt(OLD_RULE_THRESHOLD),
    "stage1_decision",
] = "FAIL_SECOND_ASSOCIATE_RULE"

detail.loc[
    old_mask
    & detail["total_passed_college_sch"].lt(OLD_RULE_THRESHOLD),
    "stage1_reason",
] = (
    f"Fewer than {OLD_RULE_THRESHOLD} completed college-level SCH "
    f"(60-SCH greater degree requirement + 15)."
)

# 2025-26: only one AA is permitted by the new multiple-degree policy.
new_mask = detail["rule_regime"].eq(
    "NEW_15_BEYOND_FIRST_PLAN_IN_RESIDENCE"
)

prior_degree = (
    detail["first_prior_degree_code"]
    .astype(str)
    .str.strip()
    .str.upper()
)

detail.loc[
    new_mask & prior_degree.eq("AA"),
    "stage1_decision",
] = "FAIL_SAME_DEGREE_TYPE"

detail.loc[
    new_mask & prior_degree.eq("AA"),
    "stage1_reason",
] = (
    "2025-2026 policy permits one AA type; target Liberal Arts is also AA."
)

detail.loc[
    new_mask & ~prior_degree.eq("AA"),
    "stage1_decision",
] = "NEEDS_15_UNIQUE_RESIDENT_SCH_TEST"

detail.loc[
    new_mask & ~prior_degree.eq("AA"),
    "stage1_reason",
] = (
    "Different associate type; must test 15 additional hours beyond the first "
    "degree plan, completed in residence at LSCO with GPA >= 2.0."
)


# =============================================================================
# OUTPUTS
# =============================================================================

detail.to_csv(
    DETAIL_OUT,
    index=False,
)

safe_cols = [
    "catalog_year",
    "credential_id",
    "rule_regime",
    "first_prior_degree_code",
    "first_prior_lineage",
    "stage1_decision",
]

safe = (
    detail.groupby(
        safe_cols,
        dropna=False,
    )
    .agg(
        candidates=(student_col, "size"),
        min_total_passed_college_sch=("total_passed_college_sch", "min"),
        median_total_passed_college_sch=("total_passed_college_sch", "median"),
        max_total_passed_college_sch=("total_passed_college_sch", "max"),
    )
    .reset_index()
)

safe.to_csv(
    SAFE_OUT,
    index=False,
)


# =============================================================================
# CONSOLE — STUDENT BLIND
# =============================================================================

print("=" * 110)
print("SECOND ASSOCIATE — STAGE 1 ADJUDICATION")
print("=" * 110)

print()
print("Candidates:", len(detail))
print("Unique students:", detail[student_col].nunique())

print()
print("BY CATALOG / RULE REGIME")
print("-" * 110)
print(
    detail.groupby(
        ["catalog_year", "rule_regime"],
        dropna=False,
    )
    .size()
    .rename("candidates")
    .to_string()
)

print()
print("STAGE 1 DECISIONS")
print("-" * 110)
print(
    detail["stage1_decision"]
    .value_counts(dropna=False)
    .to_string()
)

print()
print("OLD-RULE CASES — TOTAL EARNED SCH")
print("-" * 110)

old = detail[old_mask].copy()
if old.empty:
    print("NONE")
else:
    print(
        old.groupby("stage1_decision")
        .agg(
            candidates=(student_col, "size"),
            min_sch=("total_passed_college_sch", "min"),
            median_sch=("total_passed_college_sch", "median"),
            max_sch=("total_passed_college_sch", "max"),
        )
        .to_string()
    )

print()
print("2025-2026 CASES — FIRST PRIOR DEGREE TYPE")
print("-" * 110)

new = detail[new_mask].copy()
if new.empty:
    print("NONE")
else:
    print(
        new.groupby(
            [
                "first_prior_degree_code",
                "first_prior_lineage",
                "stage1_decision",
            ],
            dropna=False,
        )
        .size()
        .rename("candidates")
        .to_string()
    )

print()
print("CONTROL")
print("-" * 110)
print(
    "Candidates partitioned:",
    len(detail),
    "=",
    int(detail["stage1_decision"].notna().sum()),
)
print("PASS")

print()
print("Restricted local detail:")
print(DETAIL_OUT)

print()
print("FERPA-safe summary:")
print(SAFE_OUT)

print()
print("FERPA NOTICE: do not upload the restricted detail file.")
