from db import get_conn


def add_credit(customer_name, amount, note=None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO khata (customer_name, balance) VALUES (?,?) ON CONFLICT(customer_name) DO UPDATE SET balance=balance+?",
            (customer_name, amount, amount),
        )
        conn.execute(
            "INSERT INTO khata_transactions (customer_name, txn_type, amount, note) VALUES (?,?,?,?)",
            (customer_name, "credit", amount, note),
        )
        conn.commit()
        balance = conn.execute("SELECT balance FROM khata WHERE customer_name=?", (customer_name,)).fetchone()[0]
        return {"ok": True, "message": f"Added ₹{amount} credit for {customer_name}. Balance: ₹{balance}"}
    finally:
        conn.close()


def record_payment(customer_name, amount):
    conn = get_conn()
    try:
        row = conn.execute("SELECT balance FROM khata WHERE customer_name=?", (customer_name,)).fetchone()
        if not row:
            return {"ok": False, "error": f"No khata found for '{customer_name}'."}
        if amount > row["balance"]:
            return {"ok": False, "error": f"Payment ₹{amount} exceeds balance ₹{row['balance']} for {customer_name}. Confirm?"}
        conn.execute("UPDATE khata SET balance=balance-? WHERE customer_name=?", (amount, customer_name))
        conn.execute(
            "INSERT INTO khata_transactions (customer_name, txn_type, amount) VALUES (?,?,?)",
            (customer_name, "payment", amount),
        )
        conn.commit()
        balance = conn.execute("SELECT balance FROM khata WHERE customer_name=?", (customer_name,)).fetchone()[0]
        return {"ok": True, "message": f"Recorded ₹{amount} payment from {customer_name}. Remaining balance: ₹{balance}"}
    finally:
        conn.close()


def get_balance(customer_name):
    conn = get_conn()
    try:
        row = conn.execute("SELECT balance FROM khata WHERE customer_name=?", (customer_name,)).fetchone()
        if not row:
            return {"ok": False, "error": f"No khata found for '{customer_name}'."}
        txns = conn.execute(
            "SELECT txn_type, amount, note, created_at FROM khata_transactions WHERE customer_name=? ORDER BY created_at DESC LIMIT 5",
            (customer_name,),
        ).fetchall()
        return {
            "ok": True,
            "customer": customer_name,
            "balance": row["balance"],
            "recent_transactions": [dict(t) for t in txns],
        }
    finally:
        conn.close()


def list_khata():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT customer_name, balance FROM khata WHERE balance > 0 ORDER BY balance DESC").fetchall()
        return {"ok": True, "customers": [dict(r) for r in rows]}
    finally:
        conn.close()
