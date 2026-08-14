from __future__ import annotations
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / 'data'
DATABASE_PATH = DATA_DIR / 'inventory.db'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 external_code TEXT,
 name TEXT NOT NULL,
 category TEXT,
 storage_area TEXT NOT NULL DEFAULT '',
 unit TEXT NOT NULL,
 count_order INTEGER NOT NULL DEFAULT 0,
 expected_min REAL,
 expected_max REAL,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS storage_locations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 parent_id INTEGER,
 display_order INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(parent_id) REFERENCES storage_locations(id)
);
CREATE TABLE IF NOT EXISTS product_locations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL,
 location_id INTEGER NOT NULL,
 assigned_employee_id INTEGER,
 expected_min REAL,
 expected_max REAL,
 count_order INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT,
 FOREIGN KEY(product_id) REFERENCES products(id),
 FOREIGN KEY(location_id) REFERENCES storage_locations(id),
 FOREIGN KEY(assigned_employee_id) REFERENCES employees(id),
 UNIQUE(product_id, location_id)
);
CREATE TABLE IF NOT EXISTS product_location_assignment_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_location_id INTEGER NOT NULL,
 employee_id INTEGER,
 valid_from TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 valid_to TEXT,
 FOREIGN KEY(product_location_id) REFERENCES product_locations(id),
 FOREIGN KEY(employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS inventory_sessions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 employee_id INTEGER NOT NULL,
 storage_area TEXT NOT NULL DEFAULT '',
 location_id INTEGER,
 count_type TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'in_progress',
 started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 completed_at TEXT,
 notes TEXT,
 FOREIGN KEY(employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS inventory_counts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 session_id INTEGER NOT NULL,
 product_id INTEGER NOT NULL,
 product_location_id INTEGER,
 assigned_employee_id INTEGER,
 counted_by_employee_id INTEGER,
 quantity REAL,
 status TEXT NOT NULL DEFAULT 'not_counted',
 notes TEXT,
 counted_at TEXT,
 updated_at TEXT,
 FOREIGN KEY(session_id) REFERENCES inventory_sessions(id),
 FOREIGN KEY(product_id) REFERENCES products(id)
);
CREATE INDEX IF NOT EXISTS idx_product_locations_location ON product_locations(location_id, active);
CREATE INDEX IF NOT EXISTS idx_product_locations_employee ON product_locations(assigned_employee_id, active);
CREATE INDEX IF NOT EXISTS idx_inventory_counts_session ON inventory_counts(session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_new_count_position ON inventory_counts(session_id, product_location_id) WHERE product_location_id IS NOT NULL;
'''

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def _add_column(conn, table, column, definition):
    cols={r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _add_column(conn,'inventory_sessions','location_id','INTEGER')
        _add_column(conn,'inventory_counts','product_location_id','INTEGER')
        _add_column(conn,'inventory_counts','assigned_employee_id','INTEGER')
        _add_column(conn,'inventory_counts','counted_by_employee_id','INTEGER')
        _add_column(conn,'inventory_counts','updated_at','TEXT')
