from pathlib import Path
import re
import pandas as pd

ROOT = Path.cwd()

CASES = (
    ROOT / "data/processed/reporting/"
    "expiring_2021_2022_student_reconciliation_20260811/"
    "REMAINING_THREE_DEEP_DIVE_LOCAL.csv"
)

HISTORY = (
    ROOT / "data/processed/"
    "normalized_actual_student_course_history.csv"
)


# =============================================================================
# HELPERS
# =============================================================================

def norm(v):
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def norm_id(v):
    return re.sub(r"\.0$", "", norm(v))


def norm_course(v):
    return re.sub(r"[^A-Z0-9]", "", norm(v))


def find_col(cols, names, required=True):
    lookup = {str(c).strip().lower(): c for c in cols}

    for n in names:
        if n.lower() in lookup:
            return lookup[n.lower()]

    if required:
        raise RuntimeError(
            f"Missing one of {names}\nColumns: {list(cols)}"
        )

    return None


# =============================================================================
# PUBLISHED 2021-2022 ORDINARY SEAMAN I
#
# NOTE:
# Catalog rendering "NAUT1 1372" is treated as NAUT 1372.
# =============================================================================

REQUIRED = {
    "EDUC1300": "Learning Framework",
    "NAUT1370": "Introduction to Tugs and Towing",
    "NAUT1372": "Seamanship I",
    "NAUT1371": "Introduction to Ships and Shipping",
    "NAUT1374": "Basic Safety and Survival",
}

# Same subject matter/titles under the next catalog's numbering.
RENBR = {
    "NAUT1370": "NAUT1343",
    "NAUT1372": "NAUT1320",
    "NAUT1371": "NAUT1305",
    "NAUT1374": "NAUT1315",
}

REVERSE_RENBR = {
    new: old
    for old, new in RENBR.items()
}


# =============================================================================
# IDENTIFY THE NON-D ORDINARY SEAMAN CASE
# =============================================================================

cases = pd.read_csv(
    CASES,
    dtype=str,
    low_memory=False,
).fillna("")

target = cases[
    cases["unawarded_credential"]
    .str.upper()
    .eq("ORDINARY SEAMAN I")
    &
    cases["educ1300_best_letter_grade"]
    .str.upper()
    .ne("D")
].copy()

if len(target) != 1:
    raise RuntimeError(
        f"Expected exactly one non-D Ordinary Seaman I case; "
        f"found {len(target)}"
    )

sid = norm_id(target.iloc[0]["student_id"])


# =============================================================================
# LOAD TRANSCRIPT
# =============================================================================

h = pd.read_csv(
    HISTORY,
    dtype=str,
    low_memory=False,
).fillna("")

sid_col = find_col(
    h.columns,
    ["student_id", "StudentID", "ID", "Banner ID"]
)

course_col = find_col(
    h.columns,
    ["course", "course_code", "CourseCode", "course_id", "CourseID"],
    required=False,
)

subject_col = find_col(
    h.columns,
    ["subject", "Subject", "course_subject"],
    required=False,
)

number_col = find_col(
    h.columns,
    ["course_number", "CourseNumber", "number"],
    required=False,
)

grade_col = find_col(
    h.columns,
    ["grade", "Grade", "final_grade", "FinalGrade",
     "grade_code", "GradeCode"]
)

term_col = find_col(
    h.columns,
    ["term", "Term", "term_code", "TermCode",
     "term_taken", "TermTaken"],
    required=False,
)

title_col = find_col(
    h.columns,
    ["course_title", "CourseTitle", "title", "Title",
     "course_description"],
    required=False,
)

hours_col = find_col(
    h.columns,
    ["credit_hours", "CreditHours", "credits",
     "Credits", "sch", "SCH"],
    required=False,
)

h["_student_id"] = h[sid_col].map(norm_id)

if course_col:
    h["_course"] = h[course_col].map(norm_course)

elif subject_col and number_col:
    h["_course"] = (
        h[subject_col].map(norm)
        + h[number_col].map(norm)
    ).map(norm_course)

else:
    raise RuntimeError("Cannot construct course codes.")

h["_grade"] = h[grade_col].map(norm)

s = h[h["_student_id"].eq(sid)].copy()

if s.empty:
    raise RuntimeError("No course history found for target student.")


# =============================================================================
# PASSING ATTEMPTS
# =============================================================================

