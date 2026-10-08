from pathlib import Path
import re
import pandas as pd

ROOT = Path.cwd()

AWARDS = (
    ROOT / "data/raw/institutional_awards/"
    "lsco_awards_sample_20260730.xlsx"
)

CROSSWALK = (
    ROOT / "data/interim/institutional_awards/"
    "award_program_crosswalk_curated.xlsx"
)

COURSES = (
    ROOT / "data/processed/"
    "normalized_actual_student_course_history.csv"
)

OUTDIR = (
    ROOT / "data/processed/reporting/"
    "educ1300_d_certificate_award_check_20260811"
)

DETAIL = OUTDIR / "EDUC1300_D_OFFICIAL_CERTIFICATE_DETAIL.csv"
SUMMARY = OUTDIR / "EDUC1300_D_OFFICIAL_CERTIFICATE_SUMMARY.csv"

OUTDIR.mkdir(parents=True, exist_ok=True)


def norm(v):
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def norm_id(v):
    return str(v).strip()


def find_col(columns, candidates, required=True):
    lookup = {str(c).strip().lower(): c for c in columns}
    for c in candidates:
        if c.lower() in lookup:
            return lookup[c.lower()]
    if required:
        raise RuntimeError(
            f"Could not resolve one of {candidates}. "
            f"Available columns: {list(columns)}"
        )
    return None


def term_num(v):
    s = re.sub(r"\D", "", str(v))
    return int(s) if s else None


print("=" * 100)
print("OFFICIAL CERTIFICATE AWARDS WITH EDUC 1300 = D")
print("=" * 100)

# =============================================================================
# OFFICIAL AWARDS ONLY
# =============================================================================

official = pd.read_excel(
    AWARDS,
    dtype=str
).fillna("")

crosswalk = pd.read_excel(
    CROSSWALK,
    dtype=str
).fillna("")

keys = [
    "Curr1ProgramCode",
    "Major1Code",
    "DegreeCode",
]

for c in keys:
    official[c] = official[c].map(norm)
    crosswalk[c] = crosswalk[c].map(norm)

# Award metadata comes from the curated Banner award crosswalk.
keep = keys + [
    c for c in [
        "MajorDesc",
        "DegreeDesc",
        "canonical_lineage",
        "award_level",
    ]
    if c in crosswalk.columns
]

cw = crosswalk[keep].drop_duplicates()

awards = official.merge(
    cw,
    on=keys,
    how="left",
    validate="many_to_one"
)

if "award_level" in awards.columns:
    cert = awards[
        awards["award_level"]
        .map(norm)
        .isin({"CERTIFICATE", "CERTIFICATE OF COMPLETION"})
    ].copy()
else:
    # LSCO Level 1 certificate code in the supplied award history.
    cert = awards[
        awards["DegreeCode"].eq("CERT1")
    ].copy()

id_col = find_col(
    cert.columns,
    ["ID", "student_id", "StudentID"]
)

cert["_student_id"] = cert[id_col].map(norm_id)

# Find award term/date.
award_term_col = find_col(
    cert.columns,
    [
        "AwardTerm",
        "AwardTermCode",
        "GradTerm",
        "GradTermCode",
        "GraduationTerm",
        "DegreeTerm",
        "TermCode",
        "Term",
    ],
    required=False
)

award_date_col = find_col(
    cert.columns,
    [
        "AwardDate",
        "DegreeDate",
        "GraduationDate",
        "ConferralDate",
    ],
    required=False
)

if award_term_col:
    cert["_award_term"] = cert[award_term_col].map(term_num)
else:
    cert["_award_term"] = None

if award_date_col:
    cert["_award_date"] = pd.to_datetime(
        cert[award_date_col],
        errors="coerce"
    )
else:
    cert["_award_date"] = pd.NaT


# =============================================================================
# ACTUAL EDUC 1300 HISTORY
# =============================================================================

courses = pd.read_csv(
    COURSES,
    dtype=str,
    low_memory=False
).fillna("")

course_id_col = find_col(
    courses.columns,
    ["student_id", "StudentID", "StudenID", "ID"]
)

subject_col = find_col(
    courses.columns,
    ["subject", "Subject", "course_subject", "CourseSubject"],
    required=False
)

number_col = find_col(
    courses.columns,
    ["course_number", "CourseNumber", "number", "Number"],
    required=False
)

course_col = find_col(
    courses.columns,
    [
        "course",
        "Course",
        "course_code",
        "CourseCode",
        "course_id",
        "CourseID",
    ],
    required=False
)

grade_col = find_col(
    courses.columns,
    [
        "grade",
        "Grade",
        "final_grade",
        "FinalGrade",
        "grade_code",
        "GradeCode",
    ]
)

