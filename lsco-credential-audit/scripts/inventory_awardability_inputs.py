from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path.cwd()

OUTPUT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "full_actual_audit"
    / "evidence"
    / "awardability"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INVENTORY_CSV = OUTPUT_DIR / "awardability_input_inventory.csv"
READINESS_JSON = OUTPUT_DIR / "awardability_input_readiness.json"


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def existing(paths: Iterable[Path]) -> list[Path]:
    return [p for p in paths if p.exists() and p.is_file()]


def read_header(path: Path) -> list[str]:
    try:
        return list(pd.read_csv(path, nrows=0, low_memory=False).columns)
    except Exception:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.reader(f)
            return next(reader, [])


def normalize_name(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def match_columns(columns: list[str], aliases: list[str]) -> list[str]:
    normalized = {normalize_name(c): c for c in columns}
    matches: list[str] = []

    for alias in aliases:
        alias_n = normalize_name(alias)

        if alias_n in normalized:
            matches.append(normalized[alias_n])
            continue

        for normalized_col, original_col in normalized.items():
            if alias_n in normalized_col:
                matches.append(original_col)

    return sorted(set(matches))


def file_metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.relative_to(ROOT)),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def count_rows_safely(path: Path, max_size_mb: int = 200) -> int | None:
    """
    Count rows only for reasonably small files.
    Avoid scanning the 59-million-row detail output.
    """
    if path.stat().st_size > max_size_mb * 1024 * 1024:
        return None

    count = 0
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        next(f, None)
        for _ in f:
            count += 1
    return count


# --------------------------------------------------------------------------------------
# Locate latest award-selection output
# --------------------------------------------------------------------------------------

reporting_root = ROOT / "data" / "processed" / "reporting"

award_dirs = sorted(
    [
        p
        for p in reporting_root.glob("award_selection_*")
        if p.is_dir()
    ],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)

latest_award_dir = award_dirs[0] if award_dirs else None
latest_award_files = (
    sorted(latest_award_dir.glob("*.csv"))
    if latest_award_dir
    else []
)


# --------------------------------------------------------------------------------------
# Candidate source files
# --------------------------------------------------------------------------------------

candidate_groups: dict[str, list[Path]] = {
    "selected_awards": latest_award_files,

    "course_attempts": existing(
        [
            ROOT / "data" / "processed" / "all_student_course_attempts_normalized.csv",
            ROOT / "data" / "processed" / "student_course_attempts_normalized.csv",
            ROOT / "data" / "processed" / "student_course_history_normalized_FULL_ACTUAL.csv",
            ROOT / "data" / "processed" / "full_actual_audit" / "all_student_course_attempts_normalized.csv",
            ROOT / "data" / "processed" / "full_actual_audit" / "student_course_history_normalized_FULL_ACTUAL.csv",
        ]
    ),

    "requirements": existing(
        [
            ROOT / "data" / "processed" / "catalogs" / "requirements_master_multiyear.csv",
            ROOT / "data" / "processed" / "catalogs" / "requirements_master_multicatalog.csv",
            ROOT / "data" / "processed" / "catalogs" / "requirements_master_multicatalog.csv",
        ]
    ),

    "audit_detail": existing(
        [
            ROOT / "data" / "processed" / "full_actual_audit" / "full_actual_audit_results.csv",
        ]
    ),

    "audit_summary": existing(
        [
            ROOT / "data" / "processed" / "full_actual_audit" / "full_actual_credential_summary.csv",
        ]
    ),

    "course_crosswalk": existing(
        [
            ROOT / "data" / "processed" / "catalogs" / "catalog_academic_course_crosswalk_final.csv",
            ROOT / "data" / "processed" / "catalog_academic_course_crosswalk_final.csv",
        ]
    ),
}


# --------------------------------------------------------------------------------------
# Semantic fields we need
# --------------------------------------------------------------------------------------

