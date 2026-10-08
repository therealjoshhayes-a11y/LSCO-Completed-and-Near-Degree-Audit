from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import sys

import pandas as pd


# ======================================================================================
# OFFICIAL-AWARD SCREENING — CURRENT FALL 2026 EMPIRICAL UNIVERSE
# ======================================================================================
#
# Scope:
#   * Reads the reconciled current eligible empirical summary.
#   * Preserves EVERY empirical COMPLETE catalog/credential row.
#   * Screens COMPLETE rows against official award history at student + suppression-family grain.
#   * Does NOT select the latest catalog within a lineage.
#   * REVIEW_REQUIRED and NO_AUTOMATIC_MATCH official awards NEVER suppress a candidate.
#   * Writes a FERPA-safe aggregate impact report for unresolved official-award keys.
#
# Nothing in the July production audit is modified.
#
# Run from repository root:
#   python -u .\scripts\run_official_award_screening.py
#

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import profile_refresh_delta as refresh  # noqa: E402


CURRENT_SUMMARY = Path(
    "data/processed/incremental_audit/fall_2026_refresh_20261007/"
    "RESTRICTED_current_eligible_empirical_credential_summary.csv"
)

REQUIREMENTS = Path(
    "data/processed/catalogs/staging_six_year/requirements_master_multiyear.csv"
)

PRIOR_AWARDS = refresh.DEFAULT_PRIOR_AWARDS
NEW_AWARDS = refresh.DEFAULT_NEW_AWARDS

RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path(
    "data/processed/reporting"
) / f"official_award_screening_{RUN_STAMP}"

EXPECTED_CURRENT_ROWS = 3_108_838
EXPECTED_CREDENTIAL_YEARS = 520
EXPECTED_OFFICIAL_ROWS = 5_480
EXPECTED_MAPPED_OFFICIAL_ROWS = 5_216
EXPECTED_NO_MATCH_OFFICIAL_ROWS = 142
EXPECTED_REVIEW_OFFICIAL_ROWS = 122


