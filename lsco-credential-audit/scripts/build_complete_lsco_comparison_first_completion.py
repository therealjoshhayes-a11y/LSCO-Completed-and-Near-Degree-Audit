from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re
import sys

import pandas as pd

# -----------------------------------------------------------------------------
# Local paths. Run from the repository root (for example, PS R:\>).
# -----------------------------------------------------------------------------
REPORTING_ROOT = Path("data/processed/reporting")
PUBLISHED_REFERENCE_DIR = Path("data/raw/reference")
OUTPUT_DIR = REPORTING_ROOT / f"complete_lsco_comparison_{datetime.now():%Y%m%d_%H%M%S}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_WORKBOOK = OUTPUT_DIR / "LSCO_Complete_Detected_vs_Published_Report.xlsx"
PUBLISHED_CSV = PUBLISHED_REFERENCE_DIR / "lsco_published_credential_counts.csv"
MAPPING_CSV = OUTPUT_DIR / "published_to_detected_lineage_mapping.csv"

# -----------------------------------------------------------------------------
# Published LSCO award counts transcribed from:
# "Degrees and Certificates Awarded by Program — Academic Year 2019 through
# Academic Year 2024". Blank cells in the source are represented as zero.
# -----------------------------------------------------------------------------
YEARS = ["2019-2020", "2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025"]