FIELD_ALIASES: dict[str, list[str]] = {
    "student_id": [
        "student_id",
        "student",
        "banner_id",
        "pidm",
    ],

    "catalog_year": [
        "catalog_year",
        "catalog",
    ],

    "credential_id": [
        "credential_id",
        "credential",
        "program_id",
        "award_id",
    ],

    "credential_family": [
        "credential_family",
        "credential_lineage",
        "lineage",
        "family",
    ],

    "credential_type": [
        "credential_type",
        "award_type",
        "degree_type",
        "program_type",
    ],

    "course_code": [
        "course_code",
        "course",
        "subject_course",
        "subject_number",
        "crse_id",
    ],

    "subject": [
        "subject",
        "rubric",
        "subj",
    ],

    "course_number": [
        "course_number",
        "course_no",
        "crse_numb",
        "number",
    ],

    "term": [
        "term_taken",
        "term",
        "term_code",
        "semester",
    ],

    "term_sort": [
        "term_sort",
        "term_sequence",
        "term_order",
    ],

    "grade": [
        "grade",
        "final_grade",
        "grade_code",
        "grde_code_final",
    ],

    "credit_hours": [
        "credit_hours",
        "course_hours",
        "hours",
        "credit_hrs",
        "credits",
        "credit_hour",
    ],

    "institutional_source": [
        "institutional",
        "institution",
        "course_source",
        "credit_source",
        "source_type",
        "transfer_indicator",
        "transfer",
        "home_institution",
    ],

    "repeat_indicator": [
        "repeat_indicator",
        "repeat",
        "repeat_code",
        "repeat_status",
        "grade_replacement",
    ],

    "quality_points": [
        "quality_points",
        "grade_points",
        "quality_pts",
    ],

    "quality_hours": [
        "quality_hours",
        "gpa_hours",
        "attempted_gpa_hours",
    ],

    "requirement_id": [
        "requirement_id",
        "requirement",
    ],

    "rule_type": [
        "rule_type",
        "requirement_type",
    ],

    "option_type": [
        "option_type",
        "option_types",
    ],

    "requirement_group": [
        "requirement_group",
        "group_name",
        "section",
        "requirement_section",
        "semester_name",
    ],

    "matched_options": [
        "matched_options",
        "matched_courses",
        "used_courses",
    ],

    "matched_grades": [
        "matched_grades",
        "grades_used",
    ],

    "status": [
        "status",
        "audit_status",
    ],

    "program_hours": [
        "program_hours",
        "total_program_hours",
        "credential_hours",
        "degree_hours",
        "certificate_hours",
    ],
}


# --------------------------------------------------------------------------------------
# Build inventory
# --------------------------------------------------------------------------------------

inventory_rows: list[dict] = []

for group_name, paths in candidate_groups.items():
    for path in paths:
        columns = read_header(path)
        metadata = file_metadata(path)

        row = {
            "source_group": group_name,
            **metadata,
            "row_count_if_small": count_rows_safely(path),
            "column_count": len(columns),
            "columns": " | ".join(columns),
        }

        for semantic_field, aliases in FIELD_ALIASES.items():
            row[f"{semantic_field}_matches"] = " | ".join(
                match_columns(columns, aliases)
            )

        inventory_rows.append(row)

inventory_df = pd.DataFrame(inventory_rows)

if not inventory_df.empty:
    inventory_df = inventory_df.sort_values(
        ["source_group", "modified", "path"],
        ascending=[True, False, True],
    )

inventory_df.to_csv(INVENTORY_CSV, index=False)


# --------------------------------------------------------------------------------------
# Readiness assessment
# --------------------------------------------------------------------------------------

def group_has(group: str, field: str) -> bool:
    if inventory_df.empty:
        return False

    subset = inventory_df[inventory_df["source_group"] == group]
    column = f"{field}_matches"

    if column not in subset.columns or subset.empty:
        return False

    return bool(subset[column].fillna("").str.strip().ne("").any())


def group_files(group: str) -> list[str]:
    if inventory_df.empty:
        return []

    return inventory_df.loc[
        inventory_df["source_group"] == group,
        "path",
    ].tolist()


