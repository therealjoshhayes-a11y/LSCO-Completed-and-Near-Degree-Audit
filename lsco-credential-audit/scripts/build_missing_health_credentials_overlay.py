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
    python .\scripts\build_missing_health_credentials_overlay.py
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
LEVEL_RE = re.compile(r"\blevel\s+(i{1,3}|iv|v|\d+)\b", re.I)
TOTAL_RE = re.compile(
    r"\b(total\s+(program|degree|certificate)\s+hours?|program\s+total)\b",
    re.I,
)
NON_CREDIT_RE = re.compile(
    r"continuing education\s*\(non-credit\)|total program contact hours",
    re.I,
)
OR_RE = re.compile(r"\b(or|and/or)\b", re.I)


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


def parse_curriculum_rows(
    year: str,
    source_file: Path,
    block: Block,
    metadata: dict,
) -> tuple[list[dict], list[dict]]:
    output = []
    diagnostics = []
    sequence = 0
    current_semester = "PROGRAM REQUIREMENTS"
    table_counter = -1

    for item in block.items:
        if item["kind"] == "paragraph":
            text = item["text"]
            if SEMESTER_RE.search(text) or LEVEL_RE.search(text):
                current_semester = text
            continue

        table_counter += 1
        rows = item["rows"]

        for row_index, cells in enumerate(rows):
            row_text = clean(" | ".join(cells))
            if not row_text:
                continue

            if SEMESTER_RE.search(row_text) or LEVEL_RE.fullmatch(normalize(row_text)):
                current_semester = row_text
                continue

            if TOTAL_RE.search(row_text):
                continue

            matches = COURSE_RE.findall(row_text.upper())
            course_codes = []
            for rubric, number in matches:
                code = f"{rubric} {number}"
                if code not in course_codes:
                    course_codes.append(code)

            if not course_codes:
                continue

            has_or = bool(OR_RE.search(row_text))
            row_hours, raw_hours = explicit_hours(cells, course_codes)

            if len(course_codes) > 1 and has_or:
                sequence += 1
                hours = row_hours or max(inferred_hours(code) for code in course_codes)
                output.append(
                    {
                        "requirement_id": f"{metadata['credential_id']}_R{sequence}",
                        "catalog_year": year,
                        "catalog_year_start": year.split("-")[0],
                        "credential_family": metadata["credential_family"],
                        "credential_id": metadata["credential_id"],
                        "credential_title": metadata["credential_title"],
                        "requirement_sequence": sequence,
                        "semester_label": current_semester,
                        "rule_type": "ANY_N",
                        "original_rule_type": "ANY_N",
                        "credit_hours": hours,
                        "correction_note": "CONTROLLED_SOURCE_RECOVERY_CONFIRMED_2026-07-20",
                        "course_codes": " | ".join(course_codes),
                        "raw_requirement_text": row_text,
                        "source_table_index": table_counter,
                        "source_row_index": row_index,
                        "raw_credit_hours_text": raw_hours,
                        "issue_flags": "RECOVERED_MISSING_CREDENTIAL",
                        "source_file": str(source_file),
                        "validation_rows": "",
                        "validation_statuses": "",
                        "validation_notes": "",
                    }
                )
                continue

            # Multiple compressed courses without OR are separate exact requirements.
            for course_code in course_codes:
                sequence += 1
                hours = row_hours if len(course_codes) == 1 and row_hours else inferred_hours(course_code)
                output.append(
                    {
                        "requirement_id": f"{metadata['credential_id']}_R{sequence}",
                        "catalog_year": year,
                        "catalog_year_start": year.split("-")[0],
                        "credential_family": metadata["credential_family"],
                        "credential_id": metadata["credential_id"],
                        "credential_title": metadata["credential_title"],
                        "requirement_sequence": sequence,
                        "semester_label": current_semester,
                        "rule_type": "EXACT",
                        "original_rule_type": "EXACT",
                        "credit_hours": hours,
                        "correction_note": "CONTROLLED_SOURCE_RECOVERY_CONFIRMED_2026-07-20",
                        "course_codes": course_code,
                        "raw_requirement_text": row_text,
                        "source_table_index": table_counter,
                        "source_row_index": row_index,
                        "raw_credit_hours_text": raw_hours,
                        "issue_flags": "RECOVERED_MISSING_CREDENTIAL",
                        "source_file": str(source_file),
                        "validation_rows": "",
                        "validation_statuses": "",
                        "validation_notes": "",
                    }
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
                    "has_or": has_or,
                    "explicit_hours": row_hours if row_hours is not None else "",
                }
            )

    return output, diagnostics


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
            rows, diagnostics = parse_curriculum_rows(
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

            status = (
                "PASS_TOTAL_MATCH"
                if float(executable_hours) == float(metadata["expected_hours"])
                else "REVIEW_TOTAL_MISMATCH"
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
                    "expected_program_hours": metadata["expected_hours"],
                    "executable_requirement_hours": executable_hours,
                    "validation_status": status,
                }
            )

            print(
                f"{year} | {metadata['credential_title']}: "
                f"requirements={len(unique_requirements):>2} | "
                f"hours={executable_hours:>5} / {metadata['expected_hours']} | "
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
        f"{int(validation['validation_status'].ne('PASS_TOTAL_MATCH').sum()):,}"
    )
    print(f"Output directory: {output_dir}")
    print()
    print("No production requirements files were modified.")

    if duplicate_ids.any() or validation["validation_status"].ne("PASS_TOTAL_MATCH").any():
        print("OVERLAY GATE: REVIEW REQUIRED")
        return 2

    print("OVERLAY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
