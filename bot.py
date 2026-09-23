"""
Telegram bot — thin transport layer over the agent.
"""
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatAction

from db import init_db, get_conn
from agent import run_agent
from tools.reports import sales_summary
from tools.inventory import low_stock_report
from tools.billing import finalize_bill, create_bill, add_item_to_bill, view_bill

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

chat_histories: dict[str, list] = {}
processed_updates: set[int] = set()
bill_states: dict[str, dict] = {}

DISCOUNTS = {0: 2, 5: 3, 12: 5, 18: 7}


def _main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Check Stock", callback_data="stock"),
         InlineKeyboardButton("⚠️ Low Stock", callback_data="lowstock")],
        [InlineKeyboardButton("🧾 Start Bill", callback_data="bill"),
         InlineKeyboardButton("✅ Finalize Bill", callback_data="finalize")],
        [InlineKeyboardButton("👥 Khata List", callback_data="khata"),
         InlineKeyboardButton("📊 Today's Sales", callback_data="sales")],
        [InlineKeyboardButton("📄 PDF Invoice", callback_data="pdf"),
         InlineKeyboardButton("📈 Analysis Deck", callback_data="pptx")],
        [InlineKeyboardButton("🔍 All Products", callback_data="products"),
         InlineKeyboardButton("📋 Low Stock", callback_data="lowstock")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _payment_menu():
    keyboard = [
        [InlineKeyboardButton("💵 Cash", callback_data="pay_cash"),
         InlineKeyboardButton("📱 UPI", callback_data="pay_upi"),
         InlineKeyboardButton("💳 Card", callback_data="pay_card")],
        [InlineKeyboardButton("❌ Cancel Bill", callback_data="cancel_bill")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _get_products_with_discounts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, sku, mrp, gst_rate, quantity, unit FROM products WHERE quantity > 0 ORDER BY quantity DESC LIMIT 15"
    ).fetchall()
    conn.close()
    products = []
    for r in rows:
        disc = DISCOUNTS.get(int(r["gst_rate"]), 0)
        products.append({
            "name": r["name"], "mrp": r["mrp"], "gst_rate": r["gst_rate"],
            "quantity": r["quantity"], "unit": r["unit"], "discount": disc,
            "discounted_price": round(r["mrp"] * (1 - disc / 100), 2),
        })
    return products


def _format_product_list(products):
    lines = ["\U0001f6d2 *Available Products & Discounts:*\n"]
    for p in products:
        disc_str = f"  \U0001f3f7 {p['discount']}% off -> Rs.{p['discounted_price']}" if p["discount"] > 0 else ""
        lines.append(f"- *{p['name']}* Rs.{p['mrp']}/{p['unit']}{disc_str} (stock: {p['quantity']})")
    lines.append("\nType items like: `2kg sugar, 4 Maggi, 1 Aashirvaad atta`")
    return "\n".join(lines)


def _parse_items(text):
    """Parse '2kg sugar, 4 Maggi, 1 Aashirvaad atta' into [{name, qty}]"""
    import re
    items = []
    for part in re.split(r'[,;]+', text):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(\d+(?:\.\d+)?)\s*(?:kg|g|l|ml|pcs|pc)?\s+(.+)$', part, re.IGNORECASE)
        if m:
            items.append({"qty": float(m.group(1)), "name": m.group(2).strip()})
        else:
            # fallback: qty at end or just name with qty=1
            m2 = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)$', part)
            if m2:
                items.append({"qty": float(m2.group(2)), "name": m2.group(1).strip()})
            else:
                items.append({"qty": 1, "name": part})
    return items


async def _start_bill_flow(chat_id, send_fn):
    bill_states[chat_id] = {"step": "ask_customer"}
    await send_fn(
        "\U0001f9fe *New Bill*\n\nEnter *customer name* (or type `walkin`):",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.update_id in processed_updates:
        return
    processed_updates.add(update.update_id)

    chat_id = str(update.effective_chat.id)
    user_text = update.message.text.strip()
    send = lambda text, **kw: update.message.reply_text(text, **kw)
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Thank you / appreciation messages
    if any(w in user_text.lower() for w in ["thank", "thanks", "thankyou", "thank you", "shukriya", "dhanyawad", "ty"]):
        import random
        replies = [
            "🙏 Thank you for shopping with us! Come back soon, we always have fresh stock for you!",
            "😊 Thanks a lot! Your support keeps our store going. See you next time!",
            "🛒 Thank you! You're one of our valued customers. Have a great day!",
            "🌟 Thanks for visiting! We hope to see you again soon. Spread the word!",
            "💚 Thank you! Every purchase you make helps our small store grow. You're the best!",
        ]
        await send(random.choice(replies))
        return

    # If user types a payment mode and there's a draft bill but no active state,
    # they came from the agent flow — jump straight to finalize
    if not bill_states.get(chat_id) and user_text.lower() in ["cash", "upi", "card"]:
        from tools.billing import view_bill as _vb
        if _vb(chat_id)["ok"]:
            await _do_finalize(chat_id, user_text.lower(), send)
            return

    # If user says "finalize" with a draft bill but no active state, show payment menu
    if not bill_states.get(chat_id) and any(w in user_text.lower() for w in ["finalize", "finalise", "confirm bill"]):
        from tools.billing import view_bill as _vb
        if _vb(chat_id)["ok"]:
            bill_states[chat_id] = {"step": "ask_payment"}
            await send("💳 Choose payment method:", reply_markup=_payment_menu())
            return

    state = bill_states.get(chat_id)
    if state:
        step = state["step"]

        if step == "ask_customer":
            customer = "Walk-in" if user_text.lower() == "walkin" else user_text
            bill_states[chat_id] = {"step": "ask_items", "customer": customer}
            products = _get_products_with_discounts()
            await send(f"Customer: *{customer}*\n\n" + _format_product_list(products), parse_mode="Markdown")
            return

        if step == "ask_items":
            customer = state.get("customer", "Walk-in")
            create_bill(chat_id, customer)
            errors, lines = [], []
            for item_str in _parse_items(user_text):
                res = add_item_to_bill(chat_id, item_str["name"], item_str["qty"])
                if res["ok"]:
                    lines.append(res["message"])
                else:
                    errors.append(res["error"])
            summary = view_bill(chat_id)
            if not summary["ok"] or not summary["items"]:
                await send("\u274c Could not add any items. Check product names and try again.")
                bill_states.pop(chat_id, None)
                return
            bill_states[chat_id] = {"step": "ask_payment", "customer": customer}
            reply_lines = [f"\U0001f9fe *Draft bill for {customer}:*"]
            for it in summary["items"]:
                reply_lines.append(f"- {it['name']} x{it['qty']} = \u20b9{it['line_total']:.2f}")
            reply_lines.append(f"\n*Total: \u20b9{summary['total_amount']:.2f}*")
            if errors:
                reply_lines.append("\n\u26a0\ufe0f Skipped: " + "; ".join(errors))
            await send("\n".join(reply_lines), parse_mode="Markdown")
            await send("\U0001f4b3 *Choose payment method:*", parse_mode="Markdown", reply_markup=_payment_menu())
            return

        if step == "ask_payment":
            mode = user_text.lower()
            if mode not in ["cash", "upi", "card"]:
                await send("Type `cash`, `upi`, or `card`", reply_markup=_payment_menu())
                return
            await _do_finalize(chat_id, mode, send)
            return

    history = chat_histories.get(chat_id, [])
    try:
        reply, updated_history, files = run_agent(chat_id, user_text, history)
        chat_histories[chat_id] = updated_history[-20:]
        await send(reply, reply_markup=_main_menu())
        for fpath in files:
            with open(fpath, "rb") as f:
                await context.bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(fpath))
    except Exception as e:
        logger.exception("Agent error")
        await send(f"Error: {e}")


async def _do_finalize(chat_id, payment_mode, send_fn):
    result = finalize_bill(chat_id, payment_mode)
    bill_states.pop(chat_id, None)
    if not result["ok"]:
        await send_fn(f"Error: {result['error']}", reply_markup=_main_menu())
        return
    lines = [
        "\u2705 *Bill Finalized!*",
        f"Bill: `{result['bill_number']}`",
        f"Customer: {result.get('customer') or 'Walk-in'}",
        f"Payment: {payment_mode.upper()}", "",
    ]
    for item in result.get("items", []):
        disc = DISCOUNTS.get(int(item["gst_rate"]), 0)
        disc_str = f" ({disc}% off)" if disc else ""
        lines.append(f"- {item['name']} x{item['qty']} Rs.{item['line_total']:.2f}{disc_str}")
    lines += ["", f"Subtotal: Rs.{result['subtotal']:.2f}",
              f"GST: Rs.{result['total_gst']:.2f}",
              f"*Total: Rs.{result['total_amount']:.2f}*"]
    await send_fn("\n".join(lines), parse_mode="Markdown", reply_markup=_main_menu())
    low = low_stock_report()
    if low["ok"] and low["low_stock_items"]:
        alert = ["\U0001f534 *Low Stock Alert*"] + [f"- {i['name']}: {i['quantity']} {i['unit']} left" for i in low["low_stock_items"]]
        await send_fn("\n".join(alert), parse_mode="Markdown")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    chat_histories[chat_id] = []
    bill_states.pop(chat_id, None)
    await update.message.reply_text("Chat cleared. Store data intact.", reply_markup=_main_menu())


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f3ea *Namaste! Welcome to your Kirana Store*\n\nWhat would you like to do?",
        parse_mode="Markdown", reply_markup=_main_menu(),
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001f3ea *Main Menu*", parse_mode="Markdown", reply_markup=_main_menu(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    send = lambda text, **kw: query.message.reply_text(text, **kw)

    if query.data.startswith("pay_"):
        mode = query.data.replace("pay_", "")
        await _do_finalize(chat_id, mode, send)
        return

    if query.data == "cancel_bill":
        bill_states.pop(chat_id, None)
        await send("Bill cancelled.", reply_markup=_main_menu())
        return

    if query.data == "bill":
        await _start_bill_flow(chat_id, send)
        return

    prompts = {
        "stock": "list all products",
        "lowstock": "what's running out?",
        "finalize": "finalize the bill with UPI",
        "khata": "list all khata",
        "sales": "today's sales summary",
        "pdf": "send me the last bill as PDF",
        "pptx": "generate sales analysis deck",
        "products": "list all products",
    }
    user_text = prompts.get(query.data, query.data)
    history = chat_histories.get(chat_id, [])
    try:
        reply, updated_history, files = run_agent(chat_id, user_text, history)
        chat_histories[chat_id] = updated_history[-20:]
        await send(reply, reply_markup=_main_menu())
        for fpath in files:
            with open(fpath, "rb") as f:
                await context.bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(fpath))
    except Exception as e:
        await send(f"Error: {e}")


