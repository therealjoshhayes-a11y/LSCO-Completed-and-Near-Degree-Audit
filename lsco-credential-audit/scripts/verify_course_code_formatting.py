import pandas as pd
import re

PATH = r"data\processed\catalogs\requirements_master_multiyear.csv"

df = pd.read_csv(PATH, dtype=str).fillna("")

course_rows = df[
    df["option_type"].str.strip().str.upper().eq("COURSE")
].copy()

course_rows["course_code"] = (
    course_rows["option_value"]
    .str.upper()
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

valid_pattern = re.compile(r"^[A-Z]{2,5} \d{4}$")

course_rows["valid_format"] = course_rows["course_code"].map(
    lambda value: bool(valid_pattern.fullmatch(value))
)

invalid = course_rows[~course_rows["valid_format"]].copy()

print("COURSE option rows:", len(course_rows))
print("Valid course-code rows:", int(course_rows["valid_format"].sum()))
print("Invalid course-code rows:", len(invalid))

if len(invalid):
    print()
    print("Invalid option values:")
    print(invalid["option_value"].value_counts().head(100).to_string())

    print()
    print("Affected credential-years:")
    print(
        invalid.groupby(
            ["catalog_year", "credential_id", "option_value"]
        ).size().head(100).to_string()
    )

duplicate_options = (
    course_rows.groupby(["requirement_id", "course_code"])
    .size()
    .reset_index(name="count")
)

duplicate_options = duplicate_options[duplicate_options["count"] > 1]

print()
print(
    "Duplicate course options within the same requirement:",
    len(duplicate_options)
)

if len(duplicate_options):
    print(duplicate_options.head(100).to_string(index=False))
