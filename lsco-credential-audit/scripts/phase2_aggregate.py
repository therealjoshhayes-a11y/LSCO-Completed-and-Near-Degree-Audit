"""
PHASE 2 — full aggregation across all 514 chunk pairs.
Reads student-level detail/summary locally, but only ever WRITES aggregate
counts (credential x catalog_year x course/bucket -> count). student_id never
touches the output file or stdout.
"""

import glob
import os
import re
import pandas as pd

CHUNK_DIR = r"R:\data\processed\full_actual_audit\chunks"
REQ_PATH = r"R:\data\processed\catalogs\requirements_master_multicatalog.csv"
OUT_PATH = r"R:\data\processed\reporting\course_needs_aggregate.csv"


def parse_level(credential_id: str) -> str:
    """Best-effort credential level label parsed from the credential_id token."""
    if not isinstance(credential_id, str):
        return ""
    cid = credential_id.upper()
    if "CERTIFICATE_OF_COMPLETION" in cid:
        return "Certificate of Completion"
    if "_AAS_" in cid or cid.endswith("_AAS") or "_AAS_2" in cid:
        return "AAS"
    if "_AAT" in cid:
        return "AAT"
    if "CERTIFICATE" in cid:
        return "Certificate"
    return ""


def make_label(course_codes, raw_text, rule_type) -> str:
    if isinstance(course_codes, str) and course_codes.strip():
        parts = [p.strip() for p in re.split(r"[;|]", course_codes) if p.strip()]
        if len(parts) > 1:
            return "One of: " + " / ".join(parts)
        return parts[0]
    if isinstance(raw_text, str) and raw_text.strip():
        text = raw_text.strip().rstrip("*").strip()
        return f"[{rule_type}] {text}"
    return f"[{rule_type}] (unspecified)"


# ---------------------------------------------------------------------------
# Build requirement_id -> (credential_family, credential_id, credential_title,
#                           credential_level, rule_type, course_label) lookup
# ---------------------------------------------------------------------------
req_cols = [
    "requirement_id", "credential_family", "credential_id", "credential_title",
    "rule_type", "course_codes", "raw_requirement_text",
]
req = pd.read_csv(REQ_PATH, dtype=str, usecols=req_cols, low_memory=False)
req["credential_level"] = req["credential_id"].apply(parse_level)
req["course_label"] = req.apply(
    lambda r: make_label(r["course_codes"], r["raw_requirement_text"], r["rule_type"]), axis=1
)
req_lookup = req.set_index("requirement_id")[
    ["credential_family", "credential_title", "credential_level", "rule_type", "course_label"]
]

# ---------------------------------------------------------------------------
# Iterate all chunks
# ---------------------------------------------------------------------------
summary_files = sorted(glob.glob(os.path.join(CHUNK_DIR, "*_credential_summary.csv")))
detail_files = sorted(glob.glob(os.path.join(CHUNK_DIR, "*_audit_results.csv")))
assert len(summary_files) == len(detail_files), "summary/detail chunk count mismatch"

agg = {}  # (family, credential_id, title, level, catalog_year, rule_type, label) -> count
total_rows_processed = 0
students_seen = 0

for i, (sf, dfp) in enumerate(zip(summary_files, detail_files), start=1):
    summ = pd.read_csv(
        sf, dtype=str,
        usecols=["student_id", "catalog_year", "credential_id", "catalog_eligible"],
        low_memory=False,
    )
    summ = summ[summ["catalog_eligible"] == "True"]
    if summ.empty:
        continue
    eligible_keys = set(zip(summ["student_id"], summ["catalog_year"], summ["credential_id"]))
    students_seen += summ["student_id"].nunique()

    det = pd.read_csv(
        dfp, dtype=str,
        usecols=["student_id", "catalog_year", "credential_id", "requirement_id", "status"],
        low_memory=False,
    )
    det = det[det["status"] == "UNMET"]
    if det.empty:
        continue

    det["_key"] = list(zip(det["student_id"], det["catalog_year"], det["credential_id"]))
    det = det[det["_key"].isin(eligible_keys)]
    if det.empty:
        continue

    det = det.join(req_lookup, on="requirement_id")
    det = det.dropna(subset=["credential_family"])  # drop any unmatched requirement_id

    grouped = det.groupby(
        ["credential_family", "credential_id", "credential_title", "credential_level",
         "catalog_year", "rule_type", "course_label"]
    ).size()

    for key, count in grouped.items():
        agg[key] = agg.get(key, 0) + int(count)

    total_rows_processed += len(det)

    if i % 50 == 0:
        print(f"  processed {i}/{len(summary_files)} chunks...")

print(f"\nDone. eligible-unmet rows processed (aggregate count only): {total_rows_processed}")
print(f"student-appearances summed across chunks (aggregate count only): {students_seen}")

out_rows = [
    {
        "credential_family": fam, "credential_id": cid, "credential_title": title,
        "credential_level": level, "catalog_year": cyear, "rule_type": rtype,
        "course_label": label, "unmet_count": count,
    }
    for (fam, cid, title, level, cyear, rtype, label), count in agg.items()
]
out_df = pd.DataFrame(out_rows).sort_values(
    ["credential_family", "credential_title", "catalog_year", "unmet_count"],
    ascending=[True, True, True, False],
)
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
out_df.to_csv(OUT_PATH, index=False)
print(f"\nWrote aggregate file: {OUT_PATH}  ({len(out_df)} rows, no student_id column)")
print("\nTop 20 rows by unmet_count (aggregate only):")
print(out_df.sort_values("unmet_count", ascending=False).head(20).to_string(index=False))
