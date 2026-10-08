from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import re

import pandas as pd


SEED = 20260731

AUDIT_ROOT = Path("data/processed/full_actual_audit")
CHUNK_DIR = AUDIT_ROOT / "chunks"
CHUNK_MAP_PATH = AUDIT_ROOT / "student_chunk_map.csv"

AWARDS_PATH = Path(
    "data/raw/institutional_awards/"
    "lsco_awards_sample_20260730.xlsx"
)

ADDITIONAL_PATH = Path(
    "data/processed/reporting/"
    "final_award_stack_classification/"
    "06_final_additional_credentials.csv"
)

RECON_ROOT = Path(
    "data/processed/reporting/"
    "institutional_award_reconciliation_20260730_173223"
)

OUTPUT_ROOT = Path("outputs/demo_degree_audits")


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def txt(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def find_column(
    columns: list[str],
    candidates: list[str],
    required: bool = True,
) -> str | None:
    lookup = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        found = lookup.get(candidate.lower())
        if found is not None:
            return found

    if required:
        raise KeyError(
            f"Missing expected column. Tried {candidates}. "
            f"Available columns: {columns}"
        )

    return None


def as_true(series: pd.Series) -> pd.Series:
    return clean(series).str.upper().isin(
        ["TRUE", "YES", "1"]
    )


def masked(student_id: str) -> str:
    return f"***{student_id[-4:]}"


def credential_stem(credential_id: str) -> str:
    value = txt(credential_id).upper()

    return re.sub(
        r"_(2021|2022|2023|2024|2025|2026)$",
        "",
        value,
    )


def locate_reconciliation_file() -> Path:
    matches: list[Path] = []

    for path in sorted(RECON_ROOT.rglob("*.csv")):
        try:
            columns = pd.read_csv(
                path,
                nrows=0,
            ).columns.tolist()
        except Exception:
            continue

        lower = {
            str(column).strip().lower()
            for column in columns
        }

        if (
            "student_id" in lower
            and "reconciliation_bucket" in lower
            and (
                "credential_id" in lower
                or "credential_id_modeled" in lower
                or "detected_credential_id" in lower
            )
        ):
            matches.append(path)

    if not matches:
        raise FileNotFoundError(
            "No reconciliation source CSV found."
        )

    preferred = [
        path
        for path in matches
        if "all_reconciled_student_lineages"
        in path.name.lower()
    ]

    return preferred[0] if preferred else matches[0]


def row_identity(
    row: pd.Series,
) -> tuple[str, str]:
    columns = row.index.tolist()

    student_col = find_column(
        columns,
        ["student_id"],
    )

    credential_col = find_column(
        columns,
        [
            "detected_credential_id",
            "credential_id_modeled",
            "credential_id",
        ],
    )

    return (
        txt(row[student_col]),
        txt(row[credential_col]),
    )


def chunk_token_for_student(
    chunk_map: pd.DataFrame,
    student_id: str,
) -> str:
    match = chunk_map[
        clean(chunk_map["student_id"]).eq(
            student_id
        )
    ]

    if len(match) != 1:
        raise RuntimeError(
            f"Expected one chunk mapping for "
            f"{masked(student_id)}; found {len(match)}."
        )

    return txt(
        match.iloc[0]["chunk_token"]
    ).zfill(5)


def eligible_audits_for_candidate(
    student_id: str,
    source_credential_id: str,
    chunk_token: str,
) -> pd.DataFrame:
    summary_path = (
        CHUNK_DIR
        / f"chunk_{chunk_token}_credential_summary.csv"
    )

    summary = pd.read_csv(
        summary_path,
        dtype=str,
        low_memory=False,
    )

    student_rows = summary[
        clean(summary["student_id"]).eq(
            student_id
        )
    ].copy()

    source_stem = credential_stem(
        source_credential_id
    )

    student_rows["_credential_stem"] = (
        clean(student_rows["credential_id"])
        .map(credential_stem)
    )

    eligible = student_rows[
        student_rows["_credential_stem"].eq(
            source_stem
        )
        & clean(student_rows["audit_status"]).eq(
            "COMPLETE"
        )
        & as_true(
            student_rows["catalog_eligible"]
        )
    ].copy()

    if eligible.empty:
        return eligible

    eligible["_catalog_start"] = pd.to_numeric(
        clean(eligible["catalog_year"])
        .str.extract(r"^(\d{4})")[0],
        errors="coerce",
    )

    eligible["_award_term_sort_numeric"] = pd.to_numeric(
        eligible["award_term_sort"],
        errors="coerce",
    )

    return (
        eligible.sort_values(
            [
                "_catalog_start",
                "_award_term_sort_numeric",
            ],
            ascending=[False, False],
            na_position="last",
        )
        .reset_index(drop=True)
    )


def select_working_candidate(
    candidates: pd.DataFrame,
    chunk_map: pd.DataFrame,
    seed: int,
    excluded_students: set[str] | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    excluded_students = excluded_students or set()

    shuffled = candidates.sample(
        frac=1,
        random_state=seed,
    )

    rejected = 0

    for _, row in shuffled.iterrows():
        student_id, source_credential_id = (
            row_identity(row)
        )

        if student_id in excluded_students:
            continue

        try:
            chunk_token = chunk_token_for_student(
                chunk_map,
                student_id,
            )

            eligible = eligible_audits_for_candidate(
                student_id,
                source_credential_id,
                chunk_token,
            )

        except Exception:
            rejected += 1
            continue

        if eligible.empty:
            rejected += 1
            continue

        print(
            f"Selected {masked(student_id)} after "
            f"rejecting {rejected:,} ineligible candidates."
        )

        return (
            row,
            eligible.iloc[0],
            chunk_token,
        )

    raise RuntimeError(
        "No candidate with a catalog-eligible COMPLETE "
        "audit could be selected."
    )


def load_case_files(
    student_id: str,
    selected_summary: pd.Series,
    chunk_token: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_path = (
        CHUNK_DIR
        / f"chunk_{chunk_token}_audit_results.csv"
    )

    history_path = (
        CHUNK_DIR
        / f"chunk_{chunk_token}_student_course_history.csv"
    )

    detail = pd.read_csv(
        detail_path,
        dtype=str,
        low_memory=False,
    )

    history = pd.read_csv(
        history_path,
        dtype=str,
        low_memory=False,
    )

    credential_id = txt(
        selected_summary["credential_id"]
    )

    catalog_year = txt(
        selected_summary["catalog_year"]
    )

    exact_detail = detail[
        clean(detail["student_id"]).eq(
            student_id
        )
        & clean(detail["credential_id"]).eq(
            credential_id
        )
        & clean(detail["catalog_year"]).eq(
            catalog_year
        )
    ].copy()

    history_student_col = find_column(
        history.columns.tolist(),
        ["student_id", "id"],
    )

    exact_history = history[
        clean(history[history_student_col]).eq(
            student_id
        )
    ].copy()

    if exact_detail.empty:
        raise RuntimeError(
            f"No requirement rows found for "
            f"{credential_id}, {catalog_year}."
        )

    return exact_detail, exact_history


def query_original_awards(
    awards: pd.DataFrame,
    student_id: str,
) -> pd.DataFrame:
    id_col = find_column(
        awards.columns.tolist(),
        ["ID", "student_id", "Student ID"],
    )

    return awards[
        clean(awards[id_col]).eq(
            student_id
        )
    ].copy()


def table_html(
    frame: pd.DataFrame,
    empty_message: str,
) -> str:
    if frame.empty:
        return (
            '<div class="empty">'
            f"{escape(empty_message)}"
            "</div>"
        )

    safe = frame.copy()

    for column in safe.columns:
        safe[column] = safe[column].map(
            lambda value: escape(txt(value))
        )

    return safe.to_html(
        index=False,
        border=0,
        escape=False,
        classes="data-table",
    )


def write_case(
    folder: Path,
    title: str,
    source_row: pd.Series,
    selected_summary: pd.Series,
    detail: pd.DataFrame,
    history: pd.DataFrame,
    awards_query: pd.DataFrame,
    chunk_token: str,
) -> Path:
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_frame = pd.DataFrame(
        [selected_summary.to_dict()]
    )

    source_frame = pd.DataFrame(
        [source_row.to_dict()]
    )

    student_id = txt(
        selected_summary["student_id"]
    )

    credential_id = txt(
        selected_summary["credential_id"]
    )

    catalog_year = txt(
        selected_summary["catalog_year"]
    )

    controls = pd.DataFrame(
        [
            {
                "Control": "Student",
                "Value": masked(student_id),
            },
            {
                "Control": "Chunk",
                "Value": chunk_token,
            },
            {
                "Control": "Credential",
                "Value": credential_id,
            },
            {
                "Control": "Catalog year selected",
                "Value": catalog_year,
            },
            {
                "Control": "Audit status",
                "Value": txt(
                    selected_summary["audit_status"]
                ),
            },
            {
                "Control": "Catalog eligible",
                "Value": txt(
                    selected_summary[
                        "catalog_eligible"
                    ]
                ),
            },
        ]
    )

    preferred_detail_columns = [
        column
        for column in [
            "requirement_id",
            "rule_type",
            "status",
            "required_options",
            "option_types",
            "matched_options",
            "matched_terms",
            "matched_grades",
            "used_course_count",
            "latest_matched_term_taken",
        ]
        if column in detail.columns
    ]

    detail_display = detail[
        preferred_detail_columns
    ].copy()

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{
    margin: 0;
    background: #f4f7f6;
    color: #1f2933;
    font-family: Arial, Helvetica, sans-serif;
}}
main {{
    max-width: 1400px;
    margin: auto;
    padding: 28px;
}}
header {{
    background: #006b54;
    color: white;
    border-radius: 8px;
    padding: 28px;
}}
.catalog {{
    display: inline-block;
    margin-top: 12px;
    padding: 8px 14px;
    border-radius: 20px;
    background: #d9efe7;
    color: #004d3d;
    font-size: 19px;
    font-weight: bold;
}}
section {{
    margin-top: 20px;
    padding: 20px;
    background: white;
    border-radius: 8px;
    overflow-x: auto;
}}
h2 {{
    color: #006b54;
    border-bottom: 2px solid #d9efe7;
    padding-bottom: 8px;
}}
.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.data-table th {{
    padding: 8px;
    text-align: left;
    background: #e3f0ec;
    color: #004d3d;
    border: 1px solid #c8d8d3;
}}
.data-table td {{
    padding: 7px 8px;
    border: 1px solid #dce4e1;
    vertical-align: top;
}}
.data-table tr:nth-child(even) {{
    background: #fafcfb;
}}
.empty {{
    padding: 14px;
    background: #fff4ce;
    border-left: 4px solid #ad7d00;
}}
</style>
</head>
<body>
<main>

<header>
<h1>{escape(title)}</h1>
<div>{escape(credential_id)}</div>
<div class="catalog">
Catalog Year Used: {escape(catalog_year)}
</div>
</header>

<section>
<h2>Catalog Selection</h2>
<p>
This result was selected only after confirming that the audit was
COMPLETE and catalog eligible. No matching was rerun.
</p>
{table_html(controls, "No controls found.")}
</section>

<section>
<h2>Credential Summary</h2>
{table_html(summary_frame, "No summary found.")}
</section>

<section>
<h2>Requirement-Level Degree Audit</h2>
{table_html(detail_display, "No requirement rows found.")}
</section>

<section>
<h2>Original Institutional Awards Query</h2>
{table_html(
    awards_query,
    "No institutional awards found."
)}
</section>

<section>
<h2>Course History</h2>
{table_html(history, "No course history found.")}
</section>

<section>
<h2>Reconciliation or Classification Record</h2>
{table_html(source_frame, "No source record found.")}
</section>

</main>
</body>
</html>
"""

    report_path = folder / "degree_audit_demo.html"

    report_path.write_text(
        html,
        encoding="utf-8",
    )

    summary_frame.to_csv(
        folder / "credential_summary.csv",
        index=False,
    )

    detail.to_csv(
        folder / "requirement_audit.csv",
        index=False,
    )

    history.to_csv(
        folder / "student_course_history.csv",
        index=False,
    )

    awards_query.to_csv(
        folder / "original_awards_query.csv",
        index=False,
    )

    source_frame.to_csv(
        folder / "classification_record.csv",
        index=False,
    )

    return report_path


def main() -> None:
    reconciliation_path = (
        locate_reconciliation_file()
    )

    reconciliation = pd.read_csv(
        reconciliation_path,
        dtype=str,
        low_memory=False,
    )

    additional = pd.read_csv(
        ADDITIONAL_PATH,
        dtype=str,
        low_memory=False,
    )

    chunk_map = pd.read_csv(
        CHUNK_MAP_PATH,
        dtype=str,
        low_memory=False,
    )

    workbook = pd.ExcelFile(
        AWARDS_PATH
    )

    award_sheet = (
        "Initial Enr Cohort Awards"
        if "Initial Enr Cohort Awards"
        in workbook.sheet_names
        else workbook.sheet_names[0]
    )

    awards = pd.read_excel(
        AWARDS_PATH,
        sheet_name=award_sheet,
        dtype=str,
    )

    bucket_col = find_column(
        reconciliation.columns.tolist(),
        ["reconciliation_bucket"],
    )

    confirmed_candidates = reconciliation[
        clean(reconciliation[bucket_col]).eq(
            "DETECTED_AND_AWARDED"
        )
    ].copy()

    confirmed_row, confirmed_summary, confirmed_chunk = (
        select_working_candidate(
            confirmed_candidates,
            chunk_map,
            SEED,
        )
    )

    confirmed_student = txt(
        confirmed_summary["student_id"]
    )

    class_col = find_column(
        additional.columns.tolist(),
        ["final_stack_classification"],
    )

    additional_candidates = additional[
        clean(additional[class_col]).eq(
            "ADDITIONAL_STACKABLE_AWARD_NOT_POSTED"
        )
    ].copy()

    additional_row, additional_summary, additional_chunk = (
        select_working_candidate(
            additional_candidates,
            chunk_map,
            SEED + 1,
            excluded_students={
                confirmed_student
            },
        )
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_dir = (
        OUTPUT_ROOT
        / timestamp
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    cases = [
        (
            "confirmed_award",
            "Confirmed Institutional Award",
            confirmed_row,
            confirmed_summary,
            confirmed_chunk,
        ),
        (
            "additional_credential",
            "Additional Credential Recommended",
            additional_row,
            additional_summary,
            additional_chunk,
        ),
    ]

    results: list[dict[str, str]] = []

    for (
        folder_name,
        title,
        source_row,
        selected_summary,
        chunk_token,
    ) in cases:
        student_id = txt(
            selected_summary["student_id"]
        )

        detail, history = load_case_files(
            student_id,
            selected_summary,
            chunk_token,
        )

        awards_query = query_original_awards(
            awards,
            student_id,
        )

        report = write_case(
            output_dir / folder_name,
            title,
            source_row,
            selected_summary,
            detail,
            history,
            awards_query,
            chunk_token,
        )

        results.append(
            {
                "title": title,
                "student": masked(student_id),
                "credential": txt(
                    selected_summary[
                        "credential_id"
                    ]
                ),
                "catalog": txt(
                    selected_summary[
                        "catalog_year"
                    ]
                ),
                "report": str(report),
            }
        )

    index_html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LSCO Degree Audit Demo</title>
<style>
body {
    max-width: 900px;
    margin: 40px auto;
    font-family: Arial, Helvetica, sans-serif;
}
h1 { color: #006b54; }
.card {
    margin: 20px 0;
    padding: 20px;
    border: 1px solid #c8d8d3;
    border-radius: 8px;
}
a {
    color: #006b54;
    font-size: 18px;
    font-weight: bold;
}
</style>
</head>
<body>
<h1>LSCO Two-Student Degree Audit Demonstration</h1>

<div class="card">
<a href="confirmed_award/degree_audit_demo.html">
Confirmed Institutional Award
</a>
</div>

<div class="card">
<a href="additional_credential/degree_audit_demo.html">
Additional Credential Recommended
</a>
</div>

</body>
</html>
"""

    index_path = output_dir / "index.html"

    index_path.write_text(
        index_html,
        encoding="utf-8",
    )

    print("=" * 100)
    print("CATALOG-ATTENTIVE DEMO COMPLETE")
    print("=" * 100)

    for result in results:
        print(result["title"])
        print(f"  Student: {result['student']}")
        print(f"  Credential: {result['credential']}")
        print(f"  Catalog year: {result['catalog']}")
        print()

    print(f"Open: {index_path.resolve()}")


if __name__ == "__main__":
    main()
