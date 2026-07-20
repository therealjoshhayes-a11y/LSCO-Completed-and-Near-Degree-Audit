from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
EVIDENCE = ROOT / "data" / "processed" / "full_actual_audit" / "evidence" / "awardability"

AWARDABILITY = EVIDENCE / "selected_awards_awardability_screen_finalized.csv"
REMAINING = EVIDENCE / "remaining_minimum_c_reviews.csv"
APPLIED = EVIDENCE / "selected_awards_applied_courses.csv"
ATTEMPTS = ROOT / "data" / "processed" / "all_student_course_attempts_normalized.csv"
FULL_HISTORY = ROOT / "data" / "processed" / "student_course_history_normalized_FULL_ACTUAL.csv"
REQUIREMENTS = ROOT / "data" / "processed" / "catalogs" / "requirements_master_multiyear.csv"

OUTPUT_XLSX = EVIDENCE / "remaining_26_transfer_major_test.xlsx"
OUTPUT_SUMMARY = EVIDENCE / "remaining_26_transfer_major_summary.csv"
OUTPUT_MATCHES = EVIDENCE / "remaining_26_transfer_major_matches.csv"
OUTPUT_GRADE_CODES = EVIDENCE / "remaining_26_nonresident_grade_codes.csv"

COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b", re.I)
RESIDENT_GRADES = {"A", "B", "C", "D", "F"}

# These are clearly not completed transfer-credit grades.
NONPASSING_NONRESIDENT = {
    "", "W", "WD", "WP", "WF", "I", "IP", "NG", "NR",
    "AU", "AUD", "X", "DROP", "WITHDRAWN",
}


def text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_grade(value) -> str:
    return text(value).upper()


def normalize_course(value) -> str:
    match = COURSE_RE.search(text(value).upper())
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def rubric(value) -> str:
    course = normalize_course(value)
    return course.split()[0] if course else ""


def parse_bool(value):
    value = text(value).upper()
    if value in {"TRUE", "T", "YES", "Y", "1"}:
        return True
    if value in {"FALSE", "F", "NO", "N", "0"}:
        return False
    return None


def split_codes(value) -> list[str]:
    return [
        f"{m.group(1).upper()} {m.group(2)}"
        for m in COURSE_RE.finditer(text(value).upper())
    ]


def discover_course_cip_lookup() -> tuple[pd.DataFrame, str]:
    """
    Search processed CSVs for a file containing both a course-code field and a CIP field.
    Only headers are read during discovery.
    """
    candidates = []

    for path in (ROOT / "data" / "processed").rglob("*.csv"):
        # Skip enormous audit outputs and the files already in use.
        lower_name = path.name.lower()
        if "audit_results" in lower_name or path == ATTEMPTS:
            continue

        try:
            columns = list(pd.read_csv(path, nrows=0).columns)
        except Exception:
            continue

        lower = {str(c).lower(): c for c in columns}

        course_cols = [
            original for lowered, original in lower.items()
            if lowered in {
                "course_code", "course", "normalized_course_code",
                "course_id", "course_number_full", "option_value",
            }
            or ("course" in lowered and "code" in lowered)
        ]
        cip_cols = [
            original for lowered, original in lower.items()
            if lowered == "cip"
            or "cip_code" in lowered
            or lowered.endswith("_cip")
            or lowered.startswith("cip_")
        ]

        if course_cols and cip_cols:
            candidates.append((path, course_cols[0], cip_cols[0]))

    if not candidates:
        return pd.DataFrame(columns=["course_code", "course_cip"]), ""

    best_frame = None
    best_source = ""
    best_count = -1

    for path, course_col, cip_col in candidates:
        try:
            frame = pd.read_csv(
                path,
                usecols=[course_col, cip_col],
                dtype=str,
                low_memory=False,
            )
        except Exception:
            continue

        frame["course_code"] = frame[course_col].map(normalize_course)
        frame["course_cip"] = frame[cip_col].map(text)
        frame = frame[
            frame["course_code"].ne("")
            & frame["course_cip"].ne("")
        ][["course_code", "course_cip"]].drop_duplicates()

        if len(frame) > best_count:
            best_frame = frame
            best_source = str(path)
            best_count = len(frame)

    if best_frame is None:
        return pd.DataFrame(columns=["course_code", "course_cip"]), ""

    return best_frame, best_source


for required in [AWARDABILITY, REMAINING, APPLIED, ATTEMPTS, REQUIREMENTS]:
    if not required.exists():
        raise FileNotFoundError(f"Required file not found: {required}")

