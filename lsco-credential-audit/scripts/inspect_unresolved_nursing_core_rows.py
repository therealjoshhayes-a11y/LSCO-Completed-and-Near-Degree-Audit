#!/usr/bin/env python
"""
Inspect no-course-code curriculum rows for the unresolved nursing credential-years.

This is diagnostic only. It does not modify production or overlay files.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterator

import pandas as pd
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


CATALOG_PATHS = {
    "2022-2023": "data/raw/catalogs/2022-2023/2022-2023_Catalog.docx",
    "2023-2024": "data/raw/catalogs/2023-2024/2023-2024_Catalog.docx",
    "2024-2025": "data/raw/catalogs/2024-2025/2024-2025_Catalog.docx",
    "2025-2026": "data/raw/catalogs/2025-2026/2025-2026_Catalog.docx",
}

TARGETS = {
    ("2022-2023", "registered nursing transition"),
    ("2023-2024", "registered nursing associate degree nursing"),
    ("2023-2024", "registered nursing transition"),
    ("2024-2025", "registered nursing associate degree nursing"),
    ("2024-2025", "registered nursing transition"),
    ("2025-2026", "registered nursing associate degree nursing"),
    ("2025-2026", "registered nursing transition"),
}

COURSE_RE = re.compile(r"\b[A-Z]{4}\s*[- ]?\s*\d{4}\b")
NUMBER_RE = re.compile(r"(?<!\d)(\d{1,3})(?:\.0)?(?!\d)")
INTEREST_RE = re.compile(
    r"core|elective|communication|speech|language|philosophy|culture|"
    r"creative arts|component area|humanit|social|behavioral|math|science",
    re.I,
)


def clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).replace("\xa0", " ")
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


def heading_blocks(path: Path) -> list[dict]:
    doc = Document(path)
    blocks = list(iter_blocks(doc))
    output = []

    for i, (kind, obj) in enumerate(blocks):
        if kind != "paragraph":
            continue
        style = clean(obj.style.name if obj.style else "")
        heading = clean(obj.text)
        if style != "Heading 2" or not heading:
            continue

        items = []
        j = i + 1
        while j < len(blocks):
            next_kind, next_obj = blocks[j]
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
                            "text": text,
                            "rows": [],
                        }
                    )
            else:
                items.append(
                    {
                        "kind": "table",
                        "block_index": j,
                        "text": "",
                        "rows": table_rows(next_obj),
                    }
                )
            j += 1

        output.append(
            {
                "heading": heading,
                "normalized_heading": normalize(heading),
                "start": i,
                "end": j - 1,
                "items": items,
            }
        )

    return output


def course_count(block: dict) -> int:
    codes = set()
    for item in block["items"]:
        if item["kind"] == "paragraph":
            codes.update(COURSE_RE.findall(item["text"].upper()))
        else:
            for cells in item["rows"]:
                codes.update(COURSE_RE.findall(" | ".join(cells).upper()))
    return len(codes)


def main() -> int:
    root = Path(".").resolve()
    output_dir = root / "data/processed/catalogs/missing_health_credentials_overlay"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for year, relpath in CATALOG_PATHS.items():
        path = root / relpath
        blocks = heading_blocks(path)

        for target_year, target_heading in sorted(TARGETS):
            if target_year != year:
                continue

            candidates = [
                b for b in blocks if b["normalized_heading"] == target_heading
            ]
            if not candidates:
                raise RuntimeError(f"Missing heading: {year} | {target_heading}")

            block = sorted(candidates, key=course_count, reverse=True)[0]

            table_index = -1
            for item in block["items"]:
                if item["kind"] != "table":
                    continue
                table_index += 1

                for row_index, cells in enumerate(item["rows"]):
                    row_text = clean(" | ".join(cells))
                    if not row_text or COURSE_RE.search(row_text.upper()):
                        continue

                    numeric = [
                        int(value)
                        for value in NUMBER_RE.findall(row_text)
                        if 1 <= int(value) <= 150
                    ]
                    plausible_hours = [
                        value for value in numeric if value in {1, 2, 3, 4, 5, 6}
                    ]

                    if not plausible_hours and not INTEREST_RE.search(row_text):
                        continue

                    rows.append(
                        {
                            "catalog_year": year,
                            "credential_heading": block["heading"],
                            "source_block_start": block["start"],
                            "source_table_index": table_index,
                            "source_row_index": row_index,
                            "possible_hours": plausible_hours[-1] if plausible_hours else "",
                            "contains_core_language": bool(INTEREST_RE.search(row_text)),
                            "raw_requirement_text": row_text,
                        }
                    )

    df = pd.DataFrame(rows)
    out = output_dir / "unresolved_nursing_no_course_rows.csv"
    df.to_csv(out, index=False)

    print("=" * 110)
    print("UNRESOLVED NURSING NO-COURSE ROWS")
    print("=" * 110)
    if df.empty:
        print("No candidate rows found.")
    else:
        print(
            df[
                [
                    "catalog_year",
                    "credential_heading",
                    "possible_hours",
                    "raw_requirement_text",
                ]
            ].to_string(index=False)
        )
    print()
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
