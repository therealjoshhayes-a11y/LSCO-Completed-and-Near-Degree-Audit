from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"
REQ_PATH = ROOT / "data" / "processed" / "catalogs" / "requirements_master_multiyear.csv"
OUT = ROOT / "data" / "processed" / "full_actual_audit" / "evidence" / "awardability"

APPLIED_PATH = OUT / "selected_awards_applied_courses.csv"
INST_GPA_PATH = OUT / "student_institutional_gpa_estimates.csv"
ISSUES_PATH = OUT / "awardability_screen_issues.csv"

AWARDABILITY_OUTPUT = OUT / "selected_awards_awardability_screen.csv"
SUMMARY_OUTPUT = OUT / "awardability_screen_summary.csv"

GRADE_POINTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}


def weighted_gpa(df: pd.DataFrame) -> tuple[float, float, float]:
    valid = df[
        df["grade"].isin(GRADE_POINTS)
        & df["derived_hours"].notna()
    ].copy()

    if valid.empty:
        return np.nan, 0.0, 0.0

    quality_points = sum(
        GRADE_POINTS[grade] * float(hours)
        for grade, hours in zip(valid["grade"], valid["derived_hours"])
    )
    gpa_hours = float(valid["derived_hours"].sum())

    return (
        quality_points / gpa_hours if gpa_hours else np.nan,
        quality_points,
        gpa_hours,
    )


def classify_by_hours(program_hours: float, credential_title: str) -> str:
    """
    Authorized LSCO controlled rule:
      - every 60-hour credential is an associate;
      - the 57-hour Court Reporting credential is an associate;
      - everything else is a certificate;
      - there are no IA credentials.
    """
    title = str(credential_title or "").upper()

    if pd.notna(program_hours) and abs(float(program_hours) - 60.0) < 0.001:
        return "ASSOCIATE"

    if (
        pd.notna(program_hours)
        and abs(float(program_hours) - 57.0) < 0.001
        and "COURT" in title
        and "REPORT" in title
    ):
        return "ASSOCIATE"

    return "CERT"


def residency_policy(
    catalog_year: str,
    credential_type: str,
    program_hours: float,
) -> tuple[str, float, float]:
    if pd.isna(program_hours) or float(program_hours) <= 0:
        return "PROGRAM_HOURS_UNRESOLVED", np.nan, np.nan

    quarter = int(math.ceil(float(program_hours) * 0.25))

    if credential_type == "ASSOCIATE":
        if catalog_year == "2025-2026":
            return "ASSOCIATE_25_PERCENT_MINIMUM_15", max(quarter, 15), 0

        return "ASSOCIATE_25_PERCENT_PLUS_12_UPPER_OR_CORE", quarter, 12

    if catalog_year == "2025-2026":
        return "CERTIFICATE_25_PERCENT", quarter, 0

    return "CERTIFICATE_FIXED_13_HOURS", 13, 0


