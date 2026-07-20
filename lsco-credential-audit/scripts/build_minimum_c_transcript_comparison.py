from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from artifact_tool import Workbook, SpreadsheetFile


ROOT = Path.cwd()
EVIDENCE = ROOT / "data" / "processed" / "full_actual_audit" / "evidence" / "awardability"

AWARDABILITY = EVIDENCE / "selected_awards_awardability_screen_finalized.csv"
ATTEMPTS = ROOT / "data" / "processed" / "all_student_course_attempts_normalized.csv"
APPLIED = EVIDENCE / "selected_awards_applied_courses.csv"

OUTPUT = EVIDENCE / "minimum_c_review_transcript_comparison.xlsx"

GRADE_POINTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b", re.I)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def text(value) -> str:
    return "" if value is None else str(value).strip()


def normalize_course(value) -> str:
    match = COURSE_RE.search(text(value).upper())
    if not match:
        return text(value).upper()
    return f"{match.group(1).upper()} {match.group(2)}"


def derived_hours(course_code: str):
    match = COURSE_RE.search(text(course_code).upper())
    if not match:
        return None
    number = match.group(2)
    hours = int(number[1])
    return hours if hours > 0 else None


def resident_grade(grade: str) -> str:
    return "YES" if text(grade).upper() in GRADE_POINTS else "NO"


def grade_points(grade: str, hours):
    grade = text(grade).upper()
    if grade not in GRADE_POINTS or hours is None:
        return None
    return GRADE_POINTS[grade] * hours


def term_sort_value(value: str):
    try:
        return float(value)
    except Exception:
        return -1


for path in [AWARDABILITY, ATTEMPTS, APPLIED]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

awards = read_csv_rows(AWARDABILITY)
attempts = read_csv_rows(ATTEMPTS)
applied = read_csv_rows(APPLIED)

reviews = [
    row for row in awards
    if text(row.get("minimum_c_status")).upper() == "REVIEW"
]

if not reviews:
    raise RuntimeError("No minimum-C REVIEW awards were found.")

# Prefer a representative case from the largest remaining review group.
priority_order = [
    ("2025-2026", "PROCESS_TECHNOLOGY_2025"),
    ("2023-2024", "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2023"),
    ("2022-2023", "COURT_REPORTING_MACHINE_SHORTHAND_SCOPIST_2022"),
]

review_award = None
for year, credential_id in priority_order:
    review_award = next(
        (
            row for row in reviews
            if row.get("catalog_year") == year
            and row.get("credential_id") == credential_id
        ),
        None,
    )
    if review_award:
        break

if review_award is None:
    review_award = reviews[0]

same_credential_comparators = [
    row for row in awards
    if row.get("credential_id") == review_award.get("credential_id")
    and row.get("catalog_year") == review_award.get("catalog_year")
    and text(row.get("minimum_c_status")).upper() == "PASS"
    and text(row.get("awardability_status")).upper()
        == "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"
]

if not same_credential_comparators:
    same_credential_comparators = [
        row for row in awards
        if row.get("credential_id") == review_award.get("credential_id")
        and text(row.get("minimum_c_status")).upper() == "PASS"
    ]

if not same_credential_comparators:
    same_credential_comparators = [
        row for row in awards
        if text(row.get("minimum_c_status")).upper() == "PASS"
        and text(row.get("awardability_status")).upper()
            == "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"
    ]

if not same_credential_comparators:
    raise RuntimeError("No bona fide comparator could be selected.")

completer_award = same_credential_comparators[0]

review_student = text(review_award["student_id"])
completer_student = text(completer_award["student_id"])

def student_attempt_rows(student_id: str) -> list[dict]:
    rows = []
    for row in attempts:
        if text(row.get("student_id")) != student_id:
            continue
        course = normalize_course(row.get("course_code"))
        hours = derived_hours(course)
        grade = text(row.get("final_grade")).upper()
        rows.append(
            {
                "term_sort": text(row.get("term_sort")),
                "term_taken": text(row.get("term_taken")),
                "student_major": text(row.get("student_major")),
                "course_code": course,
                "final_grade": grade,
                "derived_hours": hours,
                "resident_grade": resident_grade(grade),
                "quality_points": grade_points(grade, hours),
            }
        )
    rows.sort(
        key=lambda r: (
            term_sort_value(r["term_sort"]),
            r["course_code"],
        )
    )
    return rows


def award_applied_rows(award: dict) -> list[dict]:
    rows = []
    for row in applied:
        if (
            text(row.get("student_id")) == text(award.get("student_id"))
            and text(row.get("catalog_year")) == text(award.get("catalog_year"))
            and text(row.get("credential_id")) == text(award.get("credential_id"))
        ):
            rows.append(row)
    rows.sort(
        key=lambda r: (
            text(r.get("estimated_major")).upper() != "TRUE",
            text(r.get("course")),
        )
    )
    return rows


review_transcript = student_attempt_rows(review_student)
completer_transcript = student_attempt_rows(completer_student)
review_applied = award_applied_rows(review_award)
completer_applied = award_applied_rows(completer_award)

