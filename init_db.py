import os
import sqlite3
from datetime import datetime
import hashlib
import secrets

import os

def init_database():
    # Remove existing database if it exists
    db_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game.db')
    print(f"Initializing database: {os.path.abspath(db_name)}")
    
    if os.path.exists(db_name):
        try:
            print("Removing existing database...")
            os.remove(db_name)
            # Also remove any journal/WAL files
            for ext in ['-shm', '-wal', '-journal']:
                fname = f"{db_name}{ext}"
                if os.path.exists(fname):
                    print(f"Removing {fname}...")
                    os.remove(fname)
        except Exception as e:
            print(f"Error removing existing database: {e}")
    
    try:
        conn = sqlite3.connect(db_name)
        conn.execute('PRAGMA journal_mode=WAL')  # Use Write-Ahead Logging for better concurrency
    except Exception as e:
        print(f"Error creating database connection: {e}")
        raise
    c = conn.cursor()
    
    # Enable foreign key constraints
    c.execute('PRAGMA foreign_keys = ON')
    
    # Create users table
    c.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'instructor', 'admin')),
            full_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create instructor_students table
    c.execute('''
        CREATE TABLE instructor_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instructor_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL UNIQUE,
            FOREIGN KEY (instructor_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    ''')
    
    # Create logs table
    c.execute('''
        CREATE TABLE logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            scene_id INTEGER,
            attempt_sql TEXT,
            score TEXT,
            hint_used BOOLEAN DEFAULT 0,
            timestamp TEXT,
            FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    ''')
    
    # Set up the rest of the database
    print("Setting up database tables...")
    from db import setup_database
    setup_database(conn)
    print("Database setup complete.")
    
    # Check if admin user already exists
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    admin_exists = c.fetchone()[0] > 0
    
    # Only create admin user if it doesn't exist
    if not admin_exists:
        salt = secrets.token_hex(16)
        password = 'admin123'
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        
        c.execute('''
            INSERT INTO users (username, password_hash, salt, role, full_name)
            VALUES (?, ?, ?, 'admin', 'Admin User')
        ''', ('admin', password_hash, salt))
        print("Admin user created successfully")
        print(f"Admin username: admin")
        print(f"Admin password: {password}")
    else:
        print("Admin user already exists, skipping creation")
    
    conn.commit()
    conn.close()
    
    print("Database initialized successfully!")
    print(f"Admin username: admin")
    print(f"Admin password: {password}")

if __name__ == '__main__':
    init_database()
