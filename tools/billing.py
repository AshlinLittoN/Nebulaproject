import math
import uuid
from db import get_conn
from tools.inventory import _find_product


def _bill_number():
    from datetime import datetime
    return "BILL-" + datetime.now().strftime("%Y%m%d%H%M%S")


def _calc_gst(price, gst_rate, quantity):
    line_base = round(price * quantity, 2)
    gst_amt = round(line_base * gst_rate / 100, 2)
    return line_base, gst_amt


def create_bill(chat_id, customer_name=None):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id, bill_number FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if existing:
            return {"ok": True, "bill_id": existing["id"], "bill_number": existing["bill_number"], "message": "Resumed existing draft bill."}
        bill_number = _bill_number()
        cur = conn.execute(
            "INSERT INTO bills (bill_number, status, customer_name, telegram_chat_id) VALUES (?,?,?,?)",
            (bill_number, "draft", customer_name, chat_id),
        )
        conn.commit()
        return {"ok": True, "bill_id": cur.lastrowid, "bill_number": bill_number, "message": "New bill started."}
    finally:
        conn.close()


def add_item_to_bill(chat_id, sku_or_name, quantity):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill. Say 'start a bill' first."}

        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}

        # Oversell guard: check available stock minus already-drafted qty
        drafted = conn.execute(
            "SELECT COALESCE(SUM(bi.quantity),0) as qty FROM bill_items bi JOIN bills b ON bi.bill_id=b.id WHERE bi.product_id=? AND b.status='draft'",
            (product["id"],),
        ).fetchone()[0]
        available = product["quantity"] - drafted
        if available < quantity:
            return {"ok": False, "error": f"Only {available} {product['unit']} of {product['name']} available (stock: {product['quantity']}, in other drafts: {drafted})."}

        # Guard: don't sell below cost
        if product["mrp"] < product["cost_price"]:
            return {"ok": False, "error": f"MRP ₹{product['mrp']} is below cost ₹{product['cost_price']} for {product['name']}. Update pricing first."}

        line_base, gst_amt = _calc_gst(product["mrp"], product["gst_rate"], quantity)
        line_total = round(line_base + gst_amt, 2)

        # Upsert: if item already in bill, update quantity
        existing_item = conn.execute(
            "SELECT * FROM bill_items WHERE bill_id=? AND product_id=?", (bill["id"], product["id"])
        ).fetchone()
        if existing_item:
            new_qty = existing_item["quantity"] + quantity
            new_base, new_gst = _calc_gst(product["mrp"], product["gst_rate"], new_qty)
            new_total = round(new_base + new_gst, 2)
            conn.execute(
                "UPDATE bill_items SET quantity=?, gst_amount=?, line_total=? WHERE id=?",
                (new_qty, new_gst, new_total, existing_item["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO bill_items (bill_id, product_id, quantity, unit_price, gst_rate, gst_amount, line_total) VALUES (?,?,?,?,?,?,?)",
                (bill["id"], product["id"], quantity, product["mrp"], product["gst_rate"], gst_amt, line_total),
            )
        conn.commit()
        return {"ok": True, "message": f"Added {quantity} x {product['name']} @ ₹{product['mrp']} = ₹{line_total} (GST ₹{gst_amt})"}
    finally:
        conn.close()


def remove_item_from_bill(chat_id, sku_or_name):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill."}
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}
        conn.execute("DELETE FROM bill_items WHERE bill_id=? AND product_id=?", (bill["id"], product["id"]))
        conn.commit()
        return {"ok": True, "message": f"Removed {product['name']} from bill."}
    finally:
        conn.close()


def update_item_quantity(chat_id, sku_or_name, quantity):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill."}
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}

        # Oversell guard for new quantity
        other_drafted = conn.execute(
            "SELECT COALESCE(SUM(bi.quantity),0) as qty FROM bill_items bi JOIN bills b ON bi.bill_id=b.id WHERE bi.product_id=? AND b.status='draft' AND b.id!=?",
            (product["id"], bill["id"]),
        ).fetchone()[0]
        available = product["quantity"] - other_drafted
        if available < quantity:
            return {"ok": False, "error": f"Only {available} {product['unit']} available."}

        line_base, gst_amt = _calc_gst(product["mrp"], product["gst_rate"], quantity)
        line_total = round(line_base + gst_amt, 2)
        conn.execute(
            "UPDATE bill_items SET quantity=?, gst_amount=?, line_total=? WHERE bill_id=? AND product_id=?",
            (quantity, gst_amt, line_total, bill["id"], product["id"]),
        )
        conn.commit()
        return {"ok": True, "message": f"Updated {product['name']} to {quantity} {product['unit']}."}
    finally:
        conn.close()


def view_bill(chat_id):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill."}
        return _build_bill_summary(conn, bill)
    finally:
        conn.close()


