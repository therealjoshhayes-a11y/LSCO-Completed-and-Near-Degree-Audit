import pandas as pd

from lsco_audit.paths import PROCESSED_DIR


INPUTS = [
    PROCESSED_DIR / "requirements_pattern_a.csv",
    PROCESSED_DIR / "requirements_pattern_b.csv",
    PROCESSED_DIR / "requirements_pattern_c.csv",
]

OUTPUT = PROCESSED_DIR / "requirements_master.csv"


def build_master_requirements() -> None:
    frames = []

    for path in INPUTS:
        df = pd.read_csv(path)
        df["source_file"] = path.name
        frames.append(df)

    master = pd.concat(frames, ignore_index=True)

    master = master.drop_duplicates(
        subset=[
            "requirement_id",
            "credential_id",
            "option_value",
            "option_type",
            "source_page",
            "source_line",
        ]
    )

    master.to_csv(OUTPUT, index=False)

    print(f"Wrote {OUTPUT}")
    print(f"Rows: {len(master)}")
    print(f"Credentials: {master['credential_id'].nunique()}")
    print(master["option_type"].value_counts())


if __name__ == "__main__":
    build_master_requirements()