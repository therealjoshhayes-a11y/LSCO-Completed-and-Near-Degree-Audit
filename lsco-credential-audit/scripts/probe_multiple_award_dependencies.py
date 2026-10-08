from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
REPORTING = ROOT / "data" / "processed" / "reporting"
SCRIPTS = ROOT / "scripts"

OUT = ROOT / "LOCAL_MULTIPLE_AWARD_DEPENDENCY_PREFLIGHT.txt"

KEYWORDS = [
    "certificate_lineage_bruteforce_review",
    "additional certificate",
    "additional_certificate",
    "25_percent",
    "25 percent",
    "25%",
    "unique_resident",
    "unique resident",
    "certificate_review",
    "governed_lineage_relationships_final",
    "stackable_nonconsuming",
    "detected_remains_additional_award",
]

KNOWN_PROBE_SCRIPTS = {
    "adjudicate_second_associate_stage1.py",
    "adjudicate_second_associate_stage2.py",
    "classify_governed_award_stacks.py",
    "repair_proven_nonconsuming_governance.py",
    "rebuild_certificate_review_without_associates.py",
}


def emit(handle, value=""):
    handle.write(str(value))
    handle.write("\n")


def truthy(value) -> bool:
    return str(value or "").strip().upper() in {
        "TRUE", "T", "YES", "Y", "1",
    }


def latest_dir(pattern: str, required_name: str) -> Path | None:
    dirs = [
        p
        for p in REPORTING.glob(pattern)
        if p.is_dir() and (p / required_name).exists()
    ]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def header_only(path: Path) -> list[str]:
    if not path.exists():
        return []
    return pd.read_csv(path, nrows=0).columns.tolist()