def finalize_bill(chat_id, payment_mode, payment_ref=None, customer_name=None):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill to finalize."}

        # Idempotency: if already finalized, return existing
        if bill["status"] == "finalized":
            return {"ok": True, "message": f"Bill {bill['bill_number']} already finalized.", "bill_number": bill["bill_number"]}

        items = conn.execute(
            "SELECT bi.*, p.name, p.unit, p.quantity as stock, p.cost_price FROM bill_items bi JOIN products p ON bi.product_id=p.id WHERE bi.bill_id=?",
            (bill["id"],),
        ).fetchall()
        if not items:
            return {"ok": False, "error": "Bill is empty."}

        # Final oversell check (atomic)
        for item in items:
            if item["stock"] < item["quantity"]:
                return {"ok": False, "error": f"Insufficient stock for {item['name']}: need {item['quantity']}, have {item['stock']}."}

        subtotal = sum(item["quantity"] * item["unit_price"] for item in items)
        total_gst = sum(item["gst_amount"] for item in items)
        total = round(subtotal + total_gst, 2)

        from datetime import datetime
        conn.execute(
            "UPDATE bills SET status='finalized', payment_mode=?, payment_ref=?, customer_name=COALESCE(?,customer_name), subtotal=?, total_gst=?, total_amount=?, finalized_at=datetime('now','localtime') WHERE id=?",
            (payment_mode, payment_ref, customer_name, round(subtotal, 2), round(total_gst, 2), total, bill["id"]),
        )
        # Decrement stock
        for item in items:
            conn.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (item["quantity"], item["product_id"]))
            conn.execute(
                "INSERT INTO stock_movements (product_id, movement_type, quantity, reference) VALUES (?,?,?,?)",
                (item["product_id"], "out", item["quantity"], bill["bill_number"]),
            )
        conn.commit()
        summary = _build_bill_summary(conn, conn.execute("SELECT * FROM bills WHERE id=?", (bill["id"],)).fetchone())
        summary["message"] = f"Bill {bill['bill_number']} finalized. Total: ₹{total}"
        # Check for low stock after decrement
        low = []
        for item in items:
            row = conn.execute(
                "SELECT name, quantity, reorder_level, unit FROM products WHERE id=?", (item["product_id"],)
            ).fetchone()
            if row and row["quantity"] <= row["reorder_level"]:
                low.append(f"⚠️ {row['name']}: only {row['quantity']} {row['unit']} left (reorder at {row['reorder_level']})")
        if low:
            summary["low_stock_alerts"] = low
        return summary
    finally:
        conn.close()


def cancel_bill(chat_id):
    conn = get_conn()
    try:
        bill = conn.execute(
            "SELECT * FROM bills WHERE telegram_chat_id=? AND status='draft'", (chat_id,)
        ).fetchone()
        if not bill:
            return {"ok": False, "error": "No active bill."}
        conn.execute("UPDATE bills SET status='cancelled' WHERE id=?", (bill["id"],))
        conn.commit()
        return {"ok": True, "message": f"Bill {bill['bill_number']} cancelled."}
    finally:
        conn.close()


def get_bill_by_number(bill_number):
    conn = get_conn()
    try:
        bill = conn.execute("SELECT * FROM bills WHERE bill_number=?", (bill_number,)).fetchone()
        if not bill:
            return {"ok": False, "error": f"Bill {bill_number} not found."}
        return _build_bill_summary(conn, bill)
    finally:
        conn.close()


def _build_bill_summary(conn, bill):
    items = conn.execute(
        "SELECT bi.*, p.name, p.unit, p.hsn_code, p.is_loose FROM bill_items bi JOIN products p ON bi.product_id=p.id WHERE bi.bill_id=?",
        (bill["id"],),
    ).fetchall()
    item_list = []
    gst_summary = {}
    subtotal = 0
    total_gst = 0
    for item in items:
        base = round(item["unit_price"] * item["quantity"], 2)
        gst = item["gst_amount"]
        subtotal += base
        total_gst += gst
        rate = item["gst_rate"]
        if rate not in gst_summary:
            gst_summary[rate] = {"taxable": 0, "cgst": 0, "sgst": 0}
        gst_summary[rate]["taxable"] += base
        gst_summary[rate]["cgst"] += round(gst / 2, 2)
        gst_summary[rate]["sgst"] += round(gst / 2, 2)
        item_list.append({
            "name": item["name"], "hsn": item["hsn_code"],
            "qty": item["quantity"], "unit": item["unit"],
            "unit_price": item["unit_price"], "gst_rate": rate,
            "gst_amount": gst, "line_total": item["line_total"],
        })
    return {
        "ok": True,
        "bill_id": bill["id"],
        "bill_number": bill["bill_number"],
        "status": bill["status"],
        "customer": bill["customer_name"],
        "payment_mode": bill["payment_mode"],
        "items": item_list,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst, 2),
        "total_amount": round(subtotal + total_gst, 2),
        "gst_breakup": gst_summary,
        "created_at": bill["created_at"],
    }