PUBLISHED_ROWS = [
    ("Business", "Business - AS", [25, 27, 41, 31, 30, 23]),
    ("Business", "Business Management - AAS", [9, 12, 5, 6, 11, 15]),
    ("Business", "Business Management Accounting - CERT", [9, 10, 5, 0, 9, 14]),
    ("Business", "Business Operations - CERT", [0, 0, 0, 2, 22, 23]),
    ("Business", "Entrepreneurship - CERT", [6, 9, 5, 1, 6, 4]),
    ("Business", "Customer Service - IA", [7, 6, 2, 0, 0, 0]),
    ("Communication", "Communication - AA", [3, 0, 1, 2, 2, 3]),
    ("Computer Information Systems", "Computer Information Systems - AS", [0, 0, 1, 0, 1, 2]),
    ("Computer Science", "Computer Science - AS", [4, 4, 1, 4, 5, 7]),
    ("Construction Management", "Business Construction Management - AAS", [0, 0, 0, 0, 1, 4]),
    ("Construction Management", "Construction Management - CERT", [0, 0, 0, 3, 5, 9]),
    ("Cosmetology", "Cosmetology Operator - AAS", [0, 0, 0, 0, 0, 2]),
    ("Cosmetology", "Cosmetology Operator - CERT", [0, 0, 0, 0, 33, 93]),
    ("Court Reporting", "Court Reporting - AAS", [0, 0, 0, 6, 9, 8]),
    ("Court Reporting", "Court Reporting - CERT", [0, 0, 0, 10, 14, 10]),
    ("Court Reporting", "Court Reporting Machine Shorthand Scopist - CERT", [0, 0, 0, 30, 14, 10]),
    ("Criminal Justice", "Criminal Justice - AS", [10, 11, 11, 10, 7, 8]),
    ("Criminal Justice", "Criminal Justice - CERT", [4, 5, 0, 1, 1, 0]),
    ("Criminal Justice", "Criminal Justice Law Enforcement - CERT", [4, 5, 3, 2, 10, 32]),
    ("Dental Assisting", "Dental Assisting - AAS", [0, 0, 0, 2, 3, 10]),
    ("Dental Assisting", "Dental Assisting - CERT", [20, 18, 23, 18, 22, 19]),
    ("Electromechanical Technology", "Electromechanical Tech - AAS", [0, 0, 0, 0, 1, 7]),
    ("Electromechanical Technology", "Electromechanical Tech - CERT", [0, 0, 0, 0, 9, 9]),
    ("Electromechanical Technology", "Electromechanical Tech Basic - CERT", [0, 0, 0, 0, 3, 0]),
    ("Emergency Medical Services", "EMT Basic - CERT", [63, 21, 4, 4, 11, 7]),
    ("Emergency Medical Services", "EMT Intermediate - CERT", [13, 0, 3, 0, 1, 0]),
    ("Industrial Systems", "Industrial Technology - AAS", [6, 3, 4, 0, 1, 0]),
    ("Industrial Systems", "Instrumentation - AAS", [9, 14, 14, 27, 26, 20]),
    ("Industrial Systems", "Instrumentation - CERT", [11, 16, 14, 25, 39, 30]),
    ("Industrial Systems", "Instrumentation Basic - CERT", [0, 0, 0, 0, 2, 0]),
    ("Industrial Systems", "Process Operating Technology - AAS", [47, 32, 32, 34, 30, 48]),
    ("Industrial Systems", "Process Technology - CERT", [49, 44, 31, 48, 63, 78]),
    ("Industrial Systems", "Safety, Health, and Environment - AAS", [0, 0, 0, 1, 6, 6]),
    ("Industrial Systems", "Safety, Health, and Environment - CERT", [7, 4, 4, 3, 9, 5]),
    ("Information Technology", "CISCO Network/Cybersecurity Tech - CERT", [3, 6, 7, 4, 7, 6]),
    ("Information Technology", "Cybersecurity Specialist - CERT", [4, 2, 6, 6, 7, 5]),
    ("Information Technology", "Info Tech Support Assistant Network Specialist - CERT", [4, 3, 7, 6, 4, 2]),
    ("Information Technology", "Info Tech Support Assistant Software Development - CERT", [3, 2, 5, 7, 3, 4]),
    ("Information Technology", "Info Tech Support Specialist - AAS", [4, 2, 6, 6, 2, 3]),
    ("Liberal Arts", "General Studies - CERT", [102, 115, 142, 181, 176, 194]),
    ("Liberal Arts", "Liberal Arts - AA", [35, 59, 66, 60, 44, 100]),
    ("Logistics Management", "Logistics Management - CERT", [0, 0, 0, 0, 2, 3]),
    ("Logistics Management", "Logistics Management (Maritime) - AAS", [0, 0, 0, 0, 2, 2]),
    ("Maritime", "Ordinary Seaman I - CERT", [2, 10, 7, 2, 15, 11]),
    ("Maritime", "Ordinary Seaman II - CERT", [0, 0, 0, 0, 2, 3]),
    ("Massage Therapy", "Massage Therapy - CERT", [0, 0, 0, 0, 6, 2]),
    ("Massage Therapy", "Massage Therapy Management - AAS", [0, 0, 0, 0, 1, 0]),
    ("Nursing", "Advanced Nurse Aide - IA", [4, 8, 9, 0, 0, 0]),
    ("Nursing", "Medical Assistant - CERT", [0, 0, 4, 11, 13, 13]),
    ("Nursing", "Registered Nursing - AAS", [45, 34, 32, 57, 64, 51]),
    ("Nursing", "Vocational Nursing - CERT", [102, 97, 83, 81, 72, 53]),
    ("Pharmacy Technology", "Pharmacy Technology - CERT", [3, 6, 4, 12, 6, 8]),
    ("Pharmacy Technology", "Pharmacy Technology Basic - CERT", [8, 10, 13, 8, 4, 10]),
    ("Pharmacy Technology", "Pharmacy Technology Business Management - AAS", [0, 0, 0, 2, 1, 1]),
    ("Real Estate", "Business Real Estate Management - AAS", [0, 0, 0, 0, 2, 1]),
    ("Real Estate", "Real Estate Management - CERT", [0, 0, 0, 2, 14, 6]),
    ("Science", "Environmental Science - AS", [0, 0, 0, 0, 1, 3]),
    ("Science", "Natural Science - AS", [2, 2, 1, 4, 3, 2]),
    ("Science", "Pre-Professional Health Science - AS", [0, 1, 5, 3, 6, 6]),
    ("Sociology", "Sociology - AA", [4, 2, 10, 17, 10, 10]),
    ("Teaching", "Teaching Grades EC-6, 4-8, Special Ed. EC-12 - AAT 1", [25, 19, 11, 15, 8, 6]),
    ("Teaching", "Teaching Grades 8-12, EC-12 (Excluding Special Ed.) - AAT 2", [2, 5, 6, 7, 17, 34]),
    ("Welding", "Layout & Fabrication Welding - CERT", [0, 0, 0, 0, 0, 2]),
    ("Welding", "Production Welder - CERT", [0, 0, 0, 0, 7, 60]),
    ("Welding", "Welding Technology - AAS", [0, 0, 0, 0, 1, 0]),
    ("Welding", "Welding Technology - CERT", [7, 8, 7, 7, 4, 0]),
]

