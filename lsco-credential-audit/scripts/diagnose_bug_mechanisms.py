import pandas as pd

census = pd.read_csv(r"data\processed\reporting\requirement_matchability_census.csv", dtype=str)
census["miss_rate"] = census["miss_rate"].astype(float)
census["codes_in_banner"] = census["codes_in_banner"].astype(int)
bug_ids = set(census[(census["codes_in_banner"] > 0) & (census["miss_rate"] >= 0.999)]["requirement_id"])
print("Bug requirement ids:", len(bug_ids))

reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
bug_reqs = reqs[reqs["requirement_id"].isin(bug_ids)].copy()

# --- Mechanism 2: impossible arithmetic ---
grp = bug_reqs.groupby("requirement_id").agg(
    rule_type=("rule_type", "first"),
    min_required=("min_required", "first"),
    option_count=("option_value", "size"),
).reset_index()
grp["min_required_num"] = pd.to_numeric(grp["min_required"], errors="coerce")
impossible = grp[grp["min_required_num"] > grp["option_count"]]
print()
print("IMPOSSIBLE (min_required > option_count):", len(impossible), "of", len(grp))
if len(impossible):
    print(impossible[["requirement_id", "rule_type", "min_required", "option_count"]].head(30).to_string(index=False))
print()
print("min_required distribution across bug requirements:")
print(grp.groupby(["min_required", "option_count"]).size().to_string())

# --- Mechanism 1: compound override ---
comp = pd.read_csv(
    r"data\processed\catalogs\semantic_policies\compound_requirement_alternatives.csv",
    dtype=str,
).fillna("")
comp_ids = set(comp["requirement_id"])
overridden = bug_ids & comp_ids
print()
print("Bug requirements under compound-alternatives override:", len(overridden), "of", len(bug_ids))
if overridden:
    sub = comp[comp["requirement_id"].isin(overridden)]
    print()
    print("Alternative-group structure for the first 12 overridden requirements")
    print("(each group is ALL-of; a student must hold every course in some group):")
    for rid, rows in list(sub.groupby("requirement_id"))[:12]:
        groups = {
            g: list(r.sort_values("alternative_course_order")["option_value"])
            for g, r in rows.groupby("alternative_group")
        }
        print(f"{rid}:")
        for g, courses in sorted(groups.items()):
            print(f"   group {g}: {courses}")

# --- Anything explained by neither mechanism ---
unexplained = bug_ids - set(impossible["requirement_id"]) - comp_ids
print()
print("Bug requirements explained by NEITHER mechanism:", len(unexplained))
if unexplained:
    print(sorted(unexplained)[:20])