MAPPED_FAMILIES = {('AAS_BMCD', 'BMCD', 'AAS'): 'BUSINESS_CONSTRUCTION_MANAGEMENT', ('AAS_BMRD', 'BMRD', 'AAS'): 'BUSINESS_REAL_ESTATE_MANAGEMENT', ('AAS_BSMT', 'BSMT', 'AAS'): 'BUSINESS_MANAGEMENT', ('AAS_COSD', 'COSD', 'AAS'): 'COSMETOLOGY_OPERATOR_MANAGEMENT', ('AAS_CRTD', 'CRTD', 'AAS'): 'COURT_REPORTING_AAS', ('AAS_DNTD', 'DNTD', 'AAS'): 'DENTAL_ASSISTING_AAS', ('AAS_INTE', 'INTE', 'AAS'): 'INDUSTRIAL_TECHNOLOGY', ('AAS_ISTR', 'ISTR', 'AAS'): 'INSTRUMENTATION_AAS', ('AAS_ITSS', 'ITSS', 'AAS'): 'INFORMATION_TECHNOLOGY_SUPPORT_SPECIALIST', ('AAS_LOMD', 'LOMD', 'AAS'): 'LOGISTICS_MANAGEMENT_MARITIME_AAS', ('AAS_MMMD', 'MMMD', 'AAS'): 'ELECTROMECHANICAL_TECHNOLOGY_AAS', ('AAS_MSGD', 'MSGD', 'AAS'): 'MASSAGE_THERAPY_MANAGEMENT', ('AAS_PHRD', 'PHRD', 'AAS'): 'PHARMACY_TECHNOLOGY_BUSINESS_MANAGEMENT', ('AAS_PROC', 'PROC', 'AAS'): 'PROCESS_OPERATING_TECHNOLOGY', ('AAS_RNAD', 'RNAD', 'AAS'): 'REGISTERED_NURSING_AAS', ('AAS_RNSG', 'RNSG', 'AAS'): 'REGISTERED_NURSING_AAS', ('AAS_SHED', 'SHED', 'AAS'): 'SAFETY_HEALTH_ENVIRONMENT_AAS', ('AAS_WLFD', 'WLFD', 'AAS'): 'WELDING_FABRICATION_TECHNOLOGY', ('AAS_WLLD', 'WLLD', 'AAS'): 'WELDING_TECHNOLOGY_AAS', ('AAT_AAT1', 'AAT1', 'AAT'): 'TEACHING_AAT1', ('AAT_AAT2', 'AAT2', 'AAT'): 'TEACHING_AAT2', ('AA_AACM', 'AACM', 'AA'): 'COMMUNICATION', ('AA_AALA', 'AALA', 'AA'): 'LIBERAL_ARTS', ('AA_AASO', 'AASO', 'AA'): 'SOCIOLOGY', ('AA_ASLA', 'AALA', 'AA'): 'LIBERAL_ARTS', ('AA_LART', 'LART', 'AA'): 'LIBERAL_ARTS', ('AS_ASBU', 'ASBU', 'AS'): 'BUSINESS', ('AS_ASCI', 'ASCI', 'AS'): 'COMPUTER_INFORMATION_SYSTEMS', ('AS_ASCJ', 'ASCJ', 'AS'): 'CRIMINAL_JUSTICE_AS', ('AS_ASCS', 'ASCS', 'AS'): 'COMPUTER_SCIENCE', ('AS_ASES', 'ASES', 'AS'): 'ENVIRONMENTAL_SCIENCE', ('AS_ASNS', 'ASNS', 'AS'): 'NATURAL_SCIENCE', ('AS_ASPM', 'ASPM', 'AS'): 'PRE_PROFESSIONAL_HEALTH_SCIENCE', ('AS_BAAD', 'BAAD', 'AS'): 'BUSINESS_ADMINISTRATION', ('CERT1_ABS2', 'ABS2', 'CERT1'): 'ORDINARY_SEAMAN_II', ('CERT1_ABSC', 'ABSC', 'CERT1'): 'ORDINARY_SEAMAN_I', ('CERT1_ACCB', 'ACCB', 'CERT1'): 'ACCOUNTING_SERVICES_BASIC', ('CERT1_AUTB', 'AUTB', 'CERT1'): 'AUTOMOTIVE_TECHNOLOGY_BASIC', ('CERT1_BCTB', 'BCTB', 'CERT1'): 'BUILDING_CONSTRUCTION_TECHNOLOGY_BASIC', ('CERT1_BFMB', 'BFMB', 'CERT1'): 'BANKING_AND_FINANCIAL_SERVICES_BASIC', ('CERT1_BMAC', 'BMAC', 'CERT1'): 'BUSINESS_MANAGEMENT_ACCOUNTING', ('CERT1_BMCC', 'BMCC', 'CERT1'): 'CONSTRUCTION_MANAGEMENT', ('CERT1_BMEC', 'BMEC', 'CERT1'): 'ENTREPRENEURSHIP', ('CERT1_BMOP', 'BMOP', 'CERT1'): 'BUSINESS_OPERATIONS', ('CERT1_BMRC', 'BMRC', 'CERT1'): 'REAL_ESTATE_CERTIFICATE', ('CERT1_CJCR', 'CJCR', 'CERT1'): 'CRIMINAL_JUSTICE_CERTIFICATE', ('CERT1_CNCT', 'CNCT', 'CERT1'): 'CISCO_NETWORKING_CYBERSECURITY_TECHNICIAN_CERTIFICATE', ('CERT1_COSC', 'COSC', 'CERT1'): 'COSMETOLOGY_OPERATOR_CERTIFICATE', ('CERT1_CRSC', 'CRSC', 'CERT1'): 'COURT_REPORTING_MACHINE_SHORTHAND_SCOPIST', ('CERT1_CRTC', 'CRTC', 'CERT1'): 'COURT_REPORTING_CERTIFICATE', ('CERT1_CRTC', 'CRTD', 'CERT1'): 'COURT_REPORTING_CERTIFICATE', ('CERT1_CRTC', 'CRTR', 'CERT1'): 'COURT_REPORTING_CERTIFICATE', ('CERT1_CUST', 'CUST', 'CERT2'): 'CUSTOMER_SERVICE', ('CERT1_CYBS', 'CYBS', 'CERT1'): 'CYBERSECURITY_SPECIALIST_CERTIFICATE', ('CERT1_CYSB', 'CYSB', 'CERT1'): 'INFORMATION_TECHNOLOGY_CYBERSECURITY_BASIC', ('CERT1_DATC', 'DATC', 'CERT1'): 'DATA_ANALYTICS', ('CERT1_DCAC', 'DCAC', 'CERT1'): 'AUDIO_VISUAL_TECHNOLOGY_CERTIFICATE_OF_COMPLETION', ('CERT1_DNTA', 'DNTA', 'CERT1'): 'DENTAL_ASSISTING_CERTIFICATE', ('CERT1_DNTB', 'DNTB', 'CERT1'): 'DENTAL_FRONT_OFFICE', ('CERT1_EMS1', 'EMS1', 'CERT1'): 'EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_CERTIFICATE', ('CERT1_EMS2', 'EMS2', 'CERT1'): 'EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_CERTIFICATE', ('CERT1_HVAB', 'HVAB', 'CERT1'): 'HEATING_VENTILATION_AIR_CONDITIONING_HVAC_TECHNOLOGY_BASIC', ('CERT1_INST', 'INST', 'CERT1'): 'INSTRUMENTATION_CERTIFICATE_OF_COMPLETION', ('CERT1_ISTB', 'ISTB', 'CERT1'): 'INSTRUMENTATION_BASIC', ('CERT1_ITHC', 'ITHC', 'CERT1'): 'IT_NETWORKING_CERTIFICATE', ('CERT1_ITSC', 'ITSC', 'CERT1'): 'IT_SOFTWARE_CERTIFICATE', ('CERT1_LOMC', 'LOMC', 'CERT1'): 'LOGISTICS_MANAGEMENT_CERTIFICATE', ('CERT1_MDAS', 'MDAS', 'CERT1'): 'MEDICAL_ASSISTING_CERTIFICATE', ('CERT1_MMMB', 'MMMB', 'CERT1'): 'ELECTROMECHANICAL_TECHNOLOGY_BASIC', ('CERT1_MMMC', 'MMMC', 'CERT1'): 'ELECTROMECHANICAL_TECHNOLOGY_CERTIFICATE', ('CERT1_MSGC', 'MSGC', 'CERT1'): 'MASSAGE_THERAPY', ('CERT1_PHAR', 'PHAR', 'CERT1'): 'PHARMACY_TECHNOLOGY_BASIC_CERTIFICATE', ('CERT1_PHRA', 'PHAR', 'CERT1'): 'PHARMACY_TECHNOLOGY_BASIC_CERTIFICATE', ('CERT1_PHRA', 'PHRA', 'CERT1'): 'HOSPITAL_PHARMACY_TECHNOLOGY_CERTIFICATE', ('CERT1_PTAC', 'PTAC', 'CERT1'): 'PROCESS_TECHNOLOGY', ('CERT1_SHEC', 'SHEC', 'CERT1'): 'SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE', ('CERT1_TEPC', 'TEPC', 'CERT1'): 'TEACHER_EDUCATION_CERTIFICATE_OF_COMPLETION', ('CERT1_WLDB', 'WLDB', 'CERT1'): 'PRODUCTION_WELDER', ('CERT1_WLDC', 'WLDC', 'CERT1'): 'WELDING_TECHNOLOGY_CERTIFICATE', ('CERT1_WLFC', 'WLFC', 'CERT1'): 'LAYOUT_AND_FABRICATION_WELDING_CERTIFICATE', ('CERT2_GENS', 'GENS', 'CERT2'): 'GENERAL_STUDIES_CERTIFICATE', ('CERT2_GSRT', 'GSRT', 'CERT2'): 'GENERAL_STUDIES_CERTIFICATE', ('CERT2_VNSG', 'VNSG', 'CERT2'): 'VOCATIONAL_NURSING_CERTIFICATE', ('ZCONV CERT', 'ZVN', 'CERT1'): 'VOCATIONAL_NURSING_CERTIFICATE'}

