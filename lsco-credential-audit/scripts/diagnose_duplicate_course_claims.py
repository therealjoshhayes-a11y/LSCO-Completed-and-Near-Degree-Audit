import pandas as pd

census = pd.read_csv(r"data\processed\reporting\requirement_matchability_census.csv", dtype=str)
census["miss_rate"] = census["miss_rate"].astype(float)
census["codes_in_banner"] = census["codes_in_banner"].astype(int)
bug_ids = set(census[(census["codes_in_banner"] > 0) & (census["miss_rate"] >= 0.999)]["requirement_id"])

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
course_rows = reqs[reqs["option_type"].str.strip().str.upper().eq("COURSE")].copy()
course_rows["option_value"] = course_rows["option_value"].str.strip()

# For every credential, which courses appear in more than one requirement?
dup = course_rows.groupby(["credential_id", "option_value"])["requirement_id"].nunique()
dup = dup[dup > 1]
print("(credential, course) pairs claimed by 2+ requirements:", len(dup))

# How many of the bug requirements involve a course that is duplicated
# somewhere else in the same credential?
course_rows["key"] = list(zip(course_rows["credential_id"], course_rows["option_value"]))
dup_keys = set(dup.index)
course_rows["is_shared"] = course_rows["key"].isin(dup_keys)
bug_rows = course_rows[course_rows["requirement_id"].isin(bug_ids)]
explained = bug_rows[bug_rows["is_shared"]]["requirement_id"].nunique()
print("Bug requirements whose course is shared with a sibling requirement:", explained, "of", len(bug_ids))
print()
print("Sample duplications (credential | course | competing requirement_ids):")
sample = course_rows[course_rows["is_shared"]].groupby(["credential_id", "option_value"])["requirement_id"].apply(sorted)
shown = 0
for (cred, course), rids in sample.items():
    if any(r in bug_ids for r in rids):
        print(f"{cred} | {course} | {rids}")
        shown += 1
        if shown >= 15:
            break
print()
still_unexplained = bug_ids - set(bug_rows[bug_rows["is_shared"]]["requirement_id"])
print("Bug requirements still unexplained by duplication:", len(still_unexplained))
if still_unexplained:
    print(sorted(still_unexplained)[:15])
