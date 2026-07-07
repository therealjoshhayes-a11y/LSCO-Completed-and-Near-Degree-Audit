from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re

from docx import Document

from lsco_audit.catalog.registry import load_catalog_registry


COURSE_RE = re.compile(r"\b[A-Z]{3,4}\s+\d{4}\b")
SEMESTER_RE = re.compile(r"^(First|Second|Third|Fourth|Fifth|Sixth)\s+Semester$", re.I)


@dataclass(frozen=True)
class TargetCredential:
    catalog_year: str
    credential_id: str
    credential_title: str
    table_index: int


TARGETS = [
    TargetCredential("2024-2025", "LAYOUT_AND_FABRICATION_WELDING_CERT_2024", "Layout and Fabrication Welding Certificate", 87),
    TargetCredential("2024-2025", "PIPE_WELDING_CERT_2024", "Pipe Welding Certificate", 88),
    TargetCredential("2024-2025", "PRODUCTION_WELDER_CERT_2024", "Production Welder", 89),
    TargetCredential("2024-2025", "WELDING_FABRICATION_TECHNOLOGY_AAS_2024", "Welding Fabrication Technology", 90),

    TargetCredential("2025-2026", "LAYOUT_AND_FABRICATION_WELDING_CERT_2025", "Layout and Fabrication Welding Certificate", 144),
    TargetCredential("2025-2026", "PIPEFITTING_CERT_2025", "Pipefitting Certificate", 145),
    TargetCredential("2025-2026", "PIPE_WELDING_CERT_2025", "Pipe Welding Certificate", 146),
    TargetCredential("2025-2026", "PRODUCTION_WELDER_CERT_2025", "Production Welder", 147),
    TargetCredential("2025-2026", "WELDING_FABRICATION_TECHNOLOGY_AAS_2025", "Welding Fabrication Technology", 148),
]


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def parse_hours(value: str) -> list[int]:
    return [int(x) for x in re.findall(r"\b\d+\b", value or "")]


def parse_rule_type(text: str) -> str:
    upper = text.upper()

    if COURSE_RE.search(text) and " OR " in upper:
        return "ANY_N"

    if COURSE_RE.search(text):
        return "EXACT"

    if "APPROVED ELECTIVE" in upper:
        return "ELECTIVE"

    if "LANGUAGE, PHILOSOPHY, AND CULTURE" in upper:
        return "CORE_BUCKET"

    if "SOCIAL AND BEHAVIORAL SCIENCE" in upper:
        return "CORE_BUCKET"

    return "NON_COURSE"


def parse_requirement_row(
    *,
    target: TargetCredential,
    row_index: int,
    semester_label: str,
    requirement_sequence: int,
    cells: list[str],
) -> dict[str, str]:
    requirement_text = clean_text(cells[0]) if cells else ""
    hours_text = clean_text(cells[1]) if len(cells) > 1 else ""
    hours = parse_hours(hours_text)
    course_codes = COURSE_RE.findall(requirement_text)
    rule_type = parse_rule_type(requirement_text)

    issues: list[str] = []

    if rule_type in {"EXACT", "ANY_N"} and not course_codes:
        issues.append("NO_VALID_COURSE_CODE_FOUND")

    if rule_type == "ANY_N" and len(course_codes) < 2:
        issues.append("ANY_N_WITH_FEWER_THAN_TWO_COURSES")

    if not hours:
        issues.append("NO_CREDIT_HOURS_FOUND")
        credit_hours = ""
    elif len(hours) > 1:
        issues.append("MULTIPLE_CREDIT_HOUR_VALUES")
        credit_hours = str(hours[-1])
    else:
        credit_hours = str(hours[0])

    if re.search(r"\b[A-Z]{3,4}\s+\d{1,3}\b", requirement_text) and not course_codes:
        issues.append("POSSIBLE_MALFORMED_COURSE_CODE")

    return {
        "catalog_year": target.catalog_year,
        "credential_id": target.credential_id,
        "credential_title": target.credential_title,
        "source_table_index": str(target.table_index),
        "source_row_index": str(row_index),
        "requirement_sequence": str(requirement_sequence),
        "semester_label": semester_label,
        "raw_requirement_text": requirement_text,
        "credit_hours": credit_hours,
        "rule_type": rule_type,
        "course_codes": ";".join(course_codes),
        "issue_flags": ";".join(issues),
    }


