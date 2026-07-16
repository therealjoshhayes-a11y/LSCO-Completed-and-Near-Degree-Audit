import pandas as pd
reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
course_rows = reqs[reqs["option_type"].str.strip().str.upper().eq("COURSE")].copy()
course_rows["option_value"] = course_rows["option_value"].str.strip()
dup = course_rows.groupby(["credential_id","option_value"])["requirement_id"].apply(sorted)
dup = dup[dup.apply(len) > 1]
print("Remaining (credential, course) pairs claimed by 2+ requirements:", len(dup))
for (cred, course), rids in dup.items():
    rule_types = course_rows[course_rows["requirement_id"].isin(rids)][["requirement_id","rule_type","min_required"]].drop_duplicates()
    print()
    print(f"{cred} | {course}")
    print(rule_types.to_string(index=False))
