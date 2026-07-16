import pandas as pd

census = pd.read_csv(r"data\processed\reporting\requirement_matchability_census.csv", dtype=str)
census["miss_rate"] = census["miss_rate"].astype(float)
census["codes_in_banner"] = census["codes_in_banner"].astype(int)
bug_ids = set(census[(census["codes_in_banner"] > 0) & (census["miss_rate"] >= 0.999)]["requirement_id"])

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")

print("RAW option_type values across entire master (repr):")
for value, count in reqs["option_type"].value_counts(dropna=False).items():
    print(f"  {repr(value)}: {count}")

print()
print("RAW option_type values for the 335 bug requirements (repr):")
bug_rows = reqs[reqs["requirement_id"].isin(bug_ids)]
for value, count in bug_rows["option_type"].value_counts(dropna=False).items():
    print(f"  {repr(value)}: {count}")

print()
print("RAW rule_type values for bug requirements (repr):")
for value, count in bug_rows["rule_type"].value_counts(dropna=False).items():
    print(f"  {repr(value)}: {count}")
