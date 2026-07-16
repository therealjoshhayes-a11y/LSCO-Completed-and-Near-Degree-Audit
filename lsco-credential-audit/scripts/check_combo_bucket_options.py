import pandas as pd
reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
cb = reqs[reqs["option_type"].str.strip().str.upper().eq("CORE_BUCKET")].copy()
cb["val"] = cb["option_value"].str.upper()
combo = cb[cb["val"].str.contains(" OR ")]
print("CORE_BUCKET option rows containing ' OR ' (single-row combos):", len(combo))
print()
print(combo["option_value"].value_counts().to_string())
print()
print("Requirements holding a combo as their ONLY option (highest under-match risk):")
counts = cb.groupby("requirement_id").size()
solo = combo[combo["requirement_id"].map(counts).eq(1)]
print(solo.groupby(["catalog_year"]).size().to_string() if len(solo) else "none")
print()
print("Sample affected credentials:")
print(solo.groupby("credential_id").size().sort_values(ascending=False).head(15).to_string() if len(solo) else "none")