NO_AUTOMATIC_MATCH = {('AAS_MOPD', 'MOPD', 'AAS'): 'Medical Office Professional AAS predates current audit lineages; no exact equivalent established.', ('AS_ASCM', 'ASCM', 'AS'): 'Academic Studies in Communication AS is not the same credential type as current Communication award families.', ('AS_ASLA', 'ASLA', 'AS'): 'Academic Studies in Liberal Arts AS is not the same credential type as Liberal Arts AA.', ('AS_ASSO', 'ASSO', 'AS'): 'Academic Studies in Sociology AS is not the same credential type as Sociology AA.', ('CERT1_CNSC', 'CNSC', 'CERT1'): 'CISCO Network Specialist certificate has no exact current audit family.', ('CERT1_MOTC', 'MOTC', 'CERT1'): 'Medical Transcriptionist has no exact current audit family.', ('CERT2_MOAA', 'MOAA', 'CERT2'): 'Legacy Medical Administrative Assistant has no exact current audit family.', ('IA_CSER', 'CSER', 'IA'): 'Institutional Award differs in award type from the current Customer Service certificate; equivalence is not assumed.', ('IA_EMS1', 'EMS1', 'IA'): 'Institutional Award differs in award type from the EMT Basic certificate; equivalence is not assumed.', ('IA_EMS2', 'EMS2', 'IA'): 'Institutional Award differs in award type from the EMT Intermediate certificate; equivalence is not assumed.', ('IA_FORE', 'FORE', 'IA'): 'Forensic Science Institutional Award has no same-type audit family established.', ('IA_GAMD', 'GAMD', 'IA'): 'Game Designer Institutional Award has no current audit family.', ('IA_MORT', 'MORT', 'IA'): 'Legacy Medical Office Receptionist Institutional Award has no exact current audit family.', ('IA_NUAD', 'NUAD', 'IA'): 'Advanced Nurse Aide Institutional Award has no current audit family.', ('IA_PHAR', 'PHAR', 'IA'): 'Retail Pharmacy Institutional Award differs in award type from the pharmacy certificate; equivalence is not assumed.', ('ZCONV AAS', 'ZENV', 'AAS'): 'Environmental Technology AAS has no clearly equivalent current audit family.', ('ZCONV CERT', 'ITSA', 'CERT1'): 'Legacy Information Technology Support Assistant award has no exact current audit family.', ('ZCONV CERT', 'ZOFR', 'CERT1'): 'Legacy Office Receptionist has no exact current audit family.'}

REVIEW_REQUIRED = {('AAS_BSMT', 'ASBU', 'AAS'): 'Program code is AAS_BSMT but Major1Code/description says Business; source fields conflict.', ('AAT_AATP', 'AATP', 'AAT'): 'Generic Teacher EC-6/8-12 AAT does not map uniquely to AAT1 versus AAT2.', ('CERT1_CJCC', 'CJCC', 'CERT1'): 'Criminal Justice Corrections certificate has no explicit Corrections audit family.', ('CERT1_MMMO', 'MMMO', 'CERT1'): 'Mechanical/Manufacturing/Maintenance certificate has no uniquely named audit family.', ('CERT1_MOAC', 'MOAC', 'CERT1'): 'Legacy Medical Office Assistant may or may not equal Medical Assisting or Medical Office Support.', ('CERT1_PTAA', 'PTAA', 'CERT1'): 'Process Technology Academy certificate may be distinct from Process Technology; no exact audit family.', ('CERT2_ITSC', 'ITSC', 'CERT2'): 'Legacy Level-2 IT Software Development award needs an explicit equivalency decision.', ('CERT2_SHEC', 'SHEC', 'CERT2'): 'Legacy Level-2 Safety/Health/Environment award needs an explicit equivalency decision.'}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def clean(value: object) -> str:
    return str(value).strip().upper()


def joined(values) -> str:
    return " | ".join(
        sorted({str(v).strip() for v in values if str(v).strip()})
    )


