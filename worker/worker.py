#!/usr/bin/env python3
"""
worker.py — Gift Video automation worker.

Ye script Google Sheet ("Orders" tab) me dekhkar:
  1. Jo order "paid" hai aur delivery ka time aa gaya hai, unke liye
     tumhari subscriber_gift_video.py se video banata hai.
  2. Video seedha customer ke EMAIL par attachment ke roop me bhej deta hai
     (koi Drive/storage ki zaroorat nahi).
     - Agar video file EMAIL_MAX_ATTACHMENT_MB se badi hai (email attachment
       limits ki wajah se), tab hi Google Drive par upload karke uska link
       email me bhejta hai — yeh sirf fallback hai.
  3. Sheet me status "delivered" (ya problem hone par "needs_manual") kar deta hai.
  4. Kaam ho jaane ke baad local video file delete kar deta hai (storage rakhne
     ki zaroorat nahi), sirf fail hone par file rakhta hai taaki manually bhej sako.

Usage:
  python worker.py                  # PC par loop mode (har minute check)
  python worker.py --once           # ek hi baar chalao aur exit (GitHub Actions isko use karta hai)
  python worker.py --heartbeat-only # sirf heartbeat likho, orders process mat karo (debug ke liye)
  python worker.py --auth           # sirf Drive OAuth login

IMPORTANT: Ye script apni saari secret values (.env file se) environment
variables ke through leti hai. Koi bhi secret code me hardcoded nahi hai.
PC pe chalane ke liye is folder me ek `.env` file banao (README dekho).
"""

import os
import sys
import time
import json
import argparse
import smtplib
import datetime as dt
from email.message import EmailMessage

from dotenv import load_dotenv
load_dotenv()  # is folder ki .env file se environment variables load karta hai

import gspread
from google.oauth2.service_account import Credentials as SACredentials
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests

# ------------------------------------------------------------------ CONFIG
# NOTE: In se kisi bhi variable me hardcoded default value NAHI honi chahiye —
# sab .env / environment variables se aani chahiye, warna Netlify ka secret
# scanner build fail kar dega aur secrets repo me leak ho sakte hain.
SHEET_ID = os.environ.get("SHEET_ID")
ORDERS_TAB = "Orders"
HEARTBEAT_TAB = "Heartbeat"

# Drive sirf FALLBACK ke liye chahiye — jab video email attachment ke liye bahut badi ho.
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
DRIVE_TOKEN_FILE = os.environ.get("DRIVE_TOKEN_FILE", "token.json")
DRIVE_CREDENTIALS_FILE = os.environ.get("DRIVE_CREDENTIALS_FILE", "credentials.json")  # OAuth client (Desktop app)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

SHEETS_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")  # sheets ke liye
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")  # channel photo/naam ke liye

EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
EMAIL_MAX_ATTACHMENT_MB = float(os.environ.get("EMAIL_MAX_ATTACHMENT_MB", "20"))  # isse bada -> Drive fallback

# Raw string (r"...") use kiya hai taaki escape sequence warnings na aayein.
# Ye paths bhi ab .env se aani chahiye (PC-specific hone ki wajah se).
VIDEO_SCRIPT_PATH = os.environ.get(
    "VIDEO_SCRIPT_PATH",
    r"D:\ALL AUTOMATION FILE\youtube video sell\gift-video-site\package\subscriber_gift_video.py",
)
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    r"D:\ALL AUTOMATION FILE\youtube video sell\gift-video-site\output video",
)

# columns (0-indexed) in the "Orders" tab
COL_ORDER_ID, COL_CREATED_AT, COL_YT, COL_EMAIL, COL_PLAN_IDX, COL_AMOUNT, \
    COL_SUBS, COL_HOURS, COL_STATUS, COL_DELIVERY_AT, COL_VIDEO_LINK, COL_RZP_ID = range(12)


def _require_config():
    """Zaroori secrets missing hone par turant clear error do, chupke fail mat ho."""
    missing = []
    if not SHEET_ID:
        missing.append("SHEET_ID")
    if not SHEETS_SERVICE_ACCOUNT_JSON:
        missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
    if missing:
        sys.exit(f"Environment variable(s) missing: {', '.join(missing)} — .env file check karo.")