readiness = {
    "latest_award_selection_directory": (
        str(latest_award_dir.relative_to(ROOT))
        if latest_award_dir
        else None
    ),

    "files_by_group": {
        group: group_files(group)
        for group in candidate_groups
    },

    "associate_institutional_gpa": {
        "student_id": group_has("course_attempts", "student_id"),
        "grade": group_has("course_attempts", "grade"),
        "credit_hours": group_has("course_attempts", "credit_hours"),
        "institutional_source": group_has("course_attempts", "institutional_source"),
        "repeat_indicator": group_has("course_attempts", "repeat_indicator"),
        "quality_points": group_has("course_attempts", "quality_points"),
        "quality_hours": group_has("course_attempts", "quality_hours"),
    },

    "certificate_plan_gpa": {
        "selected_awards_student_id": group_has("selected_awards", "student_id"),
        "selected_awards_credential_id": group_has("selected_awards", "credential_id"),
        "detail_student_id": group_has("audit_detail", "student_id"),
        "detail_credential_id": group_has("audit_detail", "credential_id"),
        "detail_requirement_id": group_has("audit_detail", "requirement_id"),
        "detail_matched_options": group_has("audit_detail", "matched_options"),
        "detail_matched_grades": group_has("audit_detail", "matched_grades"),
        "attempt_grade": group_has("course_attempts", "grade"),
        "attempt_credit_hours": group_has("course_attempts", "credit_hours"),
    },

    "residency": {
        "selected_awards_student_id": group_has("selected_awards", "student_id"),
        "selected_awards_credential_id": group_has("selected_awards", "credential_id"),
        "selected_awards_catalog_year": group_has("selected_awards", "catalog_year"),
        "attempt_institutional_source": group_has("course_attempts", "institutional_source"),
        "attempt_credit_hours": group_has("course_attempts", "credit_hours"),
        "detail_matched_options": group_has("audit_detail", "matched_options"),
        "requirements_program_hours": group_has("requirements", "program_hours"),
    },

    "estimated_major_gpa": {
        "requirements_rule_type": group_has("requirements", "rule_type"),
        "requirements_option_type": group_has("requirements", "option_type"),
        "requirements_group": group_has("requirements", "requirement_group"),
        "detail_matched_options": group_has("audit_detail", "matched_options"),
        "detail_matched_grades": group_has("audit_detail", "matched_grades"),
    },
}

with READINESS_JSON.open("w", encoding="utf-8") as f:
    json.dump(readiness, f, indent=2)


# --------------------------------------------------------------------------------------
# Console report
# --------------------------------------------------------------------------------------

print("=" * 110)
print("AWARDABILITY INPUT INVENTORY")
print("=" * 110)

if latest_award_dir:
    print(f"Latest award-selection directory: {latest_award_dir.relative_to(ROOT)}")
else:
    print("Latest award-selection directory: NOT FOUND")

print()

for group_name in candidate_groups:
    subset = inventory_df[inventory_df["source_group"] == group_name]

    print("-" * 110)
    print(group_name.upper())
    print("-" * 110)

    if subset.empty:
        print("No candidate files found.")
        continue

    for _, row in subset.iterrows():
        print(f"File: {row['path']}")
        print(f"Modified: {row['modified']}")
        print(f"Size bytes: {row['size_bytes']:,}")
        print(f"Columns ({row['column_count']}):")
        print(row["columns"])
        print()

print("=" * 110)
print("READINESS SUMMARY")
print("=" * 110)

for test_name, checks in readiness.items():
    if not isinstance(checks, dict) or test_name == "files_by_group":
        continue

    print()
    print(test_name.upper())

    for check_name, result in checks.items():
        marker = "FOUND" if result else "MISSING"
        print(f"  {marker:<8} {check_name}")

print()
print("=" * 110)
print("OUTPUTS")
print("=" * 110)
print(f"Inventory: {INVENTORY_CSV.relative_to(ROOT)}")
print(f"Readiness: {READINESS_JSON.relative_to(ROOT)}")
