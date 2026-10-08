from pathlib import Path
import pandas as pd

ROOT=Path.cwd()
PRODUCT=ROOT/"data/processed/reporting/final_unawarded_complete_20261008_155520"
EVIDENCE=PRODUCT/"RESTRICTED_2021_2022_EQUIVALENCE_CODE_TRIAGE.csv"
CROSSWALK=ROOT/"data/interim/institutional_awards/award_program_crosswalk_curated.xlsx"
OUT=PRODUCT/"RESTRICTED_2021_2022_PROGRAM_CONTINUITY_REVIEW.csv"
SAFE=PRODUCT/"FERPA_SAFE_2021_2022_PROGRAM_CONTINUITY_COUNTS.csv"
for p in (EVIDENCE,CROSSWALK):
    if not p.is_file(): raise FileNotFoundError(p)
e=pd.read_csv(EVIDENCE,dtype=str).fillna("")
cross=pd.read_excel(CROSSWALK,sheet_name="Crosswalk Draft",dtype=str).fillna("")
modeled=pd.read_excel(CROSSWALK,sheet_name="Modeled Inventory",dtype=str).fillna("")
key=["Curr1ProgramCode","Major1Code","DegreeCode"]
for c in key+["canonical_lineage"]:
    if c not in cross:raise RuntimeError("Crosswalk field missing: "+c)
for c in key:
    cross[c]=cross[c].str.strip().str.upper()
    e[c]=e[c].str.strip().str.upper()
cross["canonical_lineage"]=cross["canonical_lineage"].str.strip().str.upper()
if not {"credential_id","canonical_lineage"}.issubset(modeled):
    raise RuntimeError("Modeled Inventory missing required fields")
modeled["credential_id"]=modeled["credential_id"].str.strip().str.upper()
modeled["canonical_lineage"]=modeled["canonical_lineage"].str.strip().str.upper()
e["credential_id"]=e["credential_id"].str.strip().str.upper()
e["candidate_lineage"]=e["candidate_lineage"].str.strip().str.upper()
e["direct_official_lineage"]=e["direct_official_lineage"].str.strip().str.upper()
# Exact three-code joins are already decided upstream. This step explores
# shared program and major identifiers without declaring degree equivalence.
candidate_codes={}
for lineage,group in cross[cross.canonical_lineage.ne("")].groupby("canonical_lineage"):
    candidate_codes[lineage]=group[key].drop_duplicates()
records=[]
for _,r in e.iterrows():
    lineage=r.candidate_lineage
    cands=candidate_codes.get(lineage,pd.DataFrame(columns=key))
    shared_program=bool(r.Curr1ProgramCode and (cands.Curr1ProgramCode==r.Curr1ProgramCode).any())
    shared_major=bool(r.Major1Code and (cands.Major1Code==r.Major1Code).any())
    # Exact program+major pair is more suggestive than either independently.
    shared_pair=bool(r.Curr1ProgramCode and r.Major1Code and
        ((cands.Curr1ProgramCode==r.Curr1ProgramCode)&(cands.Major1Code==r.Major1Code)).any())
    if r.evidence_relation=="NO_OFFICIAL_RECORD": status="NO_OFFICIAL_RECORD"
    elif r.direct_official_lineage==lineage: status="SAME_LINEAGE_CONFIRM_CODE"
    elif shared_pair: status="SHARED_PROGRAM_MAJOR_REVIEW"
    elif shared_program: status="SHARED_PROGRAM_CODE_REVIEW"
    elif shared_major: status="SHARED_MAJOR_CODE_REVIEW"
    elif r.direct_official_lineage:status="DISTINCT_MAPPED_NO_SHARED_PROGRAM_CODE"
    else:status="UNMAPPED_NO_SHARED_PROGRAM_CODE"
    records.append({**r.to_dict(),
        "candidate_crosswalk_program_codes":" | ".join(sorted(set(cands.Curr1ProgramCode)-{""})),
        "candidate_crosswalk_major_codes":" | ".join(sorted(set(cands.Major1Code)-{""})),
        "official_program_candidate_match":shared_program,
        "official_major_candidate_match":shared_major,
        "official_program_major_pair_match":shared_pair,
        "program_continuity_triage":status})
out=pd.DataFrame(records)
cases=["student_id","credential_id","candidate_lineage"]
if len(out[cases].drop_duplicates())!=60:raise RuntimeError("60-case population changed")
if len(out)!=len(e):raise RuntimeError("Official evidence population changed")
out.to_csv(OUT,index=False)
groups=["candidate_award_category","program_continuity_triage"]
counts=out.groupby(groups,dropna=False).size().rename("evidence_rows").reset_index()
case_counts=out.groupby(groups,dropna=False).apply(lambda g:len(g[cases].drop_duplicates())).rename("recommendation_cases").reset_index()
counts=counts.merge(case_counts,on=groups,validate="one_to_one")
counts.to_csv(SAFE,index=False)
print("PRODUCT 2 — 2021-2022 PROGRAM CONTINUITY TRIAGE")
print(counts.to_string(index=False))
print("Restricted evidence:",OUT)
print("FERPA-safe summary:",SAFE)
print("These are code-overlap leads only, NOT adjudicated equivalences. Product 2 unchanged.")
