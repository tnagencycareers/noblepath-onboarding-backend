import os
import json
import gspread
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.oauth2.service_account import Credentials

app = Flask(__name__)
CORS(app)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet_id = os.environ.get("SHEET_ID")
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet("Agent Tracker")


STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY"
}

def abbrev(state):
    if not state:
        return ""
    return STATE_ABBREV.get(state.strip(), state.strip())

@app.route("/", methods=["GET", "HEAD"])
def index():
    return jsonify({"status": "ok"})

@app.route("/submit", methods=["POST"])
def submit():
    try:
        data = request.form.to_dict()
        if not data:
            try:
                data = request.get_json(force=True) or {}
                if "data" in data:
                    data = data["data"]
            except:
                data = {}

        print(f"Received data: {data}")

        # Parse name
        first = data.get("first-name", "")
        last  = data.get("last-name", "")
        full_name = (first + " " + last).strip()

        # Licensed status
        licensed_status = data.get("licensed-status", "")
        is_licensed = "Licensed" if licensed_status == "yes" else "Unlicensed"

        # Date
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        # Licensing progress defaults for licensed agents
        xcel_reg    = "N/A" if is_licensed == "Licensed" else ""
        exam_sched  = "N/A" if is_licensed == "Licensed" else ""
        exam_passed = "N/A" if is_licensed == "Licensed" else ""

        sheet = get_sheet()

        # Find next empty row (after header rows 1-3)
        all_values = sheet.col_values(1)  # Full Name column A
        next_row = len(all_values) + 1
        if next_row < 4:
            next_row = 4

        # Write each value to exact column position
        # A=1 Full Name, B=2 Active/Inactive, C=3 Email, D=4 Phone
        # E=5 Address, F=6 City, G=7 ZIP, H=8 Date Hired, I=9 Home State
        # J=10 Status, K=11 Licensed States, L=12 NPN, M=13 Years Licensed
        # N=14 Carriers, O=15 Upline/IMO, P=16 Debit Balance, Q=17 Lead Source
        # R=18 Xcel Registered, S=19 Exam Scheduled, T=20 Exam Passed
        # U=21 ICA Signed, V=22 SureLC Setup, W=23 Contracted
        # X=24 Active Writing, Y=25 First Policy Date, Z=26 Bootcamp Date, AA=27 Notes

        updates = [
            (next_row, 1,  full_name),
            (next_row, 2,  ""),                                     # Active/Inactive (blank, filled manually)
            (next_row, 3,  data.get("email", "")),
            (next_row, 4,  data.get("phone", "")),
            (next_row, 5,  data.get("address", "")),
            (next_row, 6,  data.get("city", "")),
            (next_row, 7,  data.get("zip", "")),
            (next_row, 8,  today),
            (next_row, 9,  abbrev(data.get("state", ""))),
            (next_row, 10, is_licensed),
            (next_row, 11, ", ".join([abbrev(s.strip()) for s in data.get("licensed-states", "").split(",") if s.strip()])),
            (next_row, 12, data.get("npn", "")),
            (next_row, 13, data.get("years-licensed", "")),
            (next_row, 14, data.get("carriers", "")),
            (next_row, 15, data.get("upline-current", "")),
            (next_row, 16, data.get("debit-amount", "0")),
            (next_row, 17, data.get("referral-source", "").replace("ZipRecruiter", "Zip Recruiter")),
            (next_row, 18, xcel_reg),
            (next_row, 19, exam_sched),
            (next_row, 20, exam_passed),
            (next_row, 21, ""),   # ICA Signed
            (next_row, 22, ""),   # SureLC Setup
            (next_row, 23, ""),   # Contracted
            (next_row, 24, ""),   # Active Writing
            (next_row, 25, ""),   # First Policy Date
            (next_row, 26, ""),   # Bootcamp Date
            (next_row, 27, data.get("notes", "")),
        ]

        # Batch update all cells at once for efficiency
        cell_list = []
        for row, col, value in updates:
            cell = gspread.Cell(row, col, value)
            cell_list.append(cell)

        sheet.update_cells(cell_list, value_input_option="USER_ENTERED")

        print(f"Successfully wrote row {next_row} for {full_name}")
        return jsonify({"result": "success", "row": next_row})

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"result": "error", "message": str(e)}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
