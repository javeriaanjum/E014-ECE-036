#!/usr/bin/env python3
"""ECE-036 extended-warranty pricing and claim engine (stdlib only).
 
Usage:  python3 engine.py [--data DIR] [--out DIR] [commands.txt]
Business rules are tagged BR-01 ... BR-08 in comments (see DESIGN.md).
"""
import argparse
import calendar
import csv
import os
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
 
# ---- BR-01: plan price as % of product price, plus GST -------------------
RATES = {
    "TV": {1: Decimal("6"), 2: Decimal("10"), 3: Decimal("14")},
    "AC": {1: Decimal("8"), 2: Decimal("13"), 3: Decimal("18")},
    "FRIDGE": {1: Decimal("5"), 2: Decimal("9"), 3: Decimal("12")},
}
GST_PCT = Decimal("18")
LOADING = Decimal("1.5")
# ---- BR-04 / BR-05 / BR-06 / BR-07 constants -----------------------------
MAX_CLAIMS_PER_YEAR = 3
DEDUCTIBLE = Decimal("500")
EXCLUDED_FAULTS = {"PHYSICAL_DAMAGE", "LIQUID", "CONSUMABLE"}
DEPRECIATION_PER_YEAR = Decimal("0.10")
REPLACE_THRESHOLD = Decimal("0.60")
ADMIN_PCT = Decimal("10")
 
CENT = Decimal("0.01")
 
 
def q2(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)
 
 
def money(x):
    return "{:.2f}".format(q2(x))
 
 
def pct_str(d):
    s = format(d.normalize(), "f")
    return s
 
 
# ---- date helpers ---------------------------------------------------------
def parse_date(s):
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))
 
 
def add_months(d, n):
    """Add n calendar months, clamping to month end (2024-01-31 + 1m = 2024-02-29)."""
    idx = d.year * 12 + (d.month - 1) + n
    y, m = divmod(idx, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))
 
 
def complete_months(start, end):
    """Largest n >= 0 with add_months(start, n) <= end."""
    if end < start:
        return 0
    n = (end.year - start.year) * 12 + (end.month - start.month)
    while n > 0 and add_months(start, n) > end:
        n -= 1
    return max(n, 0)
 
 
def completed_years(start, end):
    return complete_months(start, end) // 12
 
 
# ---- policy ---------------------------------------------------------------
class Policy:
    def __init__(self, row):
        self.policy_id = row["policy_id"]
        self.customer_id = row["customer_id"]
        self.category = row["category"]
        self.price = Decimal(row["product_price"])
        self.product_date = parse_date(row["product_purchase_date"])
        self.plan_years = int(row["plan_years"])
        self.purchase_date = parse_date(row["policy_purchase_date"])
        # BR-02 purchase window
        self.days_after = (self.purchase_date - self.product_date).days
        if self.days_after <= 30:
            self.band = "STANDARD"
        elif self.purchase_date <= add_months(self.product_date, 11):
            self.band = "LOADED_1_5X"
        else:
            self.band = "NOT_SOLD"
        # BR-01 pricing
        if self.band == "NOT_SOLD":
            self.rate = None
            self.premium = self.gst = self.total = None
            self.cover_start = self.cover_end = None
        else:
            base = RATES[self.category][self.plan_years]
            self.rate = base * LOADING if self.band == "LOADED_1_5X" else base
            self.premium = q2(self.price * self.rate / 100)
            self.gst = q2(self.premium * GST_PCT / 100)
            self.total = self.premium + self.gst
            # BR-03 coverage window
            warranty_end = add_months(self.product_date, 12)
            self.cover_start = warranty_end + timedelta(days=1)
            self.cover_end = add_months(self.cover_start, 12 * self.plan_years) - timedelta(days=1)
        # mutable state
        self.closed = False
        self.cancelled = False
        self.admitted_total = 0
        self.years = {}  # policy_year -> [count, payout]
 
    @property
    def sold(self):
        return self.band != "NOT_SOLD"
 
    def policy_year(self, d):
        """BR-08: 12-month blocks counted from coverage start."""
        k = 1
        while k < self.plan_years and add_months(self.cover_start, 12 * k) <= d:
            k += 1
        return k
 
    def year_state(self, k):
        return self.years.setdefault(k, [0, Decimal("0")])
 
    def status(self, as_of):
        if not self.sold:
            return "NOT_SOLD"
        if self.cancelled:
            return "CANCELLED"
        if self.closed:
            return "CLOSED"
        if self.cover_end < as_of:
            return "EXPIRED"
        return "ACTIVE"
 
 
