from db import get_conn
from datetime import date


def daily_close(close_date=None):
    conn = get_conn()
    try:
        today = close_date or date.today().isoformat()
        existing = conn.execute("SELECT * FROM daily_close WHERE close_date=?", (today,)).fetchone()
        if existing:
            return {"ok": True, "already_closed": True, "data": dict(existing)}

        bills = conn.execute(
            "SELECT * FROM bills WHERE status='finalized' AND DATE(finalized_at)=?", (today,)
        ).fetchall()

        total_sales = sum(b["total_amount"] for b in bills)
        total_gst = sum(b["total_gst"] for b in bills)
        cash = sum(b["total_amount"] for b in bills if b["payment_mode"] == "cash")
        upi = sum(b["total_amount"] for b in bills if b["payment_mode"] == "upi")
        card = sum(b["total_amount"] for b in bills if b["payment_mode"] == "card")

        top_rows = conn.execute(
            """SELECT p.name, SUM(bi.quantity) as total_qty, SUM(bi.line_total) as total_revenue
               FROM bill_items bi
               JOIN bills b ON bi.bill_id=b.id
               JOIN products p ON bi.product_id=p.id
               WHERE b.status='finalized' AND DATE(b.finalized_at)=?
               GROUP BY p.id ORDER BY total_revenue DESC LIMIT 5""",
            (today,),
        ).fetchall()
        import json
        top_items = json.dumps([{"name": r["name"], "qty": r["total_qty"], "revenue": r["total_revenue"]} for r in top_rows])

        conn.execute(
            "INSERT INTO daily_close (close_date, total_sales, total_gst, cash_sales, upi_sales, card_sales, bill_count, top_items) VALUES (?,?,?,?,?,?,?,?)",
            (today, total_sales, total_gst, cash, upi, card, len(bills), top_items),
        )
        conn.commit()
        import json as j
        return {
            "ok": True,
            "date": today,
            "total_sales": round(total_sales, 2),
            "total_gst": round(total_gst, 2),
            "cash": round(cash, 2),
            "upi": round(upi, 2),
            "card": round(card, 2),
            "bill_count": len(bills),
            "top_items": j.loads(top_items),
        }
    finally:
        conn.close()


def sales_summary(days=7):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT DATE(finalized_at) as day, COUNT(*) as bills,
               SUM(total_amount) as revenue, SUM(total_gst) as gst
               FROM bills WHERE status='finalized'
               GROUP BY day ORDER BY day DESC LIMIT ?""",
            (days,),
        ).fetchall()
        return {"ok": True, "summary": [dict(r) for r in rows]}
    finally:
        conn.close()
