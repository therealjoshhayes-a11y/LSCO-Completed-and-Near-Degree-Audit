"""
PHASE 1b DIAGNOSTIC — chunk file discovery + course_codes delimiter shape.
No student_id, no row-level student data. Course codes are curriculum data, not PII.
"""

import glob
import os
import re
import pandas as pd

CHUNK_DIR = r"R:\data\processed\full_actual_audit\chunks"
REQ_PATH = r"R:\data\processed\catalogs\requirements_master_multicatalog.csv"


def divider(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


# ---------------------------------------------------------------------------
# 1. Chunk file inventory
# ---------------------------------------------------------------------------
divider("CHUNK FILE INVENTORY")
summary_files = sorted(glob.glob(os.path.join(CHUNK_DIR, "*_credential_summary.csv")))
detail_files = sorted(glob.glob(os.path.join(CHUNK_DIR, "*_audit_results.csv")))
print(f"summary files found: {len(summary_files)}")
print(f"detail files found: {len(detail_files)}")

total_students = set()
for f in summary_files:
    df = pd.read_csv(f, dtype=str, usecols=["student_id"], low_memory=False)
    total_students.update(df["student_id"].unique().tolist())
    print(f"  {os.path.basename(f)}: {len(df)} rows, {df['student_id'].nunique()} unique students")

print(f"\nTOTAL unique students across all summary chunks: {len(total_students)}")

# ---------------------------------------------------------------------------
# 2. course_codes delimiter shape in requirements master
# ---------------------------------------------------------------------------
divider("course_codes delimiter characters — counts of rows containing each delimiter")
req = pd.read_csv(REQ_PATH, dtype=str, low_memory=False)
cc = req["course_codes"].dropna()

delims = [",", ";", "/", "|", " OR ", " or ", "\n"]
for d in delims:
    count = cc.str.contains(re.escape(d), regex=True).sum()
    print(f"  contains {d!r}: {count}")

divider("course_codes — distinct VALUES that contain a delimiter (sample of 25, curriculum data not PII)")
multi = cc[cc.str.contains(r"[,/;|]", regex=True)].unique()
print(f"  total distinct multi-course values: {len(multi)}")
for v in multi[:25]:
    print(f"    {v!r}")

divider("course_codes — breakdown by rule_type: is it populated per rule_type?")
tmp = req.copy()
tmp["has_course_codes"] = tmp["course_codes"].notna() & (tmp["course_codes"] != "")
print(pd.crosstab(tmp["rule_type"], tmp["has_course_codes"]).to_string())

divider("raw_requirement_text sample for rows where course_codes IS NULL but rule_type is CORE_BUCKET or ANY_N")
mask = tmp["course_codes"].isna() & tmp["rule_type"].isin(["CORE_BUCKET", "ANY_N"])
sample_text = tmp.loc[mask, "raw_requirement_text"].dropna().unique()[:10]
for t in sample_text:
    print(f"    {t!r}")

# ---------------------------------------------------------------------------
# 3. matched_options / matched_terms delimiter shape in detail (first chunk only, aggregate)
# ---------------------------------------------------------------------------
divider("matched_options delimiter shape (chunk_00001 only, values not row-linked to students)")
detail = pd.read_csv(detail_files[0], dtype=str, low_memory=False)
mo = detail["matched_options"].dropna()
print(f"  non-null matched_options: {len(mo)}")
for d in delims:
    count = mo.str.contains(re.escape(d), regex=True).sum()
    print(f"  contains {d!r}: {count}")
print("  sample distinct values (course codes, not student data):")
for v in mo.unique()[:15]:
    print(f"    {v!r}")

divider("DONE — paste everything above back")
