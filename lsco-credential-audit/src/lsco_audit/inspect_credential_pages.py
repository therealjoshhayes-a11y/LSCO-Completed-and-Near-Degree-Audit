import pandas as pd

from lsco_audit.paths import INTERIM_DIR, PROCESSED_DIR


INPUT_CSV = INTERIM_DIR / "catalog_pages.csv"
OUTPUT_TXT = PROCESSED_DIR / "credential_page_samples.txt"

SAMPLE_PAGES = [130, 131, 133]


def inspect_pages() -> None:
    pages = pd.read_csv(INPUT_CSV)
    chunks = []

    for page_number in SAMPLE_PAGES:
        row = pages.loc[pages["page_number"] == page_number].iloc[0]
        text = str(row["text"])
        lines = text.splitlines()

        chunks.append("=" * 80)
        chunks.append(f"PAGE {page_number}")
        chunks.append("=" * 80)

        for line_number, line in enumerate(lines, start=1):
            chunks.append(f"{line_number:03}: {line}")

        chunks.append("")

    OUTPUT_TXT.write_text("\n".join(chunks), encoding="utf-8")

    print(f"Wrote {OUTPUT_TXT}")


if __name__ == "__main__":
    inspect_pages()