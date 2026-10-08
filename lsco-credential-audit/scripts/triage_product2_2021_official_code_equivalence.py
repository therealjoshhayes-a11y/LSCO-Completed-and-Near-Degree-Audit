from __future__ import annotations

"""Product 2 2021-22 official-award code equivalence triage; no award decisions."""
from pathlib import Path
import pandas as pd

root=Path.cwd()
product=root/"data/processed/reporting/final_unawarded_complete_20261008_155520"
source=product/"RESTRICTED_2021_2022_HISTORICAL_AWARD_CASE_EVIDENCE.csv"
cwpath=root/"data/interim/institutional_awards/award_program_crosswalk_curated.xlsx"
caseout=product/"RESTRICTED_2021_2022_EQUIVALENCE_CODE_TRIAGE.csv"
safeout=product/"FERPA_SAFE_2021_2022_EQUIVALENCE_TRIAGE_COUNTS.csv"
for p in (source,cwpath):
    if not p.is_file(): raise FileNotFoundError(p)

e=pd.read_csv(source,dtype=str,low_memory=False).fillna("")
cw=pd.read_excel(cwpath,sheet_name="Crosswalk Draft",dtype=str).fillna("")
keys=["Curr1ProgramCode","Major1Code","DegreeCode"]
need={"student_id","credential_id","candidate_lineage","candidate_award_category",
      "evidence_relation","award_term","direct_official_lineage",*keys}
if need-set(e): raise RuntimeError("Missing evidence fields: "+str(sorted(need-set(e))))
if set(keys+["canonical_lineage"])-set(cw): raise RuntimeError("Curated crosswalk fields missing")
for c in keys: 
    e[c]=e[c].str.strip().str.upper()
    cw[c]=cw[c].str.strip().str.upper()
cw["canonical_lineage"]=cw["canonical_lineage"].str.strip().str.upper()
e["candidate_lineage"]=e["candidate_lineage"].str.strip().str.upper()
e["direct_official_lineage"]=e["direct_official_lineage"].str.strip().str.upper()

# Compile exact approved code triples BY candidate lineage. Do not treat shared
# major, program or degree codes alone as conclusive equivalence.
lineage_codes=(cw.loc[cw["canonical_lineage"].ne(""),keys+["canonical_lineage"]]
              .drop_duplicates())
by_lineage={name:set(map(tuple,g[keys].itertuples(index=False,name=None)))
            for name,g in lineage_codes.groupby("canonical_lineage")}
rows=[]
for _,r in e.iterrows():
    candidate=r["candidate_lineage"]
    triple=tuple(r[k] for k in keys)
    known=by_lineage.get(candidate,set())
    if r["evidence_relation"]=="NO_OFFICIAL_RECORD":
        category="NO_OFFICIAL_RECORD"
    elif r["direct_official_lineage"]==candidate and candidate:
        category="SAME_CANONICAL_LINEAGE_CODE_REVIEW"
    elif triple in known:
        category="EXACT_APPROVED_CODE_TRIPLE_CONFLICT_REVIEW"
    elif not r["direct_official_lineage"]:
        category="UNMAPPED_OFFICIAL_CODE_TRIPLE_REVIEW"
    elif r["DegreeCode"] in {x[2] for x in known if x[2]}:
        category="SHARED_DEGREE_CODE_DISTINCT_LINEAGE_REVIEW"
    else:
        category="DISTINCT_MAPPED_OFFICIAL_LINEAGE"
    d={k:r[k] for k in ["student_id","credential_id","candidate_lineage",
                        "candidate_award_category","award_term",*keys,
                        "direct_official_lineage","evidence_relation"]}
    d["equivalence_triage"]=category
    d["candidate_approved_code_triples_count"]=len(known)
    d["candidate_approved_code_triples"]=" | ".join("/".join(t) for t in sorted(known))
    rows.append(d)
out=pd.DataFrame(rows)
if len(out)!=len(e):raise RuntimeError("Evidence count changed")
case_key=["student_id","credential_id","candidate_lineage"]
if len(out[case_key].drop_duplicates())!=60:
    raise RuntimeError("Expected 60 selected credential cases")
out.to_csv(caseout,index=False)
agg=(out.groupby(["candidate_award_category","equivalence_triage"],dropna=False)
       .agg(evidence_rows=("student_id","size"),
            recommendation_cases=("credential_id",lambda s: 0))
       .reset_index())
# Count unique case keys, not just individual credential IDs.
case_counts=(out.groupby(["candidate_award_category","equivalence_triage"],dropna=False)
    .apply(lambda g:len(g[case_key].drop_duplicates())).rename("recommendation_cases").reset_index())
agg=agg.drop(columns="recommendation_cases").merge(case_counts,
    on=["candidate_award_category","equivalence_triage"],validate="one_to_one")
agg.to_csv(safeout,index=False)
print("PRODUCT 2 — OFFICIAL CODE EQUIVALENCE TRIAGE")
print(agg.to_string(index=False))
print("Original restricted case count:",len(out[case_key].drop_duplicates()))
print("Official evidence row count:",int(out.evidence_relation.ne("NO_OFFICIAL_RECORD").sum()))
print("Restricted code-by-code comparisons:",caseout)
print("Aggregate:",safeout)
print("All possible equivalences require registrar confirmation; no awards changed.")
