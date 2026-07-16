import pandas as pd
reqs = pd.read_csv(r"data\processed\catalogs\requirements_master_multiyear.csv", dtype=str).fillna("")
she = reqs[reqs["credential_id"].str.contains("SAFETY_HEALTH", na=False)]
print(she.groupby(["catalog_year","credential_id"]).size().to_string())