awards = pd.read_csv(AWARDABILITY, dtype=str, low_memory=False)
remaining = pd.read_csv(REMAINING, dtype=str, low_memory=False)
applied = pd.read_csv(APPLIED, dtype=str, low_memory=False)
attempts = pd.read_csv(ATTEMPTS, dtype=str, low_memory=False)
requirements = pd.read_csv(REQUIREMENTS, dtype=str, low_memory=False)

for frame in [awards, remaining, applied, attempts, requirements]:
    if "student_id" in frame.columns:
        frame["student_id"] = frame["student_id"].astype(str)

# Use the richer history file when available because it includes an explicit passed field.
history_source = str(ATTEMPTS)
if FULL_HISTORY.exists():
    full = pd.read_csv(FULL_HISTORY, dtype=str, low_memory=False)
    full["student_id"] = full["student_id"].astype(str)

    keep = [
        column for column in [
            "student_id", "student_major", "course_code", "final_grade",
            "term_taken", "term_sort", "passed", "dual_credit_indicator",
        ]
        if column in full.columns
    ]
    attempts = full[keep].copy()
    history_source = str(FULL_HISTORY)

attempts["course_code_normalized"] = attempts["course_code"].map(normalize_course)
attempts["rubric"] = attempts["course_code_normalized"].map(rubric)
attempts["grade_normalized"] = attempts["final_grade"].map(normalize_grade)
attempts["is_resident_grade"] = attempts["grade_normalized"].isin(RESIDENT_GRADES)
attempts["is_nonresident_grade"] = ~attempts["is_resident_grade"]

if "passed" in attempts.columns:
    attempts["passed_explicit"] = attempts["passed"].map(parse_bool)
else:
    attempts["passed_explicit"] = None

# Nonresident credit candidate:
# - explicit passed=True when available; otherwise
# - any nonresident grade not in the clear nonpassing list.
attempts["transfer_credit_candidate"] = (
    attempts["is_nonresident_grade"]
    & (
        attempts["passed_explicit"].eq(True)
        | (
            attempts["passed_explicit"].isna()
            & ~attempts["grade_normalized"].isin(NONPASSING_NONRESIDENT)
        )
    )
    & attempts["course_code_normalized"].ne("")
)

# Build major-course/rubric map from the credential requirements.
requirements["rule_type_u"] = requirements["rule_type"].fillna("").str.upper()
requirements["option_type_u"] = requirements["option_type"].fillna("").str.upper()
requirements["group_name_u"] = requirements["group_name"].fillna("").str.upper()
requirements["source_text_u"] = (
    requirements["source_requirement_text"].fillna("").str.upper()
)

requirements["is_core"] = (
    requirements["rule_type_u"].eq("CORE_BUCKET")
    | requirements["option_type_u"].eq("CORE_BUCKET")
    | requirements["group_name_u"].str.contains("CORE CURRICULUM", regex=False)
    | requirements["source_text_u"].str.contains("CORE CURRICULUM", regex=False)
)
requirements["is_elective"] = (
    requirements["rule_type_u"].eq("ELECTIVE")
    | requirements["option_type_u"].eq("ELECTIVE")
    | requirements["group_name_u"].str.contains("ELECTIVE", regex=False)
    | requirements["source_text_u"].str.contains("ELECTIVE", regex=False)
)

requirements["requirement_courses"] = requirements["option_value"].map(split_codes)

major_req = requirements[
    ~requirements["is_core"]
    & ~requirements["is_elective"]
].copy()

major_req = major_req.explode("requirement_courses")
major_req["major_course"] = major_req["requirement_courses"].fillna("")
major_req = major_req[major_req["major_course"].ne("")]
major_req["major_rubric"] = major_req["major_course"].map(rubric)

course_cip, cip_source = discover_course_cip_lookup()
course_to_cip = dict(
    zip(course_cip["course_code"], course_cip["course_cip"])
) if not course_cip.empty else {}

major_req["major_course_cip"] = major_req["major_course"].map(course_to_cip)

credential_maps = []
for (year, credential_id), group in major_req.groupby(
    ["catalog_year", "credential_id"], dropna=False
):
    credential_maps.append(
        {
            "catalog_year": year,
            "credential_id": credential_id,
            "major_courses": " | ".join(sorted(set(group["major_course"]))),
            "major_rubrics": " | ".join(
                sorted(set(x for x in group["major_rubric"] if x))
            ),
            "major_cips": " | ".join(
                sorted(set(x for x in group["major_course_cip"] if text(x)))
            ),
            "major_course_count": group["major_course"].nunique(),
            "major_rubric_count": group["major_rubric"].nunique(),
            "major_cip_count": group["major_course_cip"].dropna().nunique(),
        }
    )

credential_map = pd.DataFrame(credential_maps)