PASSING = {
    "A", "B", "C", "D",
    "P", "S", "CR",
}

passed = s[s["_grade"].isin(PASSING)].copy()

passed_codes = set(passed["_course"])


# =============================================================================
# AUDIT EACH 2021 REQUIREMENT
# =============================================================================

audit_rows = []

for req_code, req_title in REQUIRED.items():

    exact = passed[
        passed["_course"].eq(req_code)
    ]

    replacement_code = RENBR.get(req_code, "")

    replacement = (
        passed[
            passed["_course"].eq(replacement_code)
        ]
        if replacement_code
        else passed.iloc[0:0]
    )

    if not exact.empty:
        status = "EXACT"
        used_code = req_code
        used_grade = " | ".join(
            exact["_grade"].tolist()
        )

    elif not replacement.empty:
        status = "LATER-NUMBERED EQUIVALENT / POSSIBLE SUB"
        used_code = replacement_code
        used_grade = " | ".join(
            replacement["_grade"].tolist()
        )

    else:
        status = "MISSING"
        used_code = ""
        used_grade = ""

    audit_rows.append({
        "2021 Requirement": req_code,
        "Requirement Title": req_title,
        "Status": status,
        "Course Present": used_code,
        "Grade": used_grade,
    })


audit = pd.DataFrame(audit_rows)


# =============================================================================
# CLASSIFY EVERY TRANSCRIPT COURSE
# =============================================================================

def role(code):

    if code in REQUIRED:
        return "EXACT 2021 OSI REQUIREMENT"

    if code in REVERSE_RENBR:
        return (
            "LATER-NUMBERED OSI EQUIVALENT "
            f"(maps to {REVERSE_RENBR[code]})"
        )

    return "OTHER COURSE"


s["Role vs 2021 OSI"] = s["_course"].map(role)

display = pd.DataFrame({
    "Course": s["_course"],
    "Grade": s["_grade"],
    "Role vs 2021 OSI": s["Role vs 2021 OSI"],
})

if title_col:
    display.insert(
        1,
        "Title",
        s[title_col].astype(str)
    )

if hours_col:
    display["SCH"] = s[hours_col]

if term_col:
    display["Term"] = s[term_col]

sort_cols = (
    ["Term", "Course"]
    if "Term" in display.columns
    else ["Course"]
)

display = display.sort_values(sort_cols)


# =============================================================================
# OTHER PASSED COURSES ONLY
# =============================================================================

other = display[
    display["Role vs 2021 OSI"]
    .eq("OTHER COURSE")
    &
    display["Grade"]
    .isin(PASSING)
].copy()


# =============================================================================
# PRINT — NO STUDENT ID
# =============================================================================

print("=" * 110)
print("ORDINARY SEAMAN I — 2021-2022 COURSE AUDIT")
print("TARGET: NON-D / REGISTRAR-SAYS-AWARDED CASE")
print("=" * 110)

print("\nPUBLISHED REQUIREMENTS VS TRANSCRIPT\n")
print(audit.to_string(index=False))

print("\n" + "=" * 110)
print("OTHER PASSED COURSES PRESENT")
print("=" * 110)

if other.empty:
    print("NONE")
else:
    print(other.to_string(index=False))

print("\n" + "=" * 110)
print("COMPLETE TRANSCRIPT — CLASSIFIED AGAINST OSI")
print("=" * 110)

print(display.to_string(index=False))

print("\n" + "=" * 110)
print("INTERPRETATION")
print("=" * 110)

missing = audit[
    audit["Status"].eq("MISSING")
]

subs = audit[
    audit["Status"]
    .str.startswith("LATER-NUMBERED")
]

print("Exact 2021 requirements present:",
      int(audit["Status"].eq("EXACT").sum()))

print("Later-numbered equivalents / possible subs:",
      len(subs))

print("Requirements still missing:",
      len(missing))

if not subs.empty:
    print("\nPOSSIBLE COURSE SUBSTITUTION / RENUMBERING:")
    print(
        subs[
            [
                "2021 Requirement",
                "Requirement Title",
                "Course Present",
                "Grade",
            ]
        ].to_string(index=False)
    )

if not missing.empty:
    print("\nSTILL MISSING:")
    print(
        missing[
            [
                "2021 Requirement",
                "Requirement Title",
            ]
        ].to_string(index=False)
    )
