# Initial Project Prompt

You are assisting with development of the LSCO Credential Completion Audit Engine.

Objectives:
- Parse the LSCO catalog PDF.
- Create machine-readable credential requirements.
- Support EXACT, ANY_N, CORE_BUCKET, and ELECTIVE rules.
- Import Banner/Argos course history.
- Audit every student against every credential.
- Generate operational reports.

Assumptions:
- DegreeWorks remains authoritative.
- FERPA data never enters source control.
- Transparency and reproducibility are preferred over optimization.

Current Sprint:
Extract the catalog PDF into page-level text and produce a structured CSV preserving page numbers.
