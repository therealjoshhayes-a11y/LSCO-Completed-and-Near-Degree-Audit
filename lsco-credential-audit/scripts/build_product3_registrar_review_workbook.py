from __future__ import annotations
"""Build the LSCO restricted Product 3 registrar review workbook locally.

Run from lsco-credential-audit root. Never upload generated student-level data.
Requires: pip install artifact-tool
"""
import csv
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from artifact_tool import Workbook, SpreadsheetFile

ROOT = Path.cwd()
REPORTING = ROOT / "data/processed/reporting"
PREFIX = "final_unawarded_complete_"
FINAL = "RESTRICTED_FINAL_unawarded_complete_awards.csv"
EXPIRED = "RESTRICTED_historical_complete_expired_catalog_candidates.csv"
REVIEWS = "RESTRICTED_unresolved_awardability_reviews.csv"
TRACE = "RESTRICTED_final_selection_trace.csv"
GREEN = "#145A32"
TEAL = "#146C59"
PALE = "#EAF3ED"
GOLD = "#FFF0CA"
WHITE = "#FFFFFF"
INK = "#172B22"

def fail(message: str):
    raise RuntimeError(message)

def read_rows(path: Path):
    if not path.is_file(): fail(f"Missing local source: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

def val(row, *names):
    for name in names:
        if str(row.get(name, "")).strip():
            return str(row[name]).strip()
    return ""

def chosen_output():
    dirs = sorted(
        (d for d in REPORTING.glob(PREFIX + "*") if d.is_dir() and (d / FINAL).exists()
         and (d / EXPIRED).exists() and (d / TRACE).exists()),
        key=lambda d: d.name,
        reverse=True
    )
    if not dirs: fail("No final selector output exists. Run select_final_unawarded_complete_awards_v3.py first.")
    return dirs[0]

def add_sheet(wb, name, headers, data, widths=None):
    sh = wb.worksheets.add(name)
    n = len(headers)
    last = max(1, len(data) + 1)
    sh.get_range_by_indexes(0, 0, len(data)+1, n).values = [headers] + data
    sh.get_range_by_indexes(0, 0, 1, n).format = {
        "fill": GREEN, "font": {"bold": True, "color": WHITE},
        "row_height": 31, "wrap_text": True,
        "vertical_alignment": "center",
    }
    sh.freeze_panes.freeze_rows(1)
    for j, width in enumerate(widths or [21]*n):
        sh.get_range_by_indexes(0, j, last, 1).format.column_width = width
    if data:
        sh.get_range_by_indexes(1, 0, len(data), n).format.row_height = 21
        # Filterable release sheets.
        try:
            sh.tables.add(f"A1:{excelcol(n)}{last}", True, "LSCO_" + name.replace(" ","").replace("-","")[:20])
        except Exception as exc:
            print(f"Table formatting unavailable for {name}: {exc}")
    return sh

def excelcol(n):
    out=""
    while n:
        n,r=divmod(n-1,26)
        out=chr(65+r)+out
    return out

def main():
    source=chosen_output()
    awards=read_rows(source/FINAL)
    expired=read_rows(source/EXPIRED)
    reviews=read_rows(source/REVIEWS)
    trace=read_rows(source/TRACE)
    if not awards: fail("Final awards file is empty.")
    ids=[val(x,"student_id") for x in awards]
    if any(not x for x in ids): fail("Final recommendation missing student_id.")
    if len({(val(x,"student_id"),val(x,"candidate_lineage")) for x in awards}) != len(awards):
        fail("Student+lineage must be unique in the final recommendation list.")
    if any(val(x,"catalog_year")=="2021-2022" for x in awards):
        fail("Expired 2021-2022 recommendations detected: refusing workbook release.")
    if len(awards)!=367 or len(set(ids))!=326 or len(expired)!=117:
        fail(f"Unexpected release population: {len(awards)} awards, {len(set(ids))} students, {len(expired)} expired. Verify baseline first.")
    coll={val(x,"final_product1_selection_status") for x in trace}
    if "HISTORICAL_COMPLETE_CATALOG_EXPIRED" not in coll:
        fail("Selection trace does not document catalog expiration.")
    variance=sum(1 for x in awards if val(x,"conferral_temporal_eligibility")=="PASS_ANALYST_APPROVED_VARIANCE")
    # Fail closed if variance metadata never propagated; all selected 2026-27
    # rows must carry the explicit analyst-approved flag.
    modern=[x for x in awards if val(x,"catalog_year")=="2026-2027"]
    if any(val(x,"conferral_temporal_eligibility")!="PASS_ANALYST_APPROVED_VARIANCE" for x in modern):
        fail("2026-2027 records missing analyst-approved variance designation.")
    if len(modern)!=variance: fail("Variance count mismatch.")

    wb=Workbook.create()
    overview=wb.worksheets.add("RELEASE SUMMARY")
    rows=[
      ["LAMAR STATE COLLEGE ORANGE • PRODUCT 3",""],
      ["Unawarded-but-complete credential review",""],
      ["Evaluation date","2026-10-08"],
      ["Release classification","RESTRICTED • FERPA • Institutional review only"],
      ["Source selector directory",str(source)],
      ["Academic-complete recommendations",len(awards)],
      ["Distinct students",len(set(ids))],
      ["Certificate recommendations",sum(val(a,"candidate_award_category")=="CERTIFICATE" for a in awards)],
      ["Associate recommendations",sum(val(a,"candidate_award_category")=="ASSOCIATE" for a in awards)],
      ["Expired historical PASS combinations retained",len(expired)],
      ["Unresolved ordinary/multiple-award reviews",len(reviews)],
      ["Recommendations under analyst-approved catalog variance",variance],
      ["2026–2027 catalog source verification","OUTSTANDING — variance is NOT a verified deadline"],
      ["Action required","Registrar must verify individual awards before conferral"],
      ["Release approval","PENDING REGISTRAR REVIEW"],
      ["Source timestamp",datetime.now().strftime("%Y-%m-%d %H:%M")],
    ]
    overview.get_range("A1:B16").values=rows
    overview.get_range("A1:B2").format={"fill":GREEN,"font":{"bold":True,"color":WHITE},"row_height":32}
    overview.get_range("A3:A16").format={"font":{"bold":True,"color":INK},"fill":PALE,"row_height":26}
    overview.get_range("B3:B16").format.row_height=26
    overview.get_range("B13:B15").format={"fill":GOLD,"font":{"bold":True,"color":INK},"wrap_text":True,"row_height":30}
    overview.get_range("A:A").format.column_width=53
    overview.get_range("B:B").format.column_width=95
    overview.freeze_panes.freeze_rows(2)

    roster_headers=["Student ID","Catalog","Credential ID","Credential / Title",
       "Canonical Lineage","Award Category","Academic Status","Catalog Status",
       "Catalog Deadline","Temporal Authorization","Variance Disclosure",
       "Registrar Decision","Reviewer Notes","Verified By","Verification Date"]
    roster=[]
    for a in awards:
        temporal=val(a,"conferral_temporal_eligibility")
        roster.append([val(a,"student_id"),val(a,"catalog_year"),val(a,"credential_id"),
            val(a,"credential_title","awardability_credential_title"),val(a,"candidate_lineage"),
            val(a,"candidate_award_category"),val(a,"awardability_status"),
            val(a,"catalog_temporal_status"),val(a,"catalog_expiration_date"),temporal,
            "2026-27 SOURCE PENDING; ANALYST APPROVED" if temporal=="PASS_ANALYST_APPROVED_VARIANCE" else "",
            "PENDING","", "", ""])
    roster.sort(key=lambda x:(x[0],x[1],x[4]))
    sheet=add_sheet(wb,"AWARD ROSTER",roster_headers,roster,[18,16,36,40,40,18,38,20,18,30,43,20,42,22,20])
    if roster:
        try:
            sheet.get_range(f"L2:L{len(roster)+1}").data_validation={"rule":{"type":"list","values":["PENDING","APPROVE","HOLD","REJECT","FOLLOW UP"]}}
        except Exception as exc:print("Decision validation not available:",exc)
    exp_headers=["Student ID","Catalog","Credential ID","Canonical Lineage","Award Category",
                 "Temporal Status","Catalog Deadline","Disposition","Reviewer Notes"]
    exp_data=[[val(x,"student_id"),val(x,"catalog_year"),val(x,"credential_id"),
        val(x,"candidate_lineage"),val(x,"candidate_award_category"),
        val(x,"catalog_temporal_status"),val(x,"catalog_expiration_date"),
        val(x,"historical_completion_disposition"),""] for x in expired]
    add_sheet(wb,"EXPIRED - NOT AWARDABLE",exp_headers,exp_data,[18,16,38,39,18,23,19,57,36])
    review_headers=["Student ID","Catalog","Credential ID","Canonical Lineage","Category",
        "Review Status","Review Reason","Reviewer Decision","Reviewer Notes"]
    review_data=[[val(x,"student_id"),val(x,"catalog_year"),val(x,"credential_id"),
        val(x,"candidate_lineage"),val(x,"candidate_award_category"),
        val(x,"multiple_award_gate_status"),val(x,"multiple_award_gate_reason"),
        "PENDING",""] for x in reviews]
    add_sheet(wb,"OPEN REVIEWS",review_headers,review_data,[18,16,35,38,17,36,52,22,37])

    count=Counter((val(a,"catalog_year"),val(a,"candidate_award_category")) for a in awards)
    bycat=[[catalog,category,n] for (catalog,category),n in sorted(count.items())]
    add_sheet(wb,"COUNTS BY CATALOG",["Catalog","Award Category","Recommendations"],bycat,[20,24,25])
    add_sheet(wb,"RELEASE CHECKS",["Check","Finding","Disposition"],[
      ["Final roster",f"{len(awards)} recommendations; {len(set(ids))} unique students","PASS"],
      ["2021-22 catalog","No 2021–2022 recommendations in final roster","PASS"],
      ["Expired candidates",f"{len(expired)} preserved outside release roster","PASS"],
      ["2026-27 analyst variance",f"{variance} recommendation(s) explicitly flagged","APPROVED FOR ANALYTICAL REVIEW"],
      ["2026-27 catalog expiration source","Not independently verified","OPEN SOURCE UPDATE"],
      ["Registrar conferment authority","Not conferred by audit alone","REVIEW REQUIRED"],
      ["Privacy","Contains restricted student record identifiers","INTERNAL ONLY"],
    ],[38,75,34])

    output=source/"RESTRICTED_LSCO_Product3_Registrar_Review_20261008.xlsx"
    SpreadsheetFile.export_xlsx(wb).save(str(output))
    if not output.is_file() or output.stat().st_size<5000:
        fail("Workbook export did not produce a valid-size file.")
    print("PRODUCT 3 REGISTRAR REVIEW WORKBOOK CREATED")
    print(f"Workbook: {output}")
    print(f"Students: {len(set(ids))}; Recommendations: {len(awards)}")
    print(f"Expired excluded: {len(expired)}; Open reviews: {len(reviews)}")
    print(f"Analyst-approved 2026-27 variance recommendations: {variance}")
    print("Release status: PENDING REGISTRAR REVIEW; FERPA RESTRICTED.")

if __name__=="__main__":
    main()
