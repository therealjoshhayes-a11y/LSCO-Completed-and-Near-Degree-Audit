from __future__ import annotations
"""Fall 2026 Products 4/5 input gate.

Builds the actual 202660 registered cohort and identifies which existing
multi-catalog evidence supports course-level reallocation. Does NOT confuse
SCH shortfalls with missing whole-class obligations. No FERPA data is pushed
to GitHub. Run from the lsco-credential-audit root.
"""
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT=Path.cwd()
RAW=ROOT/"data/raw/student_exports"
REFRESH="Summer 2026 and Fall 2026 Course Attempts_(10.5.26).xlsx"
SHEET="202660 Course Attempts"
OUT=ROOT/"data/processed/reporting"/("fall_2026_products_4_5_inputs_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
TERM="202660"
GRADED={"A","B","C","D","S","P","CR"}
NONACTIVE={"W","WF","WD","DROP","DROPPED","CANCELLED","CANCELED"}
DETAIL_PATTERNS=("*combined*detail*.csv","*audit*detail*.csv","*requirement*detail*.csv","*near*complete*.csv","*summary*audit*.csv")

def require(flag,msg):
    if not flag: raise RuntimeError(msg)

def read_header(path):
    try: return list(pd.read_csv(path,nrows=0,encoding="utf-8-sig").columns)
    except (OSError,ValueError,UnicodeDecodeError): return []

def main():
    files=list(RAW.rglob(REFRESH))
    require(len(files)==1,f"Expected one authoritative refresh file, got {len(files)}: {files}")
    raw=pd.read_excel(files[0],sheet_name=SHEET,dtype=str).fillna("")
    necessary={"Student_Id","Term_Code","Subject_Code","Course_Numb","Final_Grade","Section_Numb"}
    require(necessary.issubset(raw),f"Missing refresh columns: {sorted(necessary-set(raw))}")
    fall=raw.loc[raw.Term_Code.astype(str).str.strip().eq(TERM)].copy()
    require(not fall.empty,"No Fall 2026 registrations found in source.")
    for field in ("Student_Id","Subject_Code","Course_Numb","Final_Grade","Section_Numb"):
        fall[field]=fall[field].astype(str).str.strip().str.upper()
    # The same student+term+subject+number unit as the current awardability
    # refresh normalization. Linked-section duplicates must not add classes.
    fall["course_code"]=fall.Subject_Code+" "+fall.Course_Numb
    grouped=fall.groupby(["Student_Id","course_code"],dropna=False)
    conflict=grouped.Final_Grade.nunique()
    require(not (conflict>1).any(),
        f"Contradictory linked-section Fall grades: {int((conflict>1).sum())} keys")
    fall=fall.sort_values("Section_Numb").drop_duplicates(["Student_Id","course_code"])
    excluded=fall.Final_Grade.isin(NONACTIVE)
    if excluded.any():
        fall=fall.loc[~excluded].copy()
    require(not fall.empty,"No active Fall course attempts after explicit exclusion.")
    # Grade blank is prospective. Posted grade can count as earned only when
    # passing under the specific credential's actual min-grade policies.
    fall["scenario_treatment"]=fall.Final_Grade.map(
        lambda g:"CONDITIONAL_IN_PROGRESS" if not g else
                 "POSTED_GRADE_REQUIRES_POLICY_CHECK" if g in GRADED else
                 "GRADE_REQUIRES_REVIEW")
    cohort=set(fall.Student_Id)
    require(all(cohort),"Encountered blank student identifier.")
    OUTPUTS=ROOT/"data/processed"
    artifacts=[]
    seen=set()
    for pattern in DETAIL_PATTERNS:
        for path in OUTPUTS.rglob(pattern):
            if path in seen: continue
            seen.add(path)
            if "fall_2026_products_4_5_inputs_" in str(path):continue
            try:
                size=path.stat().st_size
                if not size:continue
                cols=read_header(path)
                if not cols:continue
                lc={c.lower() for c in cols}
                detail=any("requirement" in c or "group" in c or "option" in c for c in lc)
                students=any(c in lc for c in ("student_id","studentid","studenid"))
                artifacts.append({"path":str(path.relative_to(ROOT)),
                 "size_bytes":size,"has_student_key":students,
                 "has_requirement_or_option_columns":detail,"columns":cols})
            except OSError:continue
    artifacts.sort(key=lambda r:(not r["has_requirement_or_option_columns"],
                                 not r["has_student_key"],r["path"]))
    OUT.mkdir(parents=True,exist_ok=False)
    fall[["Student_Id","course_code","Subject_Code","Course_Numb","Section_Numb",
          "Final_Grade","scenario_treatment"]].to_csv(
          OUT/"RESTRICTED_fall2026_registered_course_inventory.csv",index=False)
    (OUT/"LOCAL_AUDIT_EVIDENCE_MANIFEST.json").write_text(
       json.dumps({"fall_source":str(files[0]),"term":TERM,
       "candidate_artifacts":artifacts[:100]},indent=2),encoding="utf-8")
    metrics={"term":TERM,"distinct_registered_students":len(cohort),
             "distinct_student_course_registrations":len(fall),
             "scenario_treatments":dict(Counter(fall.scenario_treatment)),
             "eligible_requirement_detail_candidates":sum(
                 a["has_student_key"] and a["has_requirement_or_option_columns"]
                 for a in artifacts)}
    (OUT/"FERPA_SAFE_FALL_2026_PREFLIGHT.json").write_text(
         json.dumps(metrics,indent=2),encoding="utf-8")
    print("FALL 2026 PRODUCT 4/5 INPUT GATE")
    for key,value in metrics.items(): print(f"{key}: {value}")
    print("Local report:",OUT)
    print("Likely requirement-level source files (top 12):")
    for artifact in artifacts[:12]:
        print(" ",artifact["path"]," :: ",",".join(artifact["columns"][:15]))
    # Report raw grade labels, including blanks, before scenario assignment.
    # These counts are necessary to distinguish genuine Fall registrations
    # from grades already posted or special status codes.
    distribution=(fall.groupby(["Final_Grade","scenario_treatment"],dropna=False)
                  .agg(student_course_rows=("Student_Id","size"),
                       distinct_students=("Student_Id","nunique"))
                  .reset_index()
                  .sort_values(["student_course_rows","Final_Grade"],ascending=[False,True]))
    distribution.to_csv(OUT/"FERPA_SAFE_FALL_2026_GRADE_CODE_DISTRIBUTION.csv",index=False)
    print("FALL GRADE CODES AND SCENARIO TREATMENTS")
    print(distribution.to_string(index=False))
    print("No graduation or near-completion counts calculated at this gate.")
    print("Do not count unmet SCH or raw rows as whole-class requirements.")

if __name__=="__main__":main()
