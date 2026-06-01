from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pdfplumber


def extract_catalog_pages(pdf_path: Path, catalog_year: str = "2025-2026") -> pd.DataFrame:
    """Extract one row per PDF page while preserving page numbers."""
    rows: list[dict[str, object]] = []
    extracted_at = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            rows.append(
                {
                    "catalog_year": catalog_year,
                    "source_file": pdf_path.name,
                    "page_number": idx,
                    "text": text.strip(),
                    "extraction_method": "pdfplumber.extract_text",
                    "extracted_at": extracted_at,
                }
            )

    return pd.DataFrame(rows)


def write_catalog_pages(pdf_path: Path, output_csv: Path, catalog_year: str = "2025-2026") -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df = extract_catalog_pages(pdf_path=pdf_path, catalog_year=catalog_year)
    df.to_csv(output_csv, index=False)
    return output_csv
