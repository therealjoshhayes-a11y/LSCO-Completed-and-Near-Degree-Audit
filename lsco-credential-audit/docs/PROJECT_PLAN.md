# Project Plan

## Goal
Create a Python analytics engine that:

1. Parses the LSCO catalog PDF.
2. Builds machine-readable credential rules.
3. Imports Banner/Argos course history.
4. Audits every student against every credential.
5. Produces completion and near-completion reports.

## Phases
1. Catalog extraction
2. Catalog normalization
3. Core curriculum mapping
4. Student course history cleaning
5. Audit engine
6. Reporting

## Rule Types
- EXACT
- ANY_N
- CORE_BUCKET
- ELECTIVE
- NON_COURSE

## Sprint 1
Extract page-level text from the LSCO catalog PDF and save to CSV.