# Common naming differences between the public report and catalog/credential IDs.
ALIASES = {
    "business as": ["business as", "business associate of science"],
    "business management accounting cert": ["accounting cert", "business accounting cert", "business management accounting"],
    "business operations cert": ["business operations"],
    "customer service ia": ["customer service", "institutional award customer service"],
    "computer information systems as": ["computer information systems as", "cis as"],
    "business construction management aas": ["construction management aas", "business construction management"],
    "court reporting machine shorthand scopist cert": ["machine shorthand scopist", "scopist"],
    "electromechanical tech aas": ["electromechanical technology aas", "electro mechanical aas"],
    "electromechanical tech cert": ["electromechanical technology cert", "electro mechanical cert"],
    "electromechanical tech basic cert": ["electromechanical basic cert", "electro mechanical basic"],
    "emt basic cert": ["emergency medical technician basic", "emt basic"],
    "emt intermediate cert": ["emergency medical technician intermediate", "emt intermediate"],
    "process operating technology aas": ["process operating technology aas", "process technology aas"],
    "process technology cert": ["process technology cert", "process operating technology cert"],
    "cisco network cybersecurity tech cert": ["cisco network cybersecurity", "networking cybersecurity", "network cyber"],
    "info tech support assistant network specialist cert": ["network specialist cert", "information technology network specialist"],
    "info tech support assistant software development cert": ["software development cert", "information technology software development"],
    "info tech support specialist aas": ["information technology support specialist aas", "it support specialist aas"],
    "general studies cert": ["general studies cert"],
    "logistics management maritime aas": ["logistics management maritime aas", "maritime logistics aas"],
    "ordinary seaman i cert": ["ordinary seaman i", "ordinary seaman 1"],
    "ordinary seaman ii cert": ["ordinary seaman ii", "ordinary seaman 2"],
    "advanced nurse aide ia": ["advanced nurse aide", "nurse aide ia"],
    "registered nursing aas": ["registered nursing aas", "associate degree nursing"],
    "vocational nursing cert": ["vocational nursing cert", "lvn cert"],
    "business real estate management aas": ["real estate management aas", "business real estate"],
    "pre professional health science as": ["pre professional health science", "preprofessional health science"],
    "teaching grades ec 6 4 8 special ed ec 12 aat 1": ["teaching grades ec 6 4 8 special education", "aat 1"],
    "teaching grades 8 12 ec 12 excluding special ed aat 2": ["teaching grades 8 12 ec 12", "aat 2"],
    "layout fabrication welding cert": ["layout fabrication welding", "welding layout fabrication"],
    "production welder cert": ["production welder"],
}

TYPE_TOKENS = ["AAS", "AAT", "CERT", "IA", "AA", "AS"]
STOP_WORDS = {
    "THE", "AND", "OF", "IN", "FOR", "TECH", "TECHNOLOGY", "PROGRAM",
    "ASSOCIATE", "DEGREE", "CERTIFICATE", "COMPLETION", "SPECIALIST",
}


def normalize(value: object) -> str:
    text = str(value or "").upper().replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def award_type(value: object) -> str:
    tokens = normalize(value).split()
    for token in TYPE_TOKENS:
        if token in tokens:
            return token
    return ""


def meaningful_tokens(value: object) -> set[str]:
    return {
        token for token in normalize(value).split()
        if token not in STOP_WORDS and token not in TYPE_TOKENS and len(token) > 1
    }


