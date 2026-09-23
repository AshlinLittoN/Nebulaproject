from db import get_conn


def _find_product(conn, sku_or_name):
    row = conn.execute(
        "SELECT * FROM products WHERE sku=? OR LOWER(name)=LOWER(?)", (sku_or_name, sku_or_name)
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT * FROM products WHERE LOWER(name) LIKE LOWER(?)", (f"%{sku_or_name}%",)
        ).fetchone()
    return row


def lookup_by_barcode(barcode):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
        if not row:
            return {"ok": False, "error": f"No product found with barcode '{barcode}'."}
        return {
            "ok": True,
            "name": row["name"], "sku": row["sku"], "barcode": row["barcode"],
            "mrp": row["mrp"], "cost_price": row["cost_price"],
            "gst_rate": row["gst_rate"], "unit": row["unit"],
            "quantity": row["quantity"], "hsn_code": row["hsn_code"],
        }
    finally:
        conn.close()


def set_barcode(sku_or_name, barcode):
    conn = get_conn()
    try:
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}
        # Check barcode not already used by another product
        existing = conn.execute(
            "SELECT name FROM products WHERE barcode=? AND id!=?", (barcode, product["id"])
        ).fetchone()
        if existing:
            return {"ok": False, "error": f"Barcode '{barcode}' already assigned to {existing['name']}."}
        conn.execute("UPDATE products SET barcode=? WHERE id=?", (barcode, product["id"]))
        conn.commit()
        return {"ok": True, "message": f"Barcode '{barcode}' assigned to {product['name']}."}
    finally:
        conn.close()


def add_product(name, sku, unit, is_loose, cost_price, mrp, gst_rate, hsn_code, reorder_level=10):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO products (name, sku, unit, is_loose, cost_price, mrp, gst_rate, hsn_code, reorder_level, quantity) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (name, sku, unit, int(is_loose), cost_price, mrp, gst_rate, hsn_code, reorder_level),
        )
        conn.commit()
        return {"ok": True, "message": f"Product '{name}' added."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def receive_stock(sku_or_name, quantity, cost_price=None):
    conn = get_conn()
    try:
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}
        if cost_price:
            conn.execute("UPDATE products SET cost_price=? WHERE id=?", (cost_price, product["id"]))
        conn.execute("UPDATE products SET quantity = quantity + ? WHERE id=?", (quantity, product["id"]))
        conn.execute(
            "INSERT INTO stock_movements (product_id, movement_type, quantity, cost_price) VALUES (?,?,?,?)",
            (product["id"], "in", quantity, cost_price or product["cost_price"]),
        )
        conn.commit()
        new_qty = conn.execute("SELECT quantity FROM products WHERE id=?", (product["id"],)).fetchone()[0]
        return {"ok": True, "message": f"Received {quantity} {product['unit']} of {product['name']}. Stock now: {new_qty}"}
    finally:
        conn.close()


def query_stock(sku_or_name):
    conn = get_conn()
    try:
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}
        return {"ok": True, "name": product["name"], "quantity": product["quantity"], "unit": product["unit"], "mrp": product["mrp"]}
    finally:
        conn.close()


def low_stock_report():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name, quantity, unit, reorder_level FROM products WHERE quantity <= reorder_level ORDER BY quantity ASC"
        ).fetchall()
        items = [{"name": r["name"], "quantity": r["quantity"], "unit": r["unit"], "reorder_level": r["reorder_level"]} for r in rows]
        return {"ok": True, "low_stock_items": items}
    finally:
        conn.close()


def list_products(search=None):
    conn = get_conn()
    try:
        if search:
            rows = conn.execute(
                "SELECT id, name, sku, unit, is_loose, cost_price, mrp, gst_rate, hsn_code, quantity FROM products WHERE name LIKE ? OR sku LIKE ?",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, sku, unit, is_loose, cost_price, mrp, gst_rate, hsn_code, quantity FROM products"
            ).fetchall()
        return {"ok": True, "products": [dict(r) for r in rows]}
    finally:
        conn.close()


def update_product(sku_or_name, **kwargs):
    conn = get_conn()
    try:
        product = _find_product(conn, sku_or_name)
        if not product:
            return {"ok": False, "error": f"Product '{sku_or_name}' not found."}
        allowed = {"cost_price", "mrp", "gst_rate", "reorder_level", "hsn_code"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return {"ok": False, "error": "No valid fields to update."}
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE products SET {set_clause} WHERE id=?", (*updates.values(), product["id"]))
        conn.commit()
        return {"ok": True, "message": f"Updated {product['name']}: {updates}"}
    finally:
        conn.close()