wb = Workbook.create()

# --------------------------------------------------------------------------------------
# Summary sheet
# --------------------------------------------------------------------------------------
summary = wb.worksheets.add("Case Summary")
summary.merge_cells("A1:H1")
summary.get_range("A1").values = [["Minimum-C Review Comparison"]]
summary.get_range("A1:H1").format = {
    "fill": "#1F4E3D",
    "font": {"bold": True, "color": "#FFFFFF", "size": 16},
    "horizontal_alignment": "center",
    "vertical_alignment": "center",
}
summary.get_range("A1:H1").format.row_height = 28

summary.get_range("A3:D3").values = [[
    "Field", "Flagged Review Case", "Bona Fide Completer", "Interpretation"
]]
summary.get_range("A3:D3").format = {
    "fill": "#D9EAD3",
    "font": {"bold": True},
    "wrap_text": True,
}

fields = [
    ("Student ID", review_student, completer_student, "Local identifier"),
    ("Catalog Year", review_award.get("catalog_year"), completer_award.get("catalog_year"), ""),
    ("Credential", review_award.get("credential_title"), completer_award.get("credential_title"), ""),
    ("Credential ID", review_award.get("credential_id"), completer_award.get("credential_id"), ""),
    ("Program Hours", review_award.get("program_hours"), completer_award.get("program_hours"), ""),
    ("Latest Major", review_award.get("student_major", ""), completer_award.get("student_major", ""), "See transcript columns for term-by-term majors"),
    ("Academic Completion", review_award.get("audit_status"), completer_award.get("audit_status"), "Both originate from selected academically complete awards"),
    ("Residency", review_award.get("residency_status"), completer_award.get("residency_status"), ""),
    ("Institutional GPA", review_award.get("estimated_institutional_gpa"), completer_award.get("estimated_institutional_gpa"), ""),
    ("Certificate Plan GPA", review_award.get("estimated_certificate_plan_gpa"), completer_award.get("estimated_certificate_plan_gpa"), ""),
    ("Estimated Major GPA", review_award.get("estimated_major_gpa"), completer_award.get("estimated_major_gpa"), ""),
    ("Minimum-C Status", review_award.get("minimum_c_status"), completer_award.get("minimum_c_status"), ""),
    ("Applied Course Count", review_award.get("applied_course_count"), completer_award.get("applied_course_count"), ""),
    ("Estimated Major Course Count", review_award.get("estimated_major_course_count"), completer_award.get("estimated_major_course_count"), "Zero produces REVIEW"),
    ("Awardability", review_award.get("awardability_status"), completer_award.get("awardability_status"), ""),
    ("Reasons", review_award.get("awardability_reasons"), completer_award.get("awardability_reasons"), ""),
]

summary.get_range(f"A4:D{3+len(fields)}").values = [list(row) for row in fields]
summary.freeze_panes.freeze_rows(3)
summary.get_range("A:D").format.wrap_text = True
summary.get_range("A:A").format.column_width = 24
summary.get_range("B:C").format.column_width = 34
summary.get_range("D:D").format.column_width = 42

# --------------------------------------------------------------------------------------
# Side-by-side transcript sheet
# --------------------------------------------------------------------------------------
transcript = wb.worksheets.add("Transcript Comparison")
transcript.merge_cells("A1:H1")
transcript.merge_cells("J1:Q1")
transcript.get_range("A1").values = [[f"FLAGGED REVIEW — Student {review_student}"]]
transcript.get_range("J1").values = [[f"BONA FIDE COMPLETER — Student {completer_student}"]]

for rng in ["A1:H1", "J1:Q1"]:
    transcript.get_range(rng).format = {
        "fill": "#1F4E3D",
        "font": {"bold": True, "color": "#FFFFFF", "size": 13},
        "horizontal_alignment": "center",
    }

headers = [
    "Term Sort", "Term", "Major", "Course", "Grade",
    "SCH", "Resident A-F", "Quality Points"
]
transcript.get_range("A3:H3").values = [headers]
transcript.get_range("J3:Q3").values = [headers]
for rng in ["A3:H3", "J3:Q3"]:
    transcript.get_range(rng).format = {
        "fill": "#D9EAD3",
        "font": {"bold": True},
        "wrap_text": True,
    }

left = [[
    r["term_sort"], r["term_taken"], r["student_major"], r["course_code"],
    r["final_grade"], r["derived_hours"], r["resident_grade"], r["quality_points"]
] for r in review_transcript]
right = [[
    r["term_sort"], r["term_taken"], r["student_major"], r["course_code"],
    r["final_grade"], r["derived_hours"], r["resident_grade"], r["quality_points"]
] for r in completer_transcript]

max_rows = max(len(left), len(right), 1)
left += [[""] * 8 for _ in range(max_rows - len(left))]
right += [[""] * 8 for _ in range(max_rows - len(right))]

transcript.get_range(f"A4:H{3+max_rows}").values = left
transcript.get_range(f"J4:Q{3+max_rows}").values = right
transcript.freeze_panes.freeze_rows(3)

