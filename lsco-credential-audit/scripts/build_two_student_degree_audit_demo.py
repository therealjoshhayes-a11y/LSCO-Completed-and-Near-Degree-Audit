from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import re

import pandas as pd


SEED = 20260731

AWARDS_PATH = Path(
    "data/raw/institutional_awards/"
    "lsco_awards_sample_20260730.xlsx"
)

RECON_PATH = Path(
    "data/processed/reporting/"
    "institutional_award_reconciliation_20260730_173223/"
    "all_reconciled_student_lineages.csv"
)

ADDITIONAL_PATH = Path(
    "data/processed/reporting/"
    "final_award_stack_classification/"
    "06_final_additional_credentials.csv"
)

MODELED_PATH = Path(
    "data/processed/full_actual_audit/"
    "president_report_corrected/"
    "collapsed_modeled_completions.csv"
)

AUDIT_ROOT = Path(
    "data/processed/full_actual_audit"
)

OUTPUT_ROOT = Path(
    "outputs/demo_degree_audits"
)


def clean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def find_column(
    columns: list[str],
    candidates: list[str],
    required: bool = True,
) -> str | None:
    lookup = {column.lower(): column for column in columns}

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    if required:
        raise KeyError(
            f"None of these columns were found: {candidates}\n"
            f"Available columns: {columns}"
        )

    return None


def masked_id(value: object) -> str:
    text = str(value)
    return f"***{text[-4:]}" if len(text) >= 4 else "***"


def scalar_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def table_html(
    frame: pd.DataFrame,
    empty_message: str,
) -> str:
    if frame.empty:
        return (
            '<div class="empty">'
            + escape(empty_message)
            + "</div>"
        )

    safe = frame.copy()

    for column in safe.columns:
        safe[column] = safe[column].map(
            lambda value: escape(scalar_text(value))
        )

    return safe.to_html(
        index=False,
        escape=False,
        classes="data-table",
        border=0,
    )


def read_header(path: Path) -> list[str]:
    try:
        return list(
            pd.read_csv(
                path,
                nrows=0,
                low_memory=False,
            ).columns
        )
    except Exception:
        return []


def numeric_tokens(path: Path) -> set[str]:
    return set(re.findall(r"\d+", path.stem))


def identify_audit_files() -> tuple[
    list[tuple[Path, list[str]]],
    list[tuple[Path, list[str]]],
]:
    csv_paths = sorted(
        AUDIT_ROOT.rglob("*.csv")
    )

    summaries: list[tuple[Path, list[str]]] = []
    details: list[tuple[Path, list[str]]] = []

    detail_markers = {
        "requirement_id",
        "requirement_group_id",
        "requirement_label",
        "requirement_name",
        "option_type",
        "rule_type",
        "course_id",
        "course_code",
        "matched_course",
        "requirement_status",
    }

    for path in csv_paths:
        columns = read_header(path)
        lower = {column.lower() for column in columns}

        has_keys = {
            "student_id",
            "credential_id",
            "catalog_year",
        }.issubset(lower)

        if not has_keys:
            continue

        if "audit_status" in lower:
            summaries.append((path, columns))

        if lower & detail_markers:
            details.append((path, columns))

    if not summaries:
        raise RuntimeError(
            "No audit summary CSV files were identified."
        )

    if not details:
        raise RuntimeError(
            "No requirement-level audit detail CSV files were identified."
        )

    return summaries, details


def locate_summary_file(
    target: dict[str, str],
    summary_files: list[tuple[Path, list[str]]],
) -> Path | None:
    for path, columns in summary_files:
        student_col = find_column(
            columns,
            ["student_id"],
        )
        credential_col = find_column(
            columns,
            ["credential_id"],
        )
        catalog_col = find_column(
            columns,
            ["catalog_year"],
        )

        try:
            check = pd.read_csv(
                path,
                dtype=str,
                usecols=[
                    student_col,
                    credential_col,
                    catalog_col,
                ],
                low_memory=False,
            )
        except Exception:
            continue

        mask = (
            clean(check[student_col]).eq(
                target["student_id"]
            )
            & clean(check[credential_col]).eq(
                target["credential_id"]
            )
            & clean(check[catalog_col]).eq(
                target["catalog_year"]
            )
        )

        if mask.any():
            return path

    return None


def detail_candidates_for_summary(
    summary_path: Path | None,
    detail_files: list[tuple[Path, list[str]]],
) -> list[tuple[Path, list[str]]]:
    if summary_path is None:
        return detail_files

    summary_tokens = numeric_tokens(summary_path)

    if not summary_tokens:
        return detail_files

    siblings = [
        item
        for item in detail_files
        if item[0].parent == summary_path.parent
        and numeric_tokens(item[0]) & summary_tokens
    ]

    return siblings or detail_files


