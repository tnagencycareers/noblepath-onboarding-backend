import os
import json
import time
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory deduplication store
recent_submissions = {}
lock = threading.Lock()

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS not set")
    
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sheet_url = "https://docs.google.com/spreadsheets/d/" + os.environ.get("SHEET_ID")
    spreadsheet = client.open_by_url(sheet_url)
    worksheets = spreadsheet.worksheets()
    print(f"Available worksheets: {[ws.title for ws in worksheets]}")
    return spreadsheet.worksheet("Agent Tracker")

def is_duplicate(email):
    with lock:
        now = time.time()
        # Clean old entries
        for key in list(recent_submissions.keys()):
            if now - recent_submissions[key] > 30:
                del recent_submissions[key]
        
        if email in recent_submissions:
            return True
        
        recent_submissions[email] = now
        return False

def parse_params(request):
    params = {}
    
    # Try JSON first
    try:
        data = request.get_json(force=True, silent=True)
        if data:
            if "data" in data:
                params = data["data"]
            else:
                params = data
            return params
    except:
        pass
    
    # Try form data
    try:
        params = request.form.to_dict()
        if params:
            return params
    except:
        pass
    
    # Try raw body
    try:
        body = request.data.decode("utf-8")
        for pair in body.split("&"):
            parts = pair.split("=")
            if len(parts) == 2:
                from urllib.parse import unquote_plus
                params[unquote_plus(parts[0])] = unquote_plus(parts[1])
    except:
        pass
    
    return params

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "NoblePath Onboarding Backend is live"})

@app.route("/submit", methods=["POST"])
def submit():
    # Respond immediately
    try:
        params = parse_params(request)
        email = (params.get("email") or "").strip().lower()
        
        if not email:
            return jsonify({"result": "ok"})
        
        # Deduplicate
        if is_duplicate(email):
            return jsonify({"result": "duplicate"})
        
        # Determine licensed status
        form_name   = (params.get("form-name") or "").strip()
        is_licensed = (
            params.get("licensed-status") == "yes" or
            form_name == "licensed-agent-submission"
        )
        status = "Licensed" if is_licensed else "Unlicensed"
        
        first_name = params.get("first-name") or ""
        last_name  = params.get("last-name") or ""
        full_name  = (first_name + " " + last_name).strip()
        today      = datetime.now().strftime("%Y-%m-%d")
        
        # Lead source
        raw_source    = params.get("referral-source") or ""
        referral_name = (params.get("referral-name") or "").strip()
        source = raw_source
        if raw_source.lower() == "personal referral" and referral_name:
            source = f"Personal Referral — {referral_name}"
        elif raw_source.lower() == "other" and referral_name:
            source = f"Other — {referral_name}"

        # Debit balance
        debit_balance = ""
        if is_licensed:
            debit_status = params.get("debit-balance") or "no"
            debit_amt    = (params.get("debit-amount") or "").strip()
            debit_balance = debit_amt if (debit_status == "yes" and debit_amt) else "0"

        na = "N/A" if is_licensed else ""

        row = [
            full_name,
            params.get("email") or "",
            params.get("phone") or "",
            params.get("address") or "",
            today,
            params.get("state") or "",
            status,
            params.get("licensed-states") or "",
            params.get("npn") or "",
            params.get("years-licensed") or "",
            params.get("carriers") or "",
            params.get("upline-current") or "",
            debit_balance,
            source,
            na, na, na,  # Xcel, Exam Scheduled, Exam Passed
            "", "", "", "", "", ""  # ICA, SureLC, Contracted, Active, First Policy, Notes
        ]

        sheet = get_sheet()
        sheet.append_row(row, value_input_option="USER_ENTERED")

        return jsonify({"result": "success"})

    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"result": "error", "message": str(e)}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
