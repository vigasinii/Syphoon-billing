"""
app.py
======
Syphoon Billing – Flask API
Endpoints:
  GET  /usage?account=ACC-001&period=March_2025  → returns usage data for the webpage
  POST /respond                                   → receives approve/dispute from webpage
  GET  /health                                    → health check
"""

import os
import logging
from datetime import date, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)  # allow approve.html on Render to call this API

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("syphoon.api")

# ---------------------------------------------------------------------------
# Dummy account data — replace with real DB / Imham's API when ready
# ---------------------------------------------------------------------------
ACCOUNTS = {
    "ACC-001": {"client": "Acme Corp",        "requests": 172822, "rate": 0.002,  "policy": "cycle_start", "email": "billing@acmecorp.com"},
    "ACC-002": {"client": "Bright Analytics", "requests": 156309, "rate": 0.0015, "policy": "cycle_start", "email": "accounts@brightanalytics.io"},
    "ACC-003": {"client": "DataNinja Ltd",    "requests": 151889, "rate": 0.003,  "policy": "cycle_end",   "email": "finance@dataninja.com"},
}

MONTHS = {
    "January":0,"February":1,"March":2,"April":3,"May":4,"June":5,
    "July":6,"August":7,"September":8,"October":9,"November":10,"December":11
}

def parse_invoice_date(period: str, policy: str) -> date:
    parts = period.replace("_", " ").split(" ")
    mon, yr = parts[0], int(parts[1]) if len(parts) > 1 else 2025
    m = MONTHS.get(mon, 2)
    if policy == "cycle_end":
        return date(yr + 1, 1, 1) if m == 11 else date(yr, m + 2, 1)
    return date(yr, m + 1, 1)


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------
@app.route("/usage", methods=["GET"])
def get_usage():
    account_id = request.args.get("account", "")
    period     = request.args.get("period", "").replace("_", " ")

    if not account_id or account_id not in ACCOUNTS:
        return jsonify({"error": "Unknown account"}), 404

    acc = ACCOUNTS[account_id]
    invoice_date = parse_invoice_date(period, acc["policy"])
    due_date     = invoice_date + timedelta(days=30)
    amount       = round(acc["requests"] * acc["rate"], 2)

    return jsonify({
        "account_id":    account_id,
        "client":        acc["client"],
        "period":        period,
        "invoice_date":  invoice_date.strftime("%d/%m/%Y"),
        "due_date":      due_date.strftime("%d/%m/%Y"),
        "payment_terms": "Net 30",
        "requests":      acc["requests"],
        "rate":          acc["rate"],
        "amount":        amount,
        "currency":      "USD",
    })


# ---------------------------------------------------------------------------
# POST /respond
# ---------------------------------------------------------------------------
@app.route("/respond", methods=["POST"])
def respond():
    data       = request.get_json()
    account_id = data.get("account")
    period     = data.get("period", "").replace("_", " ")
    action     = data.get("action")   # "approve" or "dispute"
    remarks    = data.get("remarks", "")

    if not account_id or action not in ("approve", "dispute"):
        return jsonify({"error": "Invalid request"}), 400

    acc = ACCOUNTS.get(account_id)
    if not acc:
        return jsonify({"error": "Unknown account"}), 404

    logger.info(f"[RESPOND] {account_id} | {period} | {action.upper()}")

    if action == "approve":
        _trigger_invoice(account_id, period, acc)
        return jsonify({"status": "approved", "message": "Invoice will be issued shortly."})
    else:
        _hold_invoice(account_id, period, acc, remarks)
        return jsonify({"status": "disputed", "message": "Dispute logged. Invoice on hold."})


def _trigger_invoice(account_id, period, acc):
    """Trigger Zoho invoice on approval."""
    logger.info(f"[ZOHO] Creating invoice for {account_id} | {period}")
    # TODO: call zoho_books.create_invoice() here
    # For now log + send Slack alert
    _slack_alert(
        f"✅ *{acc['client']}* (`{account_id}`) approved usage for *{period}*.\n"
        f"Proceeding to create Zoho invoice."
    )


def _hold_invoice(account_id, period, acc, remarks):
    """Hold invoice and alert internal team on dispute."""
    logger.warning(f"[DISPUTE] {account_id} | {period} | {remarks}")
    _slack_alert(
        f"⚠️ *DISPUTE* — *{acc['client']}* (`{account_id}`) disputed usage for *{period}*.\n"
        f"*Remarks:* {remarks}\n"
        f"Invoice on hold. Review at disputes@syphoon.com"
    )


def _slack_alert(message: str):
    """Post an alert to the Slack channel."""
    token      = os.getenv("SLACK_BOT_TOKEN", "")
    channel_id = os.getenv("SLACK_CHANNEL_ID", "")
    if not token or token.startswith("xoxb-your"):
        logger.warning("[SLACK] Token not configured.")
        return
    try:
        from slack_sdk import WebClient
        WebClient(token=token).chat_postMessage(channel=channel_id, text=message)
        logger.info("[SLACK] Alert sent.")
    except Exception as e:
        logger.error(f"[SLACK] Failed: {e}")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "syphoon-billing-api"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