course_term_col = find_col(
    courses.columns,
    [
        "term",
        "Term",
        "term_taken",
        "TermTaken",
        "term_code",
        "TermCode",
    ],
    required=False
)

if subject_col and number_col:
    educ_mask = (
        courses[subject_col].map(norm).eq("EDUC")
        & courses[number_col].map(norm).eq("1300")
    )
elif course_col:
    canonical = (
        courses[course_col]
        .map(norm)
        .str.replace(r"[^A-Z0-9]", "", regex=True)
    )
    educ_mask = canonical.eq("EDUC1300")
else:
    raise RuntimeError(
        "Could not identify EDUC 1300 from course-history columns."
    )

educ = courses[educ_mask].copy()

educ["_student_id"] = educ[course_id_col].map(norm_id)
educ["_grade"] = educ[grade_col].map(norm)

if course_term_col:
    educ["_course_term"] = educ[course_term_col].map(term_num)
else:
    educ["_course_term"] = None

print(f"Official certificate award rows: {len(cert):,}")
print(f"Distinct certificate recipients: {cert['_student_id'].nunique():,}")
print(f"EDUC 1300 course attempts found: {len(educ):,}")


# =============================================================================
# CLASSIFY EDUC 1300 STATUS AT EACH CERTIFICATE AWARD
# =============================================================================

GRADE_RANK = {
    "A": 4,
    "B": 3,
    "C": 2,
    "D": 1,
    "F": 0,
}

rows = []

for _, award in cert.iterrows():

    sid = award["_student_id"]

    attempts = educ[
        educ["_student_id"].eq(sid)
    ].copy()

    # Restrict to coursework existing by the award whenever term is available.
    if (
        award["_award_term"] is not None
        and course_term_col
    ):
        attempts = attempts[
            attempts["_course_term"].notna()
            & (
                attempts["_course_term"]
                <= award["_award_term"]
            )
        ].copy()

    letter = attempts[
        attempts["_grade"].isin(GRADE_RANK)
    ].copy()

    grades = letter["_grade"].tolist()

    if not grades:
        status = "NO_EDUC_1300_LETTER_GRADE"
        best_grade = ""

    else:
        best_grade = max(
            grades,
            key=lambda g: GRADE_RANK[g]
        )

        if best_grade in {"A", "B", "C"}:
            if "D" in grades:
                status = "D_OCCURRED_BUT_C_OR_BETTER_EXISTED_BY_AWARD"
            else:
                status = "C_OR_BETTER_BY_AWARD"

        elif best_grade == "D":
            status = "D_IS_HIGHEST_EDUC_1300_GRADE_AT_AWARD"

        else:
            status = "F_IS_HIGHEST_EDUC_1300_GRADE_AT_AWARD"

    rows.append({
        "student_id": sid,
        "Curr1ProgramCode": award.get("Curr1ProgramCode", ""),
        "Major1Code": award.get("Major1Code", ""),
        "DegreeCode": award.get("DegreeCode", ""),
        "MajorDesc": award.get("MajorDesc", ""),
        "DegreeDesc": award.get("DegreeDesc", ""),
        "canonical_lineage": award.get("canonical_lineage", ""),
        "award_term": (
            award.get(award_term_col, "")
            if award_term_col else ""
        ),
        "award_date": (
            award.get(award_date_col, "")
            if award_date_col else ""
        ),
        "educ1300_grades_by_award": " | ".join(grades),
        "best_educ1300_grade_by_award": best_grade,
        "educ1300_status": status,
    })

detail = pd.DataFrame(rows)

summary = (
    detail.groupby(
        "educ1300_status",
        dropna=False
    )
    .agg(
        certificate_awards=("student_id", "size"),
        distinct_students=("student_id", "nunique"),
    )
    .reset_index()
    .sort_values(
        "certificate_awards",
        ascending=False
    )
)

detail.to_csv(DETAIL, index=False)
summary.to_csv(SUMMARY, index=False)

critical = detail[
    detail["educ1300_status"]
    .eq("D_IS_HIGHEST_EDUC_1300_GRADE_AT_AWARD")
]

print()
print("=" * 100)
print("RESULTS — STUDENT BLIND")
print("=" * 100)

print(summary.to_string(index=False))

print()
print(
    "OFFICIAL CERTIFICATE AWARDS WHERE D WAS THE "
    "HIGHEST EDUC 1300 GRADE AT AWARD: "
    f"{len(critical):,}"
)

print(
    "DISTINCT STUDENTS IN THAT GROUP: "
    f"{critical['student_id'].nunique():,}"
)

print()
print("Outputs:")
print(SUMMARY.resolve())
print(DETAIL.resolve())
print()
print("FERPA: DETAIL contains student IDs; keep local.")
