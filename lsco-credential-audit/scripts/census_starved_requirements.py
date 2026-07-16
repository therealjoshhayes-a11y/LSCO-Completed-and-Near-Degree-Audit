import pandas as pd
from collections import Counter

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
single = reqs[reqs["option_type"].str.strip().str.upper().eq("COURSE")].groupby("requirement_id").filter(lambda g: len(g) == 1)
req_course = dict(zip(single["requirement_id"], single["option_value"].str.strip()))
req_cred = dict(zip(single["requirement_id"], single["credential_id"]))

inp = pd.read_csv(r"data\processed\normalized_actual_student_course_history.csv", dtype=str, usecols=["student_id","course_code"])
inp["course_code"] = inp["course_code"].str.strip()
holders = inp.groupby("course_code")["student_id"].apply(set).to_dict()

met = Counter()
path = r"data\processed\full_actual_audit\full_actual_audit_results.csv"
for chunk in pd.read_csv(path, dtype=str, usecols=["student_id","requirement_id","status"], chunksize=500000):
    sub = chunk[chunk["requirement_id"].isin(req_course) & chunk["status"].str.strip().str.upper().eq("MET")]
    met.update(sub.groupby("requirement_id")["student_id"].nunique().to_dict())

rows = []
for rid, course in req_course.items():
    h = len(holders.get(course, ()))
    if h == 0:
        continue
    m = met.get(rid, 0)
    rows.append((req_cred[rid], rid, course, h, m))
df = pd.DataFrame(rows, columns=["credential_id","requirement_id","course","holders","holders_met"])
starved = df[(df["holders"] > 0) & (df["holders_met"] == 0)].sort_values(["credential_id","requirement_id"])
print("Single-course requirements with holders but ZERO met (true starvation):", len(starved), "of", len(df))
print(starved.to_string(index=False))
starved.to_csv(r"data\processed\reporting\true_starved_requirements.csv", index=False)
