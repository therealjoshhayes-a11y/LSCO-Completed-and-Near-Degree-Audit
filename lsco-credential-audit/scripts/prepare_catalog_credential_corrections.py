#!/usr/bin/env python
"""
Prepare controlled correction packages for catalog credentials that appear in
the DOCX curriculum blocks but are absent from the parsed requirements master.

This script does NOT modify production requirements. It creates:
- correction_candidates.csv
- one detailed text dump per suspected omitted credential-year
- one course-row CSV per suspected omitted credential-year
- excluded_noncredential_blocks.csv
- exact_title_existing_matches.csv

Run from repository root:
    python .\scripts\prepare_catalog_credential_corrections.py
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

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

# Confirmed non-credential source blocks.
NON_CREDENTIAL_HEADINGS = {
    "core curriculum",
    "general education philosophy and rationale",
    "technical and health profession education",
}

# Strong suspected omissions from structural review.
TARGET_HEADINGS = {
    "registered nursing",
    "registered nursing transition",
    "registered nursing associate degree nursing",
    "vocational nursing",
    "physical therapy assistant",
    "massage therapy",
    "court reporting",
}

COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b")
HOURS_RE = re.compile(r"(?<!\d)(\d{1,3})(?:\.\d+)?(?!\d)")
TOTAL_RE = re.compile(
    r"\b(total\s+(program|degree|certificate|semester)\s+hours?|"
    r"program\s+total|total\s+hours\s+required)\b",
    re.I,
)
AWARD_RE = re.compile(
    r"\b(associate of applied science|associate of science|associate of arts|"
    r"certificate of completion|advanced technical certificate|"
    r"occupational skills award)\b",
    re.I,
)


def clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize(value: object) -> str:
    text = clean(value).lower().replace("&", " and ")
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize(value)).strip("_")


def iter_blocks(doc: Document):
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "paragraph", Paragraph(child, doc)
        elif tag == "tbl":
            yield "table", Table(child, doc)


def table_rows(table: Table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        rows.append([clean(cell.text) for cell in row.cells])
    return rows


def find_heading_blocks(path: Path) -> list[dict]:
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

        j = i + 1
        block_items = []
        while j < len(blocks):
            next_kind, next_obj = blocks[j]
            if next_kind == "paragraph":
                next_style = clean(next_obj.style.name if next_obj.style else "")
                if next_style in {"Heading 1", "Heading 2"}:
                    break
                text = clean(next_obj.text)
                if text:
                    block_items.append(
                        {
                            "kind": "paragraph",
                            "style": next_style,
                            "text": text,
                            "rows": None,
                            "block_position": j,
                        }
                    )
            else:
                rows = table_rows(next_obj)
                block_items.append(
                    {
                        "kind": "table",
                        "style": "",
                        "text": "\n".join(" | ".join(row) for row in rows),
                        "rows": rows,
                        "block_position": j,
                    }
                )
            j += 1

        output.append(
            {
                "heading": heading,
                "normalized_heading": normalize(heading),
                "start_block": i,
                "end_block": j - 1,
                "items": block_items,
            }
        )

    return output


def extract_course_rows(block: dict) -> pd.DataFrame:
    rows = []
    sequence = 0

    for item in block["items"]:
        if item["kind"] == "paragraph":
            text = item["text"]
            matches = COURSE_RE.findall(text.upper())
            for rubric, number in matches:
                sequence += 1
                rows.append(
                    {
                        "sequence": sequence,
                        "source_kind": "paragraph",
                        "source_block_position": item["block_position"],
                        "source_row": "",
                        "course_code": f"{rubric} {number}",
                        "source_text": text,
                        "possible_hours": "",
                    }
                )
        else:
            for row_number, cells in enumerate(item["rows"], start=1):
                row_text = " | ".join(cells)
                matches = COURSE_RE.findall(row_text.upper())
                if not matches:
                    continue

                possible_hours = ""
                numeric_values = []
                for cell in cells:
                    for value in HOURS_RE.findall(cell):
                        try:
                            number_value = int(value)
                        except ValueError:
                            continue
                        if 1 <= number_value <= 12:
                            numeric_values.append(number_value)
                if numeric_values:
                    possible_hours = numeric_values[-1]

                for rubric, number in matches:
                    sequence += 1
                    rows.append(
                        {
                            "sequence": sequence,
                            "source_kind": "table",
                            "source_block_position": item["block_position"],
                            "source_row": row_number,
                            "course_code": f"{rubric} {number}",
                            "source_text": row_text,
                            "possible_hours": possible_hours,
                        }
                    )

    return pd.DataFrame(rows)


def summarize_block(year: str, source_file: Path, block: dict) -> dict:
    full_text = "\n".join(item["text"] for item in block["items"])
    course_rows = extract_course_rows(block)
    unique_courses = sorted(course_rows["course_code"].unique()) if not course_rows.empty else []

    award_match = AWARD_RE.search(full_text)
    award_text = clean(award_match.group(0)) if award_match else ""

    displayed_program_hours = ""
    for line in full_text.splitlines():
        if TOTAL_RE.search(line):
            values = [int(v) for v in HOURS_RE.findall(line) if 1 <= int(v) <= 150]
            if values:
                displayed_program_hours = values[-1]

    return {
        "catalog_year": year,
        "source_file": str(source_file),
        "source_heading": block["heading"],
        "normalized_heading": block["normalized_heading"],
        "start_block": block["start_block"],
        "end_block": block["end_block"],
        "award_text": award_text,
        "displayed_program_hours": displayed_program_hours,
        "unique_course_count": len(unique_courses),
        "course_codes": " | ".join(unique_courses),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--source-reconciliation",
        default="data/processed/catalogs/credential_block_inventory/source_block_reconciliation.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/catalogs/credential_corrections",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    recon_path = root / args.source_reconciliation
    output_dir = root / args.output_dir
    dump_dir = output_dir / "source_block_dumps"
    course_dir = output_dir / "course_rows"

    output_dir.mkdir(parents=True, exist_ok=True)
    dump_dir.mkdir(parents=True, exist_ok=True)
    course_dir.mkdir(parents=True, exist_ok=True)

    if not recon_path.exists():
        raise FileNotFoundError(f"Missing reconciliation file: {recon_path}")

    recon = pd.read_csv(recon_path, dtype=str).fillna("")
    recon["normalized_heading"] = recon["source_heading"].map(normalize)

    excluded = recon[recon["normalized_heading"].isin(NON_CREDENTIAL_HEADINGS)].copy()
    excluded["correction_class"] = "EXCLUDE_NON_CREDENTIAL_BLOCK"
    excluded.to_csv(output_dir / "excluded_noncredential_blocks.csv", index=False)

    exact_existing = recon[
        (recon["normalized_heading"] == recon["matched_credential_title"].map(normalize))
        & recon["matched_credential_id"].ne("")
    ].copy()
    exact_existing["correction_class"] = "EXISTING_CREDENTIAL_TITLE_CONFIRMED"
    exact_existing.to_csv(output_dir / "exact_title_existing_matches.csv", index=False)

    candidate_rows = []

    print("=" * 118)
    print("PREPARE CATALOG CREDENTIAL CORRECTION PACKAGES")
    print("=" * 118)

    for year, relpath in CATALOG_PATHS.items():
        source_path = root / relpath
        if not source_path.exists():
            print(f"{year}: SOURCE FILE NOT FOUND: {source_path}")
            continue

        blocks = find_heading_blocks(source_path)
        selected = [
            block for block in blocks
            if block["normalized_heading"] in TARGET_HEADINGS
        ]

        print(f"{year}: selected correction blocks={len(selected)}")

        for block in selected:
            summary = summarize_block(year, source_path, block)
            matched = recon[
                (recon["catalog_year"] == year)
                & (recon["normalized_heading"] == block["normalized_heading"])
            ]

            if matched.empty:
                reconciliation_status = "NOT_PRESENT_IN_RECONCILIATION"
                matched_id = ""
                matched_title = ""
                score = ""
            else:
                best = matched.iloc[0]
                reconciliation_status = best.get("reconciliation_status", "")
                matched_id = best.get("matched_credential_id", "")
                matched_title = best.get("matched_credential_title", "")
                score = best.get("combined_score", "")

            likely_missing = (
                reconciliation_status == "MISSING_PARSED_CREDENTIAL"
                or not matched_id
            )

            candidate = {
                **summary,
                "reconciliation_status": reconciliation_status,
                "matched_credential_id": matched_id,
                "matched_credential_title": matched_title,
                "combined_score": score,
                "proposed_action": (
                    "ADD_MISSING_CREDENTIAL_YEAR"
                    if likely_missing
                    else "REVIEW_EXISTING_OR_ALIAS"
                ),
                "approval_status": "PENDING_HUMAN_REVIEW",
                "authorized_credential_id": "",
                "authorized_credential_title": "",
                "authorized_award_type": "",
                "authorized_program_hours": "",
                "review_note": "",
            }
            candidate_rows.append(candidate)

            slug = f"{year}_{safe_slug(block['heading'])}"

            # Human-readable full source block dump.
            dump_lines = [
                f"CATALOG YEAR: {year}",
                f"SOURCE FILE: {source_path}",
                f"HEADING: {block['heading']}",
                f"BLOCK RANGE: {block['start_block']} - {block['end_block']}",
                "",
            ]
            for item in block["items"]:
                dump_lines.append(
                    f"[{item['kind'].upper()} | block {item['block_position']} | style={item['style']}]"
                )
                dump_lines.append(item["text"])
                dump_lines.append("")

            (dump_dir / f"{slug}.txt").write_text(
                "\n".join(dump_lines),
                encoding="utf-8",
            )

            course_rows = extract_course_rows(block)
            course_rows.insert(0, "catalog_year", year)
            course_rows.insert(1, "source_heading", block["heading"])
            course_rows.to_csv(course_dir / f"{slug}.csv", index=False)

    candidates = pd.DataFrame(candidate_rows)
    candidates = candidates.sort_values(
        ["catalog_year", "source_heading"]
    ).reset_index(drop=True)
    candidates.to_csv(output_dir / "correction_candidates.csv", index=False)

    summary = (
        candidates.groupby(
            ["catalog_year", "proposed_action"], dropna=False
        )
        .size()
        .reset_index(name="count")
    )
    summary.to_csv(output_dir / "correction_candidate_summary.csv", index=False)

    print()
    print(summary.to_string(index=False))
    print()
    print(f"Correction candidates: {len(candidates):,}")
    print(f"Output directory: {output_dir}")
    print()
    print("No production files were modified.")
    print("Review correction_candidates.csv and the matching source block dumps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