with OUT.open("w", encoding="utf-8") as fh:
    emit(fh, "LOCAL MULTIPLE-AWARD DEPENDENCY PREFLIGHT")
    emit(fh, f"Generated: {datetime.now().astimezone().isoformat()}")
    emit(fh)
    emit(
        fh,
        "FERPA-SAFE: this probe emits source code, file names, headers, "
        "and institutional governance rows only. It does not emit student rows.",
    )

    emit(fh)
    emit(fh, "=" * 110)
    emit(fh, "A. FINAL GOVERNANCE TABLE")
    emit(fh, "=" * 110)

    governance = (
        ROOT
        / "data"
        / "interim"
        / "institutional_awards"
        / "governed_lineage_relationships_final.csv"
    )

    emit(fh, f"PATH: {governance}")

    if governance.exists():
        gov = pd.read_csv(
            governance,
            dtype=str,
            low_memory=False,
        ).fillna("")

        emit(fh, f"ROWS: {len(gov):,}")
        emit(fh, "COLUMNS:")
        emit(fh, " | ".join(gov.columns))
        emit(fh)

        if "governance_status" in gov.columns:
            emit(fh, "GOVERNANCE STATUS COUNTS")
            emit(
                fh,
                gov["governance_status"]
                .value_counts(dropna=False)
                .to_string(),
            )
            emit(fh)

        if "relationship_type" in gov.columns:
            emit(fh, "RELATIONSHIP TYPE COUNTS")
            emit(
                fh,
                gov["relationship_type"]
                .value_counts(dropna=False)
                .to_string(),
            )
            emit(fh)

        required = {
            "detected_lineage",
            "institutional_lineage",
            "relationship_type",
            "awarded_represents_detected",
            "detected_remains_additional_award",
            "governance_status",
        }

        if required.issubset(gov.columns):
            consuming = gov[
                gov["awarded_represents_detected"].map(truthy)
            ][
                [
                    "detected_lineage",
                    "institutional_lineage",
                    "relationship_type",
                    "awarded_represents_detected",
                    "detected_remains_additional_award",
                    "governance_status",
                ]
            ].copy()

            emit(fh, "FINAL CONSUMING / REPRESENTING RELATIONSHIPS")
            if consuming.empty:
                emit(fh, "NONE")
            else:
                emit(
                    fh,
                    consuming.sort_values(
                        [
                            "detected_lineage",
                            "institutional_lineage",
                        ]
                    ).to_string(index=False),
                )
            emit(fh)

            nonconsuming = gov[
                gov["detected_remains_additional_award"].map(truthy)
            ][
                [
                    "detected_lineage",
                    "institutional_lineage",
                    "relationship_type",
                    "awarded_represents_detected",
                    "detected_remains_additional_award",
                    "governance_status",
                ]
            ].copy()

            emit(fh, "FINAL EXPLICIT NON-CONSUMING / ADDITIONAL RELATIONSHIPS")
            if nonconsuming.empty:
                emit(fh, "NONE")
            else:
                emit(
                    fh,
                    nonconsuming.sort_values(
                        [
                            "detected_lineage",
                            "institutional_lineage",
                        ]
                    ).to_string(index=False),
                )
    else:
        emit(fh, "MISSING")

    emit(fh)
    emit(fh, "=" * 110)
    emit(fh, "B. CURRENT INPUT SCHEMAS — HEADERS ONLY")
    emit(fh, "=" * 110)

    current_dir = latest_dir(
        "current_awardability_screen_*",
        "RESTRICTED_awardability_pass_combinations.csv",
    )

    if current_dir:
        current_pass = (
            current_dir
            / "RESTRICTED_awardability_pass_combinations.csv"
        )
        emit(fh, f"CURRENT PASS: {current_pass}")
        emit(fh, " | ".join(header_only(current_pass)))
    else:
        emit(fh, "CURRENT PASS: NOT FOUND")

    requirements = (
        ROOT
        / "data"
        / "processed"
        / "catalogs"
        / "staging_six_year"
        / "requirements_master_multiyear.csv"
    )

    emit(fh)
    emit(fh, f"SIX-YEAR REQUIREMENTS: {requirements}")
    emit(fh, " | ".join(header_only(requirements)) or "NOT FOUND")

    official_dir = latest_dir(
        "official_award_screening_final_*",
        "RESTRICTED_canonical_official_awards_final_mapping.csv",
    )

    if official_dir:
        official = (
            official_dir
            / "RESTRICTED_canonical_official_awards_final_mapping.csv"
        )
        emit(fh)
        emit(fh, f"OFFICIAL AWARDS: {official}")
        emit(fh, " | ".join(header_only(official)))
    else:
        emit(fh)
        emit(fh, "OFFICIAL AWARDS: NOT FOUND")

    lineage_candidates = [
        ROOT / "data" / "processed" / "reporting" / "credential_lineage_crosswalk.csv",
        ROOT / "data" / "interim" / "institutional_awards" / "award_program_crosswalk_curated.csv",
        ROOT / "data" / "interim" / "institutional_awards" / "award_program_crosswalk_curated.xlsx",
    ]

    emit(fh)
    emit(fh, "CANDIDATE LINEAGE / DEGREE-TYPE SUPPORT FILES")

    for path in lineage_candidates:
        emit(fh, f"PATH: {path}")
        if not path.exists():
            emit(fh, "  MISSING")
            continue

        try:
            if path.suffix.lower() == ".xlsx":
                xls = pd.ExcelFile(path)
                emit(fh, f"  SHEETS: {' | '.join(xls.sheet_names)}")
                for sheet in xls.sheet_names:
                    cols = pd.read_excel(
                        path,
                        sheet_name=sheet,
                        nrows=0,
                    ).columns.tolist()
                    emit(fh, f"  {sheet}: {' | '.join(map(str, cols))}")
            else:
                emit(fh, "  " + " | ".join(header_only(path)))
        except Exception as exc:
            emit(fh, f"  ERROR READING HEADER: {exc}")

    emit(fh)
    emit(fh, "=" * 110)
    emit(fh, "C. LOCAL SCRIPT DISCOVERY FOR CERTIFICATE / DEPENDENCY LOGIC")
    emit(fh, "=" * 110)

    matches = []

    if SCRIPTS.exists():
        for path in sorted(SCRIPTS.rglob("*.py")):
            try:
                source = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                continue

            lowered = source.lower()
            hit_terms = [
                keyword
                for keyword in KEYWORDS
                if keyword.lower() in lowered
            ]

            if hit_terms:
                matches.append(
                    (
                        path,
                        hit_terms,
                        source,
                    )
                )

    emit(fh, f"MATCHING SCRIPTS: {len(matches):,}")

    for path, hit_terms, _ in matches:
        emit(
            fh,
            f"{path.relative_to(ROOT)} :: "
            + " | ".join(hit_terms),
        )

    emit(fh)
    emit(fh, "=" * 110)
    emit(fh, "D. FULL SOURCE OF NEWLY DISCOVERED MATCHING SCRIPTS")
    emit(fh, "=" * 110)

    new_matches = [
        item
        for item in matches
        if item[0].name not in KNOWN_PROBE_SCRIPTS
    ]

    if not new_matches:
        emit(fh, "NONE")
    else:
        for path, hit_terms, source in new_matches:
            emit(fh)
            emit(fh, "=" * 110)
            emit(fh, f"FILE: {path.relative_to(ROOT)}")
            emit(fh, "MATCHED: " + " | ".join(hit_terms))
            emit(fh, "=" * 110)
            emit(fh, source)

print("=" * 100)
print("MULTIPLE-AWARD DEPENDENCY PREFLIGHT — COMPLETE")
print("=" * 100)
print(f"Wrote: {OUT}")
print("This file is FERPA-safe: no student rows were emitted.")