def extract_detail_rows(
    target: dict[str, str],
    candidates: list[tuple[Path, list[str]]],
) -> tuple[pd.DataFrame, Path]:
    for path, columns in candidates:
        student_col = find_column(
            columns,
            ["student_id"],
        )
        credential_col = find_column(
            columns,
            ["credential_id"],
        )
        catalog_col = find_column(
            columns,
            ["catalog_year"],
        )

        collected: list[pd.DataFrame] = []

        try:
            reader = pd.read_csv(
                path,
                dtype=str,
                low_memory=False,
                chunksize=100_000,
            )

            for chunk in reader:
                mask = (
                    clean(chunk[student_col]).eq(
                        target["student_id"]
                    )
                    & clean(chunk[credential_col]).eq(
                        target["credential_id"]
                    )
                    & clean(chunk[catalog_col]).eq(
                        target["catalog_year"]
                    )
                )

                if mask.any():
                    collected.append(
                        chunk.loc[mask].copy()
                    )

        except Exception:
            continue

        if collected:
            detail = pd.concat(
                collected,
                ignore_index=True,
            )

            return detail, path

    raise RuntimeError(
        "No requirement-level rows were found for:\n"
        f"student={masked_id(target['student_id'])}\n"
        f"credential={target['credential_id']}\n"
        f"catalog_year={target['catalog_year']}"
    )


def choose_confirmed(
    reconciliation: pd.DataFrame,
) -> pd.Series:
    candidates = reconciliation[
        reconciliation[
            "reconciliation_bucket"
        ].eq("DETECTED_AND_AWARDED")
    ].copy()

    key_col = find_column(
        list(candidates.columns),
        ["reconciliation_key"],
    )

    candidates = candidates[
        ~clean(candidates[key_col]).str.startswith(
            "IA_",
            na=False,
        )
    ].copy()

    date_col = find_column(
        list(candidates.columns),
        [
            "last_institutional_grad_date",
            "first_institutional_grad_date",
        ],
        required=False,
    )

    if date_col:
        candidates["_grad_date"] = pd.to_datetime(
            candidates[date_col],
            errors="coerce",
        )

        recent = candidates[
            candidates["_grad_date"].dt.year.ge(2024)
        ]

        if not recent.empty:
            candidates = recent

    if candidates.empty:
        raise RuntimeError(
            "No detected-and-awarded candidates were available."
        )

    return candidates.sample(
        n=1,
        random_state=SEED,
    ).iloc[0]


def choose_additional(
    additional: pd.DataFrame,
) -> pd.Series:
    candidates = additional[
        additional[
            "final_stack_classification"
        ].eq(
            "ADDITIONAL_STACKABLE_AWARD_NOT_POSTED"
        )
    ].copy()

    if candidates.empty:
        candidates = additional.copy()

    year_col = find_column(
        list(candidates.columns),
        ["detected_completion_academic_year"],
        required=False,
    )

    if year_col:
        recent = candidates[
            clean(candidates[year_col]).isin(
                ["2024-2025", "2025-2026"]
            )
        ]

        if not recent.empty:
            candidates = recent

    return candidates.sample(
        n=1,
        random_state=SEED + 1,
    ).iloc[0]


def modeled_key_from_row(
    row: pd.Series,
) -> dict[str, str]:
    columns = list(row.index)

    student_col = find_column(
        columns,
        ["student_id"],
    )

    credential_col = find_column(
        columns,
        [
            "credential_id",
            "credential_id_modeled",
            "detected_credential_id",
        ],
    )

    catalog_col = find_column(
        columns,
        [
            "catalog_year",
            "catalog_year_modeled",
            "detected_catalog_year",
        ],
    )

    lineage_col = find_column(
        columns,
        [
            "reconciliation_key",
            "canonical_lineage_modeled",
            "canonical_lineage",
            "detected_lineage",
        ],
    )

    return {
        "student_id": scalar_text(row[student_col]),
        "credential_id": scalar_text(row[credential_col]),
        "catalog_year": scalar_text(row[catalog_col]),
        "canonical_lineage": scalar_text(row[lineage_col]),
    }


def institutional_awards_for_student(
    awards: pd.DataFrame,
    student_id: str,
) -> pd.DataFrame:
    id_col = find_column(
        list(awards.columns),
        ["ID"],
    )

    return awards[
        clean(awards[id_col]).eq(student_id)
    ].copy()


def modeled_row_for_key(
    modeled: pd.DataFrame,
    target: dict[str, str],
) -> pd.DataFrame:
    return modeled[
        clean(modeled["student_id"]).eq(
            target["student_id"]
        )
        & clean(modeled["credential_id"]).eq(
            target["credential_id"]
        )
        & clean(modeled["catalog_year"]).eq(
            target["catalog_year"]
        )
    ].copy()


