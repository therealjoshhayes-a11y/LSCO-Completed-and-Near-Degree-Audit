# LSCO Credential Completion Audit Engine

## Purpose

Build a catalog-driven credential audit engine for LSCO that identifies completed credentials, near completers, graduation application gaps, and credential bottlenecks.

The engine is being expanded from a single-catalog prototype into a multi-catalog architecture that can parse, normalize, compare, and audit against every active catalog year.

## Stack

Python, VSCode, pandas, openpyxl, pypdf, pdfplumber, Git, GitHub.

## Governance

DegreeWorks and Registrar review remain the authoritative graduation determination process.

No FERPA-protected student data belongs in source control. Real Banner, Argos, DegreeWorks, student-level outputs, and private review packets must remain local.

## Multi-Catalog Grain

The stable requirement key is:

```text
catalog_year + credential_id + requirement_id
```

This lets the same credential exist across multiple catalog years without overwriting historical requirements.

## Key Files

- `config/catalogs.csv` - catalog registry and active-year routing table.
- `docs/multi_catalog_architecture.md` - folder contract and processing pattern.
- `src/lsco_audit/catalog/registry.py` - registry loader for catalog-year aware processing.
