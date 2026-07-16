"""Apply the 2026-07-16 starvation repairs to the extractor and audit engine.

Run from the repository root (the directory containing scripts/ and src/):

    python scripts/apply_starvation_repairs.py

Three patches, each documented inline at the patch site:

  PATCH 1 (extractor, root cause): key duplicate-title detection on the
      SLUGIFIED title so programs whose names differ only by punctuation
      (the Oxford-comma "Safety, Health and Environment" CERT vs
      "Safety, Health, and Environment" AAS, 2023-2026 catalogs) are
      correctly disambiguated into distinct credential IDs instead of
      silently merging into one un-completable credential.
      User policy 2026-07-16: the CERT and AAS are distinct lineages.

  PATCH 2 (extractor, documented source-defect repair): drop the
      duplicated ITSY 2343 row from the 2022-2023 Cybersecurity
      Specialist certificate. The duplication is a catalog typo (course
      printed in both semesters; totals internally consistent with the
      typo). The 2023-2024 and 2024-2025 catalogs correct it, retaining
      the Second Semester placement, so this repair keeps the LAST
      occurrence in document order and removes earlier ones.
      User decision 2026-07-16: ignore the duplicated course for the
      2022-2023 catalog.

  PATCH 3 (audit engine, tripwire): when a single-option COURSE
      requirement fails because its course was already consumed by a
      sibling requirement, report UNMET_CONSUMED_BY_SIBLING instead of
      bare UNMET. Completion arithmetic is unchanged (still counts as
      missing); the label makes this failure class visible in results
      so future credential merges/duplications cannot hide.

Each patch verifies its target text appears EXACTLY ONCE before editing
and aborts (no changes) otherwise, so a drifted working copy fails loud
instead of mis-patching. Backups: <file>_PRE_STARVATION_REPAIRS_<stamp>.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

EXTRACTOR = Path("scripts/extract_docx_requirements.py")
ENGINE = Path("src/lsco_audit/audit_multiyear_sample.py")

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def fail(message: str) -> None:
    print(f"ABORT: {message}")
    print("No files were modified.")
    sys.exit(1)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(
            f"{label}: expected target text exactly once, found {count}. "
            "Your working copy differs from the version this patch was "
            "written against -- apply this change manually instead."
        )
    return text.replace(old, new, 1)


# =============================================================================
# PATCH 1 -- slugify-keyed duplicate-title detection
# =============================================================================

P1_OLD = """    title_counts: dict[str, int] = {}
    for row in table_map_rows:
        title_counts[row["credential_title"]] = title_counts.get(row["credential_title"], 0) + 1

    duplicate_titles = {title for title, count in title_counts.items() if count > 1}

    if duplicate_titles:
        table_suffixes: dict[str, str] = {}

        for row in table_map_rows:
            if row["credential_title"] not in duplicate_titles:
                continue
"""

P1_NEW = """    # REPAIR NOTE (2026-07-16, starvation repairs): duplicate-title
    # detection keys on the SLUGIFIED title, not the raw title. The
    # 2023-2026 catalogs contain two distinct programs whose printed
    # titles differ only by an Oxford comma:
    #     "Safety, Health and Environment"  -- Certificate of Completion
    #     "Safety, Health, and Environment" -- Associate of Applied Science
    # Raw-title comparison treated them as unique, but slugify() strips
    # punctuation, so both collapsed to SAFETY_HEALTH_AND_ENVIRONMENT_<year>,
    # silently merging two credentials into one requirement set in which
    # seven duplicated courses guaranteed starvation (each course consumed
    # by one twin, leaving the other permanently UNMET) and locked both
    # real programs at zero detected completions. Keying on the slug sends
    # any post-slug collision through the AAS/CERT disambiguation below.
    # User policy 2026-07-16: the CERT and AAS are DISTINCT LINEAGES and
    # must carry distinct credential IDs end to end.
    title_counts: dict[str, int] = {}
    for row in table_map_rows:
        title_slug = slugify(row["credential_title"])
        title_counts[title_slug] = title_counts.get(title_slug, 0) + 1

    duplicate_titles = {slug for slug, count in title_counts.items() if count > 1}

    if duplicate_titles:
        table_suffixes: dict[str, str] = {}

        for row in table_map_rows:
            if slugify(row["credential_title"]) not in duplicate_titles:
                continue
"""

P1B_OLD = """        title_suffix_counts: dict[tuple[str, str], int] = {}
        for row in table_map_rows:
            if row["credential_title"] not in duplicate_titles:
                continue

            suffix = table_suffixes.get(row["source_table_index"], f'T{int(row["source_table_index"]):03d}')
            key = (row["credential_title"], suffix)
            title_suffix_counts[key] = title_suffix_counts.get(key, 0) + 1

        for row_group in (all_requirements, all_totals, table_map_rows):
            for row in row_group:
                if row["credential_title"] not in duplicate_titles:
                    continue

                table_index_value = row["source_table_index"]
                suffix = table_suffixes.get(table_index_value, f'T{int(table_index_value):03d}')

                if title_suffix_counts.get((row["credential_title"], suffix), 0) > 1:
                    suffix = f'T{int(table_index_value):03d}'