# ------------------------------------------------------------------ GOOGLE SHEETS
def get_sheet():
    _require_config()
    info = json.loads(SHEETS_SERVICE_ACCOUNT_JSON)
    creds = SACredentials.from_service_account_info(info, scopes=SHEETS_SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def write_heartbeat(sheet):
    try:
        # Seedha koshish karo ki worksheet mil jaye
        tab = sheet.worksheet(HEARTBEAT_TAB)
    except Exception:
        # Agar nahi mili (kisi bhi wajah se), toh nayi bana lo
        try:
            tab = sheet.add_worksheet(title=HEARTBEAT_TAB, rows=2, cols=2)
        except Exception:
            # Agar tab pehle se hai lekin error de diya, toh dobara fetch karo
            tab = sheet.worksheet(HEARTBEAT_TAB)

    try:
        tab.update_acell("A1", dt.datetime.now(dt.timezone.utc).isoformat())
    except Exception as e:
        print(f"Heartbeat update error: {e}")


def get_due_orders(sheet):
    tab = sheet.worksheet(ORDERS_TAB)
    rows = tab.get_all_values()
    due = []
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for i, row in enumerate(rows):
        if i == 0:
            continue  # header
        if len(row) <= COL_RZP_ID:
            continue
        if row[COL_STATUS] != "paid":
            continue

        delivery_at_str = row[COL_DELIVERY_AT].strip()
        if not delivery_at_str:
            # webhook ne calculate nahi kiya tha — created_at + hours se nikal lo
            try:
                created = dt.datetime.fromisoformat(row[COL_CREATED_AT].replace("Z", ""))
                hours = float(row[COL_HOURS])
                delivery_at = created + dt.timedelta(hours=hours)
            except Exception:
                continue
        else:
            try:
                delivery_at = dt.datetime.fromisoformat(delivery_at_str.replace("Z", ""))
            except Exception:
                continue

        if delivery_at <= now:
            due.append((i + 1, row))  # sheet row number (1-indexed), row data
    return tab, due


def update_row(tab, row_number, status=None, video_link=None, delivery_at=None):
    if status is not None:
        tab.update_cell(row_number, COL_STATUS + 1, status)
    if video_link is not None:
        tab.update_cell(row_number, COL_VIDEO_LINK + 1, video_link)
    if delivery_at is not None:
        tab.update_cell(row_number, COL_DELIVERY_AT + 1, delivery_at)


# ------------------------------------------------------------------ YOUTUBE
def get_channel_info(yt_handle):
    """YouTube Data API se channel ka naam aur photo laata hai. Fail hone par None."""
    if not YOUTUBE_API_KEY:
        return None
    handle = yt_handle.lstrip("@")
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "snippet", "forHandle": handle, "key": YOUTUBE_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None
        snippet = items[0]["snippet"]
        return {
            "title": snippet["title"],
            "photo_url": snippet["thumbnails"]["high"]["url"]
        }
    except Exception as e:
        print(f"YouTube fetch fail: {e}")
        return None


# ------------------------------------------------------------------ VIDEO GENERATION
# subscriber_gift_video.py ke apne CLI arguments hain (--channel, --target, --name,
# --avatar, --outdir, ...). Ye worker.py ke pehle wale --channel-name/--target-subs/
# --output se MATCH nahi karte the — isliye yahan sahi arguments bheje ja rahe hain.
ALLOWED_TARGETS = {"1000", "2000", "3000", "4000", "5000", "10000"}


def generate_video(channel_handle, channel_name, avatar_url, target_subs, order_id):
    """
    Tumhari subscriber_gift_video.py ko call karta hai.
    Ye script ek single --output file path le nahi sakti — sirf --outdir (folder)
    leti hai aur khud apna filename banati hai. Isliye har order ke liye ek alag
    (unique) sub-folder banate hain, script chalate hain, aur phir usme jo .mp4
    bani hai use dhundh lete hain.
    """
    import subprocess
    import glob

    target_str = str(int(float(target_subs)))
    if target_str not in ALLOWED_TARGETS:
        raise RuntimeError(
            f"target_subs '{target_subs}' allowed values me nahi hai: {sorted(ALLOWED_TARGETS)}"
        )

    out_dir = os.path.join(OUTPUT_DIR, order_id)
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        sys.executable, VIDEO_SCRIPT_PATH,
        "--channel", channel_handle,
        "--target", target_str,
        "--outdir", out_dir,
    ]
    if channel_name:
        cmd += ["--name", channel_name]
    if avatar_url:
        cmd += ["--avatar", avatar_url]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"video script fail: {result.stderr[-800:]}")

    mp4_files = sorted(
        glob.glob(os.path.join(out_dir, "*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not mp4_files:
        raise RuntimeError(f"video file bana nahi (outdir check karo: {out_dir})")
    return mp4_files[0]


# ------------------------------------------------------------------ GOOGLE DRIVE (fallback only)
def get_drive_service():
    creds = None
    if os.path.exists(DRIVE_TOKEN_FILE):
        creds = UserCredentials.from_authorized_user_file(DRIVE_TOKEN_FILE, DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(DRIVE_CREDENTIALS_FILE, DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(DRIVE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_to_drive(file_path, filename):
    service = get_drive_service()
    file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = file["id"]
    service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


# ------------------------------------------------------------------ EMAIL (Gmail SMTP)
def send_email(to_email, subject, body_text, attachment_path=None):
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        print("EMAIL_SENDER / EMAIL_APP_PASSWORD set nahi — email skip kiya.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg.set_content(body_text)

    if attachment_path:
        with open(attachment_path, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype="video", subtype="mp4",
                            filename=os.path.basename(attachment_path))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email send fail: {e}")
        return False


# ------------------------------------------------------------------ MAIN PROCESS
def process_due_orders():
    sheet = get_sheet()
    write_heartbeat(sheet)
    tab, due = get_due_orders(sheet)

    if not due:
        print(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] koi due order nahi.")
        return

    for row_number, row in due:
        order_id = row[COL_ORDER_ID]
        yt_handle = row[COL_YT]
        email = row[COL_EMAIL]
        subs = row[COL_SUBS]

        print(f"Processing order {order_id} ({yt_handle}, {subs} subs)")
        video_path = None
        try:
            info = get_channel_info(yt_handle)
            if info is None:
                print(f"  ⚠️ YouTube info nahi mila — needs_manual")
                update_row(tab, row_number, status="needs_manual")
                continue

            video_path = generate_video(
                channel_handle=yt_handle,
                channel_name=info["title"],
                avatar_url=info.get("photo_url"),
                target_subs=subs,
                order_id=order_id,
            )
            size_mb = os.path.getsize(video_path) / (1024 * 1024)

            subject = "Aapka Subscriber Gift Video taiyar hai! 🎁"

            if size_mb <= EMAIL_MAX_ATTACHMENT_MB:
                body = (f"Namaste,\n\n{subs} subscribers wala aapka gift video is email ke "
                        f"saath attach hai.\n\nDhanyavaad!")
                sent = send_email(email, subject, body, attachment_path=video_path)
                video_link = ""
            else:
                print(f"  ℹ️ video {size_mb:.1f}MB hai (limit {EMAIL_MAX_ATTACHMENT_MB}MB) — Drive fallback use ho raha hai")
                video_link = upload_to_drive(video_path, f"{order_id}_{yt_handle}.mp4")
                body = (f"Namaste,\n\n{subs} subscribers wala aapka gift video taiyar hai. "
                        f"File size zyada hone ki wajah se attach nahi kar paye, is link se "
                        f"dekh/download kar sakte hain:\n{video_link}\n\nDhanyavaad!")
                sent = send_email(email, subject, body)

            update_row(tab, row_number,
                       status="delivered" if sent else "needs_manual",
                       video_link=video_link)

            if sent and video_path and os.path.exists(video_path):
                os.remove(video_path)
                print(f"  ✅ email bhej di, local file delete kar di")
            elif not sent:
                print(f"  ⚠️ email fail hui — needs_manual, file rakhi hai manual bhejne ke liye")

        except Exception as e:
            print(f"  ❌ error: {e}")
            update_row(tab, row_number, status="needs_manual")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Ek baar chalao aur exit (GitHub Actions ke liye)")
    parser.add_argument("--heartbeat-only", action="store_true", help="Sirf heartbeat likho, kuch process mat karo")
    parser.add_argument("--auth", action="store_true", help="Sirf Google Drive OAuth login karo (fallback setup)")
    args = parser.parse_args()

    if args.auth:
        get_drive_service()
        print("Drive login done — token.json ban gaya.")
        return

    if args.heartbeat_only:
        write_heartbeat(get_sheet())
        print("Heartbeat likh diya.")
        return

    if args.once:
        process_due_orders()
        return

    # loop mode (PC par chalane ke liye)
    print("Worker loop shuru — Ctrl+C se roko.")
    while True:
        try:
            process_due_orders()
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()