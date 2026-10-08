from __future__ import annotations

"""Direct, student-level official-award reconciliation for Product 2's 2021-22 selections.

Read-only source handling. Writes restricted case evidence and aggregate summary locally.
No credential is automatically suppressed by the existence of a different award.
"""

from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
REPORTING = ROOT / "data/processed/reporting"
PRODUCT = REPORTING / "final_unawarded_complete_20261008_155520"
OFFICIAL = REPORTING / "official_award_screening_final_20261008_092747" / "RESTRICTED_canonical_official_awards_final_mapping.csv"
CROSSWALK = ROOT / "data/interim/institutional_awards/award_program_crosswalk_curated.xlsx"
TARGET = PRODUCT / "RESTRICTED_FINAL_unawarded_complete_awards.csv"
CASES_OUT = PRODUCT / "RESTRICTED_2021_2022_OFFICIAL_AWARD_RECONCILIATION.csv"
EVIDENCE_OUT = PRODUCT / "RESTRICTED_2021_2022_ALL_OFFICIAL_AWARD_EVIDENCE.csv"
SUMMARY_OUT = PRODUCT / "FERPA_SAFE_2021_2022_OFFICIAL_AWARD_RECONCILIATION_SUMMARY.csv"

def norm(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()

for path in (TARGET, OFFICIAL, CROSSWALK):
    if not path.is_file():
        raise FileNotFoundError(path)

selected = pd.read_csv(TARGET, dtype=str, low_memory=False).fillna("")
official = pd.read_csv(OFFICIAL, dtype=str, low_memory=False).fillna("")
crosswalk = pd.read_excel(CROSSWALK, sheet_name="Crosswalk Draft", dtype=str).fillna("")
required_selected = {"student_id", "catalog_year", "credential_id", "candidate_lineage", "candidate_award_category"}
required_official = {"ID", "Curr1ProgramCode", "Major1Code", "DegreeCode", "StudGradTerm"}
keys = ["Curr1ProgramCode", "Major1Code", "DegreeCode"]
if required_selected - set(selected):
    raise RuntimeError(f"Selected columns missing: {sorted(required_selected - set(selected))}")
if required_official - set(official):
    raise RuntimeError(f"Official columns missing: {sorted(required_official - set(official))}")
if not set(keys + ["canonical_lineage"]).issubset(crosswalk):
    raise RuntimeError("Curated Crosswalk Draft lacks official three-code/lineage fields.")

cases = selected.loc[selected["catalog_year"].eq("2021-2022")].copy()
if len(cases) != 60:
    raise RuntimeError(f"Expected 60 Product 2 2021-22 selections, found {len(cases)}")
if cases.duplicated(["student_id", "catalog_year", "credential_id"]).any():
    raise RuntimeError("Duplicate selected credential keys.")
cases["student_id"] = norm(cases["student_id"])
cases["candidate_lineage"] = norm(cases["candidate_lineage"])
official["student_id"] = norm(official["ID"])
for key in keys:
    official[key] = norm(official[key])
    crosswalk[key] = norm(crosswalk[key])
crosswalk["canonical_lineage"] = norm(crosswalk["canonical_lineage"])
mapping = crosswalk[keys + ["canonical_lineage"]].drop_duplicates()
ambiguity = mapping.groupby(keys)["canonical_lineage"].nunique(dropna=False)
if (ambiguity > 1).any():
    raise RuntimeError("Ambiguous official three-code mappings; refusing automatic identity comparison.")
mapping = mapping.drop_duplicates(keys)
# Preserve original official-mapping evidence, then independently resolve the exact code triple.
official = official.merge(mapping.rename(columns={"canonical_lineage": "direct_official_lineage"}),
                          on=keys, how="left", validate="many_to_one")
official["direct_official_lineage"] = norm(official["direct_official_lineage"])
official["official_mapping_status"] = official.get("mapping_status", pd.Series("", index=official.index)).fillna("")
official["official_suppression_family"] = official.get("suppression_family", pd.Series("", index=official.index)).fillna("")
official["award_term"] = official["StudGradTerm"].astype(str).str.strip()
# Do not rely on canonical-lineage match alone: manual review of direct catalog degree/major code
# remains necessary to declare an exact award already issued.
case_cols = ["student_id", "catalog_year", "credential_id", "candidate_lineage", "candidate_award_category"]
evidence = cases[case_cols].merge(
    official[["student_id", *keys, "award_term", "direct_official_lineage",
              "official_mapping_status", "official_suppression_family"]],
    on="student_id", how="left", validate="many_to_many", indicator=True
)
evidence["evidence_relation"] = "NO_OFFICIAL_RECORD"
has_official = evidence["_merge"].eq("both")
same = has_official & norm(evidence["direct_official_lineage"]).eq(norm(evidence["candidate_lineage"]))
evidence.loc[has_official, "evidence_relation"] = "OTHER_OR_UNMAPPED_OFFICIAL_AWARD"
evidence.loc[same, "evidence_relation"] = "SAME_CANONICAL_LINEAGE_VERIFY_CODES"
evidence.drop(columns=["_merge"]).to_csv(EVIDENCE_OUT, index=False)

def classify(group: pd.DataFrame) -> pd.Series:
    same_rows = group[group["evidence_relation"].eq("SAME_CANONICAL_LINEAGE_VERIFY_CODES")]
    found = group[~group["evidence_relation"].eq("NO_OFFICIAL_RECORD")]
    disposition = ("POSSIBLY_ALREADY_CONFERRED_REVIEW_CODES" if len(same_rows) else
                   "OTHER_OR_UNMAPPED_AWARDS_REVIEW" if len(found) else
                   "NO_OFFICIAL_AWARD_FOUND")
    return pd.Series({
        "direct_official_reconciliation_status": disposition,
        "official_award_rows": len(found),
        "same_lineage_official_rows": len(same_rows),
        "official_grad_terms": " | ".join(sorted(set(found["award_term"]) - {""})),
        "official_degree_codes": " | ".join(sorted(set(found["DegreeCode"]) - {""})),
        "official_major_codes": " | ".join(sorted(set(found["Major1Code"]) - {""})),
        "official_program_codes": " | ".join(sorted(set(found["Curr1ProgramCode"]) - {""})),
        "mapped_official_lineages": " | ".join(sorted(set(found["direct_official_lineage"]) - {""})),
    })

summary = evidence.groupby(case_cols, dropna=False, sort=False).apply(classify, include_groups=False).reset_index()
if len(summary) != 60:
    raise RuntimeError(f"Case reconciliation must have 60 rows, found {len(summary)}")
summary.to_csv(CASES_OUT, index=False)
aggregate = (summary.groupby(["candidate_award_category", "direct_official_reconciliation_status"],
                             dropna=False).size().rename("recommendations").reset_index())
aggregate.to_csv(SUMMARY_OUT, index=False)
print("PRODUCT 2 — 2021-2022 DIRECT OFFICIAL-AWARD RECONCILIATION")
print(aggregate.to_string(index=False))
print(f"Total selected recommendations reconciled: {len(summary)}")
print(f"Total matched official evidence rows: {int((evidence['evidence_relation'] != 'NO_OFFICIAL_RECORD').sum())}")
print("Restricted case reconciliation:", CASES_OUT)
print("Restricted all-award evidence:", EVIDENCE_OUT)
print("FERPA-safe aggregate:", SUMMARY_OUT)
print("No Product 2 selections, mappings, or awards were modified.")