for col in ["A", "B", "J", "K"]:
    transcript.get_range(f"{col}:{col}").format.column_width = 13
for col in ["C", "L"]:
    transcript.get_range(f"{col}:{col}").format.column_width = 18
for col in ["D", "M"]:
    transcript.get_range(f"{col}:{col}").format.column_width = 15
for col in ["E", "F", "G", "H", "N", "O", "P", "Q"]:
    transcript.get_range(f"{col}:{col}").format.column_width = 12

transcript.get_range(f"A4:H{3+max_rows}").format.wrap_text = True
transcript.get_range(f"J4:Q{3+max_rows}").format.wrap_text = True

# --------------------------------------------------------------------------------------
# Applied-course evidence sheet
# --------------------------------------------------------------------------------------
applied_sheet = wb.worksheets.add("Applied Course Evidence")
applied_sheet.merge_cells("A1:H1")
applied_sheet.merge_cells("J1:Q1")
applied_sheet.get_range("A1").values = [["FLAGGED REVIEW — Applied Courses"]]
applied_sheet.get_range("J1").values = [["BONA FIDE COMPLETER — Applied Courses"]]

for rng in ["A1:H1", "J1:Q1"]:
    applied_sheet.get_range(rng).format = {
        "fill": "#1F4E3D",
        "font": {"bold": True, "color": "#FFFFFF", "size": 13},
        "horizontal_alignment": "center",
    }

applied_headers = [
    "Requirement ID", "Course", "Grade", "SCH",
    "Core", "Elective", "Estimated Major", "Course Level"
]
applied_sheet.get_range("A3:H3").values = [applied_headers]
applied_sheet.get_range("J3:Q3").values = [applied_headers]

for rng in ["A3:H3", "J3:Q3"]:
    applied_sheet.get_range(rng).format = {
        "fill": "#D9EAD3",
        "font": {"bold": True},
        "wrap_text": True,
    }

def applied_matrix(rows):
    return [[
        r.get("requirement_id", ""),
        r.get("course", ""),
        r.get("grade", ""),
        r.get("derived_hours", ""),
        r.get("is_core", ""),
        r.get("is_elective", ""),
        r.get("estimated_major", ""),
        r.get("course_level", ""),
    ] for r in rows]

left_a = applied_matrix(review_applied)
right_a = applied_matrix(completer_applied)
max_a = max(len(left_a), len(right_a), 1)
left_a += [[""] * 8 for _ in range(max_a - len(left_a))]
right_a += [[""] * 8 for _ in range(max_a - len(right_a))]

applied_sheet.get_range(f"A4:H{3+max_a}").values = left_a
applied_sheet.get_range(f"J4:Q{3+max_a}").values = right_a
applied_sheet.freeze_panes.freeze_rows(3)

for col in ["A", "J"]:
    applied_sheet.get_range(f"{col}:{col}").format.column_width = 25
for col in ["B", "K"]:
    applied_sheet.get_range(f"{col}:{col}").format.column_width = 15
for col in ["C", "D", "E", "F", "G", "H", "L", "M", "N", "O", "P", "Q"]:
    applied_sheet.get_range(f"{col}:{col}").format.column_width = 13

# --------------------------------------------------------------------------------------
# Notes sheet
# --------------------------------------------------------------------------------------
notes = wb.worksheets.add("Review Notes")
notes.get_range("A1:D1").values = [[
    "Question", "Flagged Case Evidence", "Completer Evidence", "Reviewer Conclusion"
]]
notes.get_range("A1:D1").format = {
    "fill": "#1F4E3D",
    "font": {"bold": True, "color": "#FFFFFF"},
    "wrap_text": True,
}

questions = [
    ["Did the flagged student actually complete the catalog requirements?", "", "", ""],
    ["Does the flagged student have any applied courses marked Estimated Major = TRUE?", "", "", ""],
    ["Are applied courses present but classified only as core/elective?", "", "", ""],
    ["Are there D/F grades in applied coursework?", "", "", ""],
    ["Is the REVIEW caused by no identified major course rather than failed coursework?", "", "", ""],
    ["Does the student's declared major differ from the credential?", "", "", ""],
    ["Should this credential receive a controlled minimum-C exception or a revised major-course map?", "", "", ""],
]
notes.get_range(f"A2:D{1+len(questions)}").values = questions
notes.get_range("A:D").format.wrap_text = True
notes.get_range("A:A").format.column_width = 48
notes.get_range("B:D").format.column_width = 34
notes.freeze_panes.freeze_rows(1)

SpreadsheetFile.export_xlsx(wb).save(str(OUTPUT))

print("=" * 100)
print("TRANSCRIPT COMPARISON WORKBOOK CREATED")
print("=" * 100)
print(f"Flagged review student: {review_student}")
print(f"Flagged credential: {review_award.get('credential_title')} ({review_award.get('catalog_year')})")
print(f"Comparator student: {completer_student}")
print(f"Comparator credential: {completer_award.get('credential_title')} ({completer_award.get('catalog_year')})")
print(f"Workbook: {OUTPUT}")
