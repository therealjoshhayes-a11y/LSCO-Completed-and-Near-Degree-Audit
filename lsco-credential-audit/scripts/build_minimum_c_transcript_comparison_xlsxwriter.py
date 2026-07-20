from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
EVIDENCE = ROOT / "data" / "processed" / "full_actual_audit" / "evidence" / "awardability"

AWARDABILITY = EVIDENCE / "selected_awards_awardability_screen_finalized.csv"
ATTEMPTS = ROOT / "data" / "processed" / "all_student_course_attempts_normalized.csv"
APPLIED = EVIDENCE / "selected_awards_applied_courses.csv"
OUTPUT = EVIDENCE / "minimum_c_review_transcript_comparison.xlsx"

GRADE_POINTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b", re.I)


def clean(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_course(value) -> str:
    match = COURSE_RE.search(clean(value).upper())
    if not match:
        return clean(value).upper()
    return f"{match.group(1).upper()} {match.group(2)}"


def derive_hours(course_code):
    match = COURSE_RE.search(clean(course_code).upper())
    if not match:
        return None
    value = int(match.group(2)[1])
    return value if value > 0 else None


def to_bool(value) -> bool:
    return clean(value).upper() == "TRUE"


for path in [AWARDABILITY, ATTEMPTS, APPLIED]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

awards = pd.read_csv(AWARDABILITY, dtype=str, low_memory=False)
attempts = pd.read_csv(ATTEMPTS, dtype=str, low_memory=False)
applied = pd.read_csv(APPLIED, dtype=str, low_memory=False)

for frame in [awards, attempts, applied]:
    if "student_id" in frame.columns:
        frame["student_id"] = frame["student_id"].astype(str)

reviews = awards[
    awards["minimum_c_status"].fillna("").str.upper().eq("REVIEW")
].copy()

if reviews.empty:
    raise RuntimeError("No minimum-C REVIEW awards were found.")

priority = [
    ("2025-2026", "PROCESS_TECHNOLOGY_2025"),
    ("2023-2024", "CRIMINAL_JUSTICE_LAW_ENFORCEMENT_2023"),
    ("2022-2023", "COURT_REPORTING_MACHINE_SHORTHAND_SCOPIST_2022"),
]

review_award = None
for year, credential_id in priority:
    match = reviews[
        reviews["catalog_year"].eq(year)
        & reviews["credential_id"].eq(credential_id)
    ]
    if not match.empty:
        review_award = match.iloc[0]
        break

if review_award is None:
    review_award = reviews.iloc[0]

comparators = awards[
    awards["catalog_year"].eq(review_award["catalog_year"])
    & awards["credential_id"].eq(review_award["credential_id"])
    & awards["minimum_c_status"].fillna("").str.upper().eq("PASS")
    & awards["awardability_status"].fillna("").str.upper().eq(
        "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"
    )
].copy()

if comparators.empty:
    comparators = awards[
        awards["credential_id"].eq(review_award["credential_id"])
        & awards["minimum_c_status"].fillna("").str.upper().eq("PASS")
    ].copy()

if comparators.empty:
    raise RuntimeError("No bona fide completer was found for comparison.")

completer_award = comparators.iloc[0]

review_student = str(review_award["student_id"])
completer_student = str(completer_award["student_id"])


def transcript_for(student_id: str) -> pd.DataFrame:
    data = attempts[attempts["student_id"].eq(student_id)].copy()
    data["course_code"] = data["course_code"].map(normalize_course)
    data["derived_hours"] = data["course_code"].map(derive_hours)
    data["final_grade"] = data["final_grade"].fillna("").str.upper()
    data["resident_a_f"] = data["final_grade"].isin(GRADE_POINTS).map(
        {True: "YES", False: "NO"}
    )
    data["quality_points"] = [
        (
            GRADE_POINTS.get(grade) * hours
            if grade in GRADE_POINTS and pd.notna(hours)
            else None
        )
        for grade, hours in zip(data["final_grade"], data["derived_hours"])
    ]
    data["term_sort_numeric"] = pd.to_numeric(data["term_sort"], errors="coerce")
    return data.sort_values(
        ["term_sort_numeric", "course_code"],
        na_position="last",
    )[
        [
            "term_sort",
            "term_taken",
            "student_major",
            "course_code",
            "final_grade",
            "derived_hours",
            "resident_a_f",
            "quality_points",
        ]
    ]


def applied_for(award: pd.Series) -> pd.DataFrame:
    data = applied[
        applied["student_id"].eq(str(award["student_id"]))
        & applied["catalog_year"].eq(award["catalog_year"])
        & applied["credential_id"].eq(award["credential_id"])
    ].copy()

    for column in ["is_core", "is_elective", "estimated_major"]:
        data[column] = data[column].map(to_bool).map(
            {True: "TRUE", False: "FALSE"}
        )

    return data.sort_values(
        ["estimated_major", "course"],
        ascending=[False, True],
    )[
        [
            "requirement_id",
            "course",
            "grade",
            "derived_hours",
            "is_core",
            "is_elective",
            "estimated_major",
            "course_level",
        ]
    ]


review_transcript = transcript_for(review_student)
completer_transcript = transcript_for(completer_student)
review_applied = applied_for(review_award)
completer_applied = applied_for(completer_award)

summary_fields = [
    "student_id",
    "catalog_year",
    "credential_title",
    "credential_id",
    "program_hours",
    "audit_status",
    "residency_status",
    "estimated_institutional_gpa",
    "institutional_gpa_status",
    "estimated_certificate_plan_gpa",
    "certificate_plan_gpa_status",
    "estimated_major_gpa",
    "estimated_major_course_count",
    "minimum_c_status",
    "awardability_status",
    "awardability_reasons",
]

with pd.ExcelWriter(OUTPUT, engine="xlsxwriter") as writer:
    workbook = writer.book

    title_fmt = workbook.add_format(
        {
            "bold": True,
            "font_color": "white",
            "bg_color": "#1F4E3D",
            "font_size": 14,
            "align": "center",
            "valign": "vcenter",
        }
    )
    header_fmt = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#D9EAD3",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    body_fmt = workbook.add_format(
        {"border": 1, "text_wrap": True, "valign": "top"}
    )
    note_fmt = workbook.add_format(
        {"bg_color": "#FFF2CC", "border": 1, "text_wrap": True}
    )
    fail_fmt = workbook.add_format(
        {"bg_color": "#F4CCCC", "border": 1, "text_wrap": True}
    )
    pass_fmt = workbook.add_format(
        {"bg_color": "#D9EAD3", "border": 1, "text_wrap": True}
    )

    # Case Summary
    summary_sheet = workbook.add_worksheet("Case Summary")
    writer.sheets["Case Summary"] = summary_sheet
    summary_sheet.merge_range("A1:D1", "Minimum-C Review Comparison", title_fmt)
    summary_sheet.write_row(
        "A3",
        ["Field", "Flagged Review Case", "Bona Fide Completer", "Interpretation"],
        header_fmt,
    )

    interpretations = {
        "audit_status": "Both cases originate from selected academically complete awards.",
        "estimated_major_course_count": "A zero count produces minimum-C REVIEW.",
        "minimum_c_status": "REVIEW means the heuristic identified no major-course rows; it does not itself mean incomplete.",
        "awardability_status": "Overall status also incorporates residency and GPA screens.",
    }

    for i, field in enumerate(summary_fields, start=3):
        summary_sheet.write(i, 0, field, body_fmt)
        summary_sheet.write(i, 1, clean(review_award.get(field)), body_fmt)
        summary_sheet.write(i, 2, clean(completer_award.get(field)), body_fmt)
        summary_sheet.write(i, 3, interpretations.get(field, ""), note_fmt)

    summary_sheet.set_column("A:A", 28)
    summary_sheet.set_column("B:C", 38)
    summary_sheet.set_column("D:D", 48)
    summary_sheet.freeze_panes(3, 0)

    # Transcript Comparison
    trans_sheet = workbook.add_worksheet("Transcript Comparison")
    writer.sheets["Transcript Comparison"] = trans_sheet
    trans_sheet.merge_range(
        "A1:H1", f"FLAGGED REVIEW — Student {review_student}", title_fmt
    )
    trans_sheet.merge_range(
        "J1:Q1", f"BONA FIDE COMPLETER — Student {completer_student}", title_fmt
    )

    transcript_headers = [
        "Term Sort",
        "Term",
        "Major",
        "Course",
        "Grade",
        "SCH",
        "Resident A-F",
        "Quality Points",
    ]
    trans_sheet.write_row("A3", transcript_headers, header_fmt)
    trans_sheet.write_row("J3", transcript_headers, header_fmt)

    max_rows = max(len(review_transcript), len(completer_transcript))
    for idx in range(max_rows):
        if idx < len(review_transcript):
            trans_sheet.write_row(
                idx + 3,
                0,
                review_transcript.iloc[idx].tolist(),
                body_fmt,
            )
        if idx < len(completer_transcript):
            trans_sheet.write_row(
                idx + 3,
                9,
                completer_transcript.iloc[idx].tolist(),
                body_fmt,
            )

    for col in ["A", "B", "J", "K"]:
        trans_sheet.set_column(f"{col}:{col}", 13)
    for col in ["C", "L"]:
        trans_sheet.set_column(f"{col}:{col}", 18)
    for col in ["D", "M"]:
        trans_sheet.set_column(f"{col}:{col}", 15)
    for col in ["E", "F", "G", "H", "N", "O", "P", "Q"]:
        trans_sheet.set_column(f"{col}:{col}", 12)
    trans_sheet.freeze_panes(3, 0)

    # Applied Course Evidence
    applied_sheet = workbook.add_worksheet("Applied Course Evidence")
    writer.sheets["Applied Course Evidence"] = applied_sheet
    applied_sheet.merge_range(
        "A1:H1", "FLAGGED REVIEW — Applied Courses", title_fmt
    )
    applied_sheet.merge_range(
        "J1:Q1", "BONA FIDE COMPLETER — Applied Courses", title_fmt
    )

    applied_headers = [
        "Requirement ID",
        "Course",
        "Grade",
        "SCH",
        "Core",
        "Elective",
        "Estimated Major",
        "Course Level",
    ]
    applied_sheet.write_row("A3", applied_headers, header_fmt)
    applied_sheet.write_row("J3", applied_headers, header_fmt)

    max_applied = max(len(review_applied), len(completer_applied))
    for idx in range(max_applied):
        if idx < len(review_applied):
            row = review_applied.iloc[idx].tolist()
            fmt = (
                pass_fmt
                if str(row[6]).upper() == "TRUE"
                else body_fmt
            )
            applied_sheet.write_row(idx + 3, 0, row, fmt)
        if idx < len(completer_applied):
            row = completer_applied.iloc[idx].tolist()
            fmt = (
                pass_fmt
                if str(row[6]).upper() == "TRUE"
                else body_fmt
            )
            applied_sheet.write_row(idx + 3, 9, row, fmt)

    applied_sheet.set_column("A:A", 28)
    applied_sheet.set_column("J:J", 28)
    applied_sheet.set_column("B:H", 14)
    applied_sheet.set_column("K:Q", 14)
    applied_sheet.freeze_panes(3, 0)

    # Review Notes
    notes = workbook.add_worksheet("Review Notes")
    writer.sheets["Review Notes"] = notes
    notes.write_row(
        "A1",
        ["Question", "Flagged Case Evidence", "Completer Evidence", "Reviewer Conclusion"],
        header_fmt,
    )
    questions = [
        "Did the flagged student complete the catalog requirements?",
        "Does the flagged student have any applied courses marked Estimated Major = TRUE?",
        "Are applied courses present but classified only as core/elective?",
        "Are there D/F grades in applied coursework?",
        "Is REVIEW caused by no identified major course rather than failed coursework?",
        "Does the student's declared major differ from the credential?",
        "Should this credential receive a controlled exception or revised major-course map?",
    ]
    for i, question in enumerate(questions, start=1):
        notes.write(i, 0, question, body_fmt)
        notes.write(i, 1, "", note_fmt)
        notes.write(i, 2, "", note_fmt)
        notes.write(i, 3, "", note_fmt)

    notes.set_column("A:A", 52)
    notes.set_column("B:D", 36)
    notes.freeze_panes(1, 0)

print("=" * 100)
print("TRANSCRIPT COMPARISON WORKBOOK CREATED")
print("=" * 100)
print(f"Flagged review student: {review_student}")
print(
    f"Flagged credential: {review_award['credential_title']} "
    f"({review_award['catalog_year']})"
)
print(f"Comparator student: {completer_student}")
print(
    f"Comparator credential: {completer_award['credential_title']} "
    f"({completer_award['catalog_year']})"
)
print(f"Workbook: {OUTPUT}")
