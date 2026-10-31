# -*- coding: utf-8 -*-
"""
==========================================================================================
 CULTURAL COMMITTEE VOLUNTEER ALLOCATION SYSTEM  (Kala Fest pilot, TAPMI)
 Single-file Python project - BBAH, Introduction to Python Programming (BBAT5E07)
==========================================================================================
 HOW TO RUN
     pip install numpy pandas matplotlib
     python kala_fest_allocator.py            -> opens http://localhost:5000
 Keep "volunteers_CSV.csv", "tapmi_logo.png" and (optionally) "icon.jpeg" in the same folder.

 LIBRARIES USED  (only those named / implied by the course outline)
 ------------------------------------------------------------------------------------------
  NumPy       (Sessions 21-22)  arrays, scores, cost matrix, random numbers, statistics
  Pandas      (Sessions 23-24)  reading + cleaning the CSV, grouping, CSV export
  Matplotlib  (Sessions 19-20)  all dashboard charts (rendered to PNG, shown in the page)
  Built-in Python (no install; Sessions 1-18, 25-30): json, os, sys, io, re, math, copy, time,
      base64, hashlib, secrets, threading, webbrowser, http.server (serves the dashboard).
  NOT used (they were in the earlier version but are outside the course): PuLP, Flask,
      Flask-CORS, Werkzeug, Gunicorn, psycopg, pg8000, openpyxl, pytest, Seaborn.

 COURSE TOPIC  ->  WHERE IT APPEARS IN THIS FILE
 ------------------------------------------------------------------------------------------
  Numbers & strings ....... time parsing, formatting, ceil() staffing formula (section 3)
  Lists/tuples/sets/dicts . volunteers, requirements, eligibility sets, state (sections 2-6)
  Decisions & loops ....... eligibility rules, greedy loop, routing (sections 4-6, 9)
  Input & output .......... CSV read, JSON state file, console messages (sections 2, 8)
  Functions ............... every step is a small reusable function
  Recursion ............... merge_sort() and binary_search() (section 1)
  Visualization ........... Matplotlib charts (section 7)
  NumPy / Pandas .......... sections 2, 5, 7
  Objects & inheritance ... BaseAllocator -> GreedyAllocator / OptimalAllocator (section 5)
  Files & exceptions ...... load_state/save_state, ApiError, try/except (sections 2, 8, 9)
  Sorting & searching ..... merge_sort() ranks candidates; binary_search() finds volunteers

 DESIGN RULE: all assignment decisions are made by the Python code below. The browser page
 only shows results and sends the organizer's clicks to Python.
==========================================================================================
"""
import base64, copy, hashlib, io, json, math, os, re, secrets, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                 # draw charts to memory, no window needed
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(os.environ.get("STATE_DIR", HERE), "kala_fest_state.json")
PORT = int(os.environ.get("PORT", 5000))      # hosts (Render, Railway...) set PORT themselves
HOSTED = "PORT" in os.environ                 # on a host: do not try to open a browser
ORANGE = "#E8752E"

# ---------------------------------------------------------------- 0. CONFIGURATION
# All policy numbers live in ONE place (never scattered in the code).
CONFIG = {
    "priority_weight": {"critical": 100, "high": 60, "normal": 30},
    "tier_order": {"critical": 0, "high": 1, "normal": 2},
    "pref_bonus_max": 8,        # best preference rank earns +8, then -2 per rank (min 2)
    "skill_fit_bonus": 3,       # per preferred skill held (capped at 2 skills)
    "experience_bonus": {0: 0, 1: 1, 2: 2, 3: 3},
    "fairness_decay": 0.02,     # later slots of one role are worth 2% less -> spreads people
    "big_cost": 1_000_000.0,    # makes forbidden (ineligible) pairs unattractive
}

def validate_config(cfg):
    """Preferences must never outweigh staffing priority."""
    weights = sorted(cfg["priority_weight"].values())
    smallest_gap = min(b - a for a, b in zip(weights, weights[1:]))
    max_bonus = cfg["pref_bonus_max"] + 2 * cfg["skill_fit_bonus"] + max(cfg["experience_bonus"].values())
    if max_bonus >= smallest_gap:
        raise ValueError("Soft bonuses (%s) must stay below the priority gap (%s)" % (max_bonus, smallest_gap))
validate_config(CONFIG)

# Kala Fest requirements. 'skills' are MANDATORY (all must be held). 'start'/'end' is the
# working window (hours, 24h clock). source = fixed headcount or workload formula.
DEFAULT_REQUIREMENTS = [
 dict(id="R01", dept="Event Planning & Execution", role="Event coordinator", headcount=10, priority="critical",
      skills=["Event Coordination"], preferred=["Team Leadership"], pref_label="Event Planning & Execution", start=11, end=15, source="fixed"),
 dict(id="R02", dept="Stage & Backstage", role="Stage crew", headcount=6, priority="high",
      skills=["Stage & Backstage Management"], preferred=["Props & Decoration"], pref_label="Stage/ Backstage Management", start=11, end=15, source="fixed"),
 dict(id="R03", dept="Participant Coordination", role="Artist desk", headcount=5, priority="high",
      skills=["Participant Coordination"], preferred=[], pref_label="Artist/ Participant Coordination", start=11, end=15, source="workload",
      workload=120, service_min=1.5, peak_min=30),
 dict(id="R04", dept="Marketing & Promotions", role="Promotions", headcount=4, priority="high",
      skills=["Marketing & Promotions"], preferred=["Social Media & Content Creation", "Branding & Visual Design"], pref_label="Marketing & Promotions", start=11, end=15, source="fixed"),
 dict(id="R05", dept="Logistics", role="Logistics crew", headcount=5, priority="high",
      skills=["Logistics"], preferred=["Vendor Management"], pref_label="Logistics", start=11, end=15, source="fixed"),
 dict(id="R06", dept="Public Relations", role="PR and outreach", headcount=3, priority="normal",
      skills=["Public Relations & Outreach"], preferred=[], pref_label="Public Relations & Outreach", start=11, end=15, source="fixed"),
 dict(id="R07", dept="Sponsorship", role="Sponsor liaison", headcount=3, priority="normal",
      skills=["Sponsorship & Fundraising"], preferred=[], pref_label="Sponsorships", start=11, end=15, source="fixed"),
 dict(id="R08", dept="Finance", role="Budget desk", headcount=2, priority="normal",
      skills=["Budgeting & Finance"], preferred=[], pref_label="Finance & Budgeting", start=11, end=15, source="fixed"),
 dict(id="R09", dept="Vendor Management", role="Vendor desk", headcount=3, priority="normal",
      skills=["Vendor Management"], preferred=[], pref_label="Vendor Management", start=11, end=15, source="fixed"),
 dict(id="R10", dept="Hospitality", role="Guest hosts", headcount=3, priority="normal",
      skills=["Hospitality & Guest Handling"], preferred=[], pref_label="Hospitality", start=11, end=15, source="fixed"),
 dict(id="R11", dept="IT Support", role="Tech support", headcount=2, priority="high",
      skills=["Technical Support"], preferred=["Sound & Audio Editing"], pref_label="IT Support", start=11, end=15, source="fixed"),
 dict(id="R12", dept="Design & Branding", role="Designers", headcount=3, priority="normal",
      skills=["Branding & Visual Design"], preferred=["Photography & Video Editing"], pref_label="Marketing & Promotions", start=11, end=15, source="fixed"),
]

# ---------------------------------------------------------------- 1. RECURSION, SORTING, SEARCHING
def merge_sort(items, key):
    """Recursive merge sort (Sessions 17-18, 29-30). Stable, so ties keep input order."""
    if len(items) <= 1:
        return list(items)
    mid = len(items) // 2
    left, right = merge_sort(items[:mid], key), merge_sort(items[mid:], key)
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if key(left[i]) <= key(right[j]):
            out.append(left[i]); i += 1
        else:
            out.append(right[j]); j += 1
    return out + left[i:] + right[j:]

def binary_search(sorted_ids, target):
    """Recursive binary search over a sorted list of IDs; returns index or -1."""
    def go(lo, hi):
        if lo > hi:
            return -1
        mid = (lo + hi) // 2
        if sorted_ids[mid] == target:
            return mid
        return go(mid + 1, hi) if sorted_ids[mid] < target else go(lo, mid - 1)
    return go(0, len(sorted_ids) - 1)

# ---------------------------------------------------------------- 2. DATA LOADING + CLEANING (Pandas)
def hhmm_to_hours(text):
    h, m = str(text).strip().split(":")
    return int(h) + int(m) / 60.0

