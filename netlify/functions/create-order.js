// POST /.netlify/functions/create-order
// Body: { ytHandle, email, planIndex, amount, subs, hours }
// Env vars chahiye: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, GOOGLE_SERVICE_ACCOUNT_JSON, SHEET_ID

const Razorpay = require("razorpay");
const { appendOrder } = require("./_sheets");
const crypto = require("crypto");

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  try {
    const body = JSON.parse(event.body);
    const { ytHandle, email, planIndex, amount, subs, hours } = body;

    if (!ytHandle || !email || amount == null) {
      return { statusCode: 400, body: JSON.stringify({ error: "Missing fields" }) };
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return { statusCode: 400, body: JSON.stringify({ error: "Invalid email" }) };
    }

    const razorpay = new Razorpay({
      key_id: process.env.RAZORPAY_KEY_ID,
      key_secret: process.env.RAZORPAY_KEY_SECRET
    });

    const amountPaise = Math.round(amount * 100);
    const internalOrderId = "ord_" + crypto.randomBytes(6).toString("hex");

    const rzpOrder = await razorpay.orders.create({
      amount: amountPaise,
      currency: "INR",
      receipt: internalOrderId,
      notes: { ytHandle, email, subs: String(subs) }
    });

    // Google Sheet me "pending" row daalein. delivery_at abhi khali — webhook payment confirm hone par bharega.
    await appendOrder([
      internalOrderId,
      new Date().toISOString(),
      ytHandle,
      email,
      String(planIndex),
      String(amount),
      String(subs),
      String(hours),
      "pending",
      "",           // delivery_at
      "",           // video_link
      rzpOrder.id   // razorpay_order_id — webhook isi se row dhoondhega
    ]);

    return {
      statusCode: 200,
      body: JSON.stringify({
        orderId: rzpOrder.id,
        internalOrderId,
        amount: amountPaise
      })
    };
  } catch (err) {
    console.error(err);
    return { statusCode: 500, body: JSON.stringify({ error: err.message }) };
  }
};