"""

P1B_NEW = """        title_suffix_counts: dict[tuple[str, str], int] = {}
        for row in table_map_rows:
            if slugify(row["credential_title"]) not in duplicate_titles:
                continue

            suffix = table_suffixes.get(row["source_table_index"], f'T{int(row["source_table_index"]):03d}')
            key = (slugify(row["credential_title"]), suffix)
            title_suffix_counts[key] = title_suffix_counts.get(key, 0) + 1

        for row_group in (all_requirements, all_totals, table_map_rows):
            for row in row_group:
                if slugify(row["credential_title"]) not in duplicate_titles:
                    continue

                table_index_value = row["source_table_index"]
                suffix = table_suffixes.get(table_index_value, f'T{int(table_index_value):03d}')

                if title_suffix_counts.get((slugify(row["credential_title"]), suffix), 0) > 1:
                    suffix = f'T{int(table_index_value):03d}'
"""

# =============================================================================
# PATCH 2 -- documented repair: 2022-2023 Cybersecurity duplicate ITSY 2343
# =============================================================================

P2_FUNCTION = '''

def repair_cybersecurity_2022_duplicate_itsy_2343(
    requirements: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Remove the duplicated ITSY 2343 row from the 2022-2023 Cybersecurity
    Specialist Certificate of Completion.

    SOURCE DEFECT (catalog typo, not an extraction error): the 2022-2023
    catalog's Cybersecurity Specialist certificate table prints
    "ITSY 2343 Computer System Forensics" in BOTH the First Semester and
    Second Semester course lists. The printed semester subtotals (15 + 15)
    and the 30-hour program total are internally consistent WITH the
    duplicate, so the defect originates in the source document.

    EVIDENCE OF INTENT: the 2023-2024 and 2024-2025 catalogs correct the
    table -- First Semester's fifth course becomes ITNW 1313 Computer
    Virtualization and ITSY 2343 appears once, in Second Semester. The
    Second Semester placement is therefore treated as intended: this
    repair keeps the LAST occurrence in document order (Second Semester)
    and removes earlier occurrences.

    USER DECISION 2026-07-16: ignore the duplicated course for the
    2022-2023 catalog. The credential's effective requirement count drops
    by one; the printed 30-hour program total is inherited from the source
    typo and is NOT adjusted by this repair.
    """

    target_credential_prefix = "CYBERSECURITY_SPECIALIST"
    target_year_token = "2022"
    target_course = "ITSY 2343"

    matching_indexes = [
        index
        for index, row in enumerate(requirements)
        if target_credential_prefix in str(row.get("credential_id", ""))
        and target_year_token in str(row.get("credential_id", ""))
        and str(row.get("course_codes", "")).strip() == target_course
    ]

    if len(matching_indexes) <= 1:
        return requirements

    keep_index = matching_indexes[-1]
    drop_indexes = set(matching_indexes[:-1])

    repaired = []
    for index, row in enumerate(requirements):
        if index in drop_indexes:
            continue

        if index == keep_index:
            row = dict(row)
            existing_flags = str(row.get("issue_flags", "") or "").strip()
            repair_flag = "REPAIRED_DUPLICATE_ITSY_2343_SOURCE_CATALOG_TYPO_2022"

            if not existing_flags or existing_flags.lower() == "nan":
                row["issue_flags"] = repair_flag
            elif repair_flag not in existing_flags.split(";"):
                row["issue_flags"] = existing_flags + ";" + repair_flag

        repaired.append(row)

    return repaired