def derive_lineage(credential_id: object) -> str:
    value = clean(credential_id)
    value = re.sub(
        r"_(2021_2022|2022_2023|2023_2024|2024_2025|2025_2026|2026_2027)$",
        "",
        value,
    )
    value = re.sub(
        r"_(2021|2022|2023|2024|2025|2026)$",
        "",
        value,
    )
    return value


def infer_program_hours(group: pd.DataFrame) -> float | None:
    one = (
        group.sort_values("requirement_id", kind="mergesort")
        .drop_duplicates("requirement_id", keep="first")
        .copy()
    )
    hours = pd.to_numeric(one["credit_hours"], errors="coerce")
    if not hours.notna().any():
        return None
    return float(hours.fillna(0).sum())


def audit_suppression_family(row: pd.Series) -> str:
    lineage = clean(row["credential_lineage"])
    title = clean(row["credential_title"])
    hours_value = row["inferred_program_hours"]
    hours = None
    if str(hours_value).strip():
        try:
            hours = float(hours_value)
        except ValueError:
            hours = None

    # Registered Nursing: Banner reports the official AAS generically while the
    # audit catalogs distinguish ADN/Transition route names.
    if lineage in {
        "REGISTERED_NURSING_AAS",
        "REGISTERED_NURSING_TRANSITION",
        "REGISTERED_NURSING_ASSOCIATE_DEGREE_NURSING",
    }:
        return "REGISTERED_NURSING_AAS"

    # Catalog source identifies the Criminal Justice associate credential as AS;
    # the historical audit ID contains AAS.
    if lineage == "CRIMINAL_JUSTICE_AAS":
        return "CRIMINAL_JUSTICE_AS"
    if lineage == "CRIMINAL_JUSTICE_CERTIFICATE_OF_COMPLETION":
        return "CRIMINAL_JUSTICE_CERTIFICATE"

    if lineage == "COURT_REPORTING_CERTIFICATE_OF_COMPLETION":
        return "COURT_REPORTING_CERTIFICATE"

    # Electromechanical: preserve AAS vs certificate while normalizing name changes.
    if lineage in {
        "ELECTRO_MECHANICAL_TECHNOLOGY_AAS",
        "ELECTROMECHANICAL_TECHNOLOGY_AAS",
    }:
        return "ELECTROMECHANICAL_TECHNOLOGY_AAS"
    if lineage in {
        "ELECTRO_MECHANICAL_TECHNOLOGY_CERTIFICATE_OF_COMPLETION",
        "ELECTROMECHANICAL_TECHNOLOGY",
    }:
        return "ELECTROMECHANICAL_TECHNOLOGY_CERTIFICATE"

    # Logistics: the 2025 staged ID is misleading; the catalog title is authoritative.
    if (
        "LOGISTICS MANAGEMENT (MARITIME)" in title
        or lineage == "LOGISTICS_MANAGEMENT_MARITIME_AAS"
    ):
        return "LOGISTICS_MANAGEMENT_MARITIME_AAS"
    if title == "LOGISTICS MANAGEMENT" or lineage == "LOGISTICS_MANAGEMENT":
        return "LOGISTICS_MANAGEMENT_CERTIFICATE"

    # Real Estate changed names; keep certificate and AAS families separate.
    if lineage == "BUSINESS_REAL_ESTATE_MANAGEMENT":
        return "BUSINESS_REAL_ESTATE_MANAGEMENT"
    if "REAL ESTATE" in title:
        if "ASSOCIATE" in title or (hours is not None and hours >= 50):
            return "BUSINESS_REAL_ESTATE_MANAGEMENT"
        return "REAL_ESTATE_CERTIFICATE"
    if lineage == "REAL_ESTATE":
        return "REAL_ESTATE_CERTIFICATE"
    if lineage == "REAL_ESTATE_MANAGEMENT":
        return (
            "BUSINESS_REAL_ESTATE_MANAGEMENT"
            if hours is not None and hours >= 50
            else "REAL_ESTATE_CERTIFICATE"
        )

    # Welding changed IDs across catalogs; preserve certificate vs AAS.
    if lineage == "WELDING_TECHNOLOGY_AAS":
        return "WELDING_TECHNOLOGY_AAS"
    if lineage == "WELDING_TECHNOLOGY":
        return (
            "WELDING_TECHNOLOGY_AAS"
            if hours is not None and hours >= 50
            else "WELDING_TECHNOLOGY_CERTIFICATE"
        )
    if lineage == "WELDING_TECHNOLOGY_CERTIFICATE_OF_COMPLETION":
        return "WELDING_TECHNOLOGY_CERTIFICATE"

    # Safety/Health/Environment changed IDs; preserve certificate vs AAS.
    if lineage in {
        "SAFETY_HEALTH_AND_ENVIRONMENT_AAS",
        "SAFETY_HEALTH_AND_ENVIRONMENT",
    } and hours is not None and hours >= 50:
        return "SAFETY_HEALTH_ENVIRONMENT_AAS"
    if lineage in {
        "SAFETY_HEALTH_AND_ENVIRONMENTAL",
        "SAFETY_HEALTH_AND_ENVIRONMENT_CERTIFICATE_OF_COMPLETION",
    }:
        return "SAFETY_HEALTH_ENVIRONMENT_CERTIFICATE"

    if lineage in {"GENERAL_STUDIES", "GENERAL_STUDIES_CORE_CURRICULUM"}:
        return "GENERAL_STUDIES_CERTIFICATE"

    if lineage in {"DENTAL_ASSISTING", "DENTAL_ASSISTING_CERTIFICATE_OF_COMPLETION"}:
        if hours is None or hours < 50:
            return "DENTAL_ASSISTING_CERTIFICATE"

    if lineage in {
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_T050",
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_T072",
        "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC",
    }:
        return "EMERGENCY_MEDICAL_TECHNOLOGY_BASIC_CERTIFICATE"

    if lineage in {
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_T051",
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_T073",
        "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE",
    }:
        return "EMERGENCY_MEDICAL_TECHNOLOGY_INTERMEDIATE_CERTIFICATE"

    if lineage in {
        "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTING_NETWORKING_SPECIALIST",
        "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_NETWORKING_SPECIALIST",
        "INFORMATION_TECHNOLOGY_NETWORKING",
        "IT_NETWORKING",
    }:
        return "IT_NETWORKING_CERTIFICATE"

    if lineage in {
        "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTING_SOFTWARE_SPECIALIST_DEVELOPMENT",
        "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_SOFTWARE_DEVELOPMENT",
        "INFORMATION_TECHNOLOGY_SOFTWARE",
        "IT_SOFTWARE",
    }:
        return "IT_SOFTWARE_CERTIFICATE"

    if lineage in {"MEDICAL_ASSISTANT", "MEDICAL_ASSISTING"}:
        return "MEDICAL_ASSISTING_CERTIFICATE"

    if lineage in {"PHARMACY_TECHNOLOGY", "HOSPITAL_PHARMACY_TECHNOLOGY"}:
        return "HOSPITAL_PHARMACY_TECHNOLOGY_CERTIFICATE"

    if lineage in {"PHARMACY_TECHNOLOGY_BASIC", "RETAIL_PHARMACY_TECHNOLOGY_BASIC"}:
        return "PHARMACY_TECHNOLOGY_BASIC_CERTIFICATE"

    if lineage == "COSMETOLOGY_OPERATOR":
        return "COSMETOLOGY_OPERATOR_CERTIFICATE"

    if lineage in {
        "INFORMATION_TECHNOLOGY_SUPPORT_ASSISTANT_CYBERSECURITY_SPECIALIST",
        "CYBERSECURITY_SPECIALIST",
        "INFORMATION_TECHNOLOGY_CYBERSECURITY",
        "IT_CYBERSECURITY",
    }:
        return "CYBERSECURITY_SPECIALIST_CERTIFICATE"

    if lineage in {
        "INFORMATION_TECHNOLOGY_CYBERSECURITY_BASIC",
        "IT_CYBERSECURITY_BASIC",
    }:
        return "INFORMATION_TECHNOLOGY_CYBERSECURITY_BASIC"

    if lineage in {
        "CISCO_NETWORKING_CYBERSECURITY_TECHNICIAN",
        "IT_CISCO_NETWORKING_CYBERSECURITY_TECHNICIAN",
    }:
        return "CISCO_NETWORKING_CYBERSECURITY_TECHNICIAN_CERTIFICATE"

    if lineage == "VOCATIONAL_NURSING_CERTIFICATE_OF_COMPLETION":
        return "VOCATIONAL_NURSING_CERTIFICATE"

    return lineage


