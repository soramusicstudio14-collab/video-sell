# Setup Guide (Hindi)

Orders **Google Sheet** me save honge. Video **customer ke email par seedha attachment** ke roop me
bheji jaati hai — koi permanent storage nahi chahiye. Sirf agar video file bahut badi ho (email
attachment limit se zyada) tab hi Google Drive par upload hoti hai aur link email me jaata hai —
yeh sirf ek fallback hai.

WhatsApp poori tarah hata diya gaya hai.

---

## 1. Google Sheet banayein (Orders database)

1. Google Sheets me ek nayi sheet banao, naam do jo chaho (jaise "Gift Video Orders").
2. Is repo me `orders_sheet_template.csv` file di hai — usko apni Sheet me **File > Import > Upload**
   karke naye tab me import kar do, ya headers manually copy kar lo. Do tabs honi chahiye:

   **Tab 1: `Orders`** — pehli row me yeh headers (bilkul is order me):
   ```
   order_id | created_at | yt_handle | email | plan_index | amount | subs | hours | status | delivery_at | video_link | razorpay_order_id
   ```

   **Tab 2: `Heartbeat`** — khali rehne do, worker khud A1 me likhega.

3. URL me se Sheet ID copy karo:
   `https://docs.google.com/spreadsheets/d/`**`YEH_WALA_HISSA`**`/edit`

---

## 2. Google Service Account banayein (Sheets access ke liye)

Yeh account Netlify functions aur GitHub Actions dono use karenge Sheet padhne/likhne ke liye.

