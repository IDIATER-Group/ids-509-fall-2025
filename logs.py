import sqlite3
from datetime import datetime

from db import get_connection

def ensure_feedback_column(conn):
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(logs)")
        cols = [row[1] for row in c.fetchall()]
        if 'feedback' not in cols:
            c.execute("ALTER TABLE logs ADD COLUMN feedback TEXT")
            conn.commit()
    except Exception as e:
        print(f"[logs.migration] {e}")

def ensure_logs_table(conn):
    """Ensure the logs table exists in the given connection"""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        scene_id INTEGER,
        attempt_sql TEXT,
        score TEXT,
        hint_used BOOLEAN DEFAULT 0,
        timestamp TEXT,
        feedback TEXT,
        FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
    )''')
    conn.commit()
    # Still run migration to cover legacy DBs
    ensure_feedback_column(conn)

def setup_logs(conn):
    ensure_logs_table(conn)

def log_attempt(conn, student_id, scene_id, attempt_sql, score, hint_used=False, feedback=None):
    """Log a student's attempt at a scene
    
    Args:
        conn: Database connection
        student_id: ID of the student
        scene_id: ID of the scene
        attempt_sql: The SQL query attempted by the student
        score: The score for the attempt
        hint_used: Whether the student used a hint (default: False)
    """
    c = conn.cursor()
    c.execute('''
        INSERT INTO logs (student_id, scene_id, attempt_sql, score, hint_used, timestamp, feedback)
        VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
    ''', (student_id, scene_id, attempt_sql, score, 1 if hint_used else 0, feedback))
    conn.commit()

def get_logs(conn, student_id=None, username=None, limit=None):
    """Retrieve logs, optionally filtered by student ID or username
    
    Args:
        conn: Database connection
        student_id: Filter by student ID (optional)
        username: Filter by username (optional)
        limit: Maximum number of logs to return (optional)
        
    Returns:
        List of log entries with user and scene information
    """
    c = conn.cursor()
    
    query = '''
        SELECT l.*, u.username, u.full_name, s.title as scene_title
        FROM logs l
        JOIN users u ON l.student_id = u.user_id
        LEFT JOIN (
            SELECT id, title 
            FROM (
                SELECT id, title 
                FROM scenes 
                UNION ALL 
                SELECT id, title 
                FROM (
                    SELECT 1 as id, 'Inventory Anomaly' as title
                    UNION SELECT 2, 'Suspicious Shipment'
                    UNION SELECT 3, 'Missing Inventory'
                    UNION SELECT 4, 'Supplier Discrepancy'
                    UNION SELECT 5, 'Final Mystery'
                )
            )
        ) s ON l.scene_id = s.id
    '''
    
    conditions = []
    params = []
    
    if student_id:
        conditions.append('l.student_id = ?')
        params.append(student_id)
    elif username:
        conditions.append('u.username = ?')
        params.append(username)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    query += ' ORDER BY l.timestamp DESC'
    
    if limit:
        query += ' LIMIT ?'
        params.append(limit)
    
    c.execute(query, params)
    return c.fetchall()
