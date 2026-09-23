# Kirana Store Agent

A conversational agent that runs an Indian kirana store end-to-end over Telegram. No web app, no admin panel — the chat is the product.

**Live bot:** `@<your_bot_username>`

---

## Harness: Anthropic Claude (tool_use API)

Claude's native `tool_use` stop reason drives a tight **Observe → Reason → Act → Feed result back → Continue** loop in `agent.py`. The model decides which tools to call and in what order — there is no intent router, no regex, no keyword matching. A single `while True` loop runs until `stop_reason == "end_turn"`.

Why Claude tool_use over LangGraph/LangChain:
- The model natively chains multiple tool calls within one turn (e.g. create_bill → add 4 items → finalize, all in one user message).
- No graph nodes or edges to maintain — the model is the orchestrator.
- Tool schemas are plain JSON; business logic lives in Python, not prompts.

---

## Architecture

```
bot.py          — Telegram transport, per-chat history, idempotency guard
agent.py        — Claude control loop (observe→reason→act)
agent_tools.py  — Tool schemas (JSON) + dispatch table
tools/
  inventory.py  — add_product, receive_stock, query_stock, low_stock_report
  billing.py    — create_bill, add/remove/update items, finalize_bill, cancel_bill
  khata.py      — add_credit, record_payment, get_balance, list_khata
  reports.py    — daily_close, sales_summary
  memory.py     — set_preference, get_preference (persistent across sessions)
  pdf_invoice.py — GST-correct PDF via reportlab
  pptx_deck.py  — Sales analysis PPTX with matplotlib charts
db.py           — SQLite schema + seed data (WAL mode, FK enforcement)
kirana.db       — SQLite database (auto-created on first run)
```

---

## How Each Hard Part Is Solved

**1. Grounding** — The system prompt explicitly forbids inventing prices or stock. Every product lookup goes through `_find_product()` which queries SQLite. If a product isn't found, the tool returns `{"ok": false, "error": "..."}` and the model tells the owner.

**2. Oversell guard** — `add_item_to_bill` checks `product.quantity - already_drafted_qty >= requested_qty` before adding. `finalize_bill` does a second atomic check before decrementing. Stock never goes negative — enforced at the tool layer, not the prompt.

**3. GST correctness** — Per-item: `line_base = price × qty`, `gst = line_base × rate/100`. Intra-state split: `CGST = SGST = gst/2`. The PDF invoice shows a full GST breakup table by slab. Staples (loose atta, rice, dal, salt) are 0%; packaged staples 5%; FMCG (Maggi, biscuits, detergent) 12–18%. HSN codes seeded per product.

**4. Multi-turn bills** — A `draft` bill persists in SQLite keyed by `telegram_chat_id`. The owner can add items across multiple messages, edit quantities, remove items, then finalize. Stock is only decremented on `finalize_bill`.

**5. Idempotency** — Telegram update IDs are tracked in `processed_updates` set (bot layer). At the DB layer, `finalize_bill` checks `status='draft'` before acting — a retried finalize on an already-finalized bill returns early without double-decrementing stock.

**6. Concurrency** — SQLite WAL mode allows concurrent reads. `finalize_bill` runs the stock decrement inside a single connection with `PRAGMA journal_mode=WAL` and `foreign_keys=ON`. The oversell check + decrement happen in the same connection before `commit()`, preventing race conditions for the single-writer SQLite model.

**7. Guardrails** — Don't sell below cost: checked in `add_item_to_bill`. Don't delete stock: no delete tool exists. Khata payment exceeding balance: `record_payment` returns an error asking for confirmation. These rules live in tool code, not the system prompt.

**8. Real artifacts** — PDF via `reportlab` with proper table layout, GST breakup, CGST/SGST split, shop GSTIN. PPTX via `python-pptx` with `matplotlib` bar/pie charts for revenue, top products, payment modes, stock health.

**9. Memory across sessions** — `preferences` table in SQLite. `/new` clears `chat_histories[chat_id]` (in-memory conversation) but the DB is untouched. On every turn, `get_all_preferences()` is appended to the user message so the model always has current preferences regardless of conversation history length.

---

## Setup

```bash
pip install -r requirements.txt
# Edit .env with your keys
python bot.py
```

`.env`:
```
TELEGRAM_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
SHOP_NAME=My Kirana Store
SHOP_GSTIN=29ABCDE1234F1Z5
SHOP_ADDRESS=123 Main Street, Bangalore
```

---

## Example Interactions

```
receive 50 Maggi, cost ₹12, MRP ₹14
→ Received 50 packets of Maggi 70g. Stock now: 250

make a bill: 2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi, UPI
→ Bill BILL-20250101120000 started.
  Added 2 kg Sugar (loose) @ ₹45 = ₹90.00 (GST ₹0.00)
  Added 1 x Aashirvaad Atta 5kg @ ₹260 = ₹273.00 (GST ₹13.00)
  Added 4 x Maggi 70g @ ₹14 = ₹65.97 (GST ₹10.08)
  Total: ₹428.97 | GST: ₹23.08 | Payment: UPI ✓

put ₹500 on Ramesh's credit
→ Added ₹500 credit for Ramesh. Balance: ₹500

send me that bill as a PDF
→ [sends BILL-20250101120000.pdf]
```

---

## Seeded Products

Aashirvaad Atta 5kg (5% GST), Tata Salt 1kg (0%), Amul Butter 100g (12%), Fortune Sunflower Oil 1L (5%), Maggi 70g (18%), Parle-G 100g (18%), Surf Excel 500g (18%), Sugar/Rice/Dal loose (0%).