# ---- engine ---------------------------------------------------------------
REGISTER_COLS = ["policy_id", "customer_id", "category", "product_price", "plan_years",
                 "days_after_purchase", "pricing_band", "rate_pct", "premium_before_gst", "gst",
                 "premium_total", "coverage_start", "coverage_end", "status"]
CLAIM_COLS = ["claim_id", "policy_id", "claim_date", "policy_year", "fault_type", "repair_estimate",
              "depreciated_value", "decision", "reason", "deductible", "payout",
              "claims_remaining_in_year", "payout_remaining_in_year"]
CANCEL_COLS = ["cancel_id", "policy_id", "cancel_date", "total_months", "months_remaining",
               "refund_before_admin", "admin_charge", "refund", "reason"]
 
 
def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
 
 
class Engine:
    def __init__(self):
        self.policies = {}
        self.order = []
        self.claim_rows = []
        self.cancel_rows = []
 
    def load_policies(self, rows):
        for r in rows:
            p = Policy(r)
            self.policies[p.policy_id] = p
            self.order.append(p.policy_id)
 
    # ---- BR-03..BR-06 -----------------------------------------------------
    def claim(self, c):
        p = self.policies[c["policy_id"]]
        cd = parse_date(c["claim_date"])
        est = Decimal(c["repair_estimate"])
        fault = c["fault_type"]
        out = {"claim_id": c["claim_id"], "policy_id": p.policy_id, "claim_date": c["claim_date"],
               "policy_year": "", "fault_type": fault, "repair_estimate": money(est),
               "depreciated_value": "", "decision": "REJECTED", "reason": "",
               "deductible": money(0), "payout": money(0),
               "claims_remaining_in_year": "", "payout_remaining_in_year": ""}
 
        def reject(reason):
            out["reason"] = reason
            self.claim_rows.append(out)
 
        if not p.sold:
            return reject("NOT_SOLD")
 
        # BR-06 depreciated value: 10% per completed year since product purchase
        yrs = completed_years(p.product_date, cd)
        dv = q2(p.price * max(Decimal(0), 1 - DEPRECIATION_PER_YEAR * yrs))
        out["depreciated_value"] = money(dv)
 
        if cd < p.cover_start or cd > p.cover_end:
            return reject("OUT_OF_COVER")
 
        k = p.policy_year(cd)
        out["policy_year"] = k
        st = p.year_state(k)
 
        def remaining():
            out["claims_remaining_in_year"] = MAX_CLAIMS_PER_YEAR - st[0]
            out["payout_remaining_in_year"] = money(p.price - st[1])
 
        remaining()
        if p.closed or p.cancelled:
            return reject("POLICY_CLOSED")
        if fault in EXCLUDED_FAULTS:  # BR-05
            return reject("EXCLUDED")
        cap_left = p.price - st[1]
        if st[0] >= MAX_CLAIMS_PER_YEAR or cap_left <= 0:  # BR-04
            return reject("CLAIM_LIMIT")
 
        if est > REPLACE_THRESHOLD * dv:  # BR-06: strictly greater -> replace
            out["decision"] = "REPLACEMENT"
            payout = min(dv, cap_left)
            ded = Decimal(0)
            p.closed = True
        else:
            out["decision"] = "REPAIR"
            ded = min(DEDUCTIBLE, est) if st[0] >= 1 else Decimal(0)  # BR-04
            payout = min(est - ded, cap_left)
        payout = q2(payout)
        st[0] += 1
        st[1] += payout
        p.admitted_total += 1
        out["deductible"] = money(ded)
        out["payout"] = money(payout)
        remaining()
        self.claim_rows.append(out)
 
    # ---- BR-07 ------------------------------------------------------------
    def cancel(self, r):
        p = self.policies[r["policy_id"]]
        cd = parse_date(r["cancel_date"])
        out = {"cancel_id": r["cancel_id"], "policy_id": p.policy_id, "cancel_date": r["cancel_date"],
               "total_months": "", "months_remaining": "", "refund_before_admin": money(0),
               "admin_charge": money(0), "refund": money(0), "reason": ""}
        self.cancel_rows.append(out)
        if not p.sold:
            out["reason"] = "NOT_SOLD"
            return
        if p.cancelled:
            out["reason"] = "ALREADY_CANCELLED"
            return
        total = p.plan_years * 12
        # months remaining counted to the day after coverage end (end is inclusive);
        # a cancellation before coverage starts keeps all months (TRAP8).
        rem = complete_months(max(cd, p.cover_start), p.cover_end + timedelta(days=1))
        rem = min(rem, total)
        out["total_months"] = total
        out["months_remaining"] = rem
        p.cancelled = True
        if p.admitted_total > 0:
            out["reason"] = "CLAIM_ADMITTED"
            return
        before = q2(p.premium * rem / total)
        admin = q2(before * ADMIN_PCT / 100)
        out["refund_before_admin"] = money(before)
        out["admin_charge"] = money(admin)
        out["refund"] = money(before - admin)
 
    # ---- reports ----------------------------------------------------------
    def register_rows(self, as_of):
        rows = []
        for pid in self.order:
            p = self.policies[pid]
            rows.append({
                "policy_id": p.policy_id, "customer_id": p.customer_id, "category": p.category,
                "product_price": money(p.price), "plan_years": p.plan_years,
                "days_after_purchase": p.days_after, "pricing_band": p.band,
                "rate_pct": "" if p.rate is None else pct_str(p.rate),
                "premium_before_gst": "" if p.premium is None else money(p.premium),
                "gst": "" if p.gst is None else money(p.gst),
                "premium_total": "" if p.total is None else money(p.total),
                "coverage_start": "" if p.cover_start is None else p.cover_start.isoformat(),
                "coverage_end": "" if p.cover_end is None else p.cover_end.isoformat(),
                "status": p.status(as_of)})
        return rows
 
 
