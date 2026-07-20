#!/usr/bin/env python
"""
Build a controlled overlay for the confirmed missing health-program credential-years.

This script DOES NOT modify production requirements files. It parses the source DOCX
curriculum blocks and writes a schema-compatible overlay plus validation reports.

Confirmed target set:
- Registered Nursing / ADN / Transition (applicable years)
- Vocational Nursing (all five years)
- Physical Therapy Assistant (2025-2026)

Explicit exclusions:
- duplicate zero-course descriptive headings
- Continuing Education (Non-Credit) programs
- contact-hour-only programs

Run:
    python ./scripts/build_missing_health_credentials_overlay.py
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


CATALOG_PATHS = {
    "2021-2022": "data/raw/catalogs/2021-2022/2021-2022_Catalog.docx",
    "2022-2023": "data/raw/catalogs/2022-2023/2022-2023_Catalog.docx",
    "2023-2024": "data/raw/catalogs/2023-2024/2023-2024_Catalog.docx",
    "2024-2025": "data/raw/catalogs/2024-2025/2024-2025_Catalog.docx",
    "2025-2026": "data/raw/catalogs/2025-2026/2025-2026_Catalog.docx",
}

TARGETS = {
    ("2021-2022", "registered nursing"): {
        "credential_id": "REGISTERED_NURSING_AAS_2021",
        "credential_title": "Registered Nursing",
        "credential_family": "REGISTERED_NURSING",
        "expected_hours": 60,
    },
    ("2021-2022", "vocational nursing"): {
        "credential_id": "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2021",
        "credential_title": "Vocational Nursing",
        "credential_family": "VOCATIONAL_NURSING",
        "expected_hours": 51,
    },
    ("2022-2023", "registered nursing transition"): {
        "credential_id": "REGISTERED_NURSING_TRANSITION_2022",
        "credential_title": "Registered Nursing - Transition",
        "credential_family": "REGISTERED_NURSING_TRANSITION",
        "expected_hours": 60,
    },
    ("2022-2023", "vocational nursing"): {
        "credential_id": "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2022",
        "credential_title": "Vocational Nursing",
        "credential_family": "VOCATIONAL_NURSING",
        "expected_hours": 51,
    },
    ("2023-2024", "registered nursing associate degree nursing"): {
        "credential_id": "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2023",
        "credential_title": "Registered Nursing - Associate Degree Nursing",
        "credential_family": "REGISTERED_NURSING_ADN",
        "expected_hours": 60,
    },
    ("2023-2024", "registered nursing transition"): {
        "credential_id": "REGISTERED_NURSING_TRANSITION_2023",
        "credential_title": "Registered Nursing - Transition",
        "credential_family": "REGISTERED_NURSING_TRANSITION",
        "expected_hours": 60,
    },
    ("2023-2024", "vocational nursing"): {
        "credential_id": "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2023",
        "credential_title": "Vocational Nursing",
        "credential_family": "VOCATIONAL_NURSING",
        "expected_hours": 51,
    },
    ("2024-2025", "registered nursing associate degree nursing"): {
        "credential_id": "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2024",
        "credential_title": "Registered Nursing - Associate Degree Nursing",
        "credential_family": "REGISTERED_NURSING_ADN",
        "expected_hours": 60,
    },
    ("2024-2025", "registered nursing transition"): {
        "credential_id": "REGISTERED_NURSING_TRANSITION_2024",
        "credential_title": "Registered Nursing - Transition",
        "credential_family": "REGISTERED_NURSING_TRANSITION",
        "expected_hours": 60,
    },
    ("2024-2025", "vocational nursing"): {
        "credential_id": "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2024",
        "credential_title": "Vocational Nursing",
        "credential_family": "VOCATIONAL_NURSING",
        "expected_hours": 51,
    },
    ("2025-2026", "registered nursing associate degree nursing"): {
        "credential_id": "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2025",
        "credential_title": "Registered Nursing - Associate Degree Nursing",
        "credential_family": "REGISTERED_NURSING_ADN",
        "expected_hours": 60,
    },
    ("2025-2026", "registered nursing transition"): {
        "credential_id": "REGISTERED_NURSING_TRANSITION_2025",
        "credential_title": "Registered Nursing - Transition",
        "credential_family": "REGISTERED_NURSING_TRANSITION",
        "expected_hours": 60,
    },
    ("2025-2026", "vocational nursing"): {
        "credential_id": "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2025",
        "credential_title": "Vocational Nursing",
        "credential_family": "VOCATIONAL_NURSING",
        "expected_hours": 51,
    },
    ("2025-2026", "physical therapy assistant"): {
        "credential_id": "PHYSICAL_THERAPY_ASSISTANT_2025",
        "credential_title": "Physical Therapy Assistant",
        "credential_family": "PHYSICAL_THERAPY_ASSISTANT",
        "expected_hours": 66,
    },
}

# Controlled audit policy confirmed during catalog review.
# Admission prerequisites remain documented but are excluded from credential execution.
CONTROLLED_AUDIT_TOTALS = {
    "REGISTERED_NURSING_AAS_2021": {"prerequisite_hours": 24, "auditable_hours": 36},
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2021": {"prerequisite_hours": 12, "auditable_hours": 39},
    "REGISTERED_NURSING_TRANSITION_2022": {"prerequisite_hours": 24, "auditable_hours": 36},
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2022": {"prerequisite_hours": 12, "auditable_hours": 39},
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2023": {"prerequisite_hours": 14, "auditable_hours": 46},
    "REGISTERED_NURSING_TRANSITION_2023": {"prerequisite_hours": 24, "auditable_hours": 36},
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2023": {"prerequisite_hours": 8, "auditable_hours": 43},
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2024": {"prerequisite_hours": 14, "auditable_hours": 46},
    "REGISTERED_NURSING_TRANSITION_2024": {"prerequisite_hours": 21, "auditable_hours": 39},
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2024": {"prerequisite_hours": 8, "auditable_hours": 43},
    "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING_2025": {"prerequisite_hours": 14, "auditable_hours": 46},
    "REGISTERED_NURSING_TRANSITION_2025": {"prerequisite_hours": 21, "auditable_hours": 39},
    "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION_2025": {"prerequisite_hours": 8, "auditable_hours": 43},
    "PHYSICAL_THERAPY_ASSISTANT_2025": {"prerequisite_hours": 14, "auditable_hours": 52},
}


MASTER_COLUMNS = [
    "requirement_id",
    "catalog_year",
    "catalog_year_start",
    "credential_family",
    "credential_id",
    "credential_title",
    "requirement_sequence",
    "semester_label",
    "rule_type",
    "original_rule_type",
    "credit_hours",
    "correction_note",
    "course_codes",
    "raw_requirement_text",
    "source_table_index",
    "source_row_index",
    "raw_credit_hours_text",
    "issue_flags",
    "source_file",
    "validation_rows",
    "validation_statuses",
    "validation_notes",
]

COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b")
SEMESTER_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|summer)\s+"
    r"(semester|session|term)\b",
    re.I,
)
LEVEL_RE = re.compile(
    r"\b(level\s+(i{1,3}|iv|v|\d+)|"
    r"(first|second|third|fourth|fifth)\s+level)\b",
    re.I,
)
TOTAL_RE = re.compile(
    r"\b(total\s+(program|degree|certificate)\s+hours?|program\s+total)\b",
    re.I,
)
NON_CREDIT_RE = re.compile(
    r"continuing education\s*\(non-credit\)|total program contact hours",
    re.I,
)
OR_RE = re.compile(r"\b(or|and/or)\b", re.I)
PREREQ_RE = re.compile(r"\b(pre[- ]?requisites?|prerequisite courses?)\b", re.I)
CORE_BUCKET_PATTERNS = [
    ("LANGUAGE_PHILOSOPHY_CULTURE_OR_CREATIVE_ARTS", re.compile(
        r"(language\s*,?\s*philosophy\s*,?\s*(?:and|&)\s*culture.*creative\s+arts)|"
        r"(creative\s+arts.*language\s*,?\s*philosophy\s*,?\s*(?:and|&)\s*culture)|"
        r"(language\s+philosophy\s+and\s+culture\s+or\s+creative\s+arts)",
        re.I,
    )),
    ("COMMUNICATION", re.compile(
        r"\b(communication|speech)\b.*\b(core|elective|requirement|hours?)\b|"
        r"\b(core|elective|requirement)\b.*\b(communication|speech)\b",
        re.I,
    )),
    ("MATHEMATICS", re.compile(
        r"\b(mathematics|math)\b.*\b(core|elective|requirement|hours?)\b|"
        r"\b(core|elective|requirement)\b.*\b(mathematics|math)\b",
        re.I,
    )),
    ("LIFE_AND_PHYSICAL_SCIENCES", re.compile(
        r"\blife\s+and\s+physical\s+sciences?\b", re.I
    )),
    ("SOCIAL_AND_BEHAVIORAL_SCIENCES", re.compile(
        r"\bsocial\s+and\s+behavioral\s+sciences?\b", re.I
    )),
    ("COMPONENT_AREA_OPTION", re.compile(
        r"\bcomponent\s+area\s+option\b", re.I
    )),
]


@dataclass
class Block:
    heading: str
    normalized_heading: str
    start_index: int
    end_index: int
    items: list[dict]


def clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).replace("\xa0", " ")
    text = text.replace("â€“", "–").replace("â€”", "—")
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: object) -> str:
    text = clean(value).lower().replace("&", " and ")
    text = re.sub(r"[–—−]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iter_blocks(doc: Document) -> Iterator[tuple[str, object]]:
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "paragraph", Paragraph(child, doc)
        elif tag == "tbl":
            yield "table", Table(child, doc)


def table_rows(table: Table) -> list[list[str]]:
    return [[clean(cell.text) for cell in row.cells] for row in table.rows]


def extract_heading_blocks(path: Path) -> list[Block]:
    doc = Document(path)
    doc_blocks = list(iter_blocks(doc))
    results: list[Block] = []

    for i, (kind, obj) in enumerate(doc_blocks):
        if kind != "paragraph":
            continue
        style = clean(obj.style.name if obj.style else "")
        heading = clean(obj.text)
        if style != "Heading 2" or not heading:
            continue

        items = []
        j = i + 1
        while j < len(doc_blocks):
            next_kind, next_obj = doc_blocks[j]
            if next_kind == "paragraph":
                next_style = clean(next_obj.style.name if next_obj.style else "")
                if next_style in {"Heading 1", "Heading 2"}:
                    break
                text = clean(next_obj.text)
                if text:
                    items.append(
                        {
                            "kind": "paragraph",
                            "block_index": j,
                            "style": next_style,
                            "text": text,
                            "rows": [],
                        }
                    )
            else:
                rows = table_rows(next_obj)
                items.append(
                    {
                        "kind": "table",
                        "block_index": j,
                        "style": "",
                        "text": "\n".join(" | ".join(row) for row in rows),
                        "rows": rows,
                    }
                )
            j += 1

        results.append(
            Block(
                heading=heading,
                normalized_heading=normalize(heading),
                start_index=i,
                end_index=j - 1,
                items=items,
            )
        )

    return results


def block_course_count(block: Block) -> int:
    codes = set()
    for item in block.items:
        for rubric, number in COURSE_RE.findall(item["text"].upper()):
            codes.add(f"{rubric} {number}")
    return len(codes)


def select_curriculum_block(blocks: list[Block], target_heading: str) -> Block:
    candidates = [b for b in blocks if b.normalized_heading == target_heading]
    if not candidates:
        raise RuntimeError(f"Heading not found: {target_heading}")

    ranked = sorted(
        candidates,
        key=lambda b: (
            block_course_count(b),
            any(TOTAL_RE.search(item["text"]) for item in b.items),
            len(b.items),
        ),
        reverse=True,
    )
    selected = ranked[0]

    if block_course_count(selected) == 0:
        raise RuntimeError(f"No course-bearing block found for: {target_heading}")

    full_text = "\n".join(item["text"] for item in selected.items)
    if NON_CREDIT_RE.search(full_text):
        raise RuntimeError(f"Selected block is non-credit: {target_heading}")

    return selected


def inferred_hours(course_code: str) -> int:
    # Texas common course numbering: second digit is semester credit hours.
    number = course_code.split()[1]
    value = int(number[1])
    return value if 1 <= value <= 9 else 0


def explicit_hours(cells: list[str], course_codes: list[str]) -> tuple[int | None, str]:
    # Prefer a standalone 1-9 value in the right-most cells after course/title text.
    candidates = []
    for cell in cells:
        stripped = clean(cell)
        if re.fullmatch(r"\d(?:\.0)?", stripped):
            candidates.append(int(float(stripped)))
    if candidates:
        return candidates[-1], str(candidates[-1])

    # Compressed Acalog rows may end with one hours value per listed course.
    # Do not force it when multiple courses are present; infer individually instead.
    if len(course_codes) == 1:
        return inferred_hours(course_codes[0]), ""

    return None, ""



def detect_core_bucket(row_text: str) -> str:
    normalized = normalize(row_text)
    if (
        "language philosophy and culture" in normalized
        and "creative arts" in normalized
    ):
        return "LANGUAGE_PHILOSOPHY_CULTURE_OR_CREATIVE_ARTS"

    for bucket_name, pattern in CORE_BUCKET_PATTERNS:
        if pattern.search(row_text):
            return bucket_name
    return ""


def split_localized_or_groups(row_text: str, course_codes: list[str]) -> tuple[list[list[str]], list[str]]:
    """
    Return localized option groups and remaining exact courses.

    The catalog often compresses several required courses into one row, with a local
    option such as "BIOL 1322 or FDNS 1345" followed by unrelated required courses.
    Only adjacent course codes joined by OR are grouped.
    """
    if len(course_codes) < 2 or not OR_RE.search(row_text):
        return [], course_codes

    upper = row_text.upper()
    positions = []
    for code in course_codes:
        rubric, number = code.split()
        match = re.search(rf"\b{re.escape(rubric)}\s*[- ]?\s*{re.escape(number)}\b", upper)
        if match:
            positions.append((code, match.start(), match.end()))

    positions.sort(key=lambda x: x[1])
    grouped_codes: set[str] = set()
    option_groups: list[list[str]] = []

    for left, right in zip(positions, positions[1:]):
        between = upper[left[2]:right[1]]

        # A mixed row may place an uncoded core bucket between two coded courses:
        # PSYC 2301 | LANGUAGE... OR CREATIVE ARTS | RNSG 1327.
        # That OR belongs to the core bucket, not to the adjacent course codes.
        if detect_core_bucket(between):
            continue

        if OR_RE.search(between):
            group = [left[0], right[0]]
            # Merge overlapping adjacent OR pairs into one option group.
            if option_groups and option_groups[-1][-1] == group[0]:
                option_groups[-1].append(group[1])
            else:
                option_groups.append(group)
            grouped_codes.update(group)

    exact_courses = [code for code in course_codes if code not in grouped_codes]
    return option_groups, exact_courses


def is_corequisite_label(text: str) -> bool:
    normalized = normalize(text)
    return (
        normalized in {
            "corequisite",
            "corequisites",
            "co requisite",
            "co requisites",
            "corequisite courses",
            "corequisites credit hours",
        }
        or normalized.startswith("corequisites credit hours")
        or "corequisite" in normalized
        or "co requisite" in normalized
    )


def is_prerequisite_label(text: str) -> bool:
    """
    True only for a curriculum section label, not narrative sentences such as
    "Prerequisites must be completed prior to admission."
    """
    normalized = normalize(text)
    return (
        normalized in {
            "prerequisite",
            "prerequisites",
            "pre requisite",
            "pre requisites",
            "prerequisite courses",
            "prerequisites credit hours",
        }
        or normalized.startswith("prerequisites credit hours")
        or "pre requisite" in normalized
        or "prerequisite" in normalized
    )


def is_pure_section_label(text: str) -> bool:
    normalized = normalize(text)
    return bool(
        SEMESTER_RE.fullmatch(clean(text))
        or LEVEL_RE.fullmatch(clean(text))
        or normalized in {
            "first semester",
            "second semester",
            "third semester",
            "fourth semester",
            "fifth semester",
            "summer semester",
            "summer session",
            "first level",
            "second level",
            "third level",
            "fourth level",
            "level i",
            "level ii",
            "level iii",
            "level iv",
        }
    )


def parse_curriculum_rows(
    year: str,
    source_file: Path,
    block: Block,
    metadata: dict,
) -> tuple[list[dict], list[dict], int]:
    output = []
    diagnostics = []
    sequence = 0
    current_semester = "PROGRAM REQUIREMENTS"
    in_prerequisites = False
    excluded_prerequisite_hours = 0
    table_counter = -1

    def emit_requirement(
        *,
        rule_type: str,
        course_codes_value: str,
        credit_hours_value: int,
        raw_text: str,
        table_index: int,
        row_index: int,
        raw_hours_text: str = "",
        semester_label: str | None = None,
        issue_flag: str = "RECOVERED_MISSING_CREDENTIAL",
    ) -> None:
        nonlocal sequence
        sequence += 1
        output.append(
            {
                "requirement_id": f"{metadata['credential_id']}_R{sequence}",
                "catalog_year": year,
                "catalog_year_start": year.split("-")[0],
                "credential_family": metadata["credential_family"],
                "credential_id": metadata["credential_id"],
                "credential_title": metadata["credential_title"],
                "requirement_sequence": sequence,
                "semester_label": semester_label or current_semester,
                "rule_type": rule_type,
                "original_rule_type": rule_type,
                "credit_hours": credit_hours_value,
                "correction_note": "CONTROLLED_SOURCE_RECOVERY_V9_CONFIRMED_2026-07-20",
                "course_codes": course_codes_value,
                "raw_requirement_text": raw_text,
                "source_table_index": table_index,
                "source_row_index": row_index,
                "raw_credit_hours_text": raw_hours_text,
                "issue_flags": issue_flag,
                "source_file": str(source_file),
                "validation_rows": "",
                "validation_statuses": "",
                "validation_notes": "",
            }
        )

    for item in block.items:
        if item["kind"] == "paragraph":
            text_value = item["text"]

            # Curriculum requirements for these recovered programs are contained in
            # the Acalog tables. Narrative paragraphs may mention prerequisites or
            # list allowed core-course examples; they are evidence, not additional
            # requirements.
            if is_corequisite_label(text_value):
                current_semester = text_value
                in_prerequisites = False
            elif is_prerequisite_label(text_value):
                current_semester = text_value
                in_prerequisites = True
            elif is_pure_section_label(text_value):
                current_semester = text_value
                in_prerequisites = False
            continue

        table_counter += 1
        rows = item["rows"]

        for row_index, cells in enumerate(rows):
            row_text = clean(" | ".join(cells))
            if not row_text:
                continue

            first_cell = clean(cells[0]) if cells else row_text
            row_has_coreq = is_corequisite_label(first_cell)
            row_has_prereq = is_prerequisite_label(first_cell)
            row_has_section = bool(
                is_pure_section_label(first_cell)
                or SEMESTER_RE.match(first_cell)
                or LEVEL_RE.match(first_cell)
            )
            row_course_matches = COURSE_RE.findall(row_text.upper())

            if row_has_coreq:
                current_semester = row_text
                in_prerequisites = False
                if not row_course_matches:
                    continue

            elif row_has_prereq:
                current_semester = row_text
                in_prerequisites = True
                if not row_course_matches:
                    continue

            elif row_has_section:
                current_semester = row_text
                in_prerequisites = False
                if not row_course_matches:
                    continue

            if TOTAL_RE.search(row_text) and not row_course_matches:
                continue

            matches = row_course_matches
            course_codes = []
            for rubric, number in matches:
                code = f"{rubric} {number}"
                if code not in course_codes:
                    course_codes.append(code)

            row_hours, raw_hours = explicit_hours(cells, course_codes)
            core_bucket = detect_core_bucket(row_text)

            if core_bucket and not course_codes:
                if in_prerequisites:
                    excluded_prerequisite_hours += row_hours or 0
                    diagnostics.append(
                        {
                            "catalog_year": year,
                            "credential_id": metadata["credential_id"],
                            "credential_title": metadata["credential_title"],
                            "semester_label": current_semester,
                            "source_table_index": table_counter,
                            "source_row_index": row_index,
                            "raw_requirement_text": row_text,
                            "course_codes_found": "",
                            "has_or": True,
                            "explicit_hours": row_hours or "",
                            "classification": "PREREQUISITE_EXCLUDED_CORE_BUCKET",
                            "in_prerequisites": True,
                            "section_detected": current_semester,
                        }
                    )
                else:
                    emit_requirement(
                        rule_type="CORE_BUCKET",
                        course_codes_value=core_bucket,
                        credit_hours_value=row_hours or 3,
                        raw_text=row_text,
                        table_index=table_counter,
                        row_index=row_index,
                        raw_hours_text=raw_hours,
                        issue_flag="RECOVERED_MISSING_CREDENTIAL|CORE_BUCKET_RECOVERED",
                    )
                continue

            if not course_codes:
                continue

            option_groups, exact_courses = split_localized_or_groups(
                row_text, course_codes
            )

            # Some nursing rows combine ordinary coded requirements with an
            # uncoded three-hour core choice. Emit both rather than dropping the
            # bucket merely because course codes are present elsewhere in the row.
            mixed_core_bucket = detect_core_bucket(row_text)
            mixed_core_hours = 3 if mixed_core_bucket else 0

            if in_prerequisites:
                excluded_prerequisite_hours += sum(
                    inferred_hours(code) for code in exact_courses
                )
                for group in option_groups:
                    excluded_prerequisite_hours += max(
                        inferred_hours(code) for code in group
                    )
                diagnostics.append(
                    {
                        "catalog_year": year,
                        "credential_id": metadata["credential_id"],
                        "credential_title": metadata["credential_title"],
                        "semester_label": current_semester,
                        "source_table_index": table_counter,
                        "source_row_index": row_index,
                        "raw_requirement_text": row_text,
                        "course_codes_found": " | ".join(course_codes),
                        "has_or": bool(option_groups),
                        "explicit_hours": row_hours if row_hours is not None else "",
                        "classification": "PREREQUISITE_EXCLUDED",
                    "in_prerequisites": True,
                    "section_detected": current_semester,
                    }
                )
                continue

            if mixed_core_bucket:
                emit_requirement(
                    rule_type="CORE_BUCKET",
                    course_codes_value=mixed_core_bucket,
                    credit_hours_value=mixed_core_hours,
                    raw_text=row_text,
                    table_index=table_counter,
                    row_index=row_index,
                    raw_hours_text=raw_hours,
                    issue_flag=(
                        "RECOVERED_MISSING_CREDENTIAL|"
                        "CORE_BUCKET_RECOVERED_FROM_MIXED_ROW"
                    ),
                )

            for group in option_groups:
                emit_requirement(
                    rule_type="ANY_N",
                    course_codes_value=" | ".join(group),
                    credit_hours_value=max(inferred_hours(code) for code in group),
                    raw_text=row_text,
                    table_index=table_counter,
                    row_index=row_index,
                    raw_hours_text=raw_hours,
                )

            for course_code in exact_courses:
                hours = (
                    row_hours
                    if len(course_codes) == 1 and row_hours
                    else inferred_hours(course_code)
                )
                emit_requirement(
                    rule_type="EXACT",
                    course_codes_value=course_code,
                    credit_hours_value=hours,
                    raw_text=row_text,
                    table_index=table_counter,
                    row_index=row_index,
                    raw_hours_text=raw_hours,
                )

            diagnostics.append(
                {
                    "catalog_year": year,
                    "credential_id": metadata["credential_id"],
                    "credential_title": metadata["credential_title"],
                    "semester_label": current_semester,
                    "source_table_index": table_counter,
                    "source_row_index": row_index,
                    "raw_requirement_text": row_text,
                    "course_codes_found": " | ".join(course_codes),
                    "has_or": bool(option_groups),
                    "explicit_hours": row_hours if row_hours is not None else "",
                    "classification": "PROGRAM_REQUIREMENT",
                    "in_prerequisites": False,
                    "section_detected": current_semester,
                }
            )

    return output, diagnostics, excluded_prerequisite_hours


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--output-dir",
        default="data/processed/catalogs/missing_health_credentials_overlay",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    all_diagnostics = []
    validation_rows = []

    print("=" * 118)
    print("BUILD MISSING HEALTH-CREDENTIAL REQUIREMENTS OVERLAY")
    print("=" * 118)

    by_year: dict[str, list[tuple[str, dict]]] = {}
    for (year, heading), metadata in TARGETS.items():
        by_year.setdefault(year, []).append((heading, metadata))

    for year, targets in sorted(by_year.items()):
        source_file = root / CATALOG_PATHS[year]
        if not source_file.exists():
            raise FileNotFoundError(source_file)

        blocks = extract_heading_blocks(source_file)

        for heading, metadata in targets:
            block = select_curriculum_block(blocks, heading)
            rows, diagnostics, excluded_prerequisite_hours = parse_curriculum_rows(
                year,
                source_file,
                block,
                metadata,
            )
            all_rows.extend(rows)
            all_diagnostics.extend(diagnostics)

            unique_requirements = pd.DataFrame(rows).drop_duplicates("requirement_id")
            executable_hours = pd.to_numeric(
                unique_requirements["credit_hours"], errors="coerce"
            ).fillna(0).sum()

            controlled = CONTROLLED_AUDIT_TOTALS[metadata["credential_id"]]
            expected_auditable_hours = float(controlled["auditable_hours"])
            controlled_prerequisite_hours = int(controlled["prerequisite_hours"])

            status = (
                "PASS_AUDITABLE_TOTAL_MATCH"
                if float(executable_hours) == expected_auditable_hours
                else "REVIEW_AUDITABLE_TOTAL_MISMATCH"
            )

            validation_rows.append(
                {
                    "catalog_year": year,
                    "credential_id": metadata["credential_id"],
                    "credential_title": metadata["credential_title"],
                    "source_heading": block.heading,
                    "source_block_start": block.start_index,
                    "source_block_end": block.end_index,
                    "source_course_count": block_course_count(block),
                    "requirement_count": len(unique_requirements),
                    "catalog_program_hours": metadata["expected_hours"],
                    "parser_prerequisite_hours_detected": excluded_prerequisite_hours,
                    "controlled_prerequisite_hours_excluded": controlled_prerequisite_hours,
                    "expected_auditable_hours": expected_auditable_hours,
                    "executable_requirement_hours": executable_hours,
                    "validation_status": status,
                    "validation_note": (
                        "CONTROLLED_PREREQUISITE_POLICY"
                        if excluded_prerequisite_hours != controlled_prerequisite_hours
                        else ""
                    ),
                }
            )

            print(
                f"{year} | {metadata['credential_title']}: "
                f"requirements={len(unique_requirements):>2} | "
                f"audit_hours={executable_hours:>5} / {expected_auditable_hours:<5} | "
                f"controlled_prereq={controlled_prerequisite_hours:>3} | "
                f"parser_prereq={excluded_prerequisite_hours:>3} | "
                f"{status}"
            )

    overlay = pd.DataFrame(all_rows)
    overlay = overlay[MASTER_COLUMNS].copy()
    diagnostics = pd.DataFrame(all_diagnostics)
    validation = pd.DataFrame(validation_rows)

    duplicate_ids = overlay["requirement_id"].duplicated(keep=False)
    if duplicate_ids.any():
        duplicate_rows = overlay[duplicate_ids].copy()
    else:
        duplicate_rows = pd.DataFrame(columns=MASTER_COLUMNS)

    overlay.to_csv(output_dir / "missing_health_requirements_overlay.csv", index=False)
    diagnostics.to_csv(output_dir / "source_row_diagnostics.csv", index=False)
    validation.to_csv(output_dir / "overlay_validation.csv", index=False)
    duplicate_rows.to_csv(output_dir / "duplicate_requirement_ids.csv", index=False)

    print()
    print("=" * 118)
    print("OVERLAY SUMMARY")
    print("=" * 118)
    print(f"Credential-years: {validation['credential_id'].nunique():,}")
    print(f"Requirement rows: {len(overlay):,}")
    print(f"Duplicate requirement IDs: {int(duplicate_ids.sum()):,}")
    print(
        "Total mismatches: "
        f"{int(validation['validation_status'].ne('PASS_AUDITABLE_TOTAL_MATCH').sum()):,}"
    )
    print(f"Output directory: {output_dir}")
    print()
    print("No production requirements files were modified.")

    if duplicate_ids.any() or validation["validation_status"].ne(
        "PASS_AUDITABLE_TOTAL_MATCH"
    ).any():
        print("OVERLAY GATE: REVIEW REQUIRED")
        return 2

    print("OVERLAY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