def build_credential_metadata(requirements: pd.DataFrame) -> pd.DataFrame:
    title_col = (
        "credential_title"
        if "credential_title" in requirements.columns
        else None
    )

    rows = []
    for (catalog_year, credential_id), group in requirements.groupby(
        ["catalog_year", "credential_id"],
        sort=False,
    ):
        title = (
            str(group.iloc[0][title_col])
            if title_col
            else str(credential_id)
        )
        rows.append(
            {
                "catalog_year": str(catalog_year).strip(),
                "credential_id": str(credential_id).strip(),
                "credential_title": title,
                "credential_lineage": derive_lineage(credential_id),
                "inferred_program_hours": infer_program_hours(group),
            }
        )

    meta = pd.DataFrame(rows)
    meta["suppression_family"] = meta.apply(
        audit_suppression_family,
        axis=1,
    )
    return meta


def classify_official_awards(combined: pd.DataFrame) -> pd.DataFrame:
    out = combined.copy()

    keys = list(
        zip(
            out["Curr1ProgramCode"].map(clean),
            out["Major1Code"].map(clean),
            out["DegreeCode"].map(clean),
        )
    )

    status = []
    family = []
    note = []

    for key in keys:
        if key in MAPPED_FAMILIES:
            status.append("MAPPED_SOURCE_SUPPORTED")
            family.append(MAPPED_FAMILIES[key])
            note.append(
                "Mapped to same credential family; award type preserved."
            )
        elif key in NO_AUTOMATIC_MATCH:
            status.append("NO_AUTOMATIC_MATCH")
            family.append("")
            note.append(NO_AUTOMATIC_MATCH[key])
        elif key in REVIEW_REQUIRED:
            status.append("REVIEW_REQUIRED")
            family.append("")
            note.append(REVIEW_REQUIRED[key])
        else:
            raise RuntimeError(
                f"Unclassified official award key encountered: {key!r}"
            )

    out["mapping_status"] = status
    out["suppression_family"] = family
    out["mapping_note"] = note
    return out


