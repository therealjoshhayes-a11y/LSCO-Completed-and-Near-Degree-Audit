"""Build a multi-year audit-ready requirement master from DOCX catalog extracts.

Input:
    data/processed/catalogs/<catalog_year>/requirements_docx_draft.csv

Output:
    data/processed/catalogs/requirements_master_multiyear.csv

This bridges the five-year DOCX catalog parser to the existing audit engine shape.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DEFAULT_CATALOGS_DIR = Path("data") / "processed" / "catalogs"
DEFAULT_OUTPUT = DEFAULT_CATALOGS_DIR / "requirements_master_multiyear.csv"

COURSE_CODE_PATTERN = re.compile(r"\b[A-Z]{2,5}\s*\d{3,4}[A-Z]?\b")


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def clean_upper(value: object) -> str:
    return clean_text(value).upper()


def split_course_codes(value: object) -> list[str]:
    text = clean_upper(value)

    if not text:
        return []

    matches = COURSE_CODE_PATTERN.findall(text)
    cleaned = []

    for match in matches:
        normalized = re.sub(r"\s+", " ", match.strip().upper())
        normalized = re.sub(r"^([A-Z]{2,5})\s*(\d{3,4}[A-Z]?)$", r"\1 \2", normalized)
        if normalized not in cleaned:
            cleaned.append(normalized)

    return cleaned


def looks_like_core_bucket(text: str) -> bool:
    upper = clean_upper(text)

    bucket_markers = [
        "COMMUNICATION",
        "MATHEMATICS",
        "MATH",
        "LIFE AND PHYSICAL SCIENCE",
        "PHYSICAL SCIENCE",
        "LANGUAGE, PHILOSOPHY",
        "CREATIVE ARTS",
        "AMERICAN HISTORY",
        "GOVERNMENT",
        "POLITICAL SCIENCE",
        "SOCIAL AND BEHAVIORAL",
        "COMPONENT AREA OPTION",
        "CORE",
    ]

    return any(marker in upper for marker in bucket_markers)


def option_rows_for_requirement(row: pd.Series) -> list[dict[str, str | int]]:
    catalog_year = clean_text(row.get("catalog_year"))
    credential_id = clean_text(row.get("credential_id"))
    credential_title = clean_text(row.get("credential_title"))
    semester_label = clean_text(row.get("semester_label"))
    sequence = clean_text(row.get("requirement_sequence"))
    sequence_token = re.sub(r"[^A-Z0-9]+", "_", clean_upper(sequence)).strip("_")
    rule_type = clean_upper(row.get("rule_type"))
    raw_text = clean_text(row.get("raw_requirement_text"))
    credit_hours = row.get("credit_hours")
    issue_flags = clean_text(row.get("issue_flags"))

    requirement_id = f"{credential_id}_R{sequence_token}"

    course_codes = split_course_codes(row.get("course_codes"))

    base = {
        "catalog_year": catalog_year,
        "credential_id": credential_id,
        "credential_title": credential_title,
        "requirement_id": requirement_id,
        "requirement_sequence": sequence,
        "semester_label": semester_label,
        "rule_type": rule_type,
        "min_required": 1,
        "credit_hours": credit_hours,
        "raw_requirement_text": raw_text,
        "issue_flags": issue_flags,
    }

    rows: list[dict[str, str | int]] = []

    if course_codes:
        for course_code in course_codes:
            rows.append(
                {
                    **base,
                    "option_type": "COURSE",
                    "option_value": course_code,
                }
            )
        return rows

    if rule_type == "CORE_BUCKET":
        rows.append(
            {
                **base,
                "option_type": "CORE_BUCKET",
                "option_value": raw_text,
            }
        )
        return rows

    if (
        rule_type == "ANY_N"
        and "LANG" in clean_upper(raw_text)
        and "CREATIVE ARTS" in clean_upper(raw_text)
    ):
        rows.append(
            {
                **base,
                "option_type": "CORE_BUCKET",
                "option_value": raw_text,
            }
        )
        return rows

    if rule_type == "ELECTIVE":
        rows.append(
            {
                **base,
                "option_type": "ELECTIVE",
                "option_value": raw_text,
            }
        )
        return rows

    if rule_type == "NON_COURSE" and looks_like_core_bucket(raw_text):
        rows.append(
            {
                **base,
                "option_type": "CORE_BUCKET",
                "option_value": raw_text,
            }
        )
        return rows

    if (
        credential_id == "WELDING_FABRICATION_TECHNOLOGY_2024"
        and "WLDG 153" in clean_upper(raw_text)
    ):
        rows.append(
            {
                **base,
                "option_type": "UNKNOWN_MALFORMED_COURSE",
                "option_value": raw_text,
            }
        )
        return rows

    rows.append(
        {
            **base,
            "option_type": rule_type if rule_type else "UNKNOWN",
            "option_value": raw_text,
        }
    )
    return rows


def load_catalog_requirement_files(catalogs_dir: Path) -> pd.DataFrame:
    frames = []

    for path in sorted(catalogs_dir.glob("*/requirements_docx_draft.csv")):
        frame = pd.read_csv(path, dtype=str)
        if "catalog_year" not in frame.columns:
            frame["catalog_year"] = path.parent.name
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(
            f"No requirements_docx_draft.csv files found under {catalogs_dir}"
        )

    return pd.concat(frames, ignore_index=True)


def build_multiyear_requirement_master(catalogs_dir: Path) -> pd.DataFrame:
    requirements = load_catalog_requirement_files(catalogs_dir)

    requirements = requirements.copy()
    requirements["requirement_sequence"] = requirements["requirement_sequence"].map(clean_text)

    output_rows = []

    for _, row in requirements.sort_values(
        by=["catalog_year", "credential_id", "requirement_sequence"],
        kind="mergesort",
    ).iterrows():
        output_rows.extend(option_rows_for_requirement(row))

    master = pd.DataFrame(output_rows)

    column_order = [
        "catalog_year",
        "credential_id",
        "credential_title",
        "requirement_id",
        "requirement_sequence",
        "semester_label",
        "rule_type",
        "min_required",
        "credit_hours",
        "option_type",
        "option_value",
        "raw_requirement_text",
        "issue_flags",
    ]

    master = master[column_order].sort_values(
        by=[
            "catalog_year",
            "credential_id",
            "requirement_sequence",
            "option_type",
            "option_value",
        ],
        kind="mergesort",
    )

    return master.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogs-dir", default=str(DEFAULT_CATALOGS_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    master = build_multiyear_requirement_master(Path(args.catalogs_dir))
    master.to_csv(output_path, index=False)

    print(f"Wrote {output_path}: {len(master)} option rows")
    print(f"Catalog years: {master['catalog_year'].nunique()}")
    print(f"Credentials: {master[['catalog_year', 'credential_id']].drop_duplicates().shape[0]}")
    print()
    print(master.groupby(["catalog_year", "option_type"]).size().to_string())


if __name__ == "__main__":
    main()