def write_csvs(
    folder: Path,
    awards: pd.DataFrame,
    modeled: pd.DataFrame,
    detail: pd.DataFrame,
) -> None:
    awards.to_csv(
        folder / "institutional_awards_query.csv",
        index=False,
    )

    modeled.to_csv(
        folder / "modeled_completion_record.csv",
        index=False,
    )

    detail.to_csv(
        folder / "degree_audit_detail.csv",
        index=False,
    )


def build_packet(
    label: str,
    target: dict[str, str],
    source_row: pd.Series,
    awards: pd.DataFrame,
    modeled: pd.DataFrame,
    detail: pd.DataFrame,
    detail_path: Path,
    output_folder: Path,
) -> Path:
    packet_folder = output_folder / label
    packet_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    awards_query = institutional_awards_for_student(
        awards,
        target["student_id"],
    )

    modeled_query = modeled_row_for_key(
        modeled,
        target,
    )

    write_csvs(
        packet_folder,
        awards_query,
        modeled_query,
        detail,
    )

    source_summary = pd.DataFrame(
        [
            {
                "Field": "Demo type",
                "Value": label.replace("_", " ").title(),
            },
            {
                "Field": "Student ID",
                "Value": target["student_id"],
            },
            {
                "Field": "Credential ID",
                "Value": target["credential_id"],
            },
            {
                "Field": "Canonical lineage",
                "Value": target["canonical_lineage"],
            },
            {
                "Field": "Catalog year used",
                "Value": target["catalog_year"],
            },
            {
                "Field": "Institutional awards found",
                "Value": len(awards_query),
            },
            {
                "Field": "Audit detail rows",
                "Value": len(detail),
            },
            {
                "Field": "Requirement-detail source",
                "Value": str(detail_path),
            },
        ]
    )

    source_row_frame = pd.DataFrame(
        [
            {
                column: source_row[column]
                for column in source_row.index
            }
        ]
    )

    title = (
        "Confirmed Award Demo"
        if label == "confirmed_award"
        else "Additional Credential Demo"
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 32px;
    color: #1f2933;
    background: #f7f9f8;
}}
header {{
    background: #006b54;
    color: white;
    padding: 24px 28px;
    border-radius: 8px;
}}
header h1 {{
    margin: 0 0 8px 0;
}}
.catalog {{
    display: inline-block;
    margin-top: 8px;
    padding: 7px 12px;
    background: #d9efe7;
    color: #004d3d;
    border-radius: 18px;
    font-weight: bold;
}}
section {{
    background: white;
    margin-top: 22px;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
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
    background: #e6f2ee;
    color: #004d3d;
    text-align: left;
    padding: 8px;
    border: 1px solid #c9d9d3;
}}
.data-table td {{
    padding: 7px 8px;
    border: 1px solid #dce3e0;
    vertical-align: top;
}}
.data-table tr:nth-child(even) {{
    background: #fafcfb;
}}
.empty {{
    padding: 14px;
    background: #fff4ce;
    border-left: 4px solid #b38600;
}}
.notice {{
    background: #eef6ff;
    border-left: 4px solid #2563eb;
    padding: 12px;
}}
footer {{
    margin-top: 24px;
    color: #667;
    font-size: 12px;
}}
</style>
</head>
<body>
<header>
<h1>{escape(title)}</h1>
<div>
Credential: <strong>{escape(target["canonical_lineage"])}</strong>
</div>
<div class="catalog">
Catalog year: {escape(target["catalog_year"])}
</div>
</header>

<section>
<h2>Demo identity and source control</h2>
{table_html(source_summary, "No source summary available.")}
</section>

<section>
<h2>Reconciliation or opportunity record</h2>
{table_html(source_row_frame, "No reconciliation record available.")}
</section>

<section>
<h2>Modeled completion record</h2>
<div class="notice">
The modeled credential and every requirement row below are restricted
to student ID, credential ID, and catalog year shown above.
</div>
{table_html(modeled_query, "No modeled completion row was found.")}
</section>

<section>
<h2>Degree-audit requirement detail</h2>
{table_html(detail, "No requirement-level audit rows were found.")}
</section>

<section>
<h2>Original institutional-awards query</h2>
{table_html(
    awards_query,
    "No institutional award was found for this student in the original award list."
)}
</section>