def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
 
 
def run(data_dir, out_dir, commands_path):
    os.makedirs(out_dir, exist_ok=True)
    eng = Engine()
    claims = {r["claim_id"]: r for r in read_csv(os.path.join(data_dir, "claims.csv"))}
    cancels = {r["cancel_id"]: r for r in read_csv(os.path.join(data_dir, "cancellations.csv"))}
    with open(commands_path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f]
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("|")
        cmd, args = parts[0], parts[1:]
        if cmd == "LOAD_POLICIES":
            eng.load_policies(read_csv(os.path.join(data_dir, args[0])))
        elif cmd == "CLAIM":
            eng.claim(claims[args[0]])
        elif cmd == "CANCEL":
            eng.cancel(cancels[args[0]])
        elif cmd == "PRINT_POLICY_REGISTER":
            write_csv(os.path.join(out_dir, "policy_register.csv"), REGISTER_COLS,
                      eng.register_rows(parse_date(args[0])))
        elif cmd == "PRINT_CLAIMS_REPORT":
            write_csv(os.path.join(out_dir, "claims_report.csv"), CLAIM_COLS, eng.claim_rows)
        else:
            print("unknown command: " + ln, file=sys.stderr)
    write_csv(os.path.join(out_dir, "cancellation_report.csv"), CANCEL_COLS, eng.cancel_rows)
    return eng
 
 
def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=project_dir)
    ap.add_argument("--out", default=os.path.join(project_dir, "output"))
    ap.add_argument("commands", nargs="?", default=None)
    a = ap.parse_args()
    cmds = a.commands or os.path.join(a.data, "commands.txt")
    run(a.data, a.out, cmds)
 
 
if __name__ == "__main__":
    main()