def parse_total_row(
    *,
    target: TargetCredential,
    row_index: int,
    semester_label: str,
    cells: list[str],
) -> dict[str, str]:
    label = clean_text(cells[0]) if cells else ""
    value = clean_text(cells[1]) if len(cells) > 1 else ""
    hours = parse_hours(value)

    semester_hours = ""
    total_program_hours = ""

    if "Semester Hours" in label and "Total Program Hours" in label:
        if len(hours) >= 2:
            semester_hours = str(hours[0])
            total_program_hours = str(hours[1])
    elif "Semester Hours" in label:
        if hours:
            semester_hours = str(hours[-1])
    elif "Total Program Hours" in label:
        if hours:
            total_program_hours = str(hours[-1])

    return {
        "catalog_year": target.catalog_year,
        "credential_id": target.credential_id,
        "credential_title": target.credential_title,
        "source_table_index": str(target.table_index),
        "source_row_index": str(row_index),
        "semester_label": semester_label,
        "raw_total_text": label,
        "semester_hours": semester_hours,
        "total_program_hours": total_program_hours,
        "raw_hours_text": value,
    }


def parse_target(doc: Document, target: TargetCredential) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    table = doc.tables[target.table_index]

    requirement_rows: list[dict[str, str]] = []
    total_rows: list[dict[str, str]] = []

    semester_label = ""
    requirement_sequence = 0

    for row_index, row in enumerate(table.rows):
        cells = [clean_text(cell.text) for cell in row.cells]
        first_cell = cells[0] if cells else ""

        if not first_cell:
            continue

        if row_index == 0 and first_cell.lower().endswith("semester"):
            semester_label = first_cell
            continue

        if SEMESTER_RE.match(first_cell):
            semester_label = first_cell
            continue

        if "Semester Hours" in first_cell or "Total Program Hours" in first_cell:
            total_rows.append(
                parse_total_row(
                    target=target,
                    row_index=row_index,
                    semester_label=semester_label,
                    cells=cells,
                )
            )
            continue

        requirement_sequence += 1
        requirement_rows.append(
            parse_requirement_row(
                target=target,
                row_index=row_index,
                semester_label=semester_label,
                requirement_sequence=requirement_sequence,
                cells=cells,
            )
        )

    return requirement_rows, total_rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    registry = {record.catalog_year: record for record in load_catalog_registry()}

    targets_by_year: dict[str, list[TargetCredential]] = {}
    for target in TARGETS:
        targets_by_year.setdefault(target.catalog_year, []).append(target)

    requirement_fieldnames = [
        "catalog_year",
        "credential_id",
        "credential_title",
        "source_table_index",
        "source_row_index",
        "requirement_sequence",
        "semester_label",
        "raw_requirement_text",
        "credit_hours",
        "rule_type",
        "course_codes",
        "issue_flags",
    ]

    total_fieldnames = [
        "catalog_year",
        "credential_id",
        "credential_title",
        "source_table_index",
        "source_row_index",
        "semester_label",
        "raw_total_text",
        "semester_hours",
        "total_program_hours",
        "raw_hours_text",
    ]

    for catalog_year, targets in targets_by_year.items():
        record = registry[catalog_year]
        doc = Document(record.source_docx_path)

        all_requirements: list[dict[str, str]] = []
        all_totals: list[dict[str, str]] = []

        for target in targets:
            requirements, totals = parse_target(doc, target)
            all_requirements.extend(requirements)
            all_totals.extend(totals)

        out_dir = Path("data") / "processed" / "catalogs" / catalog_year
        write_csv(out_dir / "requirements_docx_draft.csv", all_requirements, requirement_fieldnames)
        write_csv(out_dir / "requirement_totals_docx_draft.csv", all_totals, total_fieldnames)

        print(f"{catalog_year}: wrote {len(all_requirements)} requirement rows and {len(all_totals)} total rows")


if __name__ == "__main__":
    main()
