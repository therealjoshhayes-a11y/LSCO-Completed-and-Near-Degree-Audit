from __future__ import annotations
import ast, math, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path.cwd()
REPORTING = ROOT/"data"/"processed"/"reporting"
DETAIL = ROOT/"data"/"processed"/"full_actual_audit"/"full_actual_audit_results.csv"
ATTEMPTS = ROOT/"data"/"processed"/"all_student_course_attempts_normalized.csv"
REQ = ROOT/"data"/"processed"/"catalogs"/"requirements_master_multiyear.csv"
OUT = ROOT/"data"/"processed"/"full_actual_audit"/"evidence"/"awardability"
OUT.mkdir(parents=True, exist_ok=True)

GRADE_POINTS={"A":4.0,"B":3.0,"C":2.0,"D":1.0,"F":0.0}
GRADE_RANK={"A":5,"B":4,"C":3,"D":2,"F":1}
ASSOC={"AA","AS","AAS","AAT"}
CERT={"CERT","IA"}
COURSE_RE=re.compile(r"\b([A-Z]{4})\s*[- ]?\s*(\d{4})\b",re.I)
GRADE_RE=re.compile(r"\b(NG|A|B|C|D|F|I|S|U|W|Q)\b",re.I)

def txt(v): return "" if pd.isna(v) else str(v).strip()
def norm_grade(v):
    g=txt(v).upper()
    return {"A+":"A","A-":"A","B+":"B","B-":"B","C+":"C","C-":"C","D+":"D","D-":"D"}.get(g,g)
def norm_course(v):
    m=COURSE_RE.search(txt(v).upper())
    return f"{m.group(1).upper()} {m.group(2)}" if m else None
def hours(course):
    c=norm_course(course)
    return float(c.split()[1][1]) if c and c.split()[1][1]!="0" else np.nan
def level(course):
    c=norm_course(course)
    return int(c.split()[1][0]) if c else np.nan
def list_courses(v):
    s=txt(v)
    if not s: return []
    try:
        x=ast.literal_eval(s)
        if isinstance(x,(list,tuple,set)):
            z=[norm_course(i) for i in x]
            return [i for i in z if i]
    except Exception: pass
    return [f"{m.group(1).upper()} {m.group(2)}" for m in COURSE_RE.finditer(s.upper())]
def list_grades(v):
    s=txt(v)
    if not s: return []
    try:
        x=ast.literal_eval(s)
        if isinstance(x,(list,tuple,set)): return [norm_grade(i) for i in x]
    except Exception: pass
    return [norm_grade(m.group(1)) for m in GRADE_RE.finditer(s.upper())]
def cred_type(cid,title):
    s=re.sub(r"[^A-Z0-9]+"," ",f"{txt(cid)} {txt(title)}".upper())
    t=set(s.split())
    for k in ("AAS","AAT","AA","AS"):
        if k in t:return k
    if "CERT" in t or "CERTIFICATE" in t:return "CERT"
    if "IA" in t or "INSTITUTIONAL" in t:return "IA"
    u=txt(cid).upper()
    for k in ("AAS","AAT","AA","AS","CERT","IA"):
        if u.endswith("_"+k) or f"_{k}_" in u:return k
    return "UNKNOWN"
def gpa(df):
    d=df[df.grade.isin(GRADE_POINTS) & df.derived_hours.notna()].copy()
    if d.empty:return (np.nan,0.0,0.0)
    q=sum(GRADE_POINTS[g]*h for g,h in zip(d.grade,d.derived_hours))
    h=float(d.derived_hours.sum())
    return (q/h if h else np.nan,q,h)
def policy(year,ctype,program_hours):
    ph=int(math.ceil(float(program_hours)*.25)) if pd.notna(program_hours) else np.nan
    if ctype in ASSOC:
        return ("ASSOCIATE_25_PERCENT_MINIMUM_15",max(ph,15),0) if year=="2025-2026" else ("ASSOCIATE_25_PERCENT_PLUS_12_UPPER_OR_CORE",ph,12)
    if ctype in CERT:
        return ("CERTIFICATE_25_PERCENT",ph,0) if year=="2025-2026" else ("CERTIFICATE_FIXED_13_HOURS",13,0)
    return ("UNKNOWN",np.nan,np.nan)

