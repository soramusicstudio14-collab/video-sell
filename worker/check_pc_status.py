#!/usr/bin/env python3
"""
GitHub Actions is script ko sabse pehle chalata hai taaki pata chale ki
PC (worker.py loop mode) abhi online/active hai ya nahi.

Logic: agar "Heartbeat" tab me time HEARTBEAT_FRESH_MINUTES se purana nahi hai,
matlab PC abhi bhi chal raha hai aur khud order process kar raha hai —
GitHub ko kuch karne ki zaroorat nahi, chup-chaap exit ho jaata hai.

Agar heartbeat missing hai ya purana hai, matlab PC band hai — script exit
code 0 ke saath khatm hota hai aur workflow aage worker.py --once chalata hai.

Exit codes:
  0 -> PC OFFLINE lag raha hai, GitHub Actions ko orders process karne chahiye
  1 -> PC ONLINE hai (heartbeat taaza hai), GitHub Actions kuch na kare
"""

import os
import sys
import json
import datetime as dt

import gspread
from google.oauth2.service_account import Credentials as SACredentials

SHEET_ID = os.environ["SHEET_ID"]
HEARTBEAT_TAB = "Heartbeat"
HEARTBEAT_FRESH_MINUTES = int(os.environ.get("HEARTBEAT_FRESH_MINUTES", "6"))

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def main():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = SACredentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)

    try:
        tab = sheet.worksheet(HEARTBEAT_TAB)
        value = tab.acell("A1").value
    except Exception:
        value = None

    if not value:
        print("Koi heartbeat nahi mila — PC offline maan rahe hain.")
        sys.exit(0)

    try:
        last = dt.datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        print("Heartbeat parse nahi hua — PC offline maan rahe hain.")
        sys.exit(0)

    age_minutes = (dt.datetime.utcnow() - last).total_seconds() / 60

    if age_minutes <= HEARTBEAT_FRESH_MINUTES:
        print(f"PC online hai (heartbeat {age_minutes:.1f} min purana). GitHub kuch nahi karega.")
        sys.exit(1)

    print(f"PC offline lag raha hai (heartbeat {age_minutes:.1f} min purana). GitHub process karega.")
    sys.exit(0)


if __name__ == "__main__":
    main()
