## OPS report generation code

from collections import Counter
from datetime import datetime, timezone
import pandas as pd

def _get(start, key, default=None):
    return start.get(key, default)

def classify_measurement(start: dict):
    # edit/add new experiment type if used
    exp = (start.get("experiment") or "").strip().lower()
    plan = (start.get("plan_name") or "").strip().lower()

    if exp in ("solution", "sol", "high_throughput_solution"):
        return "Solution(HT)"

    if exp in ("hplc", "sec", "sec-saxs", "secsaxs"):
        return "SEC SAXS"

    if exp == "powder":
        return "Fixed Cell"

    if exp in ("tomography", "tomo"):
        return "Tomography"

    if exp in ("scanning", "scan", "mapping"):
        return "Scanning/Raster/Mapping"
        
    if any(k in plan for k in ("raster", "mesh", "dscan", "fly", "map")):
        return "Scanning/Raster/Mapping"

    return "Unclassified"

def get_headers_in_range(db, since, until, extra_query=None):
    """
    extra_query: dict merged into db(...) query, e.g. {'run_id': '...'}.
    """
    q = {}
    if extra_query:
        q.update(extra_query)

    headers = list(db(since=since, until=until, **q))
    return headers

import time

def to_epoch(s):
    # s: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc).timestamp()

def get_headers_in_epoch_range(db, since_iso, until_iso, extra_query=None):
    tmin = to_epoch(since_iso)
    tmax = to_epoch(until_iso)
    q = {"time": {"$gte": tmin, "$lte": tmax}}
    if extra_query:
        q.update(extra_query)
    return list(db(**q))

def build_run_table(headers):
    rows = []
    for h in headers:
        st = h.start
        uid = st.get("uid")
        if not uid:
            continue

        proposal_id = st.get("proposal_id", "UNKNOWN")
        run_id = st.get("run_id", None)
        plan_name = st.get("plan_name", "")
        num_points = st.get("num_points", None)
        t = st.get("time", None)

        sample_name = st.get("sample_name", "")
        holder = st.get("holderName", "")  
        experiment = st.get("experiment", "")

        mtype = classify_measurement(st)

        rows.append({
            "time": pd.to_datetime(t, unit="s", utc=True) if t else pd.NaT,
            "proposal_id": proposal_id,
            "run_id": run_id,
            "uid": uid,
            "measurement_type": mtype,
            "experiment": experiment,
            "plan_name": plan_name,
            "num_points": num_points,
            "holderName": holder,
            "sample_name": sample_name,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["proposal_id", "time"]).reset_index(drop=True)
    return df


def summarize_by_proposal(df_runs, example_uids_per_type=3):
    if df_runs.empty:
        return pd.DataFrame()

    def _uids_for_type(sub, mtype):
        u = sub.loc[sub["measurement_type"] == mtype, "uid"].dropna().astype(str).tolist()
        return ", ".join(u[:example_uids_per_type])

    groups = []
    for pid, sub in df_runs.groupby("proposal_id", sort=True):
        sub = sub.sort_values("time")

        counts = sub["measurement_type"].value_counts().to_dict()
        holders = sorted({h for h in sub["holderName"].dropna().astype(str) if h.strip()})

        counts_str = "; ".join([f"{k}: {v}" for k, v in counts.items()])

        uid_examples = []
        for mtype in sorted(counts.keys()):
            uid_examples.append(f"{mtype} -> {_uids_for_type(sub, mtype)}")
        uid_examples_str = " | ".join(uid_examples)

        groups.append({
            "proposal_id": pid,
            "n_runs": len(sub),
            "first_time_utc": sub["time"].min(),
            "last_time_utc": sub["time"].max(),
            "measurement_counts": counts_str,
            "holders": ", ".join(holders[:20]) + (" ..." if len(holders) > 20 else ""),
            "uid_examples": uid_examples_str,
        })

    return pd.DataFrame(groups).sort_values(["last_time_utc", "proposal_id"], ascending=[False, True])

def generate_measurement_report(db, since, until, extra_query=None, out_prefix="lix_measurements_report"):
    headers = get_headers_in_range(db, since=since, until=until, extra_query=extra_query)
    df_runs = build_run_table(headers)
    df_summary = summarize_by_proposal(df_runs)

    runs_csv = f"{out_prefix}_runs.csv"
    summary_csv = f"{out_prefix}_summary.csv"
    df_runs.to_csv(runs_csv, index=False)
    df_summary.to_csv(summary_csv, index=False)

    try:
        xlsx = f"{out_prefix}.xlsx"
    
        # remove timezone Excel gives error if not
        if "time" in df_runs.columns:
            df_runs["time"] = df_runs["time"].dt.tz_localize(None)
    
        if "first_time_utc" in df_summary.columns:
            df_summary["first_time_utc"] = df_summary["first_time_utc"].dt.tz_localize(None)
    
        if "last_time_utc" in df_summary.columns:
            df_summary["last_time_utc"] = df_summary["last_time_utc"].dt.tz_localize(None)
    
        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            df_summary.to_excel(writer, sheet_name="Summary_by_proposal", index=False)
            df_runs.to_excel(writer, sheet_name="All_runs", index=False)

    except Exception as e:
        print("Excel export skipped:", e)

    return df_summary, df_runs

import pandas as pd

EXCEL_COLS = [
    "PI",
    "Proposal_id",
    "No of Runs",
    "Solution(HT)",
    "Fixed Cell",
    "SEC SAXS",
    "Scanning/Raster/Mapping",
    "Unclassified",
]

def make_excel_summary(df_runs: pd.DataFrame) -> pd.DataFrame:
    if df_runs.empty:
        return pd.DataFrame(columns=EXCEL_COLS)

    df = df_runs.copy()
    if "Proposal_id" not in df.columns and "proposal_id" in df.columns:
        df["Proposal_id"] = df["proposal_id"]
    if "PI" not in df.columns:
        df["PI"] = ""

    if "measurement_type" not in df.columns:
        raise ValueError("df_runs must contain a 'measurement_type' column.")

    # Count runs per proposal and measurement_type
    counts = (
        df.groupby(["Proposal_id", "measurement_type"])
          .size()
          .unstack(fill_value=0)
    )


    totals = df.groupby("Proposal_id").size().rename("No of Runs")


    pi = (
        df.groupby("Proposal_id")["PI"]
          .apply(lambda s: next((x for x in s.astype(str) if x.strip()), ""))
          .rename("PI")
    )
    out = pd.concat([pi, totals, counts], axis=1).reset_index()
    out = out.rename(columns={"Proposal_id": "Proposal_id"})

    for c in EXCEL_COLS:
        if c not in out.columns:
            out[c] = 0 if c not in ("PI", "Proposal_id") else ""

    out = out[EXCEL_COLS].sort_values("Proposal_id").reset_index(drop=True)

    return out

def export_excel_report(df_summary: pd.DataFrame, filename: str = "LiX_report.xlsx"):
    for col in df_summary.columns:
        if pd.api.types.is_datetime64tz_dtype(df_summary[col]):
            df_summary[col] = df_summary[col].dt.tz_localize(None)

    with pd.ExcelWriter(filename, engine="openpyxl") as w:
        df_summary.to_excel(w, sheet_name="Report", index=False)

    print("Wrote:", filename)
