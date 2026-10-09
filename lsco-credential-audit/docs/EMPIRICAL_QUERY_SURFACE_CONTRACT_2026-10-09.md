# LSCO Empirical Query Surface Contract

**Certification date:** 2026-10-09
**Status:** Validated empirical snapshot; read-only baseline
**Repository:** `LSCO-Completed-and-Near-Degree-Audit`
**Branch reviewed:** `feature/multi-catalog-architecture`
**Source-code reference:** `ebb93377fe7c721003ee7583dbad357ce55c4941`
**Scope:** Current eligible empirical credential audits for six catalog years, 2021–2022 through 2026–2027.

## 1. Purpose and authority

This document records **the existing, tested empirical query surface**, not a proposed database, replacement engine, or new reporting architecture. The empirical snapshot reports curriculum audit results against catalog requirements. It **does not** itself determine conferrability, authorization to award, official award suppression, residency or GPA awardability, catalog expiration, or institutional graduation approval. DegreeWorks and Registrar review remain authoritative for institutional graduation decisions.

**Baseline designation:** *LSCO Empirical Audit Baseline — 2026-10-09* (documentation designation; no OS-level lock, immutable storage, or checksums have yet been applied).

## 2. Authoritative current summary

**Repository-relative file:**

`data/processed/incremental_audit/fall_2026_refresh_20261007/RESTRICTED_current_eligible_empirical_credential_summary.csv`

**Grain:** exactly one row per `(student_id, catalog_year, credential_id)` in the **current eligible** universe. This is not the entire historical July archive.

**Observed column order (12):**

`student_id, catalog_year, credential_id, requirements_met, requirements_total, requirements_missing, requirements_unresolved, audit_status, award_term_sort, award_term_taken, invalidation_reason, result_provenance`

**Validated size:** **3,108,838** rows; **3,108,838** unique keys; **0** missing keys, unexpected keys, or duplicate keys relative to current eligible student/catalog pairs crossed with catalog-year credentials in the six-year requirements master.

**Expected-universe inputs:**

- `data/processed/incremental_audit/fall_2026_refresh_20261007/state/RESTRICTED_current_eligible_pairs.csv` — `(student_id, catalog_year)`.
- `data/processed/catalogs/staging_six_year/requirements_master_multiyear.csv` — catalog-year credential requirements, from which distinct `(catalog_year, credential_id)` combinations are derived.

## 3. Physical source inventory and provenance

| Source | Summary / detail location | Credential-year keys in current summary | Raw detail rows reconciled | Detail shape |
|---|---|---:|---:|---|
| July archival cache | `data/processed/full_actual_audit/full_actual_credential_summary.csv` and `full_actual_audit_results.csv` | 1,689,121 | 21,405,435 matching cached keys | 15 columns |
| October original delta | `data/processed/incremental_audit/fall_2026_refresh_20261007/RESTRICTED_delta_credential_summary.csv`; `chunks/chunk_#####_summary.csv` and `_detail.csv` | 1,388,032 | 16,691,188 | 23 columns |
| October supplemental recovery | `data/processed/incremental_audit/fall_2026_refresh_20261007/RESTRICTED_backfill_credential_summary.csv`; `recovery_backfill/chunks/chunk_#####_summary.csv` and `_detail.csv` | 31,685 | 400,964 | 23 columns |
| **Current total** | Consolidated summary plus provenance-selected detail | **3,108,838** | **38,497,587** | Mixed physical schemas; no new combined detail file |

**Source ownership:** `result_provenance = CACHE_PRIOR_202607` routes to July detail. `result_provenance = DELTA_RECOMPUTE_20261007` routes to October **original or recovery** detail, never a stale July fallback. The consolidated `result_provenance` value does **not** distinguish original October from recovery; exact-key membership in the original-delta and backfill summary files does. The original and backfill key sets were verified disjoint.

**July archive inventory:** 514 `chunk_#####_credential_summary.csv`, 514 `chunk_#####_audit_results.csv`, and 514 `chunk_#####_student_course_history.csv`; all numbered filenames present. At the inspection time, 121 chunk audit-detail files and 117 course-history files were cloud-only, although the **July consolidated detail file** `full_actual_audit_results.csv` was locally accessible for a complete scan. The old July archival *summary* contains **4,895,850** rows; the **1,689,121** cached keys are a selected subset, not the whole archive.

**October file inventory:** 476 original summary/detail chunk pairs and 15 supplemental summary/detail chunk pairs; all present and locally readable when tested.

## 4. Requirement-detail physical schemas

**July detail (15 columns):**

`student_id, catalog_year, credential_id, requirement_id, rule_type, status, matched_options, matched_terms, matched_term_sorts, matched_grades, latest_matched_term_sort, latest_matched_term_taken, required_options, option_types, used_course_count`

**October detail (23 columns):** the above 15 fields plus:

`path_group_id, path_id, path_label, path_order, path_expected_applied_hours, path_selected, invalidation_reason, result_provenance`

**Grain:** requirement evidence row per credential-year; the October engine may retain **multiple alternative-path candidate rows** for a requirement. Consequently, raw `requirement_id` should **not** be presumed unique across unselected and selected paths. For the selected subset, `(student_id, catalog_year, credential_id, requirement_id)` was tested unique.

**October selected requirement rule (confirmed from committed engine):** count a detail row when `path_group_id` is blank **or** `path_selected` is `TRUE` (case-insensitive normalization in validation). Retain nonselected paths for query and explanation. For the legacy July detail, every detail row participates in its audit summary; the old schema has no path-selection flags.