dirs=sorted([p for p in REPORTING.glob("award_selection_*") if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True)
if not dirs: raise FileNotFoundError("No award_selection_* directory found")
selected_path=dirs[0]/"selected_awards.csv"
selected=pd.read_csv(selected_path,dtype=str,low_memory=False)
for c in ("student_id","catalog_year","credential_id"): selected[c]=selected[c].astype(str)
keys=set(selected[["student_id","catalog_year","credential_id"]].itertuples(index=False,name=None))

req=pd.read_csv(REQ,dtype=str,low_memory=False)
req["credit_hours_numeric"]=pd.to_numeric(req["credit_hours"],errors="coerce")
ri=(req.sort_values(["catalog_year","credential_id","requirement_id","sequence"])
      .drop_duplicates(["catalog_year","credential_id","requirement_id"]))
ci=(ri.groupby(["catalog_year","credential_id"],as_index=False)
      .agg(credential_title=("credential_title","first"),
           program_hours=("credit_hours_numeric","sum"),
           requirement_count=("requirement_id","nunique")))
selected=selected.merge(ci,on=["catalog_year","credential_id"],how="left",validate="many_to_one")
selected["credential_type"]=[cred_type(a,b) for a,b in zip(selected.credential_id,selected.credential_title)]

attempts=pd.read_csv(ATTEMPTS,dtype=str,low_memory=False)
attempts["course"]=attempts.course_code.map(norm_course)
attempts["grade"]=attempts.final_grade.map(norm_grade)
attempts["derived_hours"]=attempts.course.map(hours)
attempts["rank"]=attempts.grade.map(GRADE_RANK)
attempts["term_sort_n"]=pd.to_numeric(attempts.term_sort,errors="coerce")
resident=attempts[attempts.grade.isin(GRADE_POINTS)].copy()
resolved=(resident.sort_values(["student_id","course","rank","term_sort_n"],ascending=[True,True,False,False])
                 .drop_duplicates(["student_id","course"]))
ig=[]
for sid,g in resolved.groupby("student_id"):
    eg,q,h=gpa(g.rename(columns={"derived_hours":"derived_hours"}))
    orig=resident[resident.student_id==sid]
    ig.append({"student_id":sid,"estimated_institutional_gpa":eg,
               "institutional_quality_points":q,"institutional_gpa_hours":h,
               "repeated_course_count":int(orig.course.value_counts().gt(1).sum())})
inst=pd.DataFrame(ig)
inst.to_csv(OUT/"student_institutional_gpa_estimates.csv",index=False)

use=["student_id","catalog_year","credential_id","requirement_id","rule_type","status","matched_options","matched_grades","used_course_count"]
parts=[]
read=0
for i,ch in enumerate(pd.read_csv(DETAIL,usecols=use,dtype=str,chunksize=500000,low_memory=False),1):
    read+=len(ch)
    mask=[k in keys for k in ch[["student_id","catalog_year","credential_id"]].itertuples(index=False,name=None)]
    f=ch.loc[mask]
    if not f.empty:parts.append(f)
    if i%20==0:print(f"Read detail chunks: {i} | rows: {read:,}")
detail=pd.concat(parts,ignore_index=True)
detail=detail[detail.status.str.upper()=="MET"].merge(
    ri[["catalog_year","credential_id","requirement_id","group_name","semester_label","source_requirement_text","option_type","credit_hours_numeric"]],
    on=["catalog_year","credential_id","requirement_id"],how="left",validate="many_to_one")

applied=[]
issues=[]
for r in detail.itertuples(index=False):
    cs,gs=list_courses(r.matched_options),list_grades(r.matched_grades)
    if len(cs)!=len(gs):
        issues.append({"student_id":r.student_id,"catalog_year":r.catalog_year,"credential_id":r.credential_id,
                       "requirement_id":r.requirement_id,"issue_type":"MATCHED_COURSE_GRADE_COUNT_MISMATCH",
                       "course_count":len(cs),"grade_count":len(gs)})
    for c,g in zip(cs,gs):
        rt=txt(r.rule_type).upper(); ot=txt(r.option_type).upper()
        gn=txt(r.group_name).upper(); st=txt(r.source_requirement_text).upper()
        core=rt=="CORE_BUCKET" or ot=="CORE_BUCKET" or "CORE CURRICULUM" in gn or "CORE CURRICULUM" in st
        elec=rt=="ELECTIVE" or ot=="ELECTIVE" or "ELECTIVE" in gn or "ELECTIVE" in st
        applied.append({"student_id":r.student_id,"catalog_year":r.catalog_year,"credential_id":r.credential_id,
                        "requirement_id":r.requirement_id,"course":c,"grade":norm_grade(g),
                        "derived_hours":hours(c),"course_level":level(c),
                        "is_core":core,"is_elective":elec,"estimated_major":not core and not elec})
ap=pd.DataFrame(applied).drop_duplicates(["student_id","catalog_year","credential_id","course"])
iss=pd.DataFrame(issues)
ap.to_csv(OUT/"selected_awards_applied_courses.csv",index=False)
iss.to_csv(OUT/"awardability_screen_issues.csv",index=False)

rows=[]
for a in selected.itertuples(index=False):
    ac=ap[(ap.student_id==a.student_id)&(ap.catalog_year==a.catalog_year)&(ap.credential_id==a.credential_id)].copy()
    reasons=[]
    resident_earned=ac[ac.grade.isin({"A","B","C","D"}) & ac.derived_hours.notna()]
    rh=float(resident_earned.derived_hours.sum())
    sh=float(resident_earned[(resident_earned.course_level==2)|resident_earned.is_core].derived_hours.sum())
    p,rr,rs=policy(a.catalog_year,a.credential_type,a.program_hours)
    residency="REVIEW" if pd.isna(rr) else ("PASS" if rh>=rr and sh>=rs else "FAIL")
    if residency=="FAIL":
        if rh<rr:reasons.append("RESIDENCY_HOURS_BELOW_MINIMUM")
        if sh<rs:reasons.append("SPECIAL_RESIDENCY_HOURS_BELOW_MINIMUM")

    cert_gpa=cert_q=cert_h=np.nan; cert_status="NOT_APPLICABLE"
    if a.credential_type in CERT:
        cert_gpa,cert_q,cert_h=gpa(ac)
        exempt=a.catalog_year=="2025-2026" and "GENERAL STUDIES" in f"{a.credential_id} {a.credential_title}".upper()
        cert_status="EXEMPT" if exempt else ("REVIEW" if pd.isna(cert_gpa) else ("PASS" if cert_gpa>=2 else "FAIL"))
        if cert_status=="FAIL":reasons.append("CERTIFICATE_PLAN_GPA_BELOW_2_00")

    major=ac[ac.estimated_major].copy()
    mg,mq,mh=gpa(major)
    below=major[major.grade.isin({"D","F"})]
    minc="REVIEW" if major.empty else ("PASS" if below.empty else "FAIL")
    if minc=="FAIL":reasons.append("ESTIMATED_MAJOR_COURSE_BELOW_C")

    im=inst[inst.student_id==a.student_id]
    igpa=igh=np.nan; istatus="NOT_APPLICABLE"; reps=np.nan
    if a.credential_type in ASSOC:
        if im.empty:istatus="REVIEW"
        else:
            z=im.iloc[0]; igpa=z.estimated_institutional_gpa; igh=z.institutional_gpa_hours; reps=z.repeated_course_count
            istatus="REVIEW" if pd.isna(igpa) else ("PASS" if igpa>=2 else "FAIL")
            if istatus=="FAIL":reasons.append("INSTITUTIONAL_GPA_BELOW_2_00")

    formal=[residency,minc]+([istatus] if a.credential_type in ASSOC else [])+([cert_status] if a.credential_type in CERT else [])
    overall="ACADEMIC_COMPLETE_SCREEN_FAIL" if "FAIL" in formal else ("ACADEMIC_COMPLETE_POLICY_REVIEW" if "REVIEW" in formal else "ACADEMIC_COMPLETE_ESTIMATED_AWARD_ELIGIBLE")
    rows.append({**a._asdict(),"residency_policy":p,"estimated_resident_applied_hours":rh,
                 "required_resident_hours":rr,"estimated_special_resident_hours":sh,
                 "required_special_resident_hours":rs,"residency_status":residency,
                 "estimated_institutional_gpa":igpa,"institutional_gpa_hours":igh,
                 "institutional_gpa_status":istatus,"repeated_course_count":reps,
                 "estimated_certificate_plan_gpa":cert_gpa,"certificate_plan_quality_points":cert_q,
                 "certificate_plan_gpa_hours":cert_h,"certificate_plan_gpa_status":cert_status,
                 "estimated_major_gpa":mg,"estimated_major_quality_points":mq,
                 "estimated_major_gpa_hours":mh,"estimated_major_course_count":len(major),
                 "estimated_major_courses_below_c":len(below),
                 "estimated_major_courses_below_c_codes":" | ".join(sorted(below.course.unique())),
                 "minimum_c_status":minc,"applied_course_count":len(ac),
                 "awardability_status":overall,"awardability_reasons":" | ".join(sorted(set(reasons)))})

out=pd.DataFrame(rows)
out.to_csv(OUT/"selected_awards_awardability_screen.csv",index=False)
summary=[]
for col in ["credential_type","residency_status","institutional_gpa_status","certificate_plan_gpa_status","minimum_c_status","awardability_status"]:
    for val,n in out[col].fillna("BLANK").value_counts().items():
        summary.append({"metric":col,"value":val,"count":n})
pd.DataFrame(summary).to_csv(OUT/"awardability_screen_summary.csv",index=False)

print("="*100)
print("AWARDABILITY SCREEN RESULTS")
print("="*100)
print(f"Selected awards screened: {len(out):,}")
for label,col in [("Credential types","credential_type"),("Residency","residency_status"),
                  ("Associate institutional GPA","institutional_gpa_status"),
                  ("Certificate-plan GPA","certificate_plan_gpa_status"),
                  ("Estimated major minimum-C","minimum_c_status"),
                  ("Overall awardability","awardability_status")]:
    print("\n"+label+":")
    print(out[col].value_counts(dropna=False).to_string())
print("\nOutputs:",OUT)
