# Multi-Catalog Architecture

## Purpose

The audit engine must support every active LSCO catalog year instead of treating one catalog as the implicit source of truth. Catalog parsing, credential normalization, and student audit outputs should therefore be keyed by catalog year.

The stable rule grain is:

```text
catalog_year + credential_id + requirement_id
```

This prevents a credential or requirement from one catalog year from overwriting the same credential in another year.

## Governance Boundary

DegreeWorks and Registrar review remain the authoritative graduation determination process. This repository is for reproducible analytics, discrepancy discovery, and operational reporting.

No FERPA-protected student data belongs in source control. Real Banner, Argos, DegreeWorks, student-level outputs, and private review packets stay local.

## Folder Contract

```text
data/
  raw/
    catalogs/
      2022-2023/
      2023-2024/
      2024-2025/
      2025-2026/
    banner/
      .gitkeep only; real extracts are ignored
  interim/
    catalogs/
      <catalog_year>/
        page_text.csv
        page_inventory.csv
        extraction_issues.csv
  processed/
    catalogs/
      <catalog_year>/
        credentials.csv
        requirements_master.csv
        core_crosswalk.csv
        core_bucket_lookup.csv

src/
  lsco_audit/
    catalog/
      extract/
      normalize/
      compare/
      validators/
    banner/
    audit/
    reporting/
```

## Catalog Registry

`config/catalogs.csv` is the routing table for active catalog ingestion. It records catalog year, volume, effective term, graduation deadline, source PDF, source DOCX, and active status.

The registry should be loaded before any catalog extraction or audit run. Parsers should not hard-code filenames or assume 2025-2026 as the default.

## Processing Pattern

1. Read `config/catalogs.csv`.
2. For each active catalog year, locate the source PDF/DOCX in `data/raw/catalogs/<catalog_year>/`.
3. Extract page-level text and page inventory into `data/interim/catalogs/<catalog_year>/`.
4. Normalize credential plans into `data/processed/catalogs/<catalog_year>/`.
5. Validate requirement rows using the year-aware key.
6. Audit student course history against a selected catalog year or all active catalog years.

## Rule Types

Initial supported rule types remain:

- EXACT
- ANY_N
- CORE_BUCKET
- ELECTIVE
- NON_COURSE

Multi-catalog support changes the storage grain, not the audit semantics.

## Near-Term Implementation Notes

The first implementation pass should prioritize mechanical parsing and year-level reproducibility. Manual injections should be isolated, documented, and keyed by catalog year so they can be retired or compared as parser accuracy improves.