def similarity(published_award: str, candidate: str) -> float:
    pub_norm = normalize(published_award)
    cand_norm = normalize(candidate)
    pub_type = award_type(pub_norm)
    cand_type = award_type(cand_norm)

    # Strongly discourage pairing different credential types.
    type_factor = 1.0
    if pub_type and cand_type and pub_type != cand_type:
        type_factor = 0.20
    elif pub_type and pub_type in cand_norm.split():
        type_factor = 1.12

    pub_tokens = meaningful_tokens(pub_norm)
    cand_tokens = meaningful_tokens(cand_norm)
    union = pub_tokens | cand_tokens
    overlap = len(pub_tokens & cand_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, pub_norm, cand_norm).ratio()

    alias_key = normalize(published_award).lower()
    alias_bonus = 0.0
    for phrase in ALIASES.get(alias_key, []):
        phrase_tokens = meaningful_tokens(phrase)
        if phrase_tokens and phrase_tokens.issubset(cand_tokens):
            alias_bonus = max(alias_bonus, 0.35)

    return min(1.0, ((0.58 * overlap) + (0.42 * sequence) + alias_bonus) * type_factor)


def find_latest_local_inputs() -> tuple[Path, Path]:
    selection_candidates = list(
        REPORTING_ROOT.glob(
            "credential_completion_comparison_*/catalog_selection_audit.csv"
        )
    )
    student_candidates = list(
        REPORTING_ROOT.glob(
            "credential_completion_comparison_*/detected_student_completions.csv"
        )
    )

    if not selection_candidates:
        raise SystemExit(
            "Could not find catalog_selection_audit.csv under "
            "data/processed/reporting."
        )

    selection_path = max(
        selection_candidates,
        key=lambda p: p.stat().st_mtime,
    )

    same_folder_student = (
        selection_path.parent
        / "detected_student_completions.csv"
    )

    if same_folder_student.exists():
        student_path = same_folder_student
    elif student_candidates:
        student_path = max(
            student_candidates,
            key=lambda p: p.stat().st_mtime,
        )
    else:
        raise SystemExit(
            "Could not find detected_student_completions.csv under "
            "data/processed/reporting."
        )

    return selection_path, student_path


FALL_SUFFIXES = {90, 91, 92, 95}
SPRING_SUFFIXES = {10, 13, 15}
SUMMER_SUFFIXES = {60, 64}


def academic_year_from_term(value: object) -> str:
    number = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(number):
        return ""

    term = int(number)
    year = term // 100
    suffix = term % 100

    if suffix in FALL_SUFFIXES:
        return f"{year}-{year + 1}"

    if suffix in SPRING_SUFFIXES or suffix in SUMMER_SUFFIXES:
        return f"{year - 1}-{year}"

    return ""


def derive_major_from_lineage(value: object) -> str:
    text = str(value or "").replace("_", " ").title()
    replacements = {
        "Aas": "AAS",
        "Aat": "AAT",
        "Aa": "AA",
        "As": "AS",
        "Cert": "CERT",
        "Ia": "IA",
        "Emt": "EMT",
        "Ems": "EMS",
        "Hvac": "HVAC",
        "It": "IT",
        "Cis": "CIS",
        "Cnc": "CNC",
        "Lvn": "LVN",
        "Rn": "RN",
    }
    return " ".join(
        replacements.get(word, word)
        for word in text.split()
    )


def build_published_long() -> pd.DataFrame:
    records = []
    for program, award, counts in PUBLISHED_ROWS:
        if len(counts) != len(YEARS):
            raise ValueError(f"Published row has wrong number of years: {award}")
        for year, count in zip(YEARS, counts):
            records.append({
                "program": program,
                "published_award": award,
                "completion_year": year,
                "lsco_published_count": int(count),
            })
    return pd.DataFrame(records)


