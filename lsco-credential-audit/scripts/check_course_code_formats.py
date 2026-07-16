import pandas as pd

df = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
opts = df[df["option_type"].str.upper().eq("COURSE")]["option_value"].str.strip()
bad = opts[~opts.str.match(r"^[A-Z]{2,4} \d{4}$")]

print("COURSE options not in SUBJ-space-NNNN format:", len(bad), "of", len(opts))
print()
print(bad.value_counts().head(30).to_string())
print()
print("repr of top offenders (exposes hidden characters):")
for value in bad.value_counts().head(10).index:
    print(repr(value))
