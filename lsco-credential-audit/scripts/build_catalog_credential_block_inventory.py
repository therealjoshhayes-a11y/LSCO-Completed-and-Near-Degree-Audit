#!/usr/bin/env python
"""
Build a structural catalog credential-block inventory and reconcile it to the
multicatalog requirements master.

This is a PRE-RUN diagnostic. It does not modify catalog data.

A source credential candidate must:
  * occur between "Degrees, Certificates and Institutional Awards" and
    "Course Descriptions";
  * begin at a Heading 2 program title;
  * contain at least one valid course code before the next Heading 1/2; and
  * contain curriculum evidence (a table, semester heading, or program total).

Matching uses:
  1. exact normalized title;
  2. exact/near course fingerprint;
  3. title + course overlap;
  4. suggestions only when confidence is insufficient.

No fuzzy suggestion is automatically accepted.

Outputs:
  data/processed/catalogs/credential_block_inventory/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator

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

START_HEADING = "degrees certificates and institutional awards"
END_HEADING = "course descriptions"

COURSE_RE = re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b")
SEMESTER_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|summer)\s+"
    r"(semester|session|term)\b",
    re.I,
)
PROGRAM_TOTAL_RE = re.compile(
    r"\b(total\s+(program|degree|certificate)\s+hours?|"
    r"program\s+total|total\s+hours\s+required)\b",
    re.I,
)
AWARD_RE = re.compile(
    r"\b("
    r"associate of applied science|associate of science|associate of arts|"
    r"certificate of completion|advanced technical certificate|"
    r"occupational skills award|institutional award|"
    r"A\.?\s*A\.?\s*S\.?|A\.?\s*S\.?|A\.?\s*A\.?"
    r")\b",
    re.I,
)

NON_COURSE_RUBRICS = {
    "TOTAL", "HOURS", "NOTE", "CORE", "AREA", "TERM", "YEAR", "LEVEL",
}


@dataclass
class SourceBlock:
    catalog_year: str
    source_file: str
    block_index: int
    source_heading: str
    normalized_title: str
    award_text: str
    displayed_program_hours: float | None
    course_count: int
    course_codes: str
    course_fingerprint: str
    table_count: int
    semester_heading_count: int
    has_program_total: bool
    first_block_index: int
    last_block_index: int
    source_status: str
    evidence_preview: str


def clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(value: object) -> str:
    text = clean(value).lower().replace("&", " and ")
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(
        r"\b(associate of applied science|associate of science|associate of arts|"
        r"certificate of completion|advanced technical certificate|"
        r"occupational skills award|institutional award)\b",
        " ",
        text,
    )
    text = re.sub(r"\b(aas|as|aa)\b", " ", text)
    text = re.sub(r"\b(program|degree|certificate)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_course_code(rubric: str, number: str) -> str:
    return f"{rubric.upper()} {number}"


def extract_course_codes(text: str) -> list[str]:
    found = []
    for rubric, number in COURSE_RE.findall(text.upper()):
        if rubric in NON_COURSE_RUBRICS:
            continue
        found.append(normalize_course_code(rubric, number))
    return found


def make_fingerprint(courses: Iterable[str]) -> str:
    payload = "|".join(sorted(set(courses)))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16] if payload else ""


def iter_document_blocks(doc: Document) -> Iterator[tuple[str, object]]:
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "paragraph", Paragraph(child, doc)
        elif tag == "tbl":
            yield "table", Table(child, doc)


def table_text(table: Table) -> str:
    rows = []
    for row in table.rows:
        rows.append(" | ".join(clean(cell.text) for cell in row.cells))
    return "\n".join(rows)


def infer_program_hours(texts: list[str]) -> float | None:
    candidates: list[float] = []
    for text in texts:
        lower = text.lower()
        if not PROGRAM_TOTAL_RE.search(lower):
            continue
        # Prefer values on the same line as a total label.
        for line in text.splitlines():
            if PROGRAM_TOTAL_RE.search(line):
                nums = re.findall(r"(?<!\d)(\d{1,3})(?:\.\d+)?(?!\d)", line)
                for num in nums:
                    value = float(num)
                    if 1 <= value <= 150:
                        candidates.append(value)
    return candidates[-1] if candidates else None


def extract_source_blocks(path: Path, catalog_year: str) -> tuple[list[SourceBlock], list[dict]]:
    doc = Document(path)
    blocks = list(iter_document_blocks(doc))

    in_program_section = False
    candidates: list[SourceBlock] = []
    rejected: list[dict] = []

    i = 0
    while i < len(blocks):
        kind, obj = blocks[i]
        if kind != "paragraph":
            i += 1
            continue

        text = clean(obj.text)
        style = clean(obj.style.name if obj.style else "")
        normalized_heading = normalize_title(text)

        if style == "Heading 1":
            if START_HEADING in normalized_heading:
                in_program_section = True
                i += 1
                continue
            if in_program_section and END_HEADING in normalized_heading:
                break

        if not in_program_section or style != "Heading 2" or not text:
            i += 1
            continue

        start = i
        j = i + 1
        block_texts: list[str] = []
        table_count = 0
        semester_count = 0
        award_text = ""
        all_courses: list[str] = []
        has_total = False

        while j < len(blocks):
            next_kind, next_obj = blocks[j]

            if next_kind == "paragraph":
                next_text = clean(next_obj.text)
                next_style = clean(next_obj.style.name if next_obj.style else "")
                if next_style in {"Heading 1", "Heading 2"}:
                    break
                if next_text:
                    block_texts.append(next_text)
                    all_courses.extend(extract_course_codes(next_text))
                    if SEMESTER_RE.search(next_text):
                        semester_count += 1
                    if PROGRAM_TOTAL_RE.search(next_text):
                        has_total = True
                    if not award_text:
                        match = AWARD_RE.search(next_text)
                        if match:
                            award_text = clean(match.group(0))
            else:
                ttext = table_text(next_obj)
                if ttext:
                    block_texts.append(ttext)
                    all_courses.extend(extract_course_codes(ttext))
                table_count += 1
                if PROGRAM_TOTAL_RE.search(ttext):
                    has_total = True
                if not award_text:
                    match = AWARD_RE.search(ttext)
                    if match:
                        award_text = clean(match.group(0))

            j += 1

        courses = sorted(set(all_courses))
        displayed_hours = infer_program_hours(block_texts)
        curriculum_evidence = table_count > 0 or semester_count > 0 or has_total

        reasons = []
        if not courses:
            reasons.append("NO_COURSE_CODES")
        if not curriculum_evidence:
            reasons.append("NO_CURRICULUM_STRUCTURE")
        if normalize_title(text) in {"course descriptions", "degrees certificates and institutional awards"}:
            reasons.append("NON_PROGRAM_HEADING")

        evidence_preview = clean(" || ".join(block_texts))[:700]

        if reasons:
            rejected.append(
                {
                    "catalog_year": catalog_year,
                    "source_file": str(path),
                    "block_index": len(rejected) + len(candidates) + 1,
                    "source_heading": text,
                    "normalized_title": normalize_title(text),
                    "course_count": len(courses),
                    "table_count": table_count,
                    "semester_heading_count": semester_count,
                    "has_program_total": has_total,
                    "rejection_reason": "|".join(reasons),
                    "evidence_preview": evidence_preview,
                }
            )
        else:
            candidates.append(
                SourceBlock(
                    catalog_year=catalog_year,
                    source_file=str(path),
                    block_index=len(candidates) + 1,
                    source_heading=text,
                    normalized_title=normalize_title(text),
                    award_text=award_text,
                    displayed_program_hours=displayed_hours,
                    course_count=len(courses),
                    course_codes=" | ".join(courses),
                    course_fingerprint=make_fingerprint(courses),
                    table_count=table_count,
                    semester_heading_count=semester_count,
                    has_program_total=has_total,
                    first_block_index=start,
                    last_block_index=j - 1,
                    source_status="SOURCE_CREDENTIAL_BLOCK",
                    evidence_preview=evidence_preview,
                )
            )

        i = j

    return candidates, rejected


def detect_column(columns: Iterable[str], options: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in columns}
    for option in options:
        if option.lower() in lower_map:
            return lower_map[option.lower()]
    return None


def parse_option_courses(value: object) -> list[str]:
    text = clean(value).upper()
    return sorted(set(extract_course_codes(text)))


def build_parsed_inventory(requirements_path: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(requirements_path, dtype=str, low_memory=False).fillna("")

    required = {"catalog_year", "credential_id", "credential_title"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Requirements file missing required columns: {sorted(missing)}")

    course_columns = [
        c
        for c in [
            detect_column(df.columns, ["course_code"]),
            detect_column(df.columns, ["option_code"]),
            detect_column(df.columns, ["requirement_option"]),
            detect_column(df.columns, ["course_options"]),
            detect_column(df.columns, ["option_value"]),
        ]
        if c
    ]

    hours_col = detect_column(df.columns, ["credit_hours", "hours", "required_hours"])
    award_col = detect_column(df.columns, ["award_type", "credential_type", "degree_type"])

    rows = []
    for (year, cid, title), group in df.groupby(
        ["catalog_year", "credential_id", "credential_title"], dropna=False
    ):
        courses = []
        for col in course_columns:
            for value in group[col]:
                courses.extend(parse_option_courses(value))
        courses = sorted(set(courses))

        hours = None
        if hours_col:
            numeric = pd.to_numeric(group[hours_col], errors="coerce")
            if numeric.notna().any():
                # Requirement hours are additive only for the requirements master,
                # but duplicates/options may inflate totals. Keep both sum and max.
                hours = float(numeric.sum())

        award = ""
        if award_col:
            nonblank = [clean(v) for v in group[award_col] if clean(v)]
            award = nonblank[0] if nonblank else ""

        rows.append(
            {
                "catalog_year": clean(year),
                "credential_id": clean(cid),
                "credential_title": clean(title),
                "normalized_title": normalize_title(title),
                "award_type": award,
                "parsed_course_count": len(courses),
                "parsed_course_codes": " | ".join(courses),
                "course_fingerprint": make_fingerprint(courses),
                "requirement_rows": len(group),
                "summed_requirement_hours": hours,
            }
        )

    metadata = {
        "course_columns_used": course_columns,
        "hours_column_used": hours_col,
        "award_column_used": award_col,
    }
    return pd.DataFrame(rows), metadata


def course_set(value: object) -> set[str]:
    return {clean(x) for x in clean(value).split("|") if clean(x)}


def overlap_metrics(source_courses: set[str], parsed_courses: set[str]) -> tuple[float, float, float]:
    if not source_courses or not parsed_courses:
        return 0.0, 0.0, 0.0
    intersection = len(source_courses & parsed_courses)
    source_coverage = intersection / len(source_courses)
    parsed_coverage = intersection / len(parsed_courses)
    jaccard = intersection / len(source_courses | parsed_courses)
    return source_coverage, parsed_coverage, jaccard


def reconcile(source_df: pd.DataFrame, parsed_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_results = []
    matched_parsed: set[tuple[str, str]] = set()

    for src in source_df.itertuples(index=False):
        year_candidates = parsed_df[parsed_df["catalog_year"] == src.catalog_year].copy()
        src_courses = course_set(src.course_codes)
        scored = []

        for cand in year_candidates.itertuples(index=False):
            cand_courses = course_set(cand.parsed_course_codes)
            source_cov, parsed_cov, jaccard = overlap_metrics(src_courses, cand_courses)
            title_score = SequenceMatcher(
                None, src.normalized_title, cand.normalized_title
            ).ratio()
            exact_title = src.normalized_title == cand.normalized_title
            exact_fingerprint = bool(
                src.course_fingerprint
                and src.course_fingerprint == cand.course_fingerprint
            )

            # Structural score favors source coverage because parsed option rows may
            # contain extra alternatives, while the source block may list one pathway.
            score = (
                0.50 * source_cov
                + 0.20 * parsed_cov
                + 0.20 * jaccard
                + 0.10 * title_score
            )
            if exact_title:
                score += 0.15
            if exact_fingerprint:
                score += 0.30

            scored.append(
                {
                    "credential_id": cand.credential_id,
                    "credential_title": cand.credential_title,
                    "exact_title": exact_title,
                    "exact_fingerprint": exact_fingerprint,
                    "title_score": title_score,
                    "source_course_coverage": source_cov,
                    "parsed_course_coverage": parsed_cov,
                    "course_jaccard": jaccard,
                    "combined_score": score,
                    "parsed_course_count": cand.parsed_course_count,
                    "requirement_rows": cand.requirement_rows,
                }
            )

        scored.sort(
            key=lambda x: (
                x["combined_score"],
                x["source_course_coverage"],
                x["course_jaccard"],
            ),
            reverse=True,
        )
        best = scored[0] if scored else None
        second = scored[1] if len(scored) > 1 else None
        margin = (
            best["combined_score"] - second["combined_score"]
            if best and second
            else 1.0
        )

        if best is None:
            status = "MISSING_PARSED_CREDENTIAL"
        elif best["exact_fingerprint"]:
            status = "MATCH_EXACT_FINGERPRINT"
        elif (
            best["exact_title"]
            and best["source_course_coverage"] >= 0.80
            and best["course_jaccard"] >= 0.65
        ):
            status = "MATCH_TITLE_AND_STRUCTURE"
        elif (
            best["source_course_coverage"] >= 0.90
            and best["course_jaccard"] >= 0.70
            and margin >= 0.08
        ):
            status = "MATCH_STRUCTURAL"
        elif (
            best["combined_score"] >= 0.70
            and best["source_course_coverage"] >= 0.70
            and margin >= 0.10
        ):
            status = "REVIEW_PROBABLE_MATCH"
        elif best["combined_score"] >= 0.45:
            status = "AMBIGUOUS_OR_PARTIAL_MATCH"
        else:
            status = "MISSING_PARSED_CREDENTIAL"

        accepted = status.startswith("MATCH_")
        if accepted and best:
            matched_parsed.add((src.catalog_year, best["credential_id"]))

        suggestions = " || ".join(
            f"{x['credential_id']}::{x['credential_title']}::"
            f"score={x['combined_score']:.3f},"
            f"src_cov={x['source_course_coverage']:.3f},"
            f"jaccard={x['course_jaccard']:.3f}"
            for x in scored[:5]
        )

        source_results.append(
            {
                **src._asdict(),
                "reconciliation_status": status,
                "matched_credential_id": best["credential_id"] if best else "",
                "matched_credential_title": best["credential_title"] if best else "",
                "combined_score": round(best["combined_score"], 4) if best else 0,
                "source_course_coverage": round(best["source_course_coverage"], 4) if best else 0,
                "parsed_course_coverage": round(best["parsed_course_coverage"], 4) if best else 0,
                "course_jaccard": round(best["course_jaccard"], 4) if best else 0,
                "title_score": round(best["title_score"], 4) if best else 0,
                "match_margin": round(margin, 4),
                "suggested_matches": suggestions,
            }
        )

    parsed_results = []
    for row in parsed_df.itertuples(index=False):
        key = (row.catalog_year, row.credential_id)
        status = (
            "MATCHED_TO_SOURCE_BLOCK"
            if key in matched_parsed
            else "UNMATCHED_PARSED_CREDENTIAL"
        )
        parsed_results.append({**row._asdict(), "reconciliation_status": status})

    return pd.DataFrame(source_results), pd.DataFrame(parsed_results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--requirements",
        default="data/processed/catalogs/requirements_master_multiyear.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/catalogs/credential_block_inventory",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    requirements_path = root / args.requirements
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 118)
    print("STRUCTURAL CATALOG CREDENTIAL-BLOCK INVENTORY")
    print("=" * 118)

    source_rows = []
    rejected_rows = []
    source_status = []

    for year, relpath in CATALOG_PATHS.items():
        path = root / relpath
        if not path.exists():
            print(f"{year}: SOURCE FILE NOT FOUND: {path}")
            source_status.append(
                {
                    "catalog_year": year,
                    "source_file": str(path),
                    "status": "FAIL_SOURCE_FILE_NOT_FOUND",
                    "credential_blocks": 0,
                    "rejected_headings": 0,
                }
            )
            continue

        blocks, rejected = extract_source_blocks(path, year)
        source_rows.extend(asdict(row) for row in blocks)
        rejected_rows.extend(rejected)
        source_status.append(
            {
                "catalog_year": year,
                "source_file": str(path),
                "status": "PASS_SOURCE_PARSED",
                "credential_blocks": len(blocks),
                "rejected_headings": len(rejected),
            }
        )
        print(
            f"{year}: credential blocks={len(blocks):,} | "
            f"rejected Heading 2 blocks={len(rejected):,}"
        )

    source_df = pd.DataFrame(source_rows)
    rejected_df = pd.DataFrame(rejected_rows)
    source_status_df = pd.DataFrame(source_status)

    if not requirements_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {requirements_path}")

    parsed_df, parsed_metadata = build_parsed_inventory(requirements_path)
    source_recon, parsed_recon = reconcile(source_df, parsed_df)

    source_df.to_csv(output_dir / "source_credential_blocks.csv", index=False)
    rejected_df.to_csv(output_dir / "rejected_heading_blocks.csv", index=False)
    source_status_df.to_csv(output_dir / "source_status.csv", index=False)
    parsed_df.to_csv(output_dir / "parsed_credential_inventory.csv", index=False)
    source_recon.to_csv(output_dir / "source_block_reconciliation.csv", index=False)
    parsed_recon.to_csv(output_dir / "parsed_credential_reconciliation.csv", index=False)

    with (output_dir / "run_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "requirements_path": str(requirements_path),
                **parsed_metadata,
            },
            handle,
            indent=2,
        )

    review_statuses = {
        "REVIEW_PROBABLE_MATCH",
        "AMBIGUOUS_OR_PARTIAL_MATCH",
        "MISSING_PARSED_CREDENTIAL",
    }
    review_df = source_recon[
        source_recon["reconciliation_status"].isin(review_statuses)
    ].copy()
    review_df.to_csv(output_dir / "credential_discrepancy_review.csv", index=False)

    summary_rows = []
    for year in sorted(CATALOG_PATHS):
        year_source = source_recon[source_recon["catalog_year"] == year]
        year_parsed = parsed_recon[parsed_recon["catalog_year"] == year]
        summary_rows.append(
            {
                "catalog_year": year,
                "source_credential_blocks": len(year_source),
                "parsed_credentials": len(year_parsed),
                "matched_source_blocks": int(
                    year_source["reconciliation_status"].str.startswith("MATCH_").sum()
                ),
                "review_probable": int(
                    (year_source["reconciliation_status"] == "REVIEW_PROBABLE_MATCH").sum()
                ),
                "ambiguous_partial": int(
                    (year_source["reconciliation_status"] == "AMBIGUOUS_OR_PARTIAL_MATCH").sum()
                ),
                "missing_parsed": int(
                    (year_source["reconciliation_status"] == "MISSING_PARSED_CREDENTIAL").sum()
                ),
                "unmatched_parsed": int(
                    (year_parsed["reconciliation_status"] == "UNMATCHED_PARSED_CREDENTIAL").sum()
                ),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output_dir / "credential_block_summary.csv", index=False)

    print()
    print(summary_df.to_string(index=False))
    print()
    print(f"Review rows: {len(review_df):,}")
    print(f"Output directory: {output_dir}")
    print()
    print("Important: unmatched parsed credentials are not automatically defects.")
    print("Multiple parsed credentials may share one source display heading.")
    print("The authoritative review queue is credential_discrepancy_review.csv")

    hard_fail = (
        source_status_df["status"].str.startswith("FAIL_").any()
        or (source_recon["reconciliation_status"] == "MISSING_PARSED_CREDENTIAL").any()
        or (source_recon["reconciliation_status"] == "AMBIGUOUS_OR_PARTIAL_MATCH").any()
    )

    print()
    if hard_fail:
        print("STRUCTURAL INVENTORY GATE: REVIEW REQUIRED")
        return 2

    print("STRUCTURAL INVENTORY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
