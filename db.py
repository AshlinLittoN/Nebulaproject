import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "kirana.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sku TEXT UNIQUE NOT NULL,
    unit TEXT NOT NULL,
    is_loose INTEGER DEFAULT 0,
    cost_price REAL NOT NULL,
    mrp REAL NOT NULL,
    gst_rate REAL NOT NULL,
    hsn_code TEXT NOT NULL,
    reorder_level REAL DEFAULT 10,
    quantity REAL DEFAULT 0,
    barcode TEXT
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL, -- 'in' or 'out'
    quantity REAL NOT NULL,
    cost_price REAL,
    reference TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'draft',  -- draft / finalized / cancelled
    customer_name TEXT,
    payment_mode TEXT,            -- cash / upi / card
    payment_ref TEXT,
    subtotal REAL DEFAULT 0,
    total_gst REAL DEFAULT 0,
    total_amount REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    finalized_at TEXT,
    telegram_chat_id TEXT
);

CREATE TABLE IF NOT EXISTS bill_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    gst_rate REAL NOT NULL,
    gst_amount REAL NOT NULL,
    line_total REAL NOT NULL,
    FOREIGN KEY (bill_id) REFERENCES bills(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS khata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT UNIQUE NOT NULL,
    balance REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS khata_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    txn_type TEXT NOT NULL,  -- 'credit' or 'payment'
    amount REAL NOT NULL,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_close (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    close_date TEXT UNIQUE NOT NULL,
    total_sales REAL,
    total_gst REAL,
    cash_sales REAL,
    upi_sales REAL,
    card_sales REAL,
    bill_count INTEGER,
    top_items TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

SEED_PRODUCTS = [
    ("Aashirvaad Atta 5kg", "AASH-ATTA-5KG", "packet", 0, 195.0, 260.0, 5.0, "1101", 20, 50),
    ("Tata Salt 1kg", "TATA-SALT-1KG", "packet", 0, 18.0, 24.0, 0.0, "2501", 30, 100),
    ("Amul Butter 100g", "AMUL-BUTR-100G", "packet", 0, 48.0, 62.0, 12.0, "0405", 20, 50),
    ("Fortune Sunflower Oil 1L", "FORT-OIL-1L", "litre", 0, 130.0, 160.0, 5.0, "1512", 15, 30),
    ("Maggi 70g", "MAGGI-70G", "packet", 0, 12.0, 14.0, 18.0, "1902", 50, 200),
    ("Parle-G 100g", "PARLEG-100G", "packet", 0, 8.0, 10.0, 18.0, "1905", 30, 100),
    ("Surf Excel 500g", "SURF-500G", "packet", 0, 85.0, 110.0, 18.0, "3402", 15, 40),
    ("Sugar (loose)", "SUGAR-LOOSE", "kg", 1, 38.0, 45.0, 0.0, "1701", 10, 50),
    ("Rice (loose)", "RICE-LOOSE", "kg", 1, 42.0, 55.0, 0.0, "1006", 10, 50),
    ("Dal (loose)", "DAL-LOOSE", "kg", 1, 85.0, 100.0, 0.0, "0713", 10, 30),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Seed products if empty
    cur = conn.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products (name, sku, unit, is_loose, cost_price, mrp, gst_rate, hsn_code, reorder_level, quantity) VALUES (?,?,?,?,?,?,?,?,?,?)",
            SEED_PRODUCTS,
        )
    conn.commit()
    conn.close()