award_dirs = sorted(
    [p for p in REPORTING.glob("award_selection_*") if p.is_dir()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)

if not award_dirs:
    raise FileNotFoundError("No award_selection_* directory found.")

selected_path = award_dirs[0] / "selected_awards.csv"

for required_path in [selected_path, REQ_PATH, APPLIED_PATH, INST_GPA_PATH]:
    if not required_path.exists():
        raise FileNotFoundError(f"Required file not found: {required_path}")

selected = pd.read_csv(selected_path, dtype=str, low_memory=False)
requirements = pd.read_csv(REQ_PATH, dtype=str, low_memory=False)
applied = pd.read_csv(APPLIED_PATH, dtype={"student_id": str}, low_memory=False)
institutional = pd.read_csv(INST_GPA_PATH, dtype={"student_id": str}, low_memory=False)

if ISSUES_PATH.exists():
    issues = pd.read_csv(ISSUES_PATH, dtype=str, low_memory=False)
else:
    issues = pd.DataFrame(
        columns=["student_id", "catalog_year", "credential_id"]
    )

for frame in [selected, applied]:
    for column in ["student_id", "catalog_year", "credential_id"]:
        if column in frame.columns:
            frame[column] = frame[column].astype(str)

institutional["student_id"] = institutional["student_id"].astype(str)

requirements["credit_hours_numeric"] = pd.to_numeric(
    requirements["credit_hours"],
    errors="coerce",
)

requirement_inventory = (
    requirements
    .sort_values(
        ["catalog_year", "credential_id", "requirement_id", "sequence"]
    )
    .drop_duplicates(["catalog_year", "credential_id", "requirement_id"])
)

credential_inventory = (
    requirement_inventory
    .groupby(["catalog_year", "credential_id"], as_index=False)
    .agg(
        credential_title=("credential_title", "first"),
        program_hours=("credit_hours_numeric", "sum"),
        requirement_count=("requirement_id", "nunique"),
    )
)

selected = selected.drop(
    columns=[
        column
        for column in ["credential_title", "program_hours", "requirement_count"]
        if column in selected.columns
    ],
    errors="ignore",
)

selected = selected.merge(
    credential_inventory,
    on=["catalog_year", "credential_id"],
    how="left",
    validate="many_to_one",
)

selected["credential_type"] = [
    classify_by_hours(hours, title)
    for hours, title in zip(
        selected["program_hours"],
        selected["credential_title"],
    )
]

applied["derived_hours"] = pd.to_numeric(
    applied["derived_hours"],
    errors="coerce",
)
applied["course_level"] = pd.to_numeric(
    applied["course_level"],
    errors="coerce",
)
applied["is_core"] = (
    applied["is_core"]
    .astype(str)
    .str.upper()
    .map({"TRUE": True, "FALSE": False})
    .fillna(False)
)
applied["estimated_major"] = (
    applied["estimated_major"]
    .astype(str)
    .str.upper()
    .map({"TRUE": True, "FALSE": False})
    .fillna(False)
)

rows: list[dict] = []

for award in selected.itertuples(index=False):
    award_courses = applied[
        (applied["student_id"] == award.student_id)
        & (applied["catalog_year"] == award.catalog_year)
        & (applied["credential_id"] == award.credential_id)
    ].copy()

    reasons: list[str] = []

    program_hours = pd.to_numeric(
        pd.Series([award.program_hours]),
        errors="coerce",
    ).iloc[0]

    policy_name, required_resident, required_special = residency_policy(
        award.catalog_year,
        award.credential_type,
        program_hours,
    )

    if pd.isna(required_resident):
        residency_status = "REVIEW"
        reasons.append("PROGRAM_HOURS_UNRESOLVED")
    else:
        resident_earned = award_courses[
            award_courses["grade"].isin({"A", "B", "C", "D"})
            & award_courses["derived_hours"].notna()
        ].copy()

        resident_hours = float(resident_earned["derived_hours"].sum())

        special_resident = resident_earned[
            (resident_earned["course_level"] == 2)
            | resident_earned["is_core"]
        ]
        special_hours = float(special_resident["derived_hours"].sum())

        residency_status = (
            "PASS"
            if resident_hours >= float(required_resident)
            and special_hours >= float(required_special)
            else "FAIL"
        )

        if resident_hours < float(required_resident):
            reasons.append("RESIDENCY_HOURS_BELOW_MINIMUM")

        if special_hours < float(required_special):
            reasons.append("SPECIAL_RESIDENCY_HOURS_BELOW_MINIMUM")

    if pd.isna(required_resident):
        resident_hours = np.nan
        special_hours = np.nan

    certificate_gpa = np.nan
    certificate_quality_points = np.nan
    certificate_gpa_hours = np.nan
    certificate_gpa_status = "NOT_APPLICABLE"

    if award.credential_type == "CERT":
        (
            certificate_gpa,
            certificate_quality_points,
            certificate_gpa_hours,
        ) = weighted_gpa(award_courses)

        if pd.isna(certificate_gpa):
            certificate_gpa_status = "REVIEW"
            reasons.append("CERTIFICATE_PLAN_GPA_UNRESOLVED")
        elif certificate_gpa >= 2.0:
            certificate_gpa_status = "PASS"
        else:
            certificate_gpa_status = "FAIL"
            reasons.append("CERTIFICATE_PLAN_GPA_BELOW_2_00")

    major_courses = award_courses[
        award_courses["estimated_major"]
    ].copy()

    major_gpa, major_quality_points, major_gpa_hours = weighted_gpa(
        major_courses
    )

    below_c = major_courses[
        major_courses["grade"].isin({"D", "F"})
    ]

    if major_courses.empty:
        minimum_c_status = "REVIEW"
        reasons.append("ESTIMATED_MAJOR_COURSES_UNRESOLVED")
    elif below_c.empty:
        minimum_c_status = "PASS"
    else:
        minimum_c_status = "FAIL"
        reasons.append("ESTIMATED_MAJOR_COURSE_BELOW_C")

    institutional_gpa = np.nan
    institutional_gpa_hours = np.nan
    institutional_gpa_status = "NOT_APPLICABLE"
    repeated_course_count = np.nan

    if award.credential_type == "ASSOCIATE":
        match = institutional[
            institutional["student_id"] == award.student_id
        ]

        if match.empty:
            institutional_gpa_status = "REVIEW"
            reasons.append("INSTITUTIONAL_GPA_UNRESOLVED")
        else:
            record = match.iloc[0]
            institutional_gpa = pd.to_numeric(
                pd.Series([record["estimated_institutional_gpa"]]),
                errors="coerce",
            ).iloc[0]
            institutional_gpa_hours = pd.to_numeric(
                pd.Series([record["institutional_gpa_hours"]]),
                errors="coerce",
            ).iloc[0]
            repeated_course_count = pd.to_numeric(
                pd.Series([record.get("repeated_course_count", np.nan)]),
                errors="coerce",
            ).iloc[0]

            if pd.isna(institutional_gpa):
                institutional_gpa_status = "REVIEW"
                reasons.append("INSTITUTIONAL_GPA_UNRESOLVED")
            elif institutional_gpa >= 2.0:
                institutional_gpa_status = "PASS"
            else:
                institutional_gpa_status = "FAIL"
                reasons.append("INSTITUTIONAL_GPA_BELOW_2_00")

    formal_statuses = [residency_status, minimum_c_status]

    if award.credential_type == "ASSOCIATE":
        formal_statuses.append(institutional_gpa_status)
    else:
        formal_statuses.append(certificate_gpa_status)

    if "FAIL" in formal_statuses:
        overall = "ACADEMIC_COMPLETE_SCREEN_FAIL"
    elif "REVIEW" in formal_statuses:
        overall = "ACADEMIC_COMPLETE_POLICY_REVIEW"
    else:
        overall = "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE"

    issue_count = 0
    if not issues.empty:
        issue_count = int(
            (
                (issues["student_id"].astype(str) == award.student_id)
                & (issues["catalog_year"].astype(str) == award.catalog_year)
                & (issues["credential_id"].astype(str) == award.credential_id)
            ).sum()
        )

    if issue_count:
        reasons.append("APPLIED_COURSE_GRADE_PARSE_REVIEW")

    rows.append(
        {
            **award._asdict(),
            "residency_policy": policy_name,
            "estimated_resident_applied_hours": resident_hours,
            "required_resident_hours": required_resident,
            "estimated_special_resident_hours": special_hours,
            "required_special_resident_hours": required_special,
            "residency_status": residency_status,
            "estimated_institutional_gpa": institutional_gpa,
            "institutional_gpa_hours": institutional_gpa_hours,
            "institutional_gpa_status": institutional_gpa_status,
            "repeated_course_count": repeated_course_count,
            "estimated_certificate_plan_gpa": certificate_gpa,
            "certificate_plan_quality_points": certificate_quality_points,
            "certificate_plan_gpa_hours": certificate_gpa_hours,
            "certificate_plan_gpa_status": certificate_gpa_status,
            "estimated_major_gpa": major_gpa,
            "estimated_major_quality_points": major_quality_points,
            "estimated_major_gpa_hours": major_gpa_hours,
            "estimated_major_course_count": len(major_courses),
            "estimated_major_courses_below_c": len(below_c),
            "estimated_major_courses_below_c_codes": " | ".join(
                sorted(below_c["course"].dropna().unique())
            ),
            "minimum_c_status": minimum_c_status,
            "applied_course_count": len(award_courses),
            "applied_parse_issue_count": issue_count,
            "awardability_status": overall,
            "awardability_reasons": " | ".join(sorted(set(reasons))),
        }
    )

awardability = pd.DataFrame(rows)
awardability.to_csv(AWARDABILITY_OUTPUT, index=False)

summary_rows: list[dict] = []
for column in [
    "credential_type",
    "residency_status",
    "institutional_gpa_status",
    "certificate_plan_gpa_status",
    "minimum_c_status",
    "awardability_status",
]:
    for value, count in (
        awardability[column]
        .fillna("BLANK")
        .value_counts(dropna=False)
        .items()
    ):
        summary_rows.append(
            {"metric": column, "value": value, "count": int(count)}
        )

pd.DataFrame(summary_rows).to_csv(SUMMARY_OUTPUT, index=False)

print("=" * 100)
print("CORRECTED AWARDABILITY SCREEN")
print("=" * 100)
print(f"Selected awards screened: {len(awardability):,}")

for label, column in [
    ("Credential types", "credential_type"),
    ("Residency", "residency_status"),
    ("Associate institutional GPA", "institutional_gpa_status"),
    ("Certificate-plan GPA", "certificate_plan_gpa_status"),
    ("Estimated major minimum-C", "minimum_c_status"),
    ("Overall awardability", "awardability_status"),
]:
    print(f"\n{label}:")
    print(awardability[column].value_counts(dropna=False).to_string())

print("\nProgram-hour classification check:")
print(
    awardability.groupby(
        ["credential_type", "program_hours"],
        dropna=False,
    )
    .size()
    .sort_index()
    .to_string()
)

print("\nOutputs:")
print(AWARDABILITY_OUTPUT)
print(SUMMARY_OUTPUT)
