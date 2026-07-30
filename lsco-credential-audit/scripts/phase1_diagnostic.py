"""
PHASE 1 DIAGNOSTIC — aggregate-only value counts.
No student_id, no row-level data is printed or written anywhere.
Run this locally against R:\, paste the console output back.
"""

import pandas as pd

REQ_PATH = r"R:\data\processed\catalogs\requirements_master_multicatalog.csv"
COURSE_PATH = r"R:\data\processed\normalized_actual_student_course_history.csv"
SUMMARY_PATH = r"R:\data\processed\full_actual_audit\chunks\chunk_00001_credential_summary.csv"
DETAIL_PATH = r"R:\data\processed\full_actual_audit\chunks\chunk_00001_audit_results.csv"


def divider(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def vc(df, col, top=40):
    if col not in df.columns:
        print(f"  [column '{col}' not found]")
        return
    counts = df[col].value_counts(dropna=False)
    print(f"  n_unique = {counts.shape[0]}")
    print(counts.head(top).to_string())


# ---------------------------------------------------------------------------
# REQUIREMENTS MASTER
# ---------------------------------------------------------------------------
divider("REQUIREMENTS MASTER — requirement_id count, rule_type, original_rule_type")
req = pd.read_csv(REQ_PATH, dtype=str, low_memory=False)
print(f"total rows: {len(req)}")
print(f"unique requirement_id: {req['requirement_id'].nunique()}")
print(f"unique credential_id: {req['credential_id'].nunique()}")
print(f"catalog_year values: {sorted(req['catalog_year'].dropna().unique().tolist())}")

divider("rule_type")
vc(req, "rule_type")

divider("original_rule_type")
vc(req, "original_rule_type")

divider("issue_flags")
vc(req, "issue_flags")

divider("validation_statuses (raw sample of distinct values, not row-linked)")
vc(req, "validation_statuses")

divider("course_codes — is it populated? sample of null vs non-null")
print(f"  null/blank course_codes: {req['course_codes'].isna().sum() + (req['course_codes'] == '').sum()}")
print(f"  non-null course_codes: {req['course_codes'].notna().sum()}")
print("  example non-null values (first 10 distinct, may include real course codes only, no student data):")
examples = req.loc[req["course_codes"].notna(), "course_codes"].dropna().unique()[:10]
for e in examples:
    print(f"    {e}")

# ---------------------------------------------------------------------------
# AUDIT DETAIL (chunk_00001) — THIS IS THE KEY ONE FOR "MISSING COURSE" LOGIC
# ---------------------------------------------------------------------------
divider("AUDIT DETAIL — status value counts (this defines 'missing' vs 'met')")
detail = pd.read_csv(DETAIL_PATH, dtype=str, low_memory=False)
print(f"total rows: {len(detail)}")
print(f"unique student_id: {detail['student_id'].nunique()}  <-- count only, not printed elsewhere")

divider("status")
vc(detail, "status")

divider("rule_type (in detail file)")
vc(detail, "rule_type")

divider("option_types")
vc(detail, "option_types")

divider("required_options vs used_course_count — describe() only (aggregate stats, no rows)")
for col in ["required_options", "used_course_count"]:
    if col in detail.columns:
        numeric = pd.to_numeric(detail[col], errors="coerce")
        print(f"  {col}: {numeric.describe().to_string()}")

# ---------------------------------------------------------------------------
# CREDENTIAL SUMMARY
# ---------------------------------------------------------------------------
divider("CREDENTIAL SUMMARY — audit_status, catalog_eligible, eligibility_reason")
summary = pd.read_csv(SUMMARY_PATH, dtype=str, low_memory=False)
print(f"total rows: {len(summary)}")
print(f"unique student_id: {summary['student_id'].nunique()}  <-- count only")

divider("audit_status")
vc(summary, "audit_status")

divider("catalog_eligible")
vc(summary, "catalog_eligible")

divider("eligibility_reason")
vc(summary, "eligibility_reason")

divider("requirements_met / requirements_total / requirements_missing / requirements_unresolved — describe() only")
for col in ["requirements_met", "requirements_total", "requirements_missing", "requirements_unresolved"]:
    if col in summary.columns:
        numeric = pd.to_numeric(summary[col], errors="coerce")
        print(f"  {col}: {numeric.describe().to_string()}")

# ---------------------------------------------------------------------------
# COURSE HISTORY — just confirm join key shape, aggregate only
# ---------------------------------------------------------------------------
divider("COURSE HISTORY — passed value counts, subject count (aggregate only)")
hist = pd.read_csv(COURSE_PATH, dtype=str, low_memory=False)
print(f"total rows: {len(hist)}")
print(f"unique student_id: {hist['student_id'].nunique()}  <-- count only")
print(f"unique course_code: {hist['course_code'].nunique()}")
vc(hist, "passed")

divider("DONE — paste everything above back")
