import glob
import os
from datetime import datetime

import pandas as pd

bug_codes = {
"ACNT 1335","ACNT 2311","AGMG 1318","AGMG 2306","AGMG 2312","ARTC 2313","ARTC 2333","ARTC 2348",
"BNKG 1303","BNKG 1340","BNKG 1345","BNKG 1356","BNKG 1359","BUSA 1313","BUSG 1304","BUSG 1307",
"CHEF 1301","CJSA 1308","CJSA 1330","CJSA 1348","CJSA 1400","CJSA 2323","CNBT 1350","COMM 2311",
"COMM 2330","COSC 1337","COSC 2325","CPMT 1345","CRTR 1310","DATN 1370","DATN 1377","EECT 1300",
"ELPT 1325","ELPT 1329","ELPT 1357","ELPT 1445","EMSP 1208","EMSP 1355","EMSP 1356","EMSP 1362",
"EMSP 2243","EMSP 2262","EMSP 2264","EMSP 2305","EMSP 2306","EMSP 2330","EMSP 2434","EMSP 2444",
"EPCT 1301","EPCT 1305","EPCT 1341","EPCT 1349","EPCT 2489","HART 1341","HART 1403","HYDR 1305",
"ITSC 1316","ITSC 2339","ITSE 1445","ITSY 2301","ITSY 2343","LMGT 1321","LMGT 1323","LMGT 1325",
"LMGT 1345","LMGT 2334","LMGT 2388","MDCA 1309","MDCA 1317","MDCA 1321","MDCA 1343","MDCA 1361",
"NAUT 1264","NAUT 1345","NAUT 1375","NAUT 2205","NAUT 2274","NAUT 2315","PFPB 1323","PFPB 2308",
"PHRA 1243","PHYS 2426","PTAC 1302","PTAC 1408","RBTC 1309","WLDG 1453","WLDG 2435","WLDG 2453",
}

def stamp(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")

current_input = r"data\processed\normalized_actual_student_course_history.csv"
print("Current audit input file modified:", stamp(current_input))

chunk_files = sorted(glob.glob(r"data\processed\full_actual_audit\chunks\chunk_*_student_course_history.csv"))
print("Chunk input snapshots found:", len(chunk_files))
if chunk_files:
    print("First chunk written:", stamp(chunk_files[0]))
    print("Last chunk written: ", stamp(chunk_files[-1]))

seen = set()
for f in chunk_files:
    codes = pd.read_csv(f, dtype=str, usecols=["course_code"])["course_code"].dropna().str.strip()
    seen.update(codes)
print()
print("Distinct course codes across all run-time chunk inputs:", len(seen))
found = sorted(bug_codes & seen)
absent = sorted(bug_codes - seen)
print("Bug codes PRESENT in run-time inputs:", len(found))
print("Bug codes ABSENT from run-time inputs:", len(absent))
print()
if absent:
    print("Absent at run time (data-vintage confirmed for these):")
    print(absent)
if found:
    print()
    print("Present at run time yet still 100pct missed (true engine bugs, if any):")
    print(found)

today = pd.read_csv(current_input, dtype=str, usecols=["course_code"])["course_code"].dropna().str.strip()
today_set = set(today)
print()
print("Distinct codes in TODAY's input:", len(today_set))
print("Codes in today's input that were absent from run-time inputs:", len(today_set - seen))