remaining = remaining.merge(
    credential_map,
    on=["catalog_year", "credential_id"],
    how="left",
)

remaining_students = set(remaining["student_id"])
student_attempts = attempts[
    attempts["student_id"].isin(remaining_students)
].copy()
student_attempts["course_cip"] = student_attempts[
    "course_code_normalized"
].map(course_to_cip)

# Add applied status for each student's selected credential.
applied_subset = applied[
    applied["student_id"].isin(remaining_students)
].copy()
applied_subset["course_normalized"] = applied_subset["course"].map(normalize_course)
applied_keys = set(
    applied_subset[
        ["student_id", "catalog_year", "credential_id", "course_normalized"]
    ].itertuples(index=False, name=None)
)

match_rows = []
summary_rows = []

for award in remaining.itertuples(index=False):
    major_rubrics = {
        item.strip()
        for item in text(getattr(award, "major_rubrics", "")).split("|")
        if item.strip()
    }
    major_cips = {
        item.strip()
        for item in text(getattr(award, "major_cips", "")).split("|")
        if item.strip()
    }

    student_rows = student_attempts[
        student_attempts["student_id"].eq(award.student_id)
    ].copy()

    transfer_rows = student_rows[
        student_rows["transfer_credit_candidate"]
    ].copy()

    rubric_matches = transfer_rows[
        transfer_rows["rubric"].isin(major_rubrics)
    ].copy()

    cip_matches = transfer_rows[
        transfer_rows["course_cip"].isin(major_cips)
    ].copy() if major_cips else transfer_rows.iloc[0:0].copy()

    combined = pd.concat([rubric_matches, cip_matches], ignore_index=True)
    combined = combined.drop_duplicates(
        ["student_id", "course_code_normalized", "term_sort", "grade_normalized"]
    )

    applied_transfer_count = 0
    for row in combined.itertuples(index=False):
        key = (
            award.student_id,
            award.catalog_year,
            award.credential_id,
            row.course_code_normalized,
        )
        used_in_award = key in applied_keys
        applied_transfer_count += int(used_in_award)

        match_rows.append(
            {
                "student_id": award.student_id,
                "catalog_year": award.catalog_year,
                "credential_id": award.credential_id,
                "credential_title": award.credential_title,
                "student_major": getattr(row, "student_major", ""),
                "term_taken": getattr(row, "term_taken", ""),
                "term_sort": getattr(row, "term_sort", ""),
                "course_code": row.course_code_normalized,
                "rubric": row.rubric,
                "course_cip": row.course_cip,
                "final_grade": row.grade_normalized,
                "passed_explicit": getattr(row, "passed_explicit", None),
                "dual_credit_indicator": getattr(
                    row, "dual_credit_indicator", ""
                ),
                "rubric_match": row.rubric in major_rubrics,
                "cip_match": text(row.course_cip) in major_cips,
                "used_in_selected_award": used_in_award,
            }
        )

    if len(combined) == 0:
        conclusion = "NO_TRANSFER_MAJOR_MATCH_FOUND"
    elif applied_transfer_count > 0:
        conclusion = "TRANSFER_MAJOR_CREDIT_APPLIED_TO_AWARD"
    else:
        conclusion = "TRANSFER_MAJOR_CREDIT_PRESENT_NOT_APPLIED"

    summary_rows.append(
        {
            "student_id": award.student_id,
            "catalog_year": award.catalog_year,
            "credential_id": award.credential_id,
            "credential_title": award.credential_title,
            "credential_type": award.credential_type,
            "last_known_major": (
                student_rows.sort_values(
                    "term_sort",
                    ascending=False,
                    na_position="last",
                )["student_major"].dropna().iloc[0]
                if "student_major" in student_rows.columns
                and student_rows["student_major"].notna().any()
                else ""
            ),
            "major_rubrics": " | ".join(sorted(major_rubrics)),
            "major_cips": " | ".join(sorted(major_cips)),
            "all_nonresident_attempts": int(
                student_rows["is_nonresident_grade"].sum()
            ),
            "transfer_credit_candidates": int(
                student_rows["transfer_credit_candidate"].sum()
            ),
            "transfer_major_rubric_matches": len(rubric_matches),
            "transfer_major_cip_matches": len(cip_matches),
            "unique_transfer_major_matches": len(combined),
            "applied_transfer_major_matches": applied_transfer_count,
            "conclusion": conclusion,
            "awardability_reasons": award.awardability_reasons,
        }
    )

summary = pd.DataFrame(summary_rows)
matches = pd.DataFrame(match_rows)

