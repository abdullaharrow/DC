import sqlite3
from datetime import datetime
import pandas as pd
from config import DB_FILE

# ----------------- Initialize Database -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS dc_entries (
            dc_entry_number TEXT UNIQUE,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS dc_rows (
            dc_entry_number TEXT,
            item TEXT,
            dozen INTEGER,
            boxes REAL,
            UNIQUE(dc_entry_number, item)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS dc_delivery_details (
            dc_entry_number TEXT,
            item TEXT,
            boxes REAL,
            date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_number TEXT PRIMARY KEY,
            from_date TEXT,
            to_date TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


# ----------------- DC Entry Operations -----------------
def create_dc_entry(dc_entry_number, rows):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("INSERT INTO dc_entries (dc_entry_number, created_at) VALUES (?, ?)",
              (dc_entry_number, datetime.now().isoformat()))

    for row in rows:
        c.execute(
            "INSERT INTO dc_rows (dc_entry_number, item, dozen, boxes) VALUES (?, ?, ?, ?)",
            (dc_entry_number, row['Item'], row['Dozen'], row['Boxes'])
        )

    conn.commit()
    conn.close()


def fetch_dc_entry(dc_entry_number):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
	 # Fetch created_at from dc_entries
    c.execute('SELECT created_at FROM dc_entries WHERE dc_entry_number = ?', (dc_entry_number,))
    created_at_row = c.fetchone()
    created_at = created_at_row[0] if created_at_row else None
    
    # Fetch rows from dc_rows
    c.execute('''
        SELECT r.item, r.dozen, r.boxes 
        FROM dc_rows r
        WHERE r.dc_entry_number = ?
    ''', (dc_entry_number,))
    rows = c.fetchall()
    conn.close()
    dc_data = [{"Item": item, "Dozen": dozen, "Boxes": boxes} for item, dozen, boxes in rows]
    return dc_data, created_at

def delete_dc_entry(dc_entry_number):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
	
    c.execute("""DELETE FROM dc_entries where dc_entry_number = ?""",
              (dc_entry_number,))

    c.execute("""
        DELETE FROM dc_rows 
        WHERE dc_entry_number = ?
    """, (dc_entry_number,))

    c.execute("""
        DELETE FROM dc_delivery_details
        WHERE dc_entry_number = ?
    """, (dc_entry_number,))

    conn.commit()
    conn.close()

def update_dc_row(dc_entry_number, item, new_dozen, new_boxes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE dc_rows 
        SET dozen = ?, boxes = ?
        WHERE dc_entry_number = ? AND item = ?
    """, (new_dozen, new_boxes, dc_entry_number, item))
    conn.commit()
    conn.close()

def delete_dc_row(dc_entry_number, item):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        DELETE FROM dc_rows 
        WHERE dc_entry_number = ? AND item = ?
    """, (dc_entry_number, item))

    c.execute("""
        DELETE FROM dc_delivery_details 
        WHERE dc_entry_number = ? AND item = ?
    """, (dc_entry_number, item))

    conn.commit()
    conn.close()

# ----------------- Delivery Operations -----------------
def add_dc_delivery_details(dc_entry_number, date, item, boxes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Fetch allowed box count
    c.execute("""
        SELECT boxes FROM dc_rows
        WHERE dc_entry_number = ? AND item = ?
    """, (dc_entry_number, item))
    row = c.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"No record found in dc_rows for DC {dc_entry_number} and item '{item}'.")

    allowed_boxes = row[0]

    # Get current total delivered
    c.execute("""
        SELECT COALESCE(SUM(boxes), 0) FROM dc_delivery_details
        WHERE dc_entry_number = ? AND item = ?
    """, (dc_entry_number, item))
    current_delivered = c.fetchone()[0]

    # Check if new delivery exceeds allowed
    if current_delivered + boxes > allowed_boxes:
        conn.close()
        raise ValueError(
            f"Cannot deliver {boxes} boxes for item '{item}'. "
            f"Total would be {current_delivered + boxes}, exceeding the allowed {allowed_boxes}."
        )

    c.execute(
        "INSERT INTO dc_delivery_details (dc_entry_number, item, boxes, date) VALUES (?, ?, ?, ?)",
        (dc_entry_number, item, boxes, date.isoformat())
    )
    conn.commit()
    conn.close()


def get_dc_delivery_details(dc_entry_number):
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT date, item as Item_Name, boxes as Delivered_Boxes 
        FROM dc_delivery_details
        WHERE dc_entry_number = ?
        ORDER BY item
    """
    df = pd.read_sql_query(query, conn, params=(dc_entry_number,))
    df["Delivered_Boxes"] = pd.to_numeric(df["Delivered_Boxes"], errors='coerce').round(2)
    conn.close()
    return df


def get_dc_cumulative_delivery_details(dc_entry_number):
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT item as Item, SUM(boxes) as total_delivered
        FROM dc_delivery_details
        WHERE dc_entry_number = ?
        GROUP BY item
        ORDER BY item
    """
    df = pd.read_sql_query(query, conn, params=(dc_entry_number,))
    conn.close()
    return df


def get_dc_delivery_details_with_date_filter(from_date, to_date):
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT dc_entry_number, date, item, boxes
        FROM dc_delivery_details
        WHERE date BETWEEN ? AND ?
        ORDER BY date DESC
    '''
    df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
    df["boxes"] = pd.to_numeric(df["boxes"], errors='coerce').round(2)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime('%d-%m-%Y')
    conn.close()
    return df


def update_dc_delivery_entry(dc_entry_number, old_date, item, new_boxes, new_date=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if new_date:
        c.execute("""
            UPDATE dc_delivery_details 
            SET boxes = ?, date = ?
            WHERE dc_entry_number = ? AND item = ? AND date = ?
        """, (new_boxes, new_date.isoformat(), dc_entry_number, item, old_date.isoformat()))
    else:
        c.execute("""
            UPDATE dc_delivery_details 
            SET boxes = ?
            WHERE dc_entry_number = ? AND item = ? AND date = ?
        """, (new_boxes, dc_entry_number, item, old_date.isoformat()))
    conn.commit()
    conn.close()

def delete_dc_delivery_entry(dc_entry_number, old_date, item):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        DELETE FROM dc_delivery_details
        WHERE dc_entry_number = ?
        AND item = ?
        AND date = ?
    """, (dc_entry_number, item, old_date.isoformat()))
    conn.commit()
    conn.close()

# ----------------- Invoice Operations -----------------
def create_invoice(invoice_number, from_date, to_date):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    created_at = datetime.now().date().isoformat()  # current date in ISO format (YYYY-MM-DD)

    c.execute('''
        INSERT INTO invoices (invoice_number, from_date, to_date, created_at)
        VALUES (?, ?, ?, ?)
    ''', (invoice_number, from_date.isoformat(), to_date.isoformat(), created_at))
    
    conn.commit()
    conn.close()


def get_invoice_delivery_details(invoice_number):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Fetch invoice date range
    c.execute('SELECT from_date, to_date, created_at FROM invoices WHERE invoice_number = ?', (invoice_number,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return None, None, pd.DataFrame(), None
    from_date, to_date, created_at = row
    from_date = datetime.fromisoformat(from_date).date()
    to_date = datetime.fromisoformat(to_date).date()
    created_at = datetime.fromisoformat(created_at).date()
    conn.close()
    # Fetch deliveries in that range
    df = get_dc_delivery_details_with_date_filter(from_date, to_date)
    return from_date, to_date, df, created_at


def get_uncompleted_dcs():
    conn = sqlite3.connect(DB_FILE)
    query = """
        WITH pending_dc AS (
            SELECT r.dc_entry_number, r.item, r.boxes as planned_boxes, 
                    COALESCE(SUM(d.boxes), 0) as delivered_boxes
                FROM dc_rows r
                LEFT JOIN dc_delivery_details d 
                    ON r.dc_entry_number = d.dc_entry_number AND r.item = d.item
                GROUP BY r.dc_entry_number, r.item, r.boxes
                HAVING delivered_boxes < r.boxes
                ORDER BY r.dc_entry_number
        )
        SELECT p.*, t.created_at
        FROM pending_dc p
        JOIN dc_entries t
            ON p.dc_entry_number = t.dc_entry_number
        ORDER BY p.dc_entry_number;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# ----------------- Fetch All Invoice Numbers -----------------
def get_all_invoices():
    """Return a list of all saved invoice numbers with their date ranges."""
    conn = sqlite3.connect(DB_FILE)
    # Using sqlite3.Row allows us to access columns by name like a dictionary
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    c.execute("SELECT invoice_number, from_date, to_date FROM invoices ORDER BY invoice_number DESC")
    rows = c.fetchall()
    conn.close()
    # Convert rows to a list of dictionaries
    return [dict(row) for row in rows]