<footer>
Generated locally on {escape(datetime.now().isoformat(timespec="seconds"))}.
FERPA-restricted operational demonstration.
</footer>
</body>
</html>
"""

    report_path = packet_folder / "degree_audit_demo.html"

    report_path.write_text(
        html,
        encoding="utf-8",
    )

    return report_path


def main() -> None:
    for path in (
        AWARDS_PATH,
        RECON_PATH,
        ADDITIONAL_PATH,
        MODELED_PATH,
        AUDIT_ROOT,
    ):
        if not path.exists():
            raise FileNotFoundError(
                f"Required input not found: {path}"
            )

    run_stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_folder = OUTPUT_ROOT / run_stamp
    output_folder.mkdir(
        parents=True,
        exist_ok=False,
    )

    awards = pd.read_excel(
        AWARDS_PATH,
        sheet_name="Initial Enr Cohort Awards",
        dtype=str,
    )

    reconciliation = pd.read_csv(
        RECON_PATH,
        dtype=str,
        low_memory=False,
    )

    additional = pd.read_csv(
        ADDITIONAL_PATH,
        dtype=str,
        low_memory=False,
    )

    modeled = pd.read_csv(
        MODELED_PATH,
        dtype=str,
        low_memory=False,
    )

    confirmed_row = choose_confirmed(
        reconciliation
    )

    additional_row = choose_additional(
        additional
    )

    confirmed_target = modeled_key_from_row(
        confirmed_row
    )

    additional_target = modeled_key_from_row(
        additional_row
    )

    if confirmed_target["student_id"] == additional_target["student_id"]:
        alternatives = additional[
            clean(additional["student_id"]).ne(
                confirmed_target["student_id"]
            )
        ]

        if alternatives.empty:
            raise RuntimeError(
                "Could not select two different students."
            )

        additional_row = alternatives.sample(
            n=1,
            random_state=SEED + 2,
        ).iloc[0]

        additional_target = modeled_key_from_row(
            additional_row
        )

    summary_files, detail_files = identify_audit_files()

    reports: list[Path] = []

    for label, target, row in [
        (
            "confirmed_award",
            confirmed_target,
            confirmed_row,
        ),
        (
            "additional_credential",
            additional_target,
            additional_row,
        ),
    ]:
        summary_path = locate_summary_file(
            target,
            summary_files,
        )

        candidate_details = (
            detail_candidates_for_summary(
                summary_path,
                detail_files,
            )
        )

        detail, detail_path = extract_detail_rows(
            target,
            candidate_details,
        )

        # Mechanical catalog-year safeguard.
        detail_catalog_col = find_column(
            list(detail.columns),
            ["catalog_year"],
        )

        observed_catalogs = sorted(
            clean(
                detail[detail_catalog_col]
            ).dropna().unique()
        )

        if observed_catalogs != [
            target["catalog_year"]
        ]:
            raise ValueError(
                "Catalog-year contamination detected for "
                f"{label}: expected {target['catalog_year']}, "
                f"observed {observed_catalogs}"
            )

        report_path = build_packet(
            label=label,
            target=target,
            source_row=row,
            awards=awards,
            modeled=modeled,
            detail=detail,
            detail_path=detail_path,
            output_folder=output_folder,
        )

        reports.append(report_path)

    index_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LSCO Degree Audit Demonstration</title>
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    max-width: 900px;
    margin: 40px auto;
    color: #1f2933;
}}
h1 {{ color: #006b54; }}
.card {{
    border: 1px solid #c9d9d3;
    border-radius: 8px;
    padding: 18px;
    margin: 18px 0;
}}
a {{
    color: #006b54;
    font-weight: bold;
}}
</style>
</head>
<body>
<h1>LSCO Degree Audit Demonstration</h1>

<div class="card">
<h2>Confirmed award</h2>
<p>
A recent student whose credential was both detected by the audit engine
and found in the original LSCO institutional-awards file.
</p>
<a href="confirmed_award/degree_audit_demo.html">
Open confirmed-award audit
</a>
</div>

<div class="card">
<h2>Additional credential</h2>
<p>
A student with an institutional award whose separately completed
credential remains additional under the governed stack rules.
</p>
<a href="additional_credential/degree_audit_demo.html">
Open additional-credential audit
</a>
</div>

<p>
Both reports enforce the exact modeled catalog year and include the
original institutional-awards query.
</p>
</body>
</html>
"""

    index_path = output_folder / "index.html"

    index_path.write_text(
        index_html,
        encoding="utf-8",
    )

    print("=" * 96)
    print("TWO-STUDENT DEGREE-AUDIT DEMO COMPLETE")
    print("=" * 96)

    print(
        "Confirmed-award student: "
        f"{masked_id(confirmed_target['student_id'])}"
    )
    print(
        "Confirmed credential: "
        f"{confirmed_target['credential_id']}"
    )
    print(
        "Confirmed catalog year: "
        f"{confirmed_target['catalog_year']}"
    )

    print()

    print(
        "Additional-credential student: "
        f"{masked_id(additional_target['student_id'])}"
    )
    print(
        "Additional credential: "
        f"{additional_target['credential_id']}"
    )
    print(
        "Additional catalog year: "
        f"{additional_target['catalog_year']}"
    )

    print()
    print(f"Open this file: {index_path.resolve()}")


if __name__ == "__main__":
    main()
