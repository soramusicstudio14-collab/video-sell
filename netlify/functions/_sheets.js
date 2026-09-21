// Shared helper: Google Sheets ko "Orders" table ki tarah use karne ke liye.
// Env vars chahiye (Netlify > Site settings > Environment variables):
//   GOOGLE_SERVICE_ACCOUNT_JSON  -> service account ki poori JSON (single line)
//   SHEET_ID                     -> Google Sheet ka ID (URL me /d/....../edit ke beech ka hissa)
//
// Sheet me do tabs honi chahiye:
//   "Orders"    columns: order_id | created_at | yt_handle | email | plan_index | amount | subs | hours | status | delivery_at | video_link | razorpay_order_id
//   "Heartbeat" cell A1: last time worker.py (PC) ne "main zinda hoon" likha

const { google } = require("googleapis");

function getAuth() {
  const creds = JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);
  return new google.auth.JWT(
    creds.client_email,
    null,
    creds.private_key,
    ["https://www.googleapis.com/auth/spreadsheets"]
  );
}

async function getSheetsClient() {
  const auth = getAuth();
  await auth.authorize();
  return google.sheets({ version: "v4", auth });
}

const SHEET_ID = process.env.SHEET_ID;
const ORDERS_TAB = "Orders";

async function appendOrder(row) {
  const sheets = await getSheetsClient();
  await sheets.spreadsheets.values.append({
    spreadsheetId: SHEET_ID,
    range: `${ORDERS_TAB}!A:L`,
    valueInputOption: "USER_ENTERED",
    insertDataOption: "INSERT_ROWS",
    requestBody: { values: [row] }
  });
}

// razorpay_order_id (column L, index 11) se row dhoondh kar status/delivery_at update karta hai
async function markPaidByRazorpayOrderId(razorpayOrderId, deliveryAtISO) {
  const sheets = await getSheetsClient();
  const { data } = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: `${ORDERS_TAB}!A:L`
  });
  const rows = data.values || [];
  const idx = rows.findIndex((r) => r[11] === razorpayOrderId);
  if (idx === -1) return false;

  const rowNumber = idx + 1; // 1-indexed, header included as-is
  await sheets.spreadsheets.values.update({
    spreadsheetId: SHEET_ID,
    range: `${ORDERS_TAB}!I${rowNumber}:J${rowNumber}`, // status, delivery_at
    valueInputOption: "USER_ENTERED",
    requestBody: { values: [["paid", deliveryAtISO]] }
  });
  return true;
}

module.exports = { getSheetsClient, appendOrder, markPaidByRazorpayOrderId, SHEET_ID, ORDERS_TAB };
