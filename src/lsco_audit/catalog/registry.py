from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


@dataclass(frozen=True)
class CatalogRecord:
    """One row from config/catalogs.csv."""

    catalog_year: str
    volume: str
    effective_term: str
    graduate_by: str
    source_pdf: str
    source_docx: str
    active: bool
    notes: str = ""

    @property
    def raw_catalog_dir(self) -> Path:
        return Path("data") / "raw" / "catalogs" / self.catalog_year

    @property
    def interim_dir(self) -> Path:
        return Path("data") / "interim" / "catalogs" / self.catalog_year

    @property
    def processed_dir(self) -> Path:
        return Path("data") / "processed" / "catalogs" / self.catalog_year


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_catalog_registry(path: str | Path = "config/catalogs.csv", active_only: bool = False) -> list[CatalogRecord]:
    """Load configured catalog years from the registry CSV."""

    registry_path = Path(path)
    records: list[CatalogRecord] = []

    with registry_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            record = CatalogRecord(
                catalog_year=row["catalog_year"].strip(),
                volume=row["volume"].strip(),
                effective_term=row["effective_term"].strip(),
                graduate_by=row["graduate_by"].strip(),
                source_pdf=row["source_pdf"].strip(),
                source_docx=row["source_docx"].strip(),
                active=parse_bool(row["active"]),
                notes=(row.get("notes") or "").strip(),
            )
            if active_only and not record.active:
                continue
            records.append(record)

    return records


def catalog_years(path: str | Path = "config/catalogs.csv", active_only: bool = True) -> list[str]:
    """Return configured catalog years in registry order."""

    return [record.catalog_year for record in load_catalog_registry(path, active_only=active_only)]