async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    if not chat_histories:
        return
    data = sales_summary(7)
    if not data["ok"] or not data["summary"]:
        return
    lines = ["\U0001f4ca *Weekly Sales Summary*"]
    total_rev = 0
    for row in data["summary"]:
        lines.append(f"- {row['day']}: Rs.{row['revenue']:.2f} ({row['bills']} bills)")
        total_rev += row["revenue"]
    lines.append(f"\n*Total: Rs.{total_rev:.2f}*")
    text = "\n".join(lines)
    for cid in list(chat_histories.keys()):
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Weekly summary failed for {cid}: {e}")


async def low_stock_check(context: ContextTypes.DEFAULT_TYPE):
    if not chat_histories:
        return
    result = low_stock_report()
    if not result["ok"] or not result["low_stock_items"]:
        return
    lines = ["\U0001f534 *Low Stock Alert*"] + [f"- {i['name']}: {i['quantity']} {i['unit']} left (reorder at {i['reorder_level']})" for i in result["low_stock_items"]]
    text = "\n".join(lines)
    for cid in list(chat_histories.keys()):
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Low stock alert failed for {cid}: {e}")


def _next_monday_9am():
    now = datetime.now()
    days_ahead = (7 - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 9:
        days_ahead = 7
    import datetime as dt
    target = now.replace(hour=9, minute=0, second=0, microsecond=0) + dt.timedelta(days=days_ahead)
    return (target - now).total_seconds()


def main():
    init_db()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(weekly_summary, interval=7 * 24 * 3600, first=_next_monday_9am())
    app.job_queue.run_repeating(low_stock_check, interval=3600, first=60)
    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