def add_formatting(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    ws = writer.sheets[sheet_name]
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
    ws.set_row(0, 24)
    header = writer.book.add_format({
        "bold": True,
        "font_color": "#FFFFFF",
        "bg_color": "#006747",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    for col_idx, col in enumerate(df.columns):
        ws.write(0, col_idx, col, header)
        values = ["" if pd.isna(v) else str(v) for v in df[col].head(5000)]
        width = min(42, max(len(str(col)) + 2, max([len(v) for v in values] + [0]) + 2))
        ws.set_column(col_idx, col_idx, width)


def main() -> None:
    selection_path, prior_student_path = find_latest_local_inputs()

    print(f"Selection audit: {selection_path}")
    print(f"Prior student detail (major labels only): {prior_student_path}")

    candidates = pd.read_csv(
        selection_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    prior_students = pd.read_csv(
        prior_student_path,
        dtype=str,
        low_memory=False,
    ).fillna("")

    required_candidate_columns = {
        "student_id",
        "credential_lineage",
        "credential_id",
        "catalog_year",
        "award_term_sort",
        "award_term_taken",
    }

    missing = (
        required_candidate_columns
        - set(candidates.columns)
    )

    if missing:
        raise SystemExit(
            "Selection-audit file is missing: "
            + ", ".join(sorted(missing))
        )

    candidates["award_term_numeric"] = pd.to_numeric(
        candidates["award_term_sort"],
        errors="coerce",
    )

    candidates = candidates[
        candidates["award_term_numeric"].notna()
    ].copy()

    if candidates.empty:
        raise SystemExit(
            "No valid completion terms were found in the selection audit."
        )

    if "catalog_rank" not in candidates.columns:
        candidates["catalog_rank"] = pd.to_numeric(
            candidates["catalog_year"]
            .astype(str)
            .str.extract(r"^(20\d{2})", expand=False),
            errors="coerce",
        ).fillna(-1)
    else:
        candidates["catalog_rank"] = pd.to_numeric(
            candidates["catalog_rank"],
            errors="coerce",
        ).fillna(-1)

    # Allocation rule for comparison with published awards:
    # 1. earliest modeled completion term within student + credential lineage;
    # 2. among rows tied at that earliest term, use the latest eligible catalog.
    candidates = candidates.sort_values(
        [
            "student_id",
            "credential_lineage",
            "award_term_numeric",
            "catalog_rank",
            "credential_id",
        ],
        ascending=[
            True,
            True,
            True,
            False,
            False,
        ],
        kind="mergesort",
    )

    first_completion = candidates.drop_duplicates(
        subset=[
            "student_id",
            "credential_lineage",
        ],
        keep="first",
    ).copy()

    first_completion["completion_year"] = (
        first_completion["award_term_numeric"]
        .map(academic_year_from_term)
    )

    if first_completion["completion_year"].eq("").any():
        bad = first_completion[
            first_completion["completion_year"].eq("")
        ][
            [
                "student_id",
                "credential_lineage",
                "award_term_sort",
            ]
        ]

        review_path = (
            OUTPUT_DIR
            / "unmapped_completion_terms.csv"
        )
        bad.to_csv(review_path, index=False)

        raise SystemExit(
            "Some completion terms could not be mapped to academic years. "
            f"Review: {review_path}"
        )

    major_map = pd.DataFrame(
        columns=[
            "credential_lineage",
            "major",
        ]
    )

    if {
        "credential_lineage",
        "major",
    }.issubset(prior_students.columns):
        major_map = (
            prior_students[
                [
                    "credential_lineage",
                    "major",
                ]
            ]
            .drop_duplicates(
                subset=[
                    "credential_lineage",
                ]
            )
        )

    students = first_completion.merge(
        major_map,
        on="credential_lineage",
        how="left",
        validate="many_to_one",
    )

    students["major"] = students["major"].where(
        students["major"]
        .astype(str)
        .str.strip()
        .ne(""),
        students["credential_lineage"]
        .map(derive_major_from_lineage),
    )

    students = students.rename(
        columns={
            "credential_id":
                "selected_credential_id",
            "catalog_year":
                "selected_catalog_year",
            "award_term_sort":
                "completion_term_sort",
            "award_term_taken":
                "completion_term",
        }
    )

    students["allocation_rule"] = (
        "Earliest modeled completion term within student and credential lineage; "
        "latest eligible catalog used only to label ties at that term"
    )

    keep_columns = [
        "student_id",
        "credential_lineage",
        "major",
        "selected_credential_id",
        "selected_catalog_year",
        "completion_term_sort",
        "completion_term",
        "completion_year",
        "allocation_rule",
    ]

    extra_columns = [
        column
        for column in [
            "catalog_eligibility_reason",
            "eligibility_reason",
        ]
        if column in students.columns
    ]

    students = students[
        keep_columns + extra_columns
    ].copy()

    students = students.sort_values(
        [
            "completion_year",
            "major",
            "student_id",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    detected = (
        students.groupby(
            [
                "completion_year",
                "credential_lineage",
                "major",
            ],
            dropna=False,
        )
        .agg(
            audit_detected_count=(
                "student_id",
                "nunique",
            )
        )
        .reset_index()
    )

    detected["audit_detected_count"] = pd.to_numeric(
        detected["audit_detected_count"],
        errors="coerce",
    ).fillna(0).astype(int)

    unique_candidates = (
        detected[
            [
                "credential_lineage",
                "major",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "major",
                "credential_lineage",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    unique_candidates["candidate_text"] = (
        unique_candidates["major"].astype(str)
        + " "
        + unique_candidates["credential_lineage"].astype(str)
    )

    in_window_students = students[
        students["completion_year"].isin(YEARS)
    ].copy()

    out_of_window_students = students[
        ~students["completion_year"].isin(YEARS)
    ].copy()

    first_completion_csv = (
        OUTPUT_DIR
        / "first_completion_student_detail.csv"
    )
    in_window_csv = (
        OUTPUT_DIR
        / "first_completion_student_detail_in_published_window.csv"
    )
    out_window_csv = (
        OUTPUT_DIR
        / "first_completion_student_detail_outside_published_window.csv"
    )
    detected_csv = (
        OUTPUT_DIR
        / "detected_counts_first_completion.csv"
    )

    students.to_csv(
        first_completion_csv,
        index=False,
    )
    in_window_students.to_csv(
        in_window_csv,
        index=False,
    )
    out_of_window_students.to_csv(
        out_window_csv,
        index=False,
    )
    detected.to_csv(
        detected_csv,
        index=False,
    )

    published = build_published_long()
    unique_awards = published[["program", "published_award"]].drop_duplicates().reset_index(drop=True)

    mapping_records = []
    for row in unique_awards.itertuples(index=False):
        scored = []
        for candidate in unique_candidates.itertuples(index=False):
            score = similarity(row.published_award, candidate.candidate_text)
            scored.append((score, candidate.credential_lineage, candidate.major))
        scored.sort(reverse=True, key=lambda x: x[0])
        best_score, best_lineage, best_major = scored[0] if scored else (0.0, "", "")
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score

        # Conservative threshold: low-confidence public credentials stay explicit zero-detected,
        # rather than being forced onto an unrelated lineage.
        if best_score < 0.43:
            status = "NO DETECTED LINEAGE"
            selected_lineage = ""
            selected_major = ""
        elif best_score < 0.60 or margin < 0.05:
            status = "AUTO-MAPPED — REVIEW"
            selected_lineage = best_lineage
            selected_major = best_major
        else:
            status = "AUTO-MAPPED"
            selected_lineage = best_lineage
            selected_major = best_major

        mapping_records.append({
            "program": row.program,
            "published_award": row.published_award,
            "credential_lineage": selected_lineage,
            "detected_major": selected_major,
            "mapping_score": round(best_score, 4),
            "score_margin": round(margin, 4),
            "mapping_status": status,
        })

    mapping = pd.DataFrame(mapping_records)
    mapping.to_csv(MAPPING_CSV, index=False)

    published_mapped = published.merge(mapping, on=["program", "published_award"], how="left", validate="many_to_one")

    detected_for_merge = detected.groupby(
        ["completion_year", "credential_lineage"], dropna=False, as_index=False
    )["audit_detected_count"].sum()

    comparison = published_mapped.merge(
        detected_for_merge,
        on=["completion_year", "credential_lineage"],
        how="left",
    )
    comparison["audit_detected_count"] = comparison["audit_detected_count"].fillna(0).astype(int)
    comparison["difference"] = comparison["audit_detected_count"] - comparison["lsco_published_count"]
    comparison["percent_difference"] = comparison.apply(
        lambda r: (r["difference"] / r["lsco_published_count"]) if r["lsco_published_count"] else None,
        axis=1,
    )

    mapped_lineages = set(mapping.loc[mapping["credential_lineage"].ne(""), "credential_lineage"])
    detected_only = detected[
        detected["completion_year"].isin(YEARS)
        & ~detected["credential_lineage"].isin(mapped_lineages)
    ].copy()
    if not detected_only.empty:
        detected_only = detected_only.groupby(
            ["completion_year", "credential_lineage", "major"], as_index=False
        )["audit_detected_count"].sum()
        detected_only["program"] = "Detected only"
        detected_only["published_award"] = detected_only["major"]
        detected_only["lsco_published_count"] = 0
        detected_only["difference"] = detected_only["audit_detected_count"]
        detected_only["percent_difference"] = None
        detected_only["detected_major"] = detected_only["major"]
        detected_only["mapping_score"] = 1.0
        detected_only["score_margin"] = 1.0
        detected_only["mapping_status"] = "DETECTED LINEAGE NOT IN PUBLISHED REPORT"
        detected_only = detected_only.drop(columns=["major"])
        comparison = pd.concat([comparison, detected_only[comparison.columns]], ignore_index=True)

    comparison = comparison.sort_values(["completion_year", "program", "published_award"]).reset_index(drop=True)

    year_summary = comparison.groupby("completion_year", as_index=False).agg(
        lsco_published_count=("lsco_published_count", "sum"),
        audit_detected_count=("audit_detected_count", "sum"),
    )
    year_summary["difference"] = year_summary["audit_detected_count"] - year_summary["lsco_published_count"]
    year_summary["percent_difference"] = year_summary.apply(
        lambda r: (r["difference"] / r["lsco_published_count"]) if r["lsco_published_count"] else None,
        axis=1,
    )

    program_summary = comparison.groupby(["completion_year", "program"], as_index=False).agg(
        lsco_published_count=("lsco_published_count", "sum"),
        audit_detected_count=("audit_detected_count", "sum"),
    )
    program_summary["difference"] = program_summary["audit_detected_count"] - program_summary["lsco_published_count"]
    program_summary["percent_difference"] = program_summary.apply(
        lambda r: (r["difference"] / r["lsco_published_count"]) if r["lsco_published_count"] else None,
        axis=1,
    )

    # Add published labels to the local student detail where a lineage mapping exists.
    student_mapping = mapping.loc[mapping["credential_lineage"].ne(""), ["credential_lineage", "program", "published_award", "mapping_status"]]
    student_mapping = student_mapping.sort_values(["credential_lineage", "mapping_score"] if "mapping_score" in student_mapping.columns else ["credential_lineage"])
    student_mapping = student_mapping.drop_duplicates("credential_lineage", keep="first")
    students_labeled = students.merge(student_mapping, on="credential_lineage", how="left", validate="many_to_one")
    students_labeled["program"] = students_labeled["program"].where(
        students_labeled["program"].astype(str).str.strip().ne(""),
        "Detected only / unmapped",
    )
    if "major" in students_labeled.columns:
        students_labeled["published_award"] = students_labeled["published_award"].where(
            students_labeled["published_award"].astype(str).str.strip().ne(""),
            students_labeled["major"],
        )

    PUBLISHED_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    published_reference = published[["completion_year", "program", "published_award", "lsco_published_count"]].copy()
    published_reference.to_csv(PUBLISHED_CSV, index=False)

    with pd.ExcelWriter(OUTPUT_WORKBOOK, engine="xlsxwriter") as writer:
        workbook = writer.book
        percent_fmt = workbook.add_format({"num_format": "0.0%"})
        integer_fmt = workbook.add_format({"num_format": "0"})
        title_fmt = workbook.add_format({
            "bold": True, "font_size": 18, "font_color": "#FFFFFF",
            "bg_color": "#006747", "align": "left", "valign": "vcenter",
        })
        subtitle_fmt = workbook.add_format({"font_size": 11, "font_color": "#404040"})

        # Executive summary with chart.
        executive = workbook.add_worksheet("Executive Summary")
        writer.sheets["Executive Summary"] = executive
        executive.merge_range("A1:H2", "LSCO Detected vs. Published Credential Awards", title_fmt)
        executive.merge_range(
            "A3:H3",
            "Published source: LSCO Degrees and Certificates Awarded by Program (2019-2020 through 2024-2025). Detected counts use the earliest modeled completion event within each student and credential lineage.",
            subtitle_fmt,
        )
        year_summary.to_excel(writer, sheet_name="Executive Summary", startrow=5, startcol=0, index=False)
        executive.set_column("A:A", 16)
        executive.set_column("B:D", 20, integer_fmt)
        executive.set_column("E:E", 20, percent_fmt)
        executive.freeze_panes(6, 0)

        chart = workbook.add_chart({"type": "column"})
        last = 6 + len(year_summary)
        chart.add_series({
            "name": "LSCO published",
            "categories": ["Executive Summary", 6, 0, last - 1, 0],
            "values": ["Executive Summary", 6, 1, last - 1, 1],
        })
        chart.add_series({
            "name": "Audit detected",
            "categories": ["Executive Summary", 6, 0, last - 1, 0],
            "values": ["Executive Summary", 6, 2, last - 1, 2],
        })
        chart.set_title({"name": "Published vs. detected awards by academic year"})
        chart.set_x_axis({"name": "Academic year"})
        chart.set_y_axis({"name": "Awards", "major_gridlines": {"visible": False}})
        chart.set_legend({"position": "bottom"})
        chart.set_style(10)
        executive.insert_chart("G6", chart, {"x_scale": 1.35, "y_scale": 1.35})

        sheets = {
            "Credential Comparison": comparison,
            "Program Summary": program_summary,
            "Year Summary": year_summary,
            "Published Source Data": published_reference,
            "Lineage Mapping": mapping,
            "Detected Counts": detected,
            "Student Detail": students_labeled,
            "First Completion Detail": students,
            "In Published Window": in_window_students,
            "Outside Published Window": out_of_window_students,
        }
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            add_formatting(writer, name, frame)

        for sheet_name in ["Credential Comparison", "Program Summary", "Year Summary"]:
            ws = writer.sheets[sheet_name]
            cols = list(sheets[sheet_name].columns)
            for field in ["lsco_published_count", "audit_detected_count", "difference"]:
                if field in cols:
                    idx = cols.index(field)
                    ws.set_column(idx, idx, 18, integer_fmt)
            if "percent_difference" in cols:
                idx = cols.index("percent_difference")
                ws.set_column(idx, idx, 18, percent_fmt)

        # Highlight mapping rows requiring attention without blocking completion.
        map_ws = writer.sheets["Lineage Mapping"]
        if len(mapping):
            status_col = list(mapping.columns).index("mapping_status")
            map_ws.conditional_format(1, status_col, len(mapping), status_col, {
                "type": "text", "criteria": "containing", "value": "REVIEW",
                "format": workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"}),
            })
            map_ws.conditional_format(1, status_col, len(mapping), status_col, {
                "type": "text", "criteria": "containing", "value": "NO DETECTED",
                "format": workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#990000"}),
            })

    print("=" * 110)
    print("COMPLETE LSCO DETECTED VS. PUBLISHED REPORT")
    print("=" * 110)
    print(f"Eligible complete catalog-version rows: {len(candidates):,}")
    print(f"First completion student-lineages:      {len(students):,}")
    print(f"In published six-year window:           {len(in_window_students):,}")
    print(f"Outside published six-year window:      {len(out_of_window_students):,}")
    print(f"Published award definitions:            {unique_awards.shape[0]:,}")
    print(f"Detected credential lineages:           {unique_candidates.shape[0]:,}")
    print(f"Auto-mapped:                  {(mapping['mapping_status'] == 'AUTO-MAPPED').sum():,}")
    print(f"Mapped — review:              {(mapping['mapping_status'] == 'AUTO-MAPPED — REVIEW').sum():,}")
    print(f"No detected lineage:          {(mapping['mapping_status'] == 'NO DETECTED LINEAGE').sum():,}")
    print(f"Workbook:                     {OUTPUT_WORKBOOK}")
    print(f"Published CSV:                {PUBLISHED_CSV}")
    print(f"Mapping CSV:                  {MAPPING_CSV}")
    print("REPORT GATE: PASSED")


if __name__ == "__main__":
    main()