'''

P2_HOOK_OLD = """    all_requirements = repair_compressed_criminal_justice_stack_rows(all_requirements)"""

P2_HOOK_NEW = """    all_requirements = repair_cybersecurity_2022_duplicate_itsy_2343(all_requirements)
    all_requirements = repair_compressed_criminal_justice_stack_rows(all_requirements)"""

P2_ANCHOR = """def repair_business_real_estate_blank_busi_2304_hours("""

# =============================================================================
# PATCH 3 -- engine tripwire: UNMET_CONSUMED_BY_SIBLING
# =============================================================================

P3_SIG_OLD = """def audit_non_elective_requirement(
    requirement_id: str,
    catalog_year: str,
    group: pd.DataFrame,
    available_courses: set[str],
    core_lookup: dict[tuple[str, str], set[str]],
    compound_alternatives: dict[str, list[list[str]]],
) -> tuple[str, list[str]]:"""

P3_SIG_NEW = """def audit_non_elective_requirement(
    requirement_id: str,
    catalog_year: str,
    group: pd.DataFrame,
    available_courses: set[str],
    core_lookup: dict[tuple[str, str], set[str]],
    compound_alternatives: dict[str, list[list[str]]],
    used_courses: set[str] | None = None,
) -> tuple[str, list[str]]:"""

P3_RET_OLD = """    required = int(group.iloc[0]["min_required"])
    matched = sorted(set(matched))

    if len(matched) >= required:
        return "MET", matched[:required]

    return "UNMET", matched"""

P3_RET_NEW = """    required = int(group.iloc[0]["min_required"])
    matched = sorted(set(matched))

    if len(matched) >= required:
        return "MET", matched[:required]

    # TRIPWIRE (2026-07-16, starvation repairs): if this requirement's
    # single COURSE option was already consumed by a sibling requirement
    # in the same credential (one-course-one-slot allocation), say so
    # loudly instead of reporting a bare UNMET. A single-option course
    # requirement starving on its own course is the signature of a
    # duplicated requirement row or a merged credential (see the
    # Safety, Health and/,and Environment Oxford-comma collision that
    # locked two programs at zero completions, diagnosed 2026-07-16).
    # Completion arithmetic is unchanged: this status still counts as a
    # missing requirement. It exists so this defect class can never
    # again hide inside ordinary UNMET noise.
    course_option_values = [
        normalize_course_code(option["option_value"])
        for _, option in group.iterrows()
        if str(option["option_type"]).strip().upper() == "COURSE"
    ]

    if (
        used_courses
        and len(course_option_values) == 1
        and course_option_values[0] in used_courses
    ):
        return "UNMET_CONSUMED_BY_SIBLING", matched

    return "UNMET", matched"""

P3_CALL_OLD = """            status, matched = audit_non_elective_requirement(
                requirement_id=requirement_id,
                catalog_year=str(catalog_year),
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
                compound_alternatives=compound_alternatives,
            )"""

P3_CALL_NEW = """            status, matched = audit_non_elective_requirement(
                requirement_id=requirement_id,
                catalog_year=str(catalog_year),
                group=group,
                available_courses=available_courses,
                core_lookup=core_lookup,
                compound_alternatives=compound_alternatives,
                used_courses=used_courses,
            )"""


def main() -> None:
    for path in (EXTRACTOR, ENGINE):
        if not path.exists():
            fail(f"Expected file not found: {path}. Run from the repository root.")

    extractor_text = EXTRACTOR.read_text(encoding="utf-8")
    engine_text = ENGINE.read_text(encoding="utf-8")

    # Validate every target BEFORE writing anything.
    for label, text, old in (
        ("PATCH 1a", extractor_text, P1_OLD),
        ("PATCH 1b", extractor_text, P1B_OLD),
        ("PATCH 2 hook", extractor_text, P2_HOOK_OLD),
        ("PATCH 2 anchor", extractor_text, P2_ANCHOR),
        ("PATCH 3 signature", engine_text, P3_SIG_OLD),
        ("PATCH 3 return", engine_text, P3_RET_OLD),
        ("PATCH 3 call site", engine_text, P3_CALL_OLD),
    ):
        count = text.count(old)
        if count != 1:
            fail(f"{label}: target found {count} times (expected 1).")

    if "repair_cybersecurity_2022_duplicate_itsy_2343" in extractor_text:
        fail("PATCH 2: repair function already present. Patches appear already applied.")

    # Backups.
    extractor_backup = EXTRACTOR.with_name(EXTRACTOR.stem + f"_PRE_STARVATION_REPAIRS_{STAMP}.py")
    engine_backup = ENGINE.with_name(ENGINE.stem + f"_PRE_STARVATION_REPAIRS_{STAMP}.py")
    shutil.copyfile(EXTRACTOR, extractor_backup)
    shutil.copyfile(ENGINE, engine_backup)

    # Apply.
    extractor_text = replace_once(extractor_text, P1_OLD, P1_NEW, "PATCH 1a")
    extractor_text = replace_once(extractor_text, P1B_OLD, P1B_NEW, "PATCH 1b")
    extractor_text = replace_once(
        extractor_text, P2_ANCHOR, P2_FUNCTION + P2_ANCHOR, "PATCH 2 function"
    )
    extractor_text = replace_once(extractor_text, P2_HOOK_OLD, P2_HOOK_NEW, "PATCH 2 hook")
    engine_text = replace_once(engine_text, P3_SIG_OLD, P3_SIG_NEW, "PATCH 3 signature")
    engine_text = replace_once(engine_text, P3_RET_OLD, P3_RET_NEW, "PATCH 3 return")
    engine_text = replace_once(engine_text, P3_CALL_OLD, P3_CALL_NEW, "PATCH 3 call site")

    EXTRACTOR.write_text(extractor_text, encoding="utf-8")
    ENGINE.write_text(engine_text, encoding="utf-8")

    print("Applied all patches.")
    print(f"Backup: {extractor_backup}")
    print(f"Backup: {engine_backup}")
    print()
    print("Next steps, in order:")
    print("  1. Re-run the catalog extraction to regenerate the requirements master.")
    print("  2. Gate: python scripts/census_starved_requirements.py  (expect 0 rows,")
    print("     noting it reads the OLD audit results until step 3 re-runs; the true")
    print("     pre-flight gate is the duplicate-claims check on the NEW master).")
    print("  3. Re-run the chunked full audit (the one expensive step).")
    print("  4. python scripts/build_student_catalog_eligibility_v2.py")
    print("  5. python scripts/select_maximum_awards.py")


if __name__ == "__main__":
    main()
