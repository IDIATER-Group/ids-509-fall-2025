import sqlite3
from datetime import datetime, timedelta

import os

def get_connection():
    # Get the absolute path to the database file in the same directory as this script
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game.db')
    print(f"Connecting to database at: {db_path}")
    return sqlite3.connect(db_path)

def setup_scenes(conn):
    """Set up the scenes table with initial data"""
    from scenes import get_scenes
    
    c = conn.cursor()
    
    # Create scenes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            story TEXT NOT NULL,
            question TEXT NOT NULL,
            answer_sql TEXT NOT NULL
        )
    ''')
    
    # Insert scenes if they don't exist
    c.execute('SELECT COUNT(*) FROM scenes')
    if c.fetchone()[0] == 0:
        scenes = get_scenes()
        for scene in scenes:
            c.execute('''
                INSERT INTO scenes (id, title, story, question, answer_sql)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                scene['id'],
                scene['title'],
                scene['story'].strip(),
                scene['question'],
                scene['answer_sql'].strip()
            ))
    
    conn.commit()

def setup_database(conn):
    c = conn.cursor()
    
    # Enable foreign key constraints
    c.execute('PRAGMA foreign_keys = ON')
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        unit_price DECIMAL(10,2)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY,
        name TEXT,
        country TEXT,
        reliability_score INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS warehouses (
        warehouse_id INTEGER PRIMARY KEY,
        location TEXT,
        capacity INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS shipments (
        shipment_id INTEGER PRIMARY KEY,
        product_id INTEGER,
        supplier_id INTEGER,
        warehouse_id INTEGER,
        quantity INTEGER,
        shipment_date TEXT,
        received_date TEXT,
        status TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
        FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        inventory_id INTEGER PRIMARY KEY,
        product_id INTEGER,
        warehouse_id INTEGER,
        stock INTEGER,
        last_updated TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
        FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE
    )''')

    # Base date for our mystery (5 days ago)
    base_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

    # Check if data exists
    c.execute('SELECT COUNT(*) FROM products')
    if c.fetchone()[0] == 0:
        # Insert products with prices
        c.executemany('INSERT INTO products VALUES (?, ?, ?, ?)', [
            (1, 'Widget', 'Tools', 49.99),        # Level 1 mystery
            (2, 'Gadget', 'Electronics', 149.99),  # Level 2 mystery
            (3, 'Doodad', 'Accessories', 29.99),   # Level 3 mystery
            (4, 'Thingamajig', 'Tools', 79.99),    # Level 4 mystery
            (5, 'Whatsit', 'Electronics', 199.99)   # Level 5 mystery
        ])

        # Insert suppliers with reliability scores
        c.executemany('INSERT INTO suppliers VALUES (?, ?, ?, ?)', [
            (1, 'Acme Corp', 'USA', 95),      # Highly reliable
            (2, 'Globex', 'Germany', 88),      # Good but some issues
            (3, 'Initech', 'Japan', 92)        # Very reliable
        ])

        # Insert warehouses with capacities
        c.executemany('INSERT INTO warehouses VALUES (?, ?, ?)', [
            (1, 'New York', 1000),  # Largest warehouse
            (2, 'Berlin', 750),      # Medium warehouse
            (3, 'Tokyo', 500)        # Smaller warehouse
        ])

    # Check if inventory data exists
    c.execute('SELECT COUNT(*) FROM inventory')
    if c.fetchone()[0] == 0:
        # Insert inventory records that reflect the mystery
        c.executemany('INSERT INTO inventory VALUES (?, ?, ?, ?, ?)', [
            # Level 1: Widget stock discrepancy
            (1, 1, 1, 200, base_date),  # More than shipped
            
            # Level 2: Missing Gadgets
            (2, 2, 2, 150, base_date),  # Less than expected
            
            # Level 3: Doodad verification needed
            (3, 3, 3, 100, base_date),  # Disputed quantity
            
            # Level 4: Late Thingamajigs
            (4, 4, 2, 0, base_date),    # Not yet received
            
            # Level 5: Whatsit investigation
            (5, 5, 1, 500, base_date)   # Suspicious quantity
        ])

    # Check if shipment data exists
    c.execute('SELECT COUNT(*) FROM shipments')
    if c.fetchone()[0] == 0:
        # Insert shipment records that create the mystery scenarios
        c.executemany('''
            INSERT INTO shipments 
            (shipment_id, product_id, supplier_id, warehouse_id, quantity, 
             shipment_date, received_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', [
            # Level 1: Widget stock discrepancy (more in inventory than shipped)
            (1, 1, 1, 1, 150, base_date, base_date, 'delivered'),  # Only 150 shipped but 200 in inventory
            
            # Level 2: Globex's shipments to Berlin (for reliability check)
            (2, 2, 2, 2, 200, base_date, base_date, 'delivered'),  # On time
            (3, 2, 2, 2, 100, base_date, base_date, 'delivered'),  # On time
            (4, 2, 2, 2, 150, base_date, None, 'in_transit'),     # Still in transit
            
            # Level 3: Doodad verification (no suspicious shipments yet)
            (5, 3, 3, 3, 100, base_date, base_date, 'delivered'),
            
            # Level 4: Suspicious shipment dates (received before shipped)
            (6, 4, 2, 2, 50, base_date, (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d'), 'delivered'),
            
            # Level 5: Suspicious supplier patterns (low reliability supplier)
            (7, 5, 2, 1, 200, (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=10)).strftime('%Y-%m-%d'), 
             (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=8)).strftime('%Y-%m-%d'), 'delivered'),
            (8, 5, 2, 1, 200, (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d'),
             (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=4)).strftime('%Y-%m-%d'), 'delivered'),
            (9, 5, 1, 1, 100, (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d'),
             (datetime.strptime(base_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d'), 'delivered')
        ])

    # Set up scenes table
    setup_scenes(conn)
    
    conn.commit()
