#!/usr/bin/env python
"""
Preflight catalog credential inventory reconciliation.

Purpose
-------
Build an independent credential inventory directly from each source catalog and
compare it against the parsed requirements inventory before launching a full audit.

The gate fails when:
- a source-catalog credential is missing from the requirements master;
- a parsed credential has no source-catalog counterpart;
- a credential has zero requirement rows;
- a catalog source file is missing;
- duplicate credential IDs exist within a catalog year;
- a source title maps ambiguously to multiple parsed credentials.

Matching is intentionally fail-closed:
- exact normalized title matches pass;
- approved aliases pass;
- fuzzy similarity is suggestion-only and never auto-passes.

Typical usage
-------------
python .\\scripts\\validate_catalog_credential_inventory.py

Optional:
python .\\scripts\\validate_catalog_credential_inventory.py ^
  --requirements data\\processed\\catalogs\\requirements_master_multicatalog.csv ^
  --aliases data\\reference\\catalog_credential_aliases.csv

Expected alias columns:
catalog_year,source_title,credential_id,note
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError as exc:
    raise SystemExit("Missing dependency: python-docx. Install with: python -m pip install python-docx") from exc

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


CATALOG_FILES = {
    "2021-2022": [
        "data/raw/catalogs/2021-2022/2021-2022_Catalog.docx",
    ],
    "2022-2023": [
        "data/raw/catalogs/2022-2023/2022-2023_Catalog.docx",
    ],
    "2023-2024": [
        "data/raw/catalogs/2023-2024/2023-2024_Catalog.docx",
    ],
    "2024-2025": [
        "data/raw/catalogs/2024-2025/2024-2025_Catalog.docx",
    ],
    "2025-2026": [
        "data/raw/catalogs/2025-2026/2025-2026_Catalog.docx",
        "data/raw/2025-2026 Catalog.pdf",
    ],
}

AWARD_PATTERNS = [
    r"\bassociate of applied science\b",
    r"\bassociate of science\b",
    r"\bassociate of arts\b",
    r"\bassociate degree\b",
    r"\bcertificate of completion\b",
    r"\badvanced technical certificate\b",
    r"\boccupational skills award\b",
    r"\bcertificate\b",
    r"\ba\.?\s*a\.?\s*s\.?\b",
    r"\ba\.?\s*s\.?\b",
    r"\ba\.?\s*a\.?\b",
]
AWARD_RE = re.compile("|".join(AWARD_PATTERNS), re.I)

IGNORE_TITLES = {
    "course descriptions",
    "academic calendars",
    "campus map",
    "college information",
    "admission information",
    "directory of personnel",
    "core curriculum",
    "degree plans",
    "programs of study",
}

START_MARKERS = (
    "degree plans",
    "programs of study",
    "academic programs",
    "career pathways",
)
END_MARKERS = ("course descriptions", "directory of personnel")


@dataclass
class SourceCredential:
    catalog_year: str
    source_file: str
    source_type: str
    source_title: str
    normalized_title: str
    award_text: str
    evidence: str
    evidence_location: str
    confidence: str


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(value: object) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"\bassociate of applied science(?: degree)?\b", "", text)
    text = re.sub(r"\bassociate of science(?: degree)?\b", "", text)
    text = re.sub(r"\bassociate of arts(?: degree)?\b", "", text)
    text = re.sub(r"\bcertificate of completion\b", "", text)
    text = re.sub(r"\badvanced technical certificate\b", "", text)
    text = re.sub(r"\boccupational skills award\b", "", text)
    text = re.sub(r"\bdegree\b|\bcertificate\b", "", text)
    text = re.sub(r"\baas\b|\bas\b|\baa\b", "", text)
    text = re.sub(r"\bprogram\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iter_docx_blocks(doc: Document) -> Iterator[tuple[str, object]]:
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "paragraph", Paragraph(child, doc)
        elif tag == "tbl":
            yield "table", Table(child, doc)


def extract_docx_inventory(path: Path, catalog_year: str) -> list[SourceCredential]:
    doc = Document(path)
    blocks = list(iter_docx_blocks(doc))
    results: list[SourceCredential] = []

    in_program_section = False
    heading1_seen = False

    for i, (kind, obj) in enumerate(blocks):
        if kind != "paragraph":
            continue

        text = clean_text(obj.text)
        style = clean_text(obj.style.name if obj.style else "")
        lower = text.lower()

        if style == "Heading 1":
            heading1_seen = True
            if any(marker in lower for marker in START_MARKERS):
                in_program_section = True
                continue
            if in_program_section and any(marker in lower for marker in END_MARKERS):
                break
            # In later LSCO files the program section is organized directly by pathway
            # Heading 1 values. Once credential-looking Heading 2 entries begin, remain in.
            if any(word in lower for word in ("pathway", "health professions", "business")):
                in_program_section = True

        if style != "Heading 2" or not text:
            continue
        if lower in IGNORE_TITLES:
            continue
        if any(marker in lower for marker in END_MARKERS):
            if in_program_section:
                break
            continue

        # Look ahead only until the next Heading 2/1. A credential is supported by
        # an award label and/or a curriculum table in its own block.
        award_text = ""
        has_table = False
        evidence_parts = []
        for j in range(i + 1, min(i + 18, len(blocks))):
            next_kind, next_obj = blocks[j]
            if next_kind == "paragraph":
                next_text = clean_text(next_obj.text)
                next_style = clean_text(next_obj.style.name if next_obj.style else "")
                if next_style in {"Heading 1", "Heading 2"}:
                    break
                if next_text and AWARD_RE.search(next_text):
                    award_text = next_text
                    evidence_parts.append(f"award={next_text}")
            elif next_kind == "table":
                has_table = True
                rows = len(next_obj.rows)
                cols = len(next_obj.columns) if next_obj.rows else 0
                evidence_parts.append(f"table={rows}x{cols}")

        # Require an award phrase or a curriculum table. This excludes policy headings.
        if not award_text and not has_table:
            continue

        confidence = "HIGH" if award_text and has_table else "MEDIUM"
        results.append(
            SourceCredential(
                catalog_year=catalog_year,
                source_file=str(path),
                source_type="DOCX",
                source_title=text,
                normalized_title=normalize_title(text),
                award_text=award_text,
                evidence="; ".join(evidence_parts),
                evidence_location=f"block_{i}",
                confidence=confidence,
            )
        )

    # Deduplicate repeated descriptive heading + plan heading while preserving evidence.
    dedup: dict[str, SourceCredential] = {}
    for row in results:
        key = row.normalized_title
        if not key:
            continue
        current = dedup.get(key)
        if current is None:
            dedup[key] = row
        elif current.confidence != "HIGH" and row.confidence == "HIGH":
            dedup[key] = row
        else:
            current.evidence = f"{current.evidence}; duplicate_heading={row.evidence_location}"

    return sorted(dedup.values(), key=lambda r: r.normalized_title)


def extract_pdf_inventory(path: Path, catalog_year: str) -> list[SourceCredential]:
    if PdfReader is None:
        raise RuntimeError("pypdf is required for PDF-only catalog inventory extraction.")

    reader = PdfReader(str(path))
    candidates: dict[str, SourceCredential] = {}

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]

        for i, line in enumerate(lines):
            if line.lower() in IGNORE_TITLES or len(line) > 130:
                continue

            window = " | ".join(lines[i + 1 : i + 6])
            award_match = AWARD_RE.search(window)
            if not award_match:
                continue

            norm = normalize_title(line)
            if len(norm) < 4:
                continue

            # Reject obvious course rows and semester labels.
            if re.search(r"\b[A-Z]{4}\s*\d{4}\b", line):
                continue
            if re.search(r"\b(first|second|third|fourth|summer)\s+semester\b", line, re.I):
                continue
            if line.lower().startswith(("total", "semester hours", "program hours")):
                continue

            row = SourceCredential(
                catalog_year=catalog_year,
                source_file=str(path),
                source_type="PDF",
                source_title=line,
                normalized_title=norm,
                award_text=award_match.group(0),
                evidence=f"award_nearby={window[:240]}",
                evidence_location=f"page_{page_number}",
                confidence="REVIEW",
            )
            candidates.setdefault(norm, row)

    return sorted(candidates.values(), key=lambda r: r.normalized_title)


def find_catalog_file(root: Path, relative_candidates: Iterable[str]) -> Path | None:
    for rel in relative_candidates:
        path = root / rel
        if path.exists():
            return path

    # Last-resort filename search under the project root.
    wanted_names = {Path(rel).name.lower() for rel in relative_candidates}
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in wanted_names:
            return path
    return None


def load_requirements(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    required = {"catalog_year", "credential_id", "credential_title"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Requirements file is missing columns: {missing}")

    df["catalog_year"] = df["catalog_year"].map(clean_text)
    df["credential_id"] = df["credential_id"].map(clean_text)
    df["credential_title"] = df["credential_title"].map(clean_text)
    df["normalized_title"] = df["credential_title"].map(normalize_title)
    return df


def load_aliases(path: Path | None) -> pd.DataFrame:
    columns = ["catalog_year", "source_title", "credential_id", "note"]
    if path is None or not path.exists():
        return pd.DataFrame(columns=columns)

    df = pd.read_csv(path, dtype=str).fillna("")
    missing = sorted(set(columns[:3]) - set(df.columns))
    if missing:
        raise ValueError(f"Alias file is missing columns: {missing}")
    if "note" not in df.columns:
        df["note"] = ""
    df["catalog_year"] = df["catalog_year"].map(clean_text)
    df["source_title"] = df["source_title"].map(clean_text)
    df["normalized_source_title"] = df["source_title"].map(normalize_title)
    df["credential_id"] = df["credential_id"].map(clean_text)
    return df


def best_suggestions(source_norm: str, parsed: pd.DataFrame, limit: int = 3) -> str:
    scored = []
    for row in parsed[["credential_id", "credential_title", "normalized_title"]].drop_duplicates().itertuples(index=False):
        score = SequenceMatcher(None, source_norm, row.normalized_title).ratio()
        scored.append((score, row.credential_id, row.credential_title))
    scored.sort(reverse=True)
    return " | ".join(f"{cid}::{title}::{score:.3f}" for score, cid, title in scored[:limit])


def reconcile(
    source_df: pd.DataFrame,
    requirements: pd.DataFrame,
    aliases: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    parsed_inventory = (
        requirements.groupby(
            ["catalog_year", "credential_id", "credential_title", "normalized_title"],
            dropna=False,
        )
        .size()
        .reset_index(name="requirement_rows")
    )

    alias_lookup = {
        (row.catalog_year, row.normalized_source_title): row.credential_id
        for row in aliases.itertuples(index=False)
    }

    source_rows = []
    matched_ids: set[tuple[str, str]] = set()

    for src in source_df.itertuples(index=False):
        parsed_year = parsed_inventory[parsed_inventory["catalog_year"] == src.catalog_year]
        exact = parsed_year[parsed_year["normalized_title"] == src.normalized_title]
        alias_id = alias_lookup.get((src.catalog_year, src.normalized_title), "")
        alias_match = parsed_year[parsed_year["credential_id"] == alias_id] if alias_id else parsed_year.iloc[0:0]

        if len(exact) == 1:
            match = exact.iloc[0]
            status = "PASS_EXACT_TITLE"
        elif len(exact) > 1:
            match = exact.iloc[0]
            status = "FAIL_AMBIGUOUS_NORMALIZED_TITLE"
        elif len(alias_match) == 1:
            match = alias_match.iloc[0]
            status = "PASS_APPROVED_ALIAS"
        elif alias_id and alias_match.empty:
            match = None
            status = "FAIL_ALIAS_TARGET_NOT_FOUND"
        else:
            match = None
            status = "FAIL_MISSING_FROM_REQUIREMENTS"

        if match is not None:
            credential_id = match["credential_id"]
            credential_title = match["credential_title"]
            requirement_rows = int(match["requirement_rows"])
            matched_ids.add((src.catalog_year, credential_id))
        else:
            credential_id = ""
            credential_title = ""
            requirement_rows = 0

        source_rows.append(
            {
                **src._asdict(),
                "status": status,
                "matched_credential_id": credential_id,
                "matched_credential_title": credential_title,
                "requirement_rows": requirement_rows,
                "suggested_matches": best_suggestions(src.normalized_title, parsed_year),
            }
        )

    source_recon = pd.DataFrame(source_rows)

    parsed_rows = []
    for row in parsed_inventory.itertuples(index=False):
        key = (row.catalog_year, row.credential_id)
        if row.requirement_rows <= 0:
            status = "FAIL_ZERO_REQUIREMENT_ROWS"
        elif key in matched_ids:
            status = "PASS_FOUND_IN_SOURCE"
        else:
            status = "FAIL_ORPHAN_PARSED_CREDENTIAL"

        parsed_rows.append(
            {
                "catalog_year": row.catalog_year,
                "credential_id": row.credential_id,
                "credential_title": row.credential_title,
                "normalized_title": row.normalized_title,
                "requirement_rows": int(row.requirement_rows),
                "status": status,
            }
        )

    return source_recon, pd.DataFrame(parsed_rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository/project root.")
    parser.add_argument(
        "--requirements",
        default="data/processed/catalogs/requirements_master_multicatalog.csv",
    )
    parser.add_argument(
        "--aliases",
        default="data/reference/catalog_credential_aliases.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/catalogs/inventory_validation",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    requirements_path = (root / args.requirements).resolve()
    aliases_path = (root / args.aliases).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not requirements_path.exists():
        raise FileNotFoundError(f"Requirements inventory not found: {requirements_path}")

    requirements = load_requirements(requirements_path)
    aliases = load_aliases(aliases_path)

    all_source_rows: list[dict] = []
    source_status_rows = []

    print("=" * 110)
    print("CATALOG CREDENTIAL INVENTORY PREFLIGHT")
    print("=" * 110)

    for catalog_year, candidates in CATALOG_FILES.items():
        path = find_catalog_file(root, candidates)
        if path is None:
            source_status_rows.append(
                {
                    "catalog_year": catalog_year,
                    "source_file": "",
                    "source_status": "FAIL_SOURCE_CATALOG_NOT_FOUND",
                    "source_credentials": 0,
                }
            )
            print(f"{catalog_year}: SOURCE FILE NOT FOUND")
            continue

        print(f"{catalog_year}: {path}")
        try:
            if path.suffix.lower() == ".docx":
                rows = extract_docx_inventory(path, catalog_year)
            elif path.suffix.lower() == ".pdf":
                rows = extract_pdf_inventory(path, catalog_year)
            else:
                raise ValueError(f"Unsupported catalog type: {path.suffix}")
        except Exception as exc:
            source_status_rows.append(
                {
                    "catalog_year": catalog_year,
                    "source_file": str(path),
                    "source_status": f"FAIL_SOURCE_EXTRACTION::{type(exc).__name__}::{exc}",
                    "source_credentials": 0,
                }
            )
            print(f"  extraction failed: {exc}")
            continue

        source_status_rows.append(
            {
                "catalog_year": catalog_year,
                "source_file": str(path),
                "source_status": "PASS_SOURCE_EXTRACTED",
                "source_credentials": len(rows),
            }
        )
        all_source_rows.extend(row.__dict__ for row in rows)
        print(f"  independent source credentials: {len(rows)}")

    source_df = pd.DataFrame(all_source_rows)
    source_status_df = pd.DataFrame(source_status_rows)

    if source_df.empty:
        source_df = pd.DataFrame(
            columns=[
                "catalog_year",
                "source_file",
                "source_type",
                "source_title",
                "normalized_title",
                "award_text",
                "evidence",
                "evidence_location",
                "confidence",
            ]
        )

    source_recon, parsed_recon = reconcile(source_df, requirements, aliases)

    # Structural checks that operate directly on the requirements inventory.
    duplicate_ids = (
        requirements[["catalog_year", "credential_id", "credential_title"]]
        .drop_duplicates()
        .groupby(["catalog_year", "credential_id"])
        .size()
        .reset_index(name="distinct_titles")
    )
    duplicate_ids = duplicate_ids[duplicate_ids["distinct_titles"] > 1].copy()
    duplicate_ids["status"] = "FAIL_DUPLICATE_CREDENTIAL_ID_MULTIPLE_TITLES"

    normalized_collisions = (
        requirements[["catalog_year", "credential_id", "credential_title", "normalized_title"]]
        .drop_duplicates()
        .groupby(["catalog_year", "normalized_title"])
        .agg(
            credential_count=("credential_id", "nunique"),
            credential_ids=("credential_id", lambda s: " | ".join(sorted(set(s)))),
            credential_titles=("credential_title", lambda s: " | ".join(sorted(set(s)))),
        )
        .reset_index()
    )
    normalized_collisions = normalized_collisions[normalized_collisions["credential_count"] > 1].copy()
    normalized_collisions["status"] = "REVIEW_NORMALIZED_TITLE_COLLISION"

    # Write detailed evidence.
    source_df.to_csv(output_dir / "source_catalog_credential_inventory.csv", index=False)
    source_recon.to_csv(output_dir / "source_to_requirements_reconciliation.csv", index=False)
    parsed_recon.to_csv(output_dir / "requirements_to_source_reconciliation.csv", index=False)
    source_status_df.to_csv(output_dir / "source_catalog_status.csv", index=False)
    duplicate_ids.to_csv(output_dir / "duplicate_credential_ids.csv", index=False)
    normalized_collisions.to_csv(output_dir / "normalized_title_collisions.csv", index=False)

    source_failures = source_recon[source_recon["status"].str.startswith("FAIL_", na=False)]
    parsed_failures = parsed_recon[parsed_recon["status"].str.startswith("FAIL_", na=False)]
    source_file_failures = source_status_df[
        source_status_df["source_status"].str.startswith("FAIL_", na=False)
    ]

    summary_rows = []
    for year in sorted(CATALOG_FILES):
        summary_rows.append(
            {
                "catalog_year": year,
                "source_credentials": int((source_df["catalog_year"] == year).sum()),
                "parsed_credentials": int(
                    parsed_recon.loc[parsed_recon["catalog_year"] == year, "credential_id"].nunique()
                ),
                "missing_from_requirements": int(
                    (
                        (source_recon["catalog_year"] == year)
                        & (source_recon["status"] == "FAIL_MISSING_FROM_REQUIREMENTS")
                    ).sum()
                ),
                "orphan_parsed_credentials": int(
                    (
                        (parsed_recon["catalog_year"] == year)
                        & (parsed_recon["status"] == "FAIL_ORPHAN_PARSED_CREDENTIAL")
                    ).sum()
                ),
                "source_status": " | ".join(
                    source_status_df.loc[
                        source_status_df["catalog_year"] == year, "source_status"
                    ].astype(str)
                ),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output_dir / "inventory_validation_summary.csv", index=False)

    print()
    print(summary_df.to_string(index=False))
    print()
    print(f"Missing source credentials: {len(source_failures):,}")
    print(f"Orphan parsed credentials: {len(parsed_failures):,}")
    print(f"Source-file failures: {len(source_file_failures):,}")
    print(f"Duplicate credential IDs: {len(duplicate_ids):,}")
    print(f"Review-only normalized collisions: {len(normalized_collisions):,}")
    print(f"Evidence directory: {output_dir}")

    hard_fail_count = (
        len(source_failures)
        + len(parsed_failures)
        + len(source_file_failures)
        + len(duplicate_ids)
    )

    print()
    if hard_fail_count:
        print("CATALOG INVENTORY GATE: FAIL")
        print("Do not launch the full audit until every FAIL row is resolved or explicitly aliased.")
        return 2

    print("CATALOG INVENTORY GATE: PASS")
    print("Every independently discovered catalog credential is represented in the requirements inventory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
