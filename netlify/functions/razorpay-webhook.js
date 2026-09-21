// Razorpay Dashboard > Settings > Webhooks me yeh URL daalein:
//   https://YOUR-SITE.netlify.app/.netlify/functions/razorpay-webhook
// Event select karein: "payment.captured"
// Env var chahiye: RAZORPAY_WEBHOOK_SECRET (webhook banate waqt khud set karein, isse yahan bhi daalein)

const crypto = require("crypto");
const { markPaidByRazorpayOrderId } = require("./_sheets");

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  const signature = event.headers["x-razorpay-signature"];
  const expected = crypto
    .createHmac("sha256", process.env.RAZORPAY_WEBHOOK_SECRET)
    .update(event.body)
    .digest("hex");

  if (signature !== expected) {
    console.warn("Invalid webhook signature");
    return { statusCode: 400, body: "Invalid signature" };
  }

  const payload = JSON.parse(event.body);
  if (payload.event !== "payment.captured") {
    return { statusCode: 200, body: "ignored" };
  }

  const payment = payload.payload.payment.entity;
  const razorpayOrderId = payment.order_id;

  // hours notes me se lena tha, lekin safe rehne ke liye Sheet me se hi read kar sakte hain.
  // Simplicity ke liye hum yahan sirf "paid" mark karte hain; delivery_at worker khud calculate
  // karega agar khali mile (created_at + hours). Chaaho to yahan bhi calculate kar sakte ho.
  const ok = await markPaidByRazorpayOrderId(razorpayOrderId, "");

  if (!ok) {
    console.error("Order not found in sheet for razorpay_order_id:", razorpayOrderId);
    return { statusCode: 200, body: "order not found, logged" };
  }

  return { statusCode: 200, body: "ok" };
};
