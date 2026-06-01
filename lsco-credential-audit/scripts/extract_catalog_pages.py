from pathlib import Path

from lsco_audit.catalog_extract import write_catalog_pages
from lsco_audit.paths import INTERIM_DIR, RAW_DIR


if __name__ == "__main__":
    pdf_path = RAW_DIR / "2025-2026 Catalog.pdf"
    output_csv = INTERIM_DIR / "catalog_pages.csv"
    result = write_catalog_pages(pdf_path=pdf_path, output_csv=output_csv)
    print(f"Wrote {result}")