1. [Google Cloud Console](https://console.cloud.google.com/) me ek project banao (ya purana use karo).
2. **APIs & Services > Library** me jaakar "Google Sheets API" enable karo.
3. **APIs & Services > Credentials > Create Credentials > Service Account** banao.
4. Service account ke andar **Keys > Add Key > JSON** — ek `.json` file download hogi. Yeh poori file hi tumhara `GOOGLE_SERVICE_ACCOUNT_JSON` value hai (poora content, ek hi line me, environment variable me daalna hoga).
5. JSON file me `client_email` field hai (jaise `xxx@project.iam.gserviceaccount.com`) — is email ko apni Google Sheet me **Share** button se **Editor** access do. **Yeh step miss mat karna, warna worker/functions Sheet access nahi kar payenge.**

---

## 3. Email bhejne ka setup (Gmail SMTP — free)

1. Jis Gmail account se video bhejna hai, usme **2-Step Verification ON karo** (Google Account > Security).
2. Google Account > Security > **App Passwords** me jaakar ek naya App Password banao (16 characters).
3. Yeh values env variables me daalo:
   ```
   EMAIL_SENDER = yourbusiness@gmail.com
   EMAIL_APP_PASSWORD = <16-char app password>
   ```
4. Bas itna hi — koi aur setup nahi chahiye. Video seedha email attachment me chali jaayegi.

Doosra email provider chahiye ho (SendGrid, Resend, Brevo, etc — bade scale par better deliverability dete hain) to `worker/worker.py` ke `send_email()` function ko badal dena, baaki kuch chhedne ki zaroorat nahi.

**Attachment size limit:** Gmail/zyada tar providers ~25MB tak attachment allow karte hain. Safe margin ke liye default `EMAIL_MAX_ATTACHMENT_MB = 20` rakha hai — isse bada video ho to worker khud Drive par upload karke sirf link email karega (neeche Step 4 dekho).

---

## 4. Google Drive setup (sirf FALLBACK ke liye — bahut badi videos)

Yeh tabhi use hota hai jab video attachment limit se badi ho. Chhoti/normal videos ke liye iski
zaroorat hi nahi padegi.

1. Google Cloud Console me **Drive API** enable karo.
2. **Credentials > Create Credentials > OAuth client ID > Desktop app** banao.
3. `credentials.json` download karke `worker/` folder me rakho.
4. Google Drive me ek folder banao (jaise "Gift Videos Backup"), uska folder ID URL se copy karo — yeh `DRIVE_FOLDER_ID` hai.
5. Apne PC par ek baar chalao (sirf tabhi zaroori hai agar kabhi badi video aayegi):
   ```
   cd worker
   pip install -r requirements.txt
   python worker.py --auth
   ```
   Browser khulega, login karo. Isse `token.json` ban jaayega.
6. OAuth consent screen ko "Testing" se "In production" karo, warna login 7 din me expire ho jaayega.

Agar tumhari videos hamesha chhoti rahengi (~20MB se kam), to yeh poora step **skip kar sakte ho** — bas `DRIVE_FOLDER_ID` khali rehne do, fallback trigger hi nahi hoga.

---

## 5. Razorpay setup

1. Razorpay Dashboard > **Settings > API Keys** se `Key Id` aur `Key Secret` lo.
   - `Key Id` — site ke `index.html` me `CONFIG.RAZORPAY_KEY_ID` me daalo (public hai, safe hai).
   - `Key Secret` — Netlify environment variable `RAZORPAY_KEY_SECRET` me daalo (kabhi site par mat daalna).
2. **Settings > Webhooks** me nayi webhook add karo:
   - URL: `https://YOUR-SITE.netlify.app/.netlify/functions/razorpay-webhook`
   - Event: `payment.captured`
   - Ek "Secret" banao — yahi `RAZORPAY_WEBHOOK_SECRET` environment variable me daalna hai.
3. Pehle **Test Mode** me sab check karo, phir Live keys par switch karo.

---

## 6. YouTube Data API key (free)

1. Google Cloud Console me **YouTube Data API v3** enable karo.
2. **Credentials > API Key** banao.
3. `YOUTUBE_API_KEY` environment variable me daalo.

Isse channel ka naam aur photo reliably milta hai — bina iske kabhi-kabhi fetch fail ho sakta hai aur order `needs_manual` ho jaayega.

---

## 7. Netlify par deploy

**Drag-and-drop se mat karo** — Functions (payment/webhook) sahi se kaam nahi karenge.

**GitHub se connect (recommended)**
1. Is poore folder ko ek GitHub repo me push karo.
2. Netlify > **Add new site > Import from Git** > apna repo chuno.
3. Build settings: `netlify.toml` already sab set kar deta hai.
4. **Site settings > Environment variables** me yeh sab daalo:
   ```
   RAZORPAY_KEY_ID
   RAZORPAY_KEY_SECRET
   RAZORPAY_WEBHOOK_SECRET
   GOOGLE_SERVICE_ACCOUNT_JSON   (poori JSON, ek line me)
   SHEET_ID
   ```

Deploy hone ke baad `index.html` me `CONFIG.CREATE_ORDER_URL` waisa hi rehne do (`/.netlify/functions/create-order`), automatically kaam karega.

---

## 8. Worker chalana — PC / GitHub hybrid

**Idea:** Agar tumhara PC on hai aur `worker.py` chal raha hai, wahi orders process karega. Agar PC off hai, GitHub Actions khud kaam sambhal lega.

### PC par (jab bhi on ho)
```
cd worker
pip install -r requirements.txt
python worker.py
```
Har 60 second Sheet check karta hai, aur `Heartbeat` tab me apna time likhta rehta hai.

### GitHub Actions (hamesha chalu, PC ki chinta nahi)
`.github/workflows/worker.yml` har 10 minute me khud check karta hai:
- `Heartbeat` 6 minute se purana nahi → PC chal raha hai → GitHub kuch nahi karta.
- Heartbeat purana/missing → PC band hai → GitHub khud `worker.py --once` chala kar due orders process kar deta hai.

**GitHub Secrets set karo** (repo > Settings > Secrets and variables > Actions):
```
SHEET_ID
GOOGLE_SERVICE_ACCOUNT_JSON
YOUTUBE_API_KEY
EMAIL_SENDER
EMAIL_APP_PASSWORD
DRIVE_FOLDER_ID      <- sirf agar fallback use karna hai
DRIVE_TOKEN_JSON     <- apne PC ke worker/token.json ka poora content (sirf agar fallback setup kiya hai)
```

---

## 9. Tumhari video script (`subscriber_gift_video.py`) jodna

`worker/worker.py` me `generate_video()` function maan kar chal raha hai ki tumhari script:
```
python subscriber_gift_video.py --channel-name "..." --target-subs 1000 --output path.mp4
```
Agar tumhari script ke arguments/naam alag hain, sirf `generate_video()` function ke andar `cmd` list badal do. Apni script ki file `worker/` folder me rakho aur `VIDEO_SCRIPT_PATH` env var me uska naam daalo.

---

## 10. Test kaise karo

1. Razorpay **Test Mode** keys use karo.
2. Site par test order karo — Sheet ke `Orders` tab me nayi row "pending" status ke saath dikhni chahiye.
3. Razorpay test payment complete karo — webhook chalega aur status "paid" ho jaana chahiye.
4. `python worker.py --once` chalao — delivery time aa chuka ho to video generate hogi aur email chali jaayegi (turant test ke liye Sheet me `hours` column temporarily `0` kar sakte ho).
5. Sheet check karo — status `delivered` ho jaana chahiye. Chhoti video ho to `video_link` khali rahega (kyunki attach ho gayi), badi ho to Drive link dikhega.
6. Apna email inbox check karo — video attachment ke saath mil jaani chahiye.

---

## Dhyan rakhne wali baatein

- **`needs_manual` status roz check karo** — YouTube fetch fail ya email send fail hone par yahi hota hai. Sheet me filter laga sakte ho. Fail hone par local video file bhi delete nahi hoti (taaki manually bhej sako) — `worker/output_videos/` folder me milegi.
- **Delivery hours:** abhi 1000→1h, 2000→2h ... 5000→5h, 10000→10h pattern hai. Badalna ho to `public/index.html` ke `CONFIG.PLANS` me badlo.
- **₹11 wala plan (1000 subscribers) hamesha page load par default-selected rehta hai** (`CONFIG.DEFAULT_PLAN_INDEX = 0`). Kisi aur plan ko default banana ho to bas yeh number badal dena.
- **Reviews section sample data hai** — `CONFIG.REVIEWS` array me 15 placeholder reviews hain. Inhe apne asli customer reviews (naam + rating + text) se replace kar dena, fake reviews live site par mat rakhna.
- **"Asli subscribers nahi badhte" disclaimer** site aur email dono jagah rakhna — refund disputes kam karta hai.
- **Razorpay KYC** ke liye site par real Refund/Terms policy chahiye hoti hai — abhi jo text hai woh sirf placeholder hai.
- **Gmail se bulk email bhejne ki daily limit hoti hai** (personal account ~500/day). Order zyada aane lagein to Google Workspace account ya SendGrid/Resend jaisa transactional email provider use karna.
- Google Sheets ek free database ke roop me theek hai lekin bahut bade scale (hazaro orders/din) par slow ho sakti hai — tab kisi real database par shift karna better rahega.