## 5. Summary and term semantics, as tested

For selected requirement rows:

- `requirements_total` = count of selected requirement rows.
- `requirements_met` = number with `status == MET`.
- `requirements_unresolved` = number with `status` beginning `UNRESOLVED`.
- `requirements_missing` = total minus met minus unresolved.
- `audit_status` = `REVIEW_REQUIRED` if unresolved > 0; otherwise `COMPLETE` if missing = 0; `NEAR_COMPLETE` if missing is 1–3; otherwise `INCOMPLETE`.
- For `COMPLETE` only, award term is selected from the **largest numeric** `latest_matched_term_sort` among selected `MET` requirement rows, retaining corresponding `latest_matched_term_taken`. The engine's stable ordering preserves first-encountered choice when numeric term sorts tie. For non-`COMPLETE`, both award-term fields are blank.

These rules describe the **empirical audit calculation**; `award_term_taken` is not necessarily an institutionally approved conferral date.

## 6. Executed validation ledger — 2026-10-09

All checks below were executed locally against the processed files. No audit computation was rerun and the probes wrote no new output files.

| Probe | Verified result |
|---|---|
| Current key universe | 3,108,838 expected = actual; 0 duplicates, missing, extra |
| October + recovery into current summary | 1,388,032 original + 31,685 supplemental = 1,419,717 exact recomputed keys; 0 overlaps, missing, unexpected, value mismatches |
| July cache into current summary | 1,689,121 source keys matched among 4,895,850 July summary rows; 0 duplicate matches, missing keys, mismatches across seven audit-value fields |
| October source chunk summaries | All 476 original and 15 recovery chunk summaries exactly agree with respective consolidated source summary; no duplicate keys or shared-field mismatches |
| October requirement evidence | 16,691,188 original raw detail rows (16,598,281 selected; 92,907 unselected), plus 400,964 recovery raw/selected rows; 0 missing/extra credential keys, duplicate selected requirements, invalid path flags, count/status mismatches |
| July cached requirement evidence | 62,309,650 July archive detail rows scanned; 21,405,435 matching cached detail rows; 1,689,121 of 1,689,121 cached keys found; 0 missing keys, duplicate requirement uses, count/status mismatches |
| Award-term independent reconstruction | 7,298 `COMPLETE` credential-year keys: 6,578 July, 720 October original, 0 recovery; 0 missing detail, numeric term issues, sort/taken mismatches; 0 non-`COMPLETE` records with award terms |

**Totals:** **38,497,587** raw detail rows supporting the current eligible universe. **38,404,680** selected/common rows; **92,907** retained unselected alternatives. The recovery cohort's 31,685 audited credential-year rows contained **zero `COMPLETE`** results; this is the observed output, not an expected requirement.

## 7. Query precedence and preservation rules

1. Select the **single authoritative credential summary record** by exact `(student_id, catalog_year, credential_id)` from the consolidated current summary.
2. Consult `result_provenance` to determine evidence generation. **Never** replace a recomputed October record's detail with July detail.
3. For recomputed keys, disambiguate original October versus recovery through exact-key membership in `RESTRICTED_delta_credential_summary.csv` or `RESTRICTED_backfill_credential_summary.csv`; each key belongs to exactly one.
4. Read requirement evidence from the corresponding detail generation, preserving its actual physical schema, path flags, statuses, matched courses, grades and terms. For counting requirements use the selection rule in §4; for exploration include unselected alternatives.
5. Treat July archival historical rows **outside current eligibility** as retained in the archival dataset; do not assert they are lost, and do not silently include them in current eligible query results.
6. Keep official-award suppression, GPA/residency, multiple-award governance, temporal eligibility and final recommendation filters **downstream and non-destructive**. They must not redefine the empirical universe.
7. Do not persist restricted student-level queries or audit detail into Git. Existing `data/processed` outputs remain local.

## 8. What this certification does **not** establish

- Correctness of every source catalog rule, course equivalency, matched grade, or underlying student transcript record.
- Institutional conferrability, DegreeWorks agreement, catalog time-window permission, or official award decisions.
- Complete availability/hydration of **every historical chunk file**; the July consolidated detail source was used to validate cache evidence.
- A performance-certified random-access query interface over all 38.5 million evidence rows. Existing scripts show retrieval logic; this validation establishes coverage and semantics, **not** a new operational index or latency guarantee.
- File immutability by hash or storage policy. “Locked” here means an **agreed read-only processing baseline**; hash manifest and immutable storage are separate future choices, not completed actions.
- A fully self-contained Git checkout: FERPA data and staged/generated runtime files are intentionally local, and source catalog documents may be external or excluded from version control.

## 9. Source-control and execution discipline

As of Git commit `ebb9337`, historical catalog academic-course crosswalk and core-bucket lookup baseline CSVs have been pushed under `config/`. Source code is remotely reviewable before future local runs; empirical/student outputs are not to be pushed. The repository can still contain untracked local diagnostic and temporary artifacts—**do not** stage them via `git add .`.

For each future query or processing operation: identify exact source files, grain, selection rule and expected invariant **before execution**; read code first; run read-only against the locked baseline where possible; do not regenerate audited outputs or create additional reporting layers without an explicit need and an approved plan.

---

**Contract conclusion:** The **current eligible** empirical credential summary and its required July/October/recovery requirement evidence have passed exact key, summary-value, requirement-count/status and award-term reconciliation. They are approved as the read-only factual foundation for downstream queries. This document records the tested boundary; it does not assert additional governance or conferral findings.
