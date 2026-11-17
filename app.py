from pathlib import Path
from datetime import date
import csv
import io
import threading

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort

import engine as warranty_engine

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "ece036-local-development-key-change-before-deployment"

# This app is designed for a local classroom/demo environment.
# One shared engine instance is used so claims/cancellations entered in the UI
# affect subsequent screens during this running session.
engine_lock = threading.RLock()


def load_csv(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return []
    return warranty_engine.read_csv(str(path))


def initialise_engine():
    """Load the provided sample pack and replay its commands in their given order."""
    commands = DATA_DIR / "commands.txt"
    if commands.exists():
        return warranty_engine.run(str(DATA_DIR), str(OUTPUT_DIR), str(commands))
    eng = warranty_engine.Engine()
    eng.load_policies(load_csv("policies.csv"))
    return eng


eng = initialise_engine()


def current_register():
    return eng.register_rows(date.today())


def money_value(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def dashboard_stats():
    policies = current_register()
    claims = eng.claim_rows
    cancellations = eng.cancel_rows
    return {
        "total_policies": len(policies),
        "active_policies": sum(p["status"] == "ACTIVE" for p in policies),
        "closed_policies": sum(p["status"] == "CLOSED" for p in policies),
        "cancelled_policies": sum(p["status"] == "CANCELLED" for p in policies),
        "total_claims": len(claims),
        "approved_claims": sum(p["decision"] in ("REPAIR", "REPLACEMENT") for p in claims),
        "rejected_claims": sum(p["decision"] == "REJECTED" for p in claims),
        "total_payout": sum(money_value(p["payout"]) for p in claims),
        "total_refunds": sum(money_value(p["refund"]) for p in cancellations),
    }


@app.route("/")
def dashboard():
    with engine_lock:
        stats = dashboard_stats()
        recent_claims = list(reversed(eng.claim_rows[-6:]))
        recent_policies = list(reversed(current_register()[-6:]))
    return render_template("index.html", stats=stats, recent_claims=recent_claims,
                           recent_policies=recent_policies, today=date.today().isoformat())


@app.route("/policies")
def policies():
    q = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "").strip().upper()
    with engine_lock:
        rows = current_register()
    if q:
        rows = [r for r in rows if q in r["policy_id"].lower()
                or q in r["customer_id"].lower() or q in r["category"].lower()]
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    return render_template("policies.html", policies=rows, q=request.args.get("q", ""),
                           status=status_filter)


@app.route("/policies/new", methods=["GET", "POST"])
def new_policy():
    if request.method == "POST":
        form = request.form
        row = {
            "policy_id": form.get("policy_id", "").strip().upper(),
            "customer_id": form.get("customer_id", "").strip().upper(),
            "category": form.get("category", "").strip().upper(),
            "product_price": form.get("product_price", "").strip(),
            "product_purchase_date": form.get("product_purchase_date", "").strip(),
            "plan_years": form.get("plan_years", "").strip(),
            "policy_purchase_date": form.get("policy_purchase_date", "").strip(),
        }
        try:
            if not all(row.values()):
                raise ValueError("Please complete every field.")
            with engine_lock:
                if row["policy_id"] in eng.policies:
                    raise ValueError("That policy ID already exists.")
                # Validate the policy using the same Policy class and rules as the original engine.
                policy_obj = warranty_engine.Policy(row)
                eng.load_policies([row])
            flash(f"Policy {policy_obj.policy_id} added. Pricing band: {policy_obj.band}.", "success")
            return redirect(url_for("policies"))
        except Exception as exc:
            flash(f"Could not add policy: {exc}", "error")
    return render_template("new_policy.html", today=date.today().isoformat())


@app.route("/claims")
def claims():
    with engine_lock:
        rows = list(reversed(eng.claim_rows))
    return render_template("claims.html", claims=rows)


@app.route("/claims/new", methods=["GET", "POST"])
def new_claim():
    with engine_lock:
        policy_options = [{"policy_id": p.policy_id, "customer_id": p.customer_id,
                           "category": p.category} for p in eng.policies.values()]
    if request.method == "POST":
        row = {
            "claim_id": request.form.get("claim_id", "").strip().upper(),
            "policy_id": request.form.get("policy_id", "").strip().upper(),
            "claim_date": request.form.get("claim_date", "").strip(),
            "repair_estimate": request.form.get("repair_estimate", "").strip(),
            "fault_type": request.form.get("fault_type", "").strip().upper(),
        }
        try:
            if not all(row.values()):
                raise ValueError("Please complete every field.")
            with engine_lock:
                if row["policy_id"] not in eng.policies:
                    raise ValueError("Policy ID was not found.")
                if any(c["claim_id"] == row["claim_id"] for c in eng.claim_rows):
                    raise ValueError("That claim ID has already been used.")
                eng.claim(row)
                result = eng.claim_rows[-1]
            flash(f"Claim {row['claim_id']}: {result['decision']} — {result['reason'] or 'Processed'}; payout ₹{result['payout']}.", "success")
            return redirect(url_for("claims"))
        except Exception as exc:
            flash(f"Could not process claim: {exc}", "error")
    return render_template("new_claim.html", policies=policy_options, today=date.today().isoformat())


@app.route("/cancellations")
def cancellations():
    with engine_lock:
        rows = list(reversed(eng.cancel_rows))
    return render_template("cancellations.html", cancellations=rows)


@app.route("/cancellations/new", methods=["GET", "POST"])
def new_cancellation():
    with engine_lock:
        policy_options = [{"policy_id": p.policy_id, "customer_id": p.customer_id}
                          for p in eng.policies.values()]
    if request.method == "POST":
        row = {
            "cancel_id": request.form.get("cancel_id", "").strip().upper(),
            "policy_id": request.form.get("policy_id", "").strip().upper(),
            "cancel_date": request.form.get("cancel_date", "").strip(),
        }
        try:
            if not all(row.values()):
                raise ValueError("Please complete every field.")
            with engine_lock:
                if row["policy_id"] not in eng.policies:
                    raise ValueError("Policy ID was not found.")
                if any(c["cancel_id"] == row["cancel_id"] for c in eng.cancel_rows):
                    raise ValueError("That cancellation ID has already been used.")
                eng.cancel(row)
                result = eng.cancel_rows[-1]
            flash(f"Cancellation {row['cancel_id']} processed. Refund: ₹{result['refund']} ({result['reason'] or 'Eligible'}).", "success")
            return redirect(url_for("cancellations"))
        except Exception as exc:
            flash(f"Could not process cancellation: {exc}", "error")
    return render_template("new_cancellation.html", policies=policy_options, today=date.today().isoformat())


@app.route("/customers")
def customers():
    rows = load_csv("customers.csv")
    return render_template("customers.html", customers=rows)


@app.route("/reports")
def reports():
    with engine_lock:
        stats = dashboard_stats()
        files = [
            ("Policy Register", "policy_register.csv", len(current_register())),
            ("Claims Report", "claims_report.csv", len(eng.claim_rows)),
            ("Cancellation Report", "cancellation_report.csv", len(eng.cancel_rows)),
        ]
        # Refresh report files to include records entered during this app session.
        warranty_engine.write_csv(str(OUTPUT_DIR / "policy_register.csv"),
                                  warranty_engine.REGISTER_COLS, current_register())
        warranty_engine.write_csv(str(OUTPUT_DIR / "claims_report.csv"),
                                  warranty_engine.CLAIM_COLS, eng.claim_rows)
        warranty_engine.write_csv(str(OUTPUT_DIR / "cancellation_report.csv"),
                                  warranty_engine.CANCEL_COLS, eng.cancel_rows)
    return render_template("reports.html", files=files, stats=stats)


@app.route("/reports/download/<filename>")
def download_report(filename):
    allowed = {
        "policy_register.csv": (warranty_engine.REGISTER_COLS, lambda: current_register()),
        "claims_report.csv": (warranty_engine.CLAIM_COLS, lambda: eng.claim_rows),
        "cancellation_report.csv": (warranty_engine.CANCEL_COLS, lambda: eng.cancel_rows),
    }
    if filename not in allowed:
        abort(404)
    with engine_lock:
        cols, getter = allowed[filename]
        path = OUTPUT_DIR / filename
        warranty_engine.write_csv(str(path), cols, getter())
    return send_file(path, as_attachment=True, download_name=filename, mimetype="text/csv")


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