grade_inventory = (
    student_attempts[
        student_attempts["is_nonresident_grade"]
    ]
    .groupby("grade_normalized", dropna=False)
    .agg(
        attempt_count=("course_code_normalized", "size"),
        distinct_students=("student_id", "nunique"),
        explicit_pass_count=(
            "passed_explicit",
            lambda values: sum(value is True for value in values),
        ),
        transfer_candidate_count=("transfer_credit_candidate", "sum"),
    )
    .reset_index()
    .sort_values("attempt_count", ascending=False)
)

credential_map_26 = remaining[
    [
        "catalog_year", "credential_id", "credential_title",
        "major_courses", "major_rubrics", "major_cips",
        "major_course_count", "major_rubric_count", "major_cip_count",
    ]
].drop_duplicates()

summary.to_csv(OUTPUT_SUMMARY, index=False)
matches.to_csv(OUTPUT_MATCHES, index=False)
grade_inventory.to_csv(OUTPUT_GRADE_CODES, index=False)

with pd.ExcelWriter(OUTPUT_XLSX, engine="xlsxwriter") as writer:
    summary.to_excel(writer, sheet_name="26 Case Summary", index=False)
    matches.to_excel(writer, sheet_name="Transfer Major Matches", index=False)
    grade_inventory.to_excel(writer, sheet_name="Grade Code Inventory", index=False)
    credential_map_26.to_excel(writer, sheet_name="Credential Major Map", index=False)

    workbook = writer.book
    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "white",
            "bg_color": "#1F4E3D",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    body = workbook.add_format(
        {"border": 1, "text_wrap": True, "valign": "top"}
    )
    pass_fmt = workbook.add_format(
        {"bg_color": "#D9EAD3", "border": 1, "text_wrap": True}
    )
    review_fmt = workbook.add_format(
        {"bg_color": "#FFF2CC", "border": 1, "text_wrap": True}
    )
    no_fmt = workbook.add_format(
        {"bg_color": "#F4CCCC", "border": 1, "text_wrap": True}
    )

    for sheet_name, frame in [
        ("26 Case Summary", summary),
        ("Transfer Major Matches", matches),
        ("Grade Code Inventory", grade_inventory),
        ("Credential Major Map", credential_map_26),
    ]:
        worksheet = writer.sheets[sheet_name]
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(len(frame), 1), max(len(frame.columns) - 1, 0))
        worksheet.set_row(0, 34, header)

        for col_idx, column in enumerate(frame.columns):
            width = min(
                max(
                    len(str(column)) + 2,
                    (
                        int(frame[column].astype(str).str.len().quantile(0.90)) + 2
                        if not frame.empty
                        else 12
                    ),
                ),
                42,
            )
            worksheet.set_column(col_idx, col_idx, width, body)

    if not summary.empty:
        conclusion_col = summary.columns.get_loc("conclusion")
        for row_idx, value in enumerate(summary["conclusion"], start=1):
            fmt = (
                pass_fmt if value == "TRANSFER_MAJOR_CREDIT_APPLIED_TO_AWARD"
                else review_fmt if value == "TRANSFER_MAJOR_CREDIT_PRESENT_NOT_APPLIED"
                else no_fmt
            )
            writer.sheets["26 Case Summary"].write(
                row_idx, conclusion_col, value, fmt
            )

print("=" * 110)
print("TRANSFER CREDIT TEST FOR 26 MINIMUM-C REVIEW CASES")
print("=" * 110)
print(f"Cases tested: {len(summary):,}")
print(f"Course history source: {history_source}")
print(f"CIP lookup source: {cip_source or 'NONE FOUND'}")

print("\nConclusions:")
print(summary["conclusion"].value_counts(dropna=False).to_string())

print("\nCases with transfer major credit applied to the selected award:")
applied_cases = summary[
    summary["conclusion"].eq("TRANSFER_MAJOR_CREDIT_APPLIED_TO_AWARD")
]
if applied_cases.empty:
    print("None")
else:
    print(
        applied_cases[
            [
                "student_id", "catalog_year", "credential_title",
                "last_known_major", "unique_transfer_major_matches",
                "applied_transfer_major_matches",
            ]
        ].to_string(index=False)
    )

print("\nCases with transfer major credit present but not applied:")
present_cases = summary[
    summary["conclusion"].eq("TRANSFER_MAJOR_CREDIT_PRESENT_NOT_APPLIED")
]
if present_cases.empty:
    print("None")
else:
    print(
        present_cases[
            [
                "student_id", "catalog_year", "credential_title",
                "last_known_major", "unique_transfer_major_matches",
            ]
        ].to_string(index=False)
    )

print("\nOutputs:")
print(OUTPUT_XLSX)
print(OUTPUT_SUMMARY)
print(OUTPUT_MATCHES)
print(OUTPUT_GRADE_CODES)
