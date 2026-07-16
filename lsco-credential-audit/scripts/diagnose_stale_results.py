import pandas as pd

census = pd.read_csv(r"data\processed\reporting\requirement_matchability_census.csv", dtype=str)
census["miss_rate"] = census["miss_rate"].astype(float)
census["codes_in_banner"] = census["codes_in_banner"].astype(int)
bug_ids = set(census[(census["codes_in_banner"] > 0) & (census["miss_rate"] >= 0.999)]["requirement_id"])

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
master_opts = (
    reqs[reqs["requirement_id"].isin(bug_ids)]
    .groupby("requirement_id")["option_value"]
    .apply(lambda s: "; ".join(sorted(v.strip() for v in s)))
    .to_dict()
)

seen = {}
path = r"data\processed\full_actual_audit\full_actual_audit_results.csv"
for chunk in pd.read_csv(path, dtype=str, usecols=["requirement_id", "required_options"], chunksize=500000):
    sub = chunk[chunk["requirement_id"].isin(bug_ids)]
    for rid, opts in zip(sub["requirement_id"], sub["required_options"]):
        if rid not in seen:
            seen[rid] = str(opts)
    if len(seen) == len(bug_ids):
        break

same = 0
diff = 0
samples = []
for rid in sorted(bug_ids):
    run_time = seen.get(rid, "<absent from results>")
    now = master_opts.get(rid, "<absent from master>")
    if " ".join(run_time.split()) == " ".join(now.split()):
        same += 1
    else:
        diff += 1
        if len(samples) < 12:
            samples.append((rid, run_time, now))

print("Bug requirements where run-time options == current master:", same)
print("Bug requirements where they DIFFER (stale results confirmed):", diff)
print()
for rid, run_time, now in samples:
    print(rid)
    print("   at run time:", repr(run_time))
    print("   master now: ", repr(now))