def official_crosswalk_frame(official: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in official.groupby(
        ["Curr1ProgramCode", "Major1Code", "DegreeCode"],
        dropna=False,
        sort=True,
    ):
        first = group.iloc[0]
        rows.append(
            {
                "Curr1ProgramCode": key[0],
                "Major1Code": key[1],
                "DegreeCode": key[2],
                "MajorDesc": joined(group["MajorDesc"]),
                "DegreeDesc": joined(group["DegreeDesc"]),
                "official_award_rows": len(group),
                "first_grad_term": group["StudGradTerm"].min(),
                "last_grad_term": group["StudGradTerm"].max(),
                "suppression_family": first["suppression_family"],
                "mapping_status": first["mapping_status"],
                "mapping_note": first["mapping_note"],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    for path in (
        CURRENT_SUMMARY,
        REQUIREMENTS,
        PRIOR_AWARDS,
        NEW_AWARDS,
    ):
        require(path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)

    # ------------------------------------------------------------------
    # Official award corpus
    # ------------------------------------------------------------------
    prior, _ = refresh.read_awards(
        PRIOR_AWARDS,
        preferred_sheet="Initial Enr Cohort Awards",
        source_label="PRIOR_OFFICIAL_AWARDS",
    )
    new, _ = refresh.read_awards(
        NEW_AWARDS,
        preferred_sheet="Summer 2026 Awards",
        source_label="SUMMER_2026_OFFICIAL_AWARDS",
    )

    prior_dedup = prior.drop_duplicates(
        subset=[
            c for c in prior.columns
            if c != "source_dataset"
        ],
        keep="first",
    ).copy()

    official = pd.concat(
        [prior_dedup, new],
        ignore_index=True,
    )

    if len(official) != EXPECTED_OFFICIAL_ROWS:
        raise RuntimeError(
            "Canonical official award count changed: "
            f"actual={len(official):,}, expected={EXPECTED_OFFICIAL_ROWS:,}"
        )

    official["ID"] = official["ID"].map(refresh.clean_text)
    official = classify_official_awards(official)

    official_status_counts = (
        official["mapping_status"].value_counts().to_dict()
    )

    expected_status = {
        "MAPPED_SOURCE_SUPPORTED": EXPECTED_MAPPED_OFFICIAL_ROWS,
        "NO_AUTOMATIC_MATCH": EXPECTED_NO_MATCH_OFFICIAL_ROWS,
        "REVIEW_REQUIRED": EXPECTED_REVIEW_OFFICIAL_ROWS,
    }

    if official_status_counts != expected_status:
        raise RuntimeError(
            "Official mapping-status reconciliation failed. "
            f"actual={official_status_counts}, expected={expected_status}"
        )

    official.to_csv(
        OUTPUT_DIR / "RESTRICTED_canonical_official_awards_with_mapping.csv",
        index=False,
    )

    official_crosswalk = official_crosswalk_frame(official)
    if len(official_crosswalk) != 110:
        raise RuntimeError(
            f"Official key crosswalk expected 110 keys; got {len(official_crosswalk):,}"
        )

    official_crosswalk.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_official_award_suppression_crosswalk.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Six-year credential -> suppression-family crosswalk
    # ------------------------------------------------------------------
    requirements = pd.read_csv(
        REQUIREMENTS,
        dtype=str,
        low_memory=False,
    ).fillna("")

    credential_meta = build_credential_metadata(requirements)

    if len(credential_meta) != EXPECTED_CREDENTIAL_YEARS:
        raise RuntimeError(
            "Staged credential-year count changed: "
            f"actual={len(credential_meta):,}, expected={EXPECTED_CREDENTIAL_YEARS:,}"
        )

    credential_meta.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_audit_suppression_family_crosswalk.csv",
        index=False,
    )

    audit_families = set(credential_meta["suppression_family"])
    mapped_official_families = set(
        official.loc[
            official["mapping_status"].eq("MAPPED_SOURCE_SUPPORTED"),
            "suppression_family",
        ]
    )

    missing_families = mapped_official_families - audit_families
    if missing_families:
        raise RuntimeError(
            "Mapped official suppression families are absent from the "
            "six-year audit family universe: "
            + ", ".join(sorted(missing_families))
        )

    # ------------------------------------------------------------------
    # Build mapped official student + family evidence
    # ------------------------------------------------------------------
    mapped_official = official[
        official["mapping_status"].eq("MAPPED_SOURCE_SUPPORTED")
        & official["suppression_family"].ne("")
    ].copy()

    official_family = (
        mapped_official.groupby(
            ["ID", "suppression_family"],
            dropna=False,
        )
        .agg(
            official_award_count=("StudGradTerm", "size"),
            official_first_grad_term=("StudGradTerm", "min"),
            official_last_grad_term=("StudGradTerm", "max"),
            official_major_codes=("Major1Code", joined),
            official_degree_codes=("DegreeCode", joined),
        )
        .reset_index()
        .rename(columns={"ID": "student_id"})
    )

    if official_family.duplicated(
        ["student_id", "suppression_family"]
    ).any():
        raise RuntimeError(
            "Official student+family evidence is not unique after aggregation."
        )

    # ------------------------------------------------------------------
    # Read current empirical summary; retain COMPLETE combinations only
    # ------------------------------------------------------------------
    complete_parts = []
    total_summary_rows = 0

    for chunk in pd.read_csv(
        CURRENT_SUMMARY,
        dtype=str,
        chunksize=250_000,
        low_memory=False,
    ):
        chunk = chunk.fillna("")
        total_summary_rows += len(chunk)

        complete = chunk[
            chunk["audit_status"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("COMPLETE")
        ].copy()

        if not complete.empty:
            complete_parts.append(complete)

    if total_summary_rows != EXPECTED_CURRENT_ROWS:
        raise RuntimeError(
            "Current empirical summary row count changed: "
            f"actual={total_summary_rows:,}, expected={EXPECTED_CURRENT_ROWS:,}"
        )

    if not complete_parts:
        raise RuntimeError("No COMPLETE rows found in current empirical summary.")

    complete = pd.concat(
        complete_parts,
        ignore_index=True,
    )

    complete["student_id"] = complete["student_id"].map(
        refresh.clean_text
    )
    complete["catalog_year"] = complete["catalog_year"].astype(str).str.strip()
    complete["credential_id"] = complete["credential_id"].astype(str).str.strip()

    before_merge = len(complete)

    complete = complete.merge(
        credential_meta,
        on=["catalog_year", "credential_id"],
        how="left",
        validate="many_to_one",
    )

    if len(complete) != before_merge:
        raise RuntimeError("Credential metadata merge changed COMPLETE row count.")

    missing_meta = complete["suppression_family"].astype(str).str.strip().eq("")
    if missing_meta.any():
        raise RuntimeError(
            "Some COMPLETE rows failed credential metadata/family assignment: "
            f"{int(missing_meta.sum()):,}"
        )

    screened = complete.merge(
        official_family,
        on=["student_id", "suppression_family"],
        how="left",
        validate="many_to_one",
    )

    if len(screened) != before_merge:
        raise RuntimeError("Official-award merge changed COMPLETE row count.")

    screened["official_award_screen_status"] = (
        screened["official_award_count"]
        .notna()
        .map(
            {
                True: "ALREADY_OFFICIALLY_AWARDED",
                False: "NOT_OFFICIALLY_AWARDED",
            }
        )
    )

    suppressed = screened[
        screened["official_award_screen_status"]
        .eq("ALREADY_OFFICIALLY_AWARDED")
    ].copy()

    unsuppressed = screened[
        screened["official_award_screen_status"]
        .eq("NOT_OFFICIALLY_AWARDED")
    ].copy()

    if len(suppressed) + len(unsuppressed) != len(screened):
        raise RuntimeError(
            "Suppressed + unsuppressed does not equal COMPLETE universe."
        )

    screened.to_csv(
        OUTPUT_DIR / "RESTRICTED_complete_combinations_official_award_screen.csv",
        index=False,
    )

    suppressed.to_csv(
        OUTPUT_DIR / "RESTRICTED_already_officially_awarded_complete_combinations.csv",
        index=False,
    )

    unsuppressed.to_csv(
        OUTPUT_DIR / "RESTRICTED_unsuppressed_complete_combinations.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # Unresolved official-award impact, aggregate only.
    # These rows NEVER suppress in this run.
    # ------------------------------------------------------------------
    unresolved = official[
        official["mapping_status"].eq("REVIEW_REQUIRED")
    ][
        [
            "ID",
            "Curr1ProgramCode",
            "Major1Code",
            "DegreeCode",
            "MajorDesc",
            "DegreeDesc",
        ]
    ].drop_duplicates(
        ["ID", "Curr1ProgramCode", "Major1Code", "DegreeCode"]
    )

    unresolved_keys = (
        official_crosswalk[
            official_crosswalk["mapping_status"].eq("REVIEW_REQUIRED")
        ][
            [
                "Curr1ProgramCode",
                "Major1Code",
                "DegreeCode",
                "MajorDesc",
                "DegreeDesc",
                "official_award_rows",
                "mapping_note",
            ]
        ]
        .copy()
    )

    candidate_for_impact = unsuppressed[
        [
            "student_id",
            "suppression_family",
            "credential_id",
            "credential_title",
            "catalog_year",
        ]
    ].copy()

    impact_join = unresolved.merge(
        candidate_for_impact,
        left_on="ID",
        right_on="student_id",
        how="inner",
    )

    if impact_join.empty:
        impact_detail = pd.DataFrame(
            columns=[
                "Curr1ProgramCode",
                "Major1Code",
                "DegreeCode",
                "candidate_suppression_family",
                "affected_candidate_students",
                "candidate_complete_combinations",
                "candidate_credential_ids",
                "candidate_catalog_years",
            ]
        )
    else:
        impact_detail = (
            impact_join.groupby(
                [
                    "Curr1ProgramCode",
                    "Major1Code",
                    "DegreeCode",
                    "suppression_family",
                ],
                dropna=False,
            )
            .agg(
                affected_candidate_students=("ID", "nunique"),
                candidate_complete_combinations=("student_id", "size"),
                candidate_credential_ids=("credential_id", joined),
                candidate_catalog_years=("catalog_year", joined),
            )
            .reset_index()
            .rename(
                columns={
                    "suppression_family": "candidate_suppression_family"
                }
            )
        )

    impact_summary = (
        impact_detail.groupby(
            ["Curr1ProgramCode", "Major1Code", "DegreeCode"],
            dropna=False,
        )
        .agg(
            impacted_candidate_families=(
                "candidate_suppression_family",
                "nunique",
            ),
            affected_candidate_students=(
                "affected_candidate_students",
                "max",
            ),
            candidate_complete_combinations=(
                "candidate_complete_combinations",
                "sum",
            ),
        )
        .reset_index()
        if not impact_detail.empty
        else pd.DataFrame(
            columns=[
                "Curr1ProgramCode",
                "Major1Code",
                "DegreeCode",
                "impacted_candidate_families",
                "affected_candidate_students",
                "candidate_complete_combinations",
            ]
        )
    )

    unresolved_impact = unresolved_keys.merge(
        impact_summary,
        on=["Curr1ProgramCode", "Major1Code", "DegreeCode"],
        how="left",
        validate="one_to_one",
    )

    for col in (
        "impacted_candidate_families",
        "affected_candidate_students",
        "candidate_complete_combinations",
    ):
        unresolved_impact[col] = pd.to_numeric(
            unresolved_impact[col],
            errors="coerce",
        ).fillna(0).astype(int)

    unresolved_impact["has_current_screening_impact"] = (
        unresolved_impact["candidate_complete_combinations"] > 0
    )

    unresolved_impact.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_unresolved_official_award_impact.csv",
        index=False,
    )

    impact_detail.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_unresolved_official_award_candidate_families.csv",
        index=False,
    )

    # ------------------------------------------------------------------
    # FERPA-safe QA
    # ------------------------------------------------------------------
    metrics = pd.DataFrame(
        [
            {"metric": "current_empirical_rows", "value": total_summary_rows},
            {"metric": "empirical_complete_combinations", "value": len(screened)},
            {"metric": "already_officially_awarded_complete_combinations", "value": len(suppressed)},
            {"metric": "unsuppressed_complete_combinations", "value": len(unsuppressed)},
            {"metric": "distinct_complete_students", "value": screened["student_id"].nunique()},
            {"metric": "distinct_suppressed_students", "value": suppressed["student_id"].nunique()},
            {"metric": "distinct_unsuppressed_students", "value": unsuppressed["student_id"].nunique()},
            {"metric": "canonical_official_award_rows", "value": len(official)},
            {"metric": "mapped_official_award_rows", "value": EXPECTED_MAPPED_OFFICIAL_ROWS},
            {"metric": "no_match_official_award_rows", "value": EXPECTED_NO_MATCH_OFFICIAL_ROWS},
            {"metric": "review_required_official_award_rows", "value": EXPECTED_REVIEW_OFFICIAL_ROWS},
            {"metric": "official_mapping_keys", "value": len(official_crosswalk)},
            {"metric": "mapped_official_keys", "value": int((official_crosswalk["mapping_status"] == "MAPPED_SOURCE_SUPPORTED").sum())},
            {"metric": "no_match_official_keys", "value": int((official_crosswalk["mapping_status"] == "NO_AUTOMATIC_MATCH").sum())},
            {"metric": "review_required_official_keys", "value": int((official_crosswalk["mapping_status"] == "REVIEW_REQUIRED").sum())},
            {"metric": "review_keys_with_current_screening_impact", "value": int(unresolved_impact["has_current_screening_impact"].sum())},
        ]
    )

    metrics.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_official_award_screen_metrics.csv",
        index=False,
    )

    by_family = (
        screened.groupby(
            ["suppression_family", "official_award_screen_status"],
            dropna=False,
        )
        .agg(
            complete_combinations=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["suppression_family", "official_award_screen_status"],
            kind="mergesort",
        )
    )

    by_family.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_screen_by_suppression_family.csv",
        index=False,
    )

    by_catalog = (
        screened.groupby(
            ["catalog_year", "official_award_screen_status"],
            dropna=False,
        )
        .agg(
            complete_combinations=("student_id", "size"),
            distinct_students=("student_id", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["catalog_year", "official_award_screen_status"],
            kind="mergesort",
        )
    )

    by_catalog.to_csv(
        OUTPUT_DIR / "FERPA_SAFE_screen_by_catalog.csv",
        index=False,
    )

    print("=" * 100)
    print("OFFICIAL AWARD SCREENING COMPLETE")
    print("=" * 100)
    print("No latest-catalog selection was performed.")
    print("REVIEW_REQUIRED and NO_AUTOMATIC_MATCH awards did not suppress any candidate.")
    print()
    print(f"Current empirical rows:                  {total_summary_rows:,}")
    print(f"Empirical COMPLETE combinations:         {len(screened):,}")
    print(f"Already officially awarded combinations: {len(suppressed):,}")
    print(f"Unsuppressed COMPLETE combinations:      {len(unsuppressed):,}")
    print()
    print("OFFICIAL AWARD MAPPING")
    print(f"Mapped/source-supported:                  {EXPECTED_MAPPED_OFFICIAL_ROWS:,} awards / 84 keys")
    print(f"No automatic match:                      {EXPECTED_NO_MATCH_OFFICIAL_ROWS:,} awards / 18 keys")
    print(f"Review required:                         {EXPECTED_REVIEW_OFFICIAL_ROWS:,} awards / 8 keys")
    print()
    print(
        "Review keys with current screening impact: "
        f"{int(unresolved_impact['has_current_screening_impact'].sum()):,} / 8"
    )

    impacting = unresolved_impact[
        unresolved_impact["has_current_screening_impact"]
    ]

    if not impacting.empty:
        print()
        print("UNRESOLVED KEYS THAT CAN AFFECT CURRENT COMPLETE CANDIDATES")
        print(
            impacting[
                [
                    "Curr1ProgramCode",
                    "Major1Code",
                    "DegreeCode",
                    "official_award_rows",
                    "impacted_candidate_families",
                    "affected_candidate_students",
                    "candidate_complete_combinations",
                ]
            ].to_string(index=False)
        )

    print()
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