def split_list(text):
    return [p.strip() for p in str(text).split(",") if p.strip()]

def find_csv():
    names = ["volunteers_CSV.csv", "volunteers CSV.csv", "volunteers.csv"]
    if len(sys.argv) > 1:
        names.insert(0, sys.argv[1])
    for n in names:
        for base in (HERE, os.getcwd()):
            p = n if os.path.isabs(n) else os.path.join(base, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("volunteers_CSV.csv not found next to this script.")

def load_volunteers(path):
    """Collect -> Clean -> Categorize. Returns (volunteer list sorted by id, cleaning report)."""
    df = pd.read_csv(path)
    report = {"rows_read": int(len(df)), "duplicates_removed": 0, "invalid_removed": 0, "notes": []}
    df.columns = [c.strip() for c in df.columns]
    before = len(df)
    df = df.drop_duplicates(subset="volunteer_id")
    report["duplicates_removed"] = before - len(df)
    vols = []
    for _, r in df.iterrows():
        try:
            hours = float(r["max_hours"])
            start, end = hhmm_to_hours(r["availability_start"]), hhmm_to_hours(r["availability_end"])
            if not (0 < hours <= 24) or end <= start:
                raise ValueError("range")
        except (ValueError, TypeError):                      # exceptions session
            report["invalid_removed"] += 1
            report["notes"].append("Dropped %s: invalid hours/availability" % r.get("volunteer_id"))
            continue
        digits = re.findall(r"\d+", str(r["experience_level"]))
        vols.append({
            "id": str(r["volunteer_id"]).strip(), "name": str(r["name"]).strip(),
            "skills": split_list(r["skills"]), "prefs": split_list(r["department_preference"]),
            "avail_start": start, "avail_end": end, "max_hours": hours,
            "exp": min(int(digits[0]) if digits else 0, 3), "active": True, "simulated": False,
            "email": ".".join(str(r["name"]).lower().split()) + "@tapmi.edu.in"})
    vols = merge_sort(vols, key=lambda v: v["id"])           # sorted -> binary search works
    report["clean_rows"] = len(vols)
    return vols, report

# ---------------------------------------------------------------- 3. CAPACITY CALCULATOR
def required_staff(workload, service_min, peak_min):
    """Required Staff = ceil(Workload x Service Time / Peak Window); units: minutes."""
    for name, val in (("workload", workload), ("service time", service_min), ("peak window", peak_min)):
        if val is None or not isinstance(val, (int, float)) or val < 0:
            raise ApiError(422, "VALIDATION_ERROR", "%s must be a non-negative number" % name)
    if peak_min <= 0:
        raise ApiError(422, "VALIDATION_ERROR", "Peak window must be greater than zero")
    return math.ceil(workload * service_min / peak_min)

# ---------------------------------------------------------------- 4. ELIGIBILITY (hard rules)
def ineligible_reasons(vol, req):
    """Return [(code, text)]; empty list = eligible. Shared by every algorithm."""
    why = []
    if not vol["active"]:
        why.append(("inactive", "volunteer is inactive"))
    missing = [s for s in req["skills"] if s not in vol["skills"]]
    if missing:
        why.append(("skill", "missing mandatory skill: " + ", ".join(missing)))
    if vol["avail_start"] > req["start"] or vol["avail_end"] < req["end"]:
        why.append(("window", "not available for the %02d:00-%02d:00 window" % (req["start"], req["end"])))
    if vol["max_hours"] < (req["end"] - req["start"]):
        why.append(("hours", "max hours %.1f is below the %.1f hour duty" % (vol["max_hours"], req["end"] - req["start"])))
    return why

def bonus_score(vol, req):
    """Soft factors only: preference + skill fit + experience (always far below priority gaps)."""
    pref = 0
    if req["pref_label"] in vol["prefs"]:
        pref = max(2, CONFIG["pref_bonus_max"] - 2 * vol["prefs"].index(req["pref_label"]))
    fit = CONFIG["skill_fit_bonus"] * min(2, sum(1 for s in req["preferred"] if s in vol["skills"]))
    return pref + fit + CONFIG["experience_bonus"][vol["exp"]]

class Context:
    """One immutable snapshot used by BOTH algorithms (fair comparison)."""
    def __init__(self, vols, reqs):
        self.vols = {v["id"]: v for v in vols}
        self.reqs = {r["id"]: r for r in reqs}
        self.req_list = list(reqs)
        self.elig = {r["id"]: [v["id"] for v in vols if not ineligible_reasons(v, r)] for r in reqs}
        self.bonus = {(r["id"], v["id"]): bonus_score(v, r) for r in reqs for v in vols if v["id"] in self.elig[r["id"]]}

# ---------------------------------------------------------------- 5. ALLOCATION ENGINE (classes + inheritance)
class BaseAllocator:
    name = "base"
    label = "Base"
    def run(self, ctx):
        t0 = time.perf_counter()
        pairs, objective, status = self.solve(ctx)
        ms = (time.perf_counter() - t0) * 1000
        return {"algorithm": self.name, "label": self.label, "status": status, "objective": round(float(objective), 2),
                "runtime_ms": round(ms, 2),
                "assignments": [{"req_id": r, "vol_id": v, "source": self.name, "override": False, "reason": ""} for r, v in pairs]}
    def solve(self, ctx):
        raise NotImplementedError

class GreedyAllocator(BaseAllocator):
    """Transparent baseline: Critical -> High -> Normal, best-scoring eligible volunteer first."""
    name, label = "greedy", "Greedy baseline"
    def solve(self, ctx):
        used, pairs, total = set(), [], 0
        ordered = merge_sort(ctx.req_list, key=lambda r: (CONFIG["tier_order"][r["priority"]], r["id"]))
        for req in ordered:
            for _slot in range(req["headcount"]):
                cands = [v for v in ctx.elig[req["id"]] if v not in used]
                if not cands:
                    break                                         # honest vacancy
                ranked = merge_sort(cands, key=lambda v: (-ctx.bonus[(req["id"], v)], v))
                best = ranked[0]
                used.add(best); pairs.append((req["id"], best)); total += ctx.bonus[(req["id"], best)]
        return pairs, total, "Completed"

def hungarian_min(cost):
    """Exact minimum-cost assignment (Hungarian algorithm) using NumPy; needs rows <= cols."""
    n, m = cost.shape
    INF = 1e18
    u, v = np.zeros(n + 1), np.zeros(m + 1)
    p, way = np.zeros(m + 1, dtype=int), np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = np.full(m + 1, INF), np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = cost[i0 - 1, :] - u[i0] - v[1:]
            free = ~used[1:]
            better = free & (cur < minv[1:])
            minv[1:][better] = cur[better]
            way[1:][better] = j0
            masked = np.where(free, minv[1:], INF)
            j1 = int(np.argmin(masked)) + 1
            delta = masked[j1 - 1]
            u[p[used]] += delta
            v[used] -= delta
            minv[~used] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0:
                break
    return {int(p[j]) - 1: j - 1 for j in range(1, m + 1) if p[j] != 0}

class OptimalAllocator(BaseAllocator):
    """Global optimum of the balanced objective (assignment problem solved exactly).
    Same hard rules as greedy; vacancies are allowed; never invents a volunteer."""
    name, label = "optimal", "Optimal (global)"
    def solve(self, ctx):
        positions = [(r, k) for r in ctx.req_list for k in range(r["headcount"])]
        cols = sorted({v for r in ctx.req_list for v in ctx.elig[r["id"]]})
        if not positions or not cols:
            return [], 0.0, "Completed (nothing to assign)"
        profit = np.zeros((len(positions), len(cols)))
        allowed = np.zeros_like(profit, dtype=bool)
        index = {v: j for j, v in enumerate(cols)}
        for i, (r, k) in enumerate(positions):
            base = CONFIG["priority_weight"][r["priority"]] * (1 - CONFIG["fairness_decay"] * k)
            for v in ctx.elig[r["id"]]:
                profit[i, index[v]] = base + ctx.bonus[(r["id"], v)]
                allowed[i, index[v]] = True
        cost = np.where(allowed, -profit, CONFIG["big_cost"])
        try:
            if cost.shape[0] <= cost.shape[1]:
                match = hungarian_min(cost)
            else:
                inv = hungarian_min(cost.T)
                match = {row: col for col, row in inv.items()}
        except Exception as e:                                   # solver failure is reported, not hidden
            return [], 0.0, "Failed: %s" % e
        pairs, total = [], 0.0
        for i, j in match.items():
            if allowed[i, j]:                                    # drop forced forbidden pairs = vacancy
                pairs.append((positions[i][0]["id"], cols[j])); total += profit[i, j]
        pairs = merge_sort(pairs, key=lambda x: (x[0], x[1]))
        return pairs, total, "Optimal"

# ---------------------------------------------------------------- 6. METRICS, SHORTAGES, RECOMMENDATIONS
def compute_metrics(ctx, assignments):
    counts = {r["id"]: 0 for r in ctx.req_list}
    for a in assignments:
        counts[a["req_id"]] += 1
    req_total = sum(r["headcount"] for r in ctx.req_list)
    got = sum(counts.values())
    coverage = np.array([counts[r["id"]] / r["headcount"] if r["headcount"] else 1.0 for r in ctx.req_list])
    pw = {r["id"]: CONFIG["priority_weight"][r["priority"]] for r in ctx.req_list}
    pcov = sum(pw[r["id"]] * counts[r["id"]] for r in ctx.req_list) / max(1, sum(pw[r["id"]] * r["headcount"] for r in ctx.req_list))
    pref_hits = sum(1 for a in assignments if ctx.reqs[a["req_id"]]["pref_label"] in ctx.vols[a["vol_id"]]["prefs"])
    assigned_ids = {a["vol_id"] for a in assignments}
    free = {v for r in ctx.req_list for v in ctx.elig[r["id"]]} - assigned_ids
    bad_skill = bad_cap = 0
    for a in assignments:
        if a.get("override"):
            continue
        why = {c for c, _ in ineligible_reasons(ctx.vols[a["vol_id"]], ctx.reqs[a["req_id"]])}
        bad_skill += "skill" in why
        bad_cap += bool(why & {"window", "hours", "inactive"})
    return {"required": req_total, "allocated": got, "vacant": req_total - got,
            "coverage_pct": round(100 * got / max(1, req_total), 1),
            "priority_coverage_pct": round(100 * pcov, 1),
            "pref_fit_pct": round(100 * pref_hits / max(1, got), 1),
            "min_dept_coverage_pct": round(100 * float(coverage.min()), 1) if len(coverage) else 0,
            "fairness_std": round(float(coverage.std()), 3),
            "eligible_unassigned": len(free), "skill_violations": bad_skill, "capacity_violations": bad_cap,
            "by_req": counts}

def vacancy_reasons(ctx, assignments):
    """Explain every vacancy with evidence (Section: shortage logic)."""
    counts = {r["id"]: 0 for r in ctx.req_list}
    taken = {a["vol_id"] for a in assignments}
    for a in assignments:
        counts[a["req_id"]] += 1
    out = []
    for r in ctx.req_list:
        vac = r["headcount"] - counts[r["id"]]
        if vac <= 0:
            continue
        active = [v for v in ctx.vols.values() if v["active"]]
        holders = [v for v in active if all(s in v["skills"] for s in r["skills"])]
        eligible = ctx.elig[r["id"]]
        free_elig = [v for v in eligible if v not in taken]
        if not active:
            why = "No active volunteers."
        elif not holders:
            why = "No volunteer holds the mandatory skill (%s)." % ", ".join(r["skills"])
        elif not eligible:
            why = "%d volunteers have the skill but none can cover %02d:00-%02d:00 within their max hours." % (len(holders), r["start"], r["end"])
        elif free_elig:
            why = "%d eligible volunteers are unassigned (they were placed elsewhere by the policy)." % len(free_elig)
        else:
            why = "All %d eligible volunteers are already assigned (some by the policy to other roles); headcount is %d." % (len(eligible), r["headcount"])
        out.append({"req_id": r["id"], "dept": r["dept"], "vacant": vac, "skill_holders": len(holders),
                    "eligible": len(eligible), "eligible_unassigned": len(free_elig), "why": why})
    return out

def recommendations(ctx, assignments):
    recs = []
    taken = {a["vol_id"] for a in assignments}
    for vr in vacancy_reasons(ctx, assignments):
        r = ctx.reqs[vr["req_id"]]
        free = [ctx.vols[v]["name"] for v in ctx.elig[r["id"]] if v not in taken][:3]
        if free:
            recs.append({"type": "manual_assign", "dept": r["dept"], "text": "Consider manually assigning %s to %s (eligible, unassigned). Not auto-transferred." % (", ".join(free), r["dept"])})
        elif vr["skill_holders"] == 0:
            recs.append({"type": "recruit_train", "dept": r["dept"], "text": "No one has %s. Recruit or train %d volunteer(s) for %s." % (", ".join(r["skills"]), vr["vacant"], r["dept"])})
        elif vr["eligible"] == 0:
            recs.append({"type": "review_window", "dept": r["dept"], "text": "%d skilled volunteers exist but are unavailable for the duty window. Review the window or duration." % vr["skill_holders"]})
        else:
            recs.append({"type": "review_headcount", "dept": r["dept"], "text": "Headcount %d exceeds eligible supply %d. Review the requirement or leave open." % (r["headcount"], vr["eligible"])})
    return recs

# ---------------------------------------------------------------- 7. CHARTS (Matplotlib)
def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

def chart_required_vs_allocated(ctx, metrics, title):
    names = [r["dept"] for r in ctx.req_list]
    req = np.array([r["headcount"] for r in ctx.req_list])
    got = np.array([metrics["by_req"][r["id"]] for r in ctx.req_list])
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(x - 0.2, req, 0.4, label="Required", color="#D9D9D9")
    ax.bar(x + 0.2, got, 0.4, label="Allocated", color=ORANGE)
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Positions"); ax.set_title(title, fontsize=10); ax.legend(frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return fig_to_b64(fig)

def chart_comparison(run):
    keys = [("coverage_pct", "Coverage %"), ("priority_coverage_pct", "Priority coverage %"), ("pref_fit_pct", "Preference fit %")]
    g, o = run["greedy"]["metrics"], run["optimal"]["metrics"]
    x = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.bar(x - 0.2, [g[k] for k, _ in keys], 0.4, label="Greedy", color="#BBBBBB")
    ax.bar(x + 0.2, [o[k] for k, _ in keys], 0.4, label="Optimal", color=ORANGE)
    ax.set_xticks(x); ax.set_xticklabels([l for _, l in keys], fontsize=9)
    ax.set_ylim(0, 105); ax.set_title("Greedy vs Optimal (same input snapshot)", fontsize=10); ax.legend(frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return fig_to_b64(fig)

def chart_skill_supply(ctx):
    names = [r["dept"] for r in ctx.req_list]
    supply = np.array([len(ctx.elig[r["id"]]) for r in ctx.req_list])
    need = np.array([r["headcount"] for r in ctx.req_list])
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.bar(x - 0.2, need, 0.4, label="Headcount needed", color="#D9D9D9")
    ax.bar(x + 0.2, supply, 0.4, label="Eligible volunteers", color="#2F7D6B")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    ax.set_title("Skill supply vs demand (shortage where green < grey)", fontsize=10); ax.legend(frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return fig_to_b64(fig)

# ---------------------------------------------------------------- 8. STATE, VERSIONS, AUDIT (files + exceptions)
class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}

LOCK = threading.RLock()
VOLUNTEERS, CLEAN_REPORT = [], {}
STATE = {}

def load_state():
    global STATE
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            STATE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        STATE = {"versions": [], "published": None, "audit": [], "last_run": None, "next_vid": 1,
                 "inactive": [], "requirements": copy.deepcopy(DEFAULT_REQUIREMENTS)}
    for v in VOLUNTEERS:
        v["active"] = v["id"] not in STATE["inactive"]

def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(STATE, f, indent=1)

def audit(user, action, entity, detail="", reason=""):
    STATE["audit"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "actor": user["name"], "role": user["role"],
                           "action": action, "entity": entity, "detail": detail, "reason": reason})

def live_context():
    return Context(VOLUNTEERS, STATE["requirements"])

def get_version(vid):
    for v in STATE["versions"]:
        if v["id"] == vid:
            return v
    raise ApiError(404, "NOT_FOUND", "Version not found")

def new_version(assignments, source, user, parent=None, summary=""):
    v = {"id": STATE["next_vid"], "number": STATE["next_vid"], "parent": parent, "status": "draft", "source": source,
         "assignments": assignments, "row_version": 1, "created_by": user["name"], "created": time.strftime("%Y-%m-%d %H:%M"),
         "summary": summary, "approved_by": None, "published_by": None, "stale": False}
    STATE["next_vid"] += 1
    STATE["versions"].append(v)
    return v

def version_view(v):
    ctx = live_context()
    m = compute_metrics(ctx, v["assignments"])
    rows = []
    for r in ctx.req_list:
        people = [dict(a, name=ctx.vols[a["vol_id"]]["name"]) for a in v["assignments"] if a["req_id"] == r["id"] and a["vol_id"] in ctx.vols]
        rows.append({"req_id": r["id"], "dept": r["dept"], "role": r["role"], "priority": r["priority"],
                     "required": r["headcount"], "allocated": len(people), "vacant": r["headcount"] - len(people),
                     "coverage": round(100 * len(people) / max(1, r["headcount"])), "people": people})
    taken = {a["vol_id"] for a in v["assignments"]}
    free = []
    for vid in sorted({x for r in ctx.req_list for x in ctx.elig[r["id"]]} - taken):
        free.append({"id": vid, "name": ctx.vols[vid]["name"],
                     "can_fill": [r["dept"] for r in ctx.req_list if vid in ctx.elig[r["id"]]][:4]})
    return {k: v[k] for k in ("id", "number", "status", "source", "row_version", "created_by", "created", "approved_by",
                              "published_by", "stale", "summary", "parent")} | {
        "is_published": STATE["published"] == v["id"], "metrics": {k: x for k, x in m.items() if k != "by_req"},
        "rows": rows, "vacancies": vacancy_reasons(ctx, v["assignments"]), "eligible_unassigned": free}

def edit_version(v, body, user):
    """Manual add / remove / replace with all hard rules; returns the version that holds the change."""
    ctx = live_context()
    if v["row_version"] != body.get("row_version", v["row_version"]):
        raise ApiError(409, "STALE_VERSION", "Someone changed this version. Reload and try again.")
    op, req_id = body.get("op"), body.get("req_id")
    if req_id not in ctx.reqs:
        raise ApiError(422, "VALIDATION_ERROR", "Unknown requirement")
    req = ctx.reqs[req_id]
    items = copy.deepcopy(v["assignments"])

    def remove(vol_id):
        n = len(items)
        items[:] = [a for a in items if not (a["req_id"] == req_id and a["vol_id"] == vol_id)]
        if len(items) == n:
            raise ApiError(422, "VALIDATION_ERROR", "That volunteer is not assigned to this role")

    def add(vol_id):
        if vol_id not in ctx.vols:
            raise ApiError(404, "NOT_FOUND", "Volunteer not found")
        vol = ctx.vols[vol_id]
        if not vol["active"]:
            raise ApiError(422, "INACTIVE", "Inactive volunteers cannot be assigned")
        if any(a["vol_id"] == vol_id for a in items):
            raise ApiError(422, "DUPLICATE", "Volunteer already has an assignment in this event version")
        if sum(1 for a in items if a["req_id"] == req_id) >= req["headcount"]:
            raise ApiError(422, "NO_OPEN_POSITION", "This role has no open position")
        why = ineligible_reasons(vol, req)
        hard = [t for c, t in why if c != "skill"]
        if hard:
            raise ApiError(422, "HARD_RULE", "Blocked: " + "; ".join(hard))
        override, reason = False, ""
        if why:                                                  # only a skill mismatch remains
            reason = str(body.get("reason", "")).strip()
            if not body.get("confirm_skill") or not reason:
                raise ApiError(409, "SKILL_MISMATCH", why[0][1] + ". A reason is required to override.")
            override = True
        items.append({"req_id": req_id, "vol_id": vol_id, "source": "manual", "override": override, "reason": reason})
        return override, reason

    if op == "remove":
        remove(body.get("vol_id")); detail, reason = "removed %s from %s" % (body.get("vol_id"), req["dept"]), ""
    elif op == "add":
        ov, reason = add(body.get("vol_id")); detail = "added %s to %s%s" % (body.get("vol_id"), req["dept"], " (skill override)" if ov else "")
    elif op == "replace":
        remove(body.get("old_vol_id")); ov, reason = add(body.get("vol_id"))
        detail = "replaced %s with %s in %s" % (body.get("old_vol_id"), body.get("vol_id"), req["dept"])
    else:
        raise ApiError(422, "VALIDATION_ERROR", "op must be add, remove or replace")
    target = v
    if v["status"] == "published":                               # published versions are immutable
        target = new_version(items, "manual", user, parent=v["id"], summary="Revision of v%d" % v["number"])
        audit(user, "new_revision", "version %d" % target["id"], "from published v%d" % v["number"])
    else:
        if v["status"] == "approved":
            v["status"], v["approved_by"] = "draft", None
            audit(user, "approval_invalidated", "version %d" % v["id"], "edited after approval")
        v["assignments"] = items
        v["row_version"] += 1
    audit(user, "manual_edit", "version %d" % target["id"], detail, reason)
    return target

# ---------------------------------------------------------------- 9. SIMULATOR (isolated deep copy)
def run_both(vols, reqs):
    ctx = Context(vols, reqs)
    out = {}
    for algo in (GreedyAllocator(), OptimalAllocator()):
        res = algo.run(ctx)
        res["metrics"] = compute_metrics(ctx, res["assignments"])
        out[algo.name] = res
    return ctx, out

def slim(res):
    return {k: res[k] for k in ("label", "status", "runtime_ms", "objective")} | {"metrics": {k: x for k, x in res["metrics"].items() if k != "by_req"}}

def simulate(p):
    before = json.dumps([VOLUNTEERS, STATE["requirements"], STATE["versions"], STATE["published"]], sort_keys=True)
    vols, reqs = copy.deepcopy(VOLUNTEERS), copy.deepcopy(STATE["requirements"])
    _, base = run_both(vols, reqs)
    notes = []
    sv, sr = copy.deepcopy(vols), copy.deepcopy(reqs)
    drop = float(p.get("dropout_pct", 0))
    if drop > 0:
        rng = np.random.default_rng(42)                          # fixed seed -> repeatable
        k = int(round(len(sv) * drop / 100))
        for i in rng.choice(len(sv), size=k, replace=False):
            sv[int(i)]["active"] = False
        notes.append("%d volunteers dropped out (random, seed 42)" % k)
    mult = float(p.get("headcount_mult", 1))
    if mult != 1:
        for r in sr:
            r["headcount"] = math.ceil(r["headcount"] * mult)
        notes.append("Headcount x%s" % mult)
    extra_h = float(p.get("extra_hours", 0))
    if extra_h:
        for r in sr:
            r["end"] = min(24, r["end"] + extra_h)
        notes.append("Duty window +%s h" % extra_h)
    n_sim, skill = int(p.get("sim_volunteers", 0)), p.get("sim_skill", "")
    for i in range(n_sim):
        sv.append({"id": "SIM-%03d" % (i + 1), "name": "Simulated volunteer %d" % (i + 1), "skills": [skill] if skill else [],
                   "prefs": [], "avail_start": 9, "avail_end": 21, "max_hours": 12, "exp": 1, "active": True,
                   "simulated": True, "email": ""})
    if n_sim:
        notes.append("%d SIMULATED volunteers with skill '%s' (scenario only)" % (n_sim, skill))
    _, scen = run_both(sv, sr)
    after = json.dumps([VOLUNTEERS, STATE["requirements"], STATE["versions"], STATE["published"]], sort_keys=True)
    return {"label": "Simulation - not published", "notes": notes or ["No change (identical to baseline)"],
            "baseline": {k: slim(x) for k, x in base.items()}, "scenario": {k: slim(x) for k, x in scen.items()},
            "live_unchanged": before == after}

# ---------------------------------------------------------------- 10. USERS + SESSIONS
def pw_hash(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()

USERS, SESSIONS = {}, {}
def build_users():
    salt = "kala"
    for email, name, role, pw in (("convener@tapmi.edu.in", "Convener", "convener", "convener123"),
                                  ("coconvener@tapmi.edu.in", "Co-convener", "co_convener", "coconvener123")):
        USERS[email] = {"name": name, "role": role, "hash": pw_hash(pw, salt), "vol_id": None}
    for v in VOLUNTEERS:
        USERS[v["email"]] = {"name": v["name"], "role": "volunteer", "hash": pw_hash("volunteer123", salt), "vol_id": v["id"]}
    return salt
SALT = "kala"

# ---------------------------------------------------------------- 11. API HANDLERS
def api_login(b, user):
    u = USERS.get(str(b.get("email", "")).strip().lower())
    if not u or u["hash"] != pw_hash(str(b.get("password", "")), SALT):
        raise ApiError(401, "AUTH", "Wrong email or password")
    tok = secrets.token_hex(16)
    SESSIONS[tok] = u
    return {"role": u["role"], "name": u["name"]}, tok

def do_run(b, user):
    ctx, res = run_both(VOLUNTEERS, STATE["requirements"])
    draft_from = b.get("draft_from", "optimal")
    if res[draft_from]["status"].startswith("Failed"):
        raise ApiError(422, "SOLVER_FAILED", res[draft_from]["status"])
    v = new_version(res[draft_from]["assignments"], draft_from, user, summary="Generated by %s" % res[draft_from]["label"])
    STATE["last_run"] = {"time": time.strftime("%H:%M:%S"), "draft_version": v["id"], "greedy": slim(res["greedy"]), "optimal": slim(res["optimal"])}
    audit(user, "run_allocation", "version %d" % v["id"], "greedy + optimal on same snapshot; draft from %s" % draft_from)
    return {"version": v["id"], "last_run": STATE["last_run"]}

def do_approve(v, user):
    if v["status"] not in ("draft",):
        raise ApiError(409, "WORKFLOW", "Only a draft can be approved")
    if v["stale"]:
        raise ApiError(409, "STALE", "Requirements changed after this draft. Regenerate or re-edit.")
    m = compute_metrics(live_context(), v["assignments"])
    if m["skill_violations"] or m["capacity_violations"]:
        raise ApiError(422, "INVALID", "Version has hard-rule violations")
    v["status"], v["approved_by"] = "approved", user["name"]
    audit(user, "approve", "version %d" % v["id"])

def do_publish(v, user):
    if v["status"] != "approved":
        raise ApiError(409, "WORKFLOW", "Only an approved version can be published")
    old = STATE["published"]                                     # single step = atomic under LOCK
    if old:
        get_version(old)["status"] = "superseded"
    v["status"], v["published_by"], STATE["published"] = "published", user["name"], v["id"]
    audit(user, "publish", "version %d" % v["id"], "replaced v%s" % old if old else "first publication")

def charts_for(vid):
    ctx = live_context()
    v = get_version(vid)
    m = compute_metrics(ctx, v["assignments"])
    out = {"required": chart_required_vs_allocated(ctx, m, "Required vs allocated - version %d (%s)" % (v["number"], v["status"])),
           "supply": chart_skill_supply(ctx)}
    if STATE["last_run"]:
        run = {"greedy": STATE["last_run"]["greedy"], "optimal": STATE["last_run"]["optimal"]}
        out["comparison"] = chart_comparison(run)
    return out

def roster_csv():
    pid = STATE["published"]
    if not pid:
        raise ApiError(404, "NOT_FOUND", "Nothing published yet")
    ctx = live_context()
    rows = [{"Department": ctx.reqs[a["req_id"]]["dept"], "Role": ctx.reqs[a["req_id"]]["role"], "Volunteer ID": a["vol_id"],
             "Name": ctx.vols[a["vol_id"]]["name"], "Source": a["source"], "Skill override": a["override"]}
            for a in get_version(pid)["assignments"]]
    return pd.DataFrame(rows).sort_values(["Department", "Name"]).to_csv(index=False)

def route(method, path, body, user):
    """Central router. Returns (data, set-cookie-token or None). Authorization is enforced HERE."""
    org = user is not None and user["role"] in ("convener", "co_convener")
    def need_org():
        if user is None: raise ApiError(401, "AUTH", "Please sign in")
        if not org: raise ApiError(403, "FORBIDDEN", "Organizer access only")
    if path == "/api/login" and method == "POST":
        return api_login(body, user)
    if user is None:
        raise ApiError(401, "AUTH", "Please sign in")
    if path == "/api/me":
        return {"name": user["name"], "role": user["role"]}, None
    if path == "/api/me/assignments":                           # only OWN, only PUBLISHED
        pid, ctx = STATE["published"], live_context()
        mine = [a for a in (get_version(pid)["assignments"] if pid else []) if a["vol_id"] == user["vol_id"]]
        return [{"dept": ctx.reqs[a["req_id"]]["dept"], "role": ctx.reqs[a["req_id"]]["role"], "event": "Kala Fest",
                 "window": "%02d:00-%02d:00" % (ctx.reqs[a["req_id"]]["start"], ctx.reqs[a["req_id"]]["end"]),
                 "version": get_version(pid)["number"]} for a in mine], None
    need_org()
    m = re.fullmatch(r"/api/version/(\d+)(?:/(\w+))?", path)
    if path == "/api/versions":
        return [{"id": v["id"], "number": v["number"], "status": v["status"], "source": v["source"], "created": v["created"],
                 "is_published": STATE["published"] == v["id"], "summary": v["summary"]} for v in STATE["versions"]], None
    if m:
        v = get_version(int(m.group(1)))
        act = m.group(2)
        if act is None and method == "GET":
            return version_view(v), None
        if act == "edit" and method == "POST":
            t = edit_version(v, body, user); save_state(); return {"version": t["id"]}, None
        if act == "approve" and method == "POST":
            do_approve(v, user); save_state(); return {"ok": True}, None
        if act == "publish" and method == "POST":
            do_publish(v, user); save_state(); return {"ok": True}, None
        if act == "candidates" and method == "POST":
            ctx = live_context(); req = ctx.reqs[body["req_id"]]
            taken = {a["vol_id"] for a in v["assignments"]}
            cands = []
            for vol in VOLUNTEERS:
                if vol["id"] in taken or not vol["active"]:
                    continue
                why = ineligible_reasons(vol, req)
                cands.append({"id": vol["id"], "name": vol["name"], "eligible": not why, "bonus": ctx.bonus.get((req["id"], vol["id"]), 0),
                              "why": "; ".join(t for _, t in why), "blocked": any(c != "skill" for c, _ in why)})
            cands = merge_sort(cands, key=lambda c: (not c["eligible"], c["blocked"], -c["bonus"], c["name"]))
            return cands[:60], None
        if act == "charts":
            return charts_for(v["id"]), None
        if act == "recs":
            ctx = live_context(); return recommendations(ctx, v["assignments"]), None
    if path == "/api/requirements":
        ctx = live_context()
        return [dict(r, eligible=len(ctx.elig[r["id"]]), skill_holders=sum(1 for v in VOLUNTEERS if v["active"] and all(s in v["skills"] for s in r["skills"])))
                for r in STATE["requirements"]], None
    m = re.fullmatch(r"/api/requirement/(R\d+)", path)
    if m and method == "POST":
        r = next((x for x in STATE["requirements"] if x["id"] == m.group(1)), None)
        if r is None: raise ApiError(404, "NOT_FOUND", "Requirement not found")
        if r["source"] == "workload" and body.get("use_workload", True):
            r["headcount"] = required_staff(float(body.get("workload", r.get("workload"))), float(body.get("service_min", r.get("service_min"))), float(body.get("peak_min", r.get("peak_min"))))
            r.update(workload=float(body.get("workload", r["workload"])), service_min=float(body.get("service_min", r["service_min"])), peak_min=float(body.get("peak_min", r["peak_min"])))
        else:
            hc = body.get("headcount")
            if not isinstance(hc, int) or hc < 0: raise ApiError(422, "VALIDATION_ERROR", "Headcount must be a whole number >= 0")
            r["headcount"] = hc
        if body.get("priority") in CONFIG["priority_weight"]: r["priority"] = body["priority"]
        for v in STATE["versions"]:                              # approvals invalidated, history preserved
            if v["status"] in ("draft", "approved"):
                v["status"], v["approved_by"], v["stale"] = "draft", None, True
        audit(user, "requirement_changed", r["id"], "headcount=%s priority=%s" % (r["headcount"], r["priority"]))
        save_state(); return r, None
    if path == "/api/calc" and method == "POST":
        n = required_staff(body.get("workload"), body.get("service_min"), body.get("peak_min"))
        return {"required": n, "formula": "ceil(%s x %s / %s) = %d" % (body["workload"], body["service_min"], body["peak_min"], n)}, None
    if path == "/api/run" and method == "POST":
        res = do_run(body, user); save_state(); return res, None
    if path == "/api/last_run":
        return STATE["last_run"], None
    if path == "/api/simulate" and method == "POST":
        return simulate(body), None
    if path == "/api/volunteers":
        return [{"id": v["id"], "name": v["name"], "skills": v["skills"], "hours": v["max_hours"], "avail": "%02d:00-%02d:00" % (v["avail_start"], v["avail_end"]),
                 "exp": v["exp"], "active": v["active"]} for v in VOLUNTEERS], {"cleaning": CLEAN_REPORT}
    m = re.fullmatch(r"/api/volunteer/(V\d+)/active", path)
    if m and method == "POST":
        i = binary_search([v["id"] for v in VOLUNTEERS], m.group(1))
        if i < 0: raise ApiError(404, "NOT_FOUND", "Volunteer not found")
        vol = VOLUNTEERS[i]; vol["active"] = bool(body.get("active"))
        STATE["inactive"] = [v["id"] for v in VOLUNTEERS if not v["active"]]
        audit(user, "volunteer_active" if vol["active"] else "volunteer_deactivated", vol["id"], vol["name"])
        save_state(); return {"ok": True}, None
    if path == "/api/audit":
        return STATE["audit"][::-1][:200], None
    if path == "/api/export.csv":
        return {"csv": roster_csv()}, None
    raise ApiError(404, "NOT_FOUND", "Unknown route")

# ---------------------------------------------------------------- 11b. BROWSER ENTRY POINTS (Netlify / static build)
def init_browser(csv_path):
    """Start the engine WITHOUT a web server (the page calls browser_call instead)."""
    global VOLUNTEERS, CLEAN_REPORT, SALT
    VOLUNTEERS, CLEAN_REPORT = load_volunteers(csv_path)
    SALT = build_users()
    load_state()

def browser_call(method, path, body_json, token):
    """Same routing as the server, but called directly from JavaScript (Pyodide)."""
    try:
        body = json.loads(body_json) if body_json else {}
        with LOCK:
            data, extra = route(method, path, body, SESSIONS.get(token))
        if path == "/api/export.csv":
            return json.dumps({"status": 200, "csv": data["csv"]})
        new_token = None
        if path == "/api/login":
            new_token, extra = extra, None
        return json.dumps({"status": 200, "token": new_token, "body": {"data": data, "meta": extra or {}}})
    except ApiError as e:
        return json.dumps({"status": e.status, "body": {"error": {"code": e.code, "message": e.message, "details": e.details}}})
    except Exception as e:
        print("Engine error:", repr(e))
        return json.dumps({"status": 500, "body": {"error": {"code": "SERVER", "message": "Unexpected error"}}})

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _send(self, code, ctype, payload, extra=None):
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)
    def _user(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sid":
                return SESSIONS.get(v)
        return None
    def _handle(self, method):
        path = self.path.split("?")[0]
        if method == "GET" and path == "/":
            return self._send(200, "text/html; charset=utf-8", PAGE)
        if method == "GET" and path == "/logo.png":
            for n in ("tapmi_logo.png", "TAPMI-Logo-.png", "logo.png"):
                p = os.path.join(HERE, n)
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return self._send(200, "image/png", f.read())
            return self._send(404, "text/plain", "none")
        if method == "GET" and path == "/bg.jpg":
            for n in ("icon.jpeg", "Icon.jpg", "icon.jpg"):
                p = os.path.join(HERE, n)
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return self._send(200, "image/jpeg", f.read())
            return self._send(404, "text/plain", "none")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            with LOCK:
                data, extra = route(method, path, body, self._user())
            if path == "/api/export.csv":
                return self._send(200, "text/csv", data["csv"], {"Content-Disposition": "attachment; filename=kala_fest_roster.csv"})
            headers = {}
            if path == "/api/login":
                headers["Set-Cookie"] = "sid=%s; Path=/; HttpOnly; SameSite=Strict" % extra
                extra = None
            self._send(200, "application/json", json.dumps({"data": data, "meta": extra or {}}), headers)
        except ApiError as e:
            self._send(e.status, "application/json", json.dumps({"error": {"code": e.code, "message": e.message, "details": e.details}}))
        except Exception as e:                                   # never leak a stack trace to the browser
            print("Server error:", repr(e))
            self._send(500, "application/json", json.dumps({"error": {"code": "SERVER", "message": "Unexpected server error"}}))
    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")

# ---------------------------------------------------------------- 12. DASHBOARD PAGE (HTML/CSS/JS shown in the browser)
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TAPMI Cultural Committee - Kala Fest</title>
<style>
:root{--o:#E8752E;--ol:#FDEBDD;--od:#8A3E0E;--bd:#E5E5E5;--tx:#222;--mu:#6b6b6b}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:var(--tx);background:#fff}
h2{font-size:18px;margin:0 0 10px;font-weight:600}h3{font-size:15px;margin:18px 0 8px}
button{font:inherit;padding:6px 12px;border:1px solid #ccc;background:#fff;border-radius:6px;cursor:pointer}button:hover{background:#f6f6f6}
button.p{background:var(--o);color:#fff;border-color:var(--o)}button.p:hover{background:#d4651f}button.s{padding:2px 8px;font-size:12px}
input,select{font:inherit;padding:6px 8px;border:1px solid #ccc;border-radius:6px}
#login{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f4f1ee url(/bg.jpg) center/cover}
#login:before{content:"";position:fixed;inset:0;background:rgba(255,255,255,.72)}
.lc{position:relative;background:#fff;border:1px solid var(--bd);border-radius:12px;padding:24px;width:340px}
.lc input{width:100%;margin-bottom:10px}.q button{margin:2px 4px 2px 0}
header{display:flex;align-items:center;gap:14px;padding:10px 20px;border-bottom:1px solid var(--bd);flex-wrap:wrap}
header b{color:var(--o);font-size:16px}nav{display:flex;gap:4px;flex:1;flex-wrap:wrap}nav button{border:none;background:none;color:var(--mu)}
nav button.on{background:var(--ol);color:var(--od);font-weight:600}main{padding:18px 20px;max-width:1100px;margin:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:10px 0}
.m{background:#f7f7f7;border-radius:8px;padding:10px 12px}.m small{display:block;color:var(--mu)}.m b{font-size:22px;font-weight:600}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:7px 8px;border-top:1px solid var(--bd);vertical-align:top}th{color:var(--mu);font-weight:500;border-top:none;font-size:12px}
.pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:12px;background:#eee}.crit{background:#fde2e2;color:#8a1f1f}.high{background:var(--ol);color:var(--od)}.ok{background:#dff3e4;color:#1d5e33}.warn{background:#fff3cd;color:#6b4e00}
.bar{height:8px;background:#eee;border-radius:4px;min-width:80px}.bar i{display:block;height:100%;background:var(--o);border-radius:4px}
.box{border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin:10px 0}.alert{background:#fff3cd;color:#6b4e00;border-radius:8px;padding:10px 12px;margin:10px 0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:700px){.two{grid-template-columns:1fr}}
.chip{display:inline-flex;gap:4px;align-items:center;background:#f1f1f1;border-radius:14px;padding:1px 4px 1px 9px;margin:2px;font-size:12px}.chip a{cursor:pointer;color:#a00;padding:0 4px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}img{max-width:100%}#toast{position:fixed;bottom:16px;right:16px;background:#222;color:#fff;padding:10px 14px;border-radius:8px;display:none;z-index:9}
.sim{font-size:12px;color:var(--od);background:var(--ol);padding:2px 8px;border-radius:10px}small.mu{color:var(--mu)}
</style></head><body>
<div id="login"><div class="lc"><img src="/logo.png" alt="TAPMI" style="width:100%;margin-bottom:10px" onerror="this.style.display='none'"><div style="color:var(--mu);font-size:12px">TAPMI, Manipal</div>
<h2><span style="color:var(--o)">Cultural Committee</span> portal</h2>
<input id="em" placeholder="name@tapmi.edu.in"><input id="pw" type="password" placeholder="Password">
<button class="p" style="width:100%" onclick="login()">Sign in</button><div id="le" style="color:#a00;margin-top:8px"></div>
<div class="q" style="margin-top:12px"><small class="mu">Demo quick fill</small><br>
<button class="s" onclick="fill('convener@tapmi.edu.in','convener123')">Convener</button>
<button class="s" onclick="fill('coconvener@tapmi.edu.in','coconvener123')">Co-convener</button>
<button class="s" onclick="fill('abhinav.karthik@tapmi.edu.in','volunteer123')">Volunteer</button></div></div></div>
<div id="app" style="display:none"><header><img src="/logo.png" alt="TAPMI" style="height:30px" onerror="this.style.display='none'"><b>Kala Fest</b><nav id="nav"></nav><span id="who" class="pill"></span><button class="s" onclick="logout()">Sign out</button></header><main id="main"></main></div>
<div id="toast"></div>
<script>
const $=s=>document.querySelector(s);let ME=null,TAB='dash',CUR=null;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(m){const t=$('#toast');t.textContent=m;t.style.display='block';setTimeout(()=>t.style.display='none',3200)}
async function api(p,m='GET',b){const r=await fetch('/api'+p,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});
 const j=await r.json();if(!r.ok){const e=new Error(j.error.message);e.code=j.error.code;throw e}return j}
function fill(e,p){$('#em').value=e;$('#pw').value=p}
async function login(){try{const j=await api('/login','POST',{email:$('#em').value,password:$('#pw').value});ME=j.data;start()}catch(e){$('#le').textContent=e.message}}
async function downloadCsv(){try{const r=await fetch('/api/export.csv');if(!r.ok){const j=await r.json();return toast(j.error.message)}const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download='kala_fest_roster.csv';a.click()}catch(e){toast(e.message)}}
async function logout(){document.cookie='sid=;Path=/;max-age=0';location.reload()}
const ORG=[['dash','Dashboard'],['reqs','Requirements'],['alloc','Allocation'],['reports','Reports'],['sim','What-if'],['vols','Volunteers'],['audit','Audit']];
function start(){$('#login').style.display='none';$('#app').style.display='block';$('#who').textContent=ME.name+' ('+ME.role.replace('_','-')+')';
 const tabs=ME.role==='volunteer'?[['mine','My assignments']]:ORG;TAB=tabs[0][0];
 $('#nav').innerHTML=tabs.map(t=>`<button data-t="${t[0]}" onclick="go('${t[0]}')">${t[1]}</button>`).join('');go(TAB)}
function go(t){TAB=t;document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));views[t]()}
const pill=s=>`<span class="pill ${s==='critical'?'crit':s==='high'?'high':''}">${s}</span>`;
const stat=v=>`<span class="pill ${v.status==='published'?'ok':'warn'}">${v.status==='published'?'Published':'Draft / not published'} v${v.number}</span>`;
const cards=m=>`<div class="cards">${[['Required',m.required],['Allocated',m.allocated],['Vacant',m.vacant],['Coverage',m.coverage_pct+'%'],['Priority coverage',m.priority_coverage_pct+'%'],['Eligible unassigned',m.eligible_unassigned]].map(x=>`<div class="m"><small>${x[0]}</small><b>${x[1]}</b></div>`).join('')}</div>`;
const deptTable=v=>`<table><tr><th>Department</th><th>Priority</th><th>Need</th><th>Filled</th><th>Vacant</th><th>Coverage</th></tr>${v.rows.map(r=>`<tr><td>${esc(r.dept)}<br><small class="mu">${esc(r.role)}</small></td><td>${pill(r.priority)}</td><td>${r.required}</td><td>${r.allocated}</td><td>${r.vacant?'<b style="color:#a00">'+r.vacant+'</b>':0}</td><td><div class="bar"><i style="width:${r.coverage}%"></i></div></td></tr>`).join('')}</table>`;
async function current(){const vs=(await api('/versions')).data;if(!vs.length)return null;const p=vs.find(v=>v.is_published);return(await api('/version/'+(p?p.id:vs[vs.length-1].id))).data}
const views={
async dash(){const v=await current();if(!v){$('#main').innerHTML='<h2>Dashboard</h2><div class="box">No allocation yet. Open <b>Allocation</b> and run Greedy + Optimal.</div>';return}
 const ch=(await api('/version/'+v.id+'/charts')).data;
 $('#main').innerHTML=`<h2>Dashboard ${stat(v)}</h2>${cards(v.metrics)}${v.vacancies.length?`<div class="alert">${v.metrics.vacant} position(s) are vacant. ${v.metrics.eligible_unassigned} eligible volunteers remain unassigned. Assign manually or leave open.</div>`:''}
 <div class="box">${deptTable(v)}</div><img src="data:image/png;base64,${ch.required}"><p><button onclick="downloadCsv()">Download published roster (CSV)</button></p>`},
async reqs(){const r=(await api('/requirements')).data;
 $('#main').innerHTML=`<h2>Department requirements</h2><div class="box"><table><tr><th>Dept</th><th>Priority</th><th>Headcount</th><th>Source</th><th>Skills (mandatory)</th><th>Skill holders</th><th>Eligible</th><th></th></tr>${r.map(x=>`<tr><td>${esc(x.dept)}</td><td>${pill(x.priority)}</td><td><input id="h${x.id}" type="number" min="0" value="${x.headcount}" style="width:64px"></td><td>${x.source==='workload'?'Workload: '+x.workload+' x '+x.service_min+' min / '+x.peak_min+' min':'Fixed'}</td><td>${esc(x.skills.join(', '))}</td><td>${x.skill_holders}</td><td>${x.eligible}</td><td><select id="p${x.id}">${['critical','high','normal'].map(p=>`<option ${p===x.priority?'selected':''}>${p}</option>`).join('')}</select> <button class="s" onclick="saveReq('${x.id}',${x.source==='workload'})">Save</button></td></tr>`).join('')}</table></div>
 <h3>Staffing calculator: ceil(workload x service time / peak window)</h3><div class="row"><input id="cw" type="number" placeholder="Workload" value="120"><input id="cs" type="number" step="0.1" placeholder="Service min" value="1.5"><input id="cp" type="number" placeholder="Peak window min" value="30"><button class="p" onclick="calc()">Calculate</button><b id="cr"></b></div><small class="mu">Editing a requirement invalidates approvals; published versions are never changed.</small>`},
async alloc(){const lr=(await api('/last_run')).data,vs=(await api('/versions')).data;
 $('#main').innerHTML=`<h2>Allocation</h2><div class="row"><select id="df"><option value="optimal">Draft from Optimal</option><option value="greedy">Draft from Greedy</option></select><button class="p" onclick="runAlloc()">Run Greedy + Optimal</button><small class="mu">Creates a draft. Volunteers cannot see drafts.</small></div>
 ${lr?`<div class="two">${['greedy','optimal'].map(k=>{const r=lr[k],m=r.metrics;return `<div class="box" style="${k==='optimal'?'border:2px solid var(--o)':''}"><b>${r.label}</b> <span class="pill">${r.status}</span><br>Filled ${m.allocated}/${m.required} | Priority cov. ${m.priority_coverage_pct}% | Pref fit ${m.pref_fit_pct}%<br>Min dept cov. ${m.min_dept_coverage_pct}% | Fairness std ${m.fairness_std}<br>Skill violations ${m.skill_violations} | Capacity violations ${m.capacity_violations} | ${r.runtime_ms} ms</div>`}).join('')}</div>`:''}
 <h3>Versions</h3><div class="box"><table><tr><th>#</th><th>Status</th><th>Source</th><th>Created</th><th></th></tr>${vs.slice().reverse().map(v=>`<tr><td>v${v.number}</td><td><span class="pill ${v.status==='published'?'ok':v.status==='approved'?'high':'warn'}">${v.status}</span></td><td>${v.source}</td><td>${v.created}<br><small class="mu">${esc(v.summary)}</small></td><td><button class="s" onclick="openV(${v.id})">Open</button></td></tr>`).join('')||'<tr><td>No versions yet</td></tr>'}</table></div><div id="vd"></div>`;
 if(CUR&&vs.find(v=>v.id===CUR))openV(CUR)},
async reports(){const v=await current();if(!v){$('#main').innerHTML='<h2>Reports</h2><div class="box">Run an allocation first.</div>';return}
 const ch=(await api('/version/'+v.id+'/charts')).data,rc=(await api('/version/'+v.id+'/recs')).data;
 $('#main').innerHTML=`<h2>Reports ${stat(v)}</h2><h3>Vacancy explanations</h3><div class="box">${v.vacancies.length?`<table><tr><th>Dept</th><th>Vacant</th><th>Skill holders</th><th>Eligible</th><th>Why</th></tr>${v.vacancies.map(x=>`<tr><td>${esc(x.dept)}</td><td>${x.vacant}</td><td>${x.skill_holders}</td><td>${x.eligible}</td><td>${esc(x.why)}</td></tr>`).join('')}</table>`:'All positions filled.'}</div>
 <h3>Underutilization: eligible but unassigned (${v.eligible_unassigned.length})</h3><div class="box">${v.eligible_unassigned.map(x=>`<span class="chip">${esc(x.name)} <small class="mu">${esc(x.can_fill.join(', '))}</small></span>`).join('')||'None'}</div>
 <h3>Recommendations</h3><div class="box">${rc.map(x=>`<div>- ${esc(x.text)}</div>`).join('')||'No action needed.'}</div>
 <h3>Charts</h3><img src="data:image/png;base64,${ch.supply}">${ch.comparison?`<img src="data:image/png;base64,${ch.comparison}">`:''}`},
async sim(){const sk=[...new Set((await api('/requirements')).data.flatMap(r=>r.skills))];
 $('#main').innerHTML=`<h2>What-if simulator <span class="sim">Simulation - not published</span></h2><div class="box"><div class="row">Volunteer dropout % <input id="s1" type="number" value="20" min="0" max="90" style="width:70px"> Headcount x <input id="s2" type="number" step="0.1" value="1.2" style="width:70px"> Extra duty hours <input id="s3" type="number" value="0" style="width:70px"></div><div class="row">Add simulated volunteers <input id="s4" type="number" value="0" min="0" style="width:70px"> with skill <select id="s5">${sk.map(s=>`<option>${esc(s)}</option>`).join('')}</select><button class="p" onclick="runSim()">Run scenario</button></div></div><div id="so"></div>`},
async vols(){const j=await api('/volunteers'),r=j.meta.cleaning;
 $('#main').innerHTML=`<h2>Volunteers (${j.data.length})</h2><div class="box"><small class="mu">Cleaning report: ${r.rows_read} rows read, ${r.duplicates_removed} duplicates removed, ${r.invalid_removed} invalid removed, ${r.clean_rows} kept.</small></div><div class="box"><table><tr><th>ID</th><th>Name</th><th>Skills</th><th>Availability</th><th>Max h</th><th>Exp</th><th>Active</th></tr>${j.data.map(v=>`<tr><td>${v.id}</td><td>${esc(v.name)}</td><td>${esc(v.skills.join(', '))}</td><td>${v.avail}</td><td>${v.hours}</td><td>${v.exp}</td><td><input type="checkbox" ${v.active?'checked':''} onchange="setActive('${v.id}',this.checked)"></td></tr>`).join('')}</table></div>`},
async audit(){const a=(await api('/audit')).data;$('#main').innerHTML=`<h2>Audit log</h2><div class="box"><table><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th><th>Reason</th></tr>${a.map(x=>`<tr><td>${x.time}</td><td>${esc(x.actor)}</td><td>${x.action}</td><td>${x.entity}</td><td>${esc(x.detail)}</td><td>${esc(x.reason)}</td></tr>`).join('')||'<tr><td>Nothing yet</td></tr>'}</table></div>`},
async mine(){const a=(await api('/me/assignments')).data;$('#main').innerHTML=`<h2>My assignments</h2>${a.length?a.map(x=>`<div class="box"><b>${x.event}, ${esc(x.dept)}</b> <span class="pill ok">Published v${x.version}</span><br>Role: ${esc(x.role)} | Duty window: ${x.window}</div>`).join(''):'<div class="box">No published assignment yet. Drafts are not shown.</div>'}<small class="mu">You only see your own published assignment, never drafts or the full roster.</small>`}};
async function saveReq(id,wl){try{await api('/requirement/'+id,'POST',{headcount:parseInt($('#h'+id).value),priority:$('#p'+id).value,use_workload:false});toast('Saved. Approvals invalidated.');views.reqs()}catch(e){toast(e.message)}}
async function calc(){try{const j=await api('/calc','POST',{workload:+$('#cw').value,service_min:+$('#cs').value,peak_min:+$('#cp').value});$('#cr').textContent=j.data.formula}catch(e){$('#cr').textContent=e.message}}
async function runAlloc(){try{const j=await api('/run','POST',{draft_from:$('#df').value});CUR=j.data.version;toast('Draft v'+j.data.version+' created');views.alloc()}catch(e){toast(e.message)}}
async function setActive(id,a){await api('/volunteer/'+id+'/active','POST',{active:a});toast(a?'Activated':'Deactivated')}
async function openV(id){CUR=id;const v=(await api('/version/'+id)).data;
 $('#vd').innerHTML=`<h3>Version ${v.number} ${stat(v)}</h3>${cards(v.metrics)}<div class="row">${v.status==='draft'?`<button class="p" onclick="act(${id},'approve')">Approve this version</button>`:''}${v.status==='approved'?`<button class="p" onclick="act(${id},'publish')">Publish</button>`:''}<button onclick="regen()">Regenerate...</button>${v.stale?'<span class="pill warn">Requirements changed since this draft</span>':''}</div>
 <div class="box"><table><tr><th>Department</th><th>Assigned</th><th>Vacant</th><th></th></tr>${v.rows.map(r=>`<tr><td>${esc(r.dept)}<br>${pill(r.priority)}</td><td>${r.people.map(p=>`<span class="chip">${esc(p.name)}${p.override?' <span class="pill warn">override</span>':''}${p.source==='manual'?' <span class="pill">manual</span>':''}<a title="Remove" onclick="edit(${id},{op:'remove',req_id:'${r.req_id}',vol_id:'${p.vol_id}'},${v.row_version})">x</a></span>`).join('')||'<small class="mu">none</small>'}</td><td>${r.vacant}</td><td>${r.vacant?`<button class="s" onclick="pick(${id},'${r.req_id}',${v.row_version})">+ Assign</button>`:''}</td></tr>`).join('')}</table></div><div id="pk"></div>`;}
async function act(id,a){try{await api('/version/'+id+'/'+a,'POST',{});toast(a==='publish'?'Published. Volunteers can now see it.':'Approved');views.alloc()}catch(e){toast(e.message)}}
function regen(){if(confirm('Regenerate creates a NEW draft from the algorithm. Manual edits stay in their old version. Continue?'))runAlloc()}
async function pick(id,req,rv){const c=(await api('/version/'+id+'/candidates','POST',{req_id:req})).data;
 $('#pk').innerHTML=`<div class="box"><b>Choose a volunteer</b> (eligible first; others need a skill-override reason)<div class="row"><select id="cv" size="8" style="min-width:380px">${c.map(x=>`<option value="${x.id}" ${x.blocked?'disabled':''}>${x.eligible?'[eligible] ':x.blocked?'[blocked] ':'[skill mismatch] '}${esc(x.name)}${x.eligible?'':' - '+esc(x.why)}</option>`).join('')}</select><button class="p" onclick="doAdd(${id},'${req}',${rv})">Assign</button></div></div>`}
async function doAdd(id,req,rv){const vid=$('#cv').value;if(!vid)return toast('Select a volunteer first');edit(id,{op:'add',req_id:req,vol_id:vid},rv)}
async function edit(id,b,rv){b.row_version=rv;try{const j=await api('/version/'+id+'/edit','POST',b);toast('Saved');CUR=j.data.version;views.alloc()}
 catch(e){if(e.code==='SKILL_MISMATCH'){const r=prompt(e.message+'\n\nEnter a reason to override:');if(r&&r.trim()){b.confirm_skill=true;b.reason=r.trim();return edit(id,b,rv)}}else toast(e.message)}}
async function runSim(){const j=await api('/simulate','POST',{dropout_pct:+$('#s1').value,headcount_mult:+$('#s2').value,extra_hours:+$('#s3').value,sim_volunteers:+$('#s4').value,sim_skill:$('#s5').value});const d=j.data;
 const row=(n,k,f)=>`<tr><td>${n}</td>${['greedy','optimal'].map(a=>`<td>${d.baseline[a].metrics[k]}${f||''}</td><td><b>${d.scenario[a].metrics[k]}${f||''}</b></td>`).join('')}</tr>`;
 $('#so').innerHTML=`<div class="box"><span class="sim">Simulation - not published</span> ${d.live_unchanged?'<span class="pill ok">Live data unchanged</span>':'<span class="pill crit">Live data CHANGED</span>'}<p>${d.notes.map(esc).join('; ')}</p><table><tr><th></th><th colspan="2">Greedy (base | scenario)</th><th colspan="2">Optimal (base | scenario)</th></tr>${row('Required','required')}${row('Allocated','allocated')}${row('Vacant','vacant')}${row('Coverage','coverage_pct','%')}${row('Priority coverage','priority_coverage_pct','%')}${row('Preference fit','pref_fit_pct','%')}</table></div>`}
</script></body></html>"""

# ---------------------------------------------------------------- 13. MAIN
def main():
    global VOLUNTEERS, CLEAN_REPORT, SALT
    try:
        VOLUNTEERS, CLEAN_REPORT = load_volunteers(find_csv())
    except FileNotFoundError as e:
        print("ERROR:", e); sys.exit(1)
    SALT = build_users()
    load_state()
    print("Loaded %d volunteers (%s)" % (len(VOLUNTEERS), CLEAN_REPORT))
    print("Dashboard: http://localhost:%d" % PORT)
    print("Logins: convener@tapmi.edu.in / convener123 | coconvener@tapmi.edu.in / coconvener123 | aarohi.anchal@tapmi.edu.in / volunteer123")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    if not HOSTED:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d" % PORT)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
