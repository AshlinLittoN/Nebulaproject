from db import get_conn


def set_preference(key, value):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO preferences (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
        conn.commit()
        return {"ok": True, "message": f"Preference '{key}' set to '{value}'."}
    finally:
        conn.close()


def get_preference(key):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return {"ok": True, "value": row["value"] if row else None}
    finally:
        conn.close()


def get_all_preferences():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        return {"ok": True, "preferences": {r["key"]: r["value"] for r in rows}}
    finally:
        conn.close()
