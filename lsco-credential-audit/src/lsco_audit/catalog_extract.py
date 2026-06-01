from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CATALOG_PDF = PROJECT_ROOT / "data" / "raw" / "2025-2026 Catalog.pdf"
OUTPUT_CSV = PROJECT_ROOT / "data" / "interim" / "catalog_pages.csv"


def extract_catalog_pages() -> None:
    rows = []

    with pdfplumber.open(CATALOG_PDF) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            rows.append(
                {
                    "catalog_year": "2025-2026",
                    "source_file": CATALOG_PDF.name,
                    "page_number": page_number,
                    "text": page.extract_text() or "",
                    "extraction_method": "pdfplumber",
                    "extracted_at": datetime.now().isoformat(timespec="seconds"),
                }
            )

    df = pd.DataFrame(rows)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)

    print(f"Extracted {len(df)} pages")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    extract_catalog_pages()