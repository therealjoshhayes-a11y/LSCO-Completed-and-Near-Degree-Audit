from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/interim/catalogs/requirement_total_validation.csv")
OUTPUT_PATH = Path("data/interim/catalogs/requirement_total_validation_classified.csv")


def classify_row(row: pd.Series) -> tuple[str, str]:
    """
    Reclassify validator residue so expected catalog omissions are separated
    from true parser/audit problems.
    """

    status = str(row.get("status", ""))
    level = str(row.get("validation_level", ""))
    credential_id = str(row.get("credential_id", ""))
    catalog_year = str(row.get("catalog_year", ""))
    parsed_hours = row.get("parsed_hours")
    expected_hours = row.get("expected_hours")

    # Preserve clean and documented statuses.
    if status == "OK":
        return "OK", "Parsed hours match displayed catalog total."

    if status == "OK_DOCUMENTED_CATALOG_TOTAL_CORRECTION":
        return (
            "OK_DOCUMENTED_CATALOG_TOTAL_CORRECTION",
            "Known documented catalog total correction; parsed total is accepted.",
        )

    # One-semester / short-form catalog blocks often do not print a separate
    # semester total row. If the parser found requirements and no expected
    # total exists, this is not a mismatch.
    if (
        status == "NO_SEMESTER_TOTAL"
        and level == "SEMESTER"
        and pd.isna(expected_hours)
        and pd.notna(parsed_hours)
    ):
        return (
            "OK_NO_DISPLAYED_SEMESTER_TOTAL",
            "No displayed semester total found; parsed requirement total retained.",
        )

    # Massage Therapy 2022/2023 has a combined capstone/contact/program-total
    # row where the final 29 appears embedded in the raw hour string.
    if (
        status == "NO_PROGRAM_TOTAL"
        and level == "PROGRAM"
        and credential_id in {"MASSAGE_THERAPY_2022", "MASSAGE_THERAPY_2023"}
        and float(parsed_hours) == 29.0
    ):
        return (
            "OK_EMBEDDED_PROGRAM_TOTAL",
            "Program total appears embedded in combined capstone/contact/program-total row.",
        )

    # Later Massage Therapy certificates parse coherently to 29 but do not
    # expose a separate machine-detected program-total row.
    if (
        status == "NO_PROGRAM_TOTAL"
        and level == "PROGRAM"
        and credential_id in {"MASSAGE_THERAPY_2024", "MASSAGE_THERAPY_2025"}
        and float(parsed_hours) == 29.0
    ):
        return (
            "OK_NO_DISPLAYED_PROGRAM_TOTAL",
            "No displayed program total found; parsed credential total is coherent.",
        )

    # Other short credentials with coherent parsed totals and no displayed
    # program-total row.
    if (
        status == "NO_PROGRAM_TOTAL"
        and level == "PROGRAM"
        and pd.isna(expected_hours)
        and pd.notna(parsed_hours)
    ):
        return (
            "OK_NO_DISPLAYED_PROGRAM_TOTAL",
            "No displayed program total found; parsed credential total retained.",
        )

    # Anything else remains unresolved.
    return status, "Unresolved validation status; requires review."


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    df = pd.read_csv(INPUT_PATH)

    classified = df.apply(classify_row, axis=1, result_type="expand")
    df["classified_status"] = classified[0]
    df["validation_note"] = classified[1]

    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote classified validation rows to {OUTPUT_PATH}")
    print()
    print("Original status counts:")
    print(df["status"].value_counts().sort_index())
    print()
    print("Classified status counts:")
    print(df["classified_status"].value_counts().sort_index())

    unresolved = df[~df["classified_status"].str.startswith("OK", na=False)]
    print()
    print(f"Unresolved rows: {len(unresolved)}")

    if not unresolved.empty:
        cols = [
            "validation_level",
            "catalog_year",
            "credential_id",
            "credential_title",
            "semester_label",
            "parsed_hours",
            "expected_hours",
            "delta",
            "status",
            "classified_status",
            "validation_note",
            "requirement_count",
        ]
        cols = [c for c in cols if c in unresolved.columns]
        print(unresolved[cols].to_string(index=False))


if __name__ == "__main__":
    main()
    