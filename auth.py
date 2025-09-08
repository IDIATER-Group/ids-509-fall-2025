import sqlite3
import hashlib
import secrets
from db import get_connection

def setup_auth(conn):
    """Initialize the authentication tables"""
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'instructor', 'admin')),
            full_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Instructor-student relationship table
    c.execute('''CREATE TABLE IF NOT EXISTS instructor_students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instructor_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL UNIQUE,
        FOREIGN KEY (instructor_id) REFERENCES users(user_id),
        FOREIGN KEY (student_id) REFERENCES users(user_id)
    )''')
    
    # Create a default admin user if no users exist
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:  # Only create admin if no users exist
        try:
            password_hash, salt = hash_password('admin123')
            c.execute('''
                INSERT OR IGNORE INTO users (username, password_hash, salt, role, full_name)
                VALUES (?, ?, ?, 'admin', 'Admin User')
            ''', ('admin', password_hash, salt))
            if c.rowcount > 0:
                print("Created default admin user")
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating admin user: {e}")
            conn.rollback()
    
    return conn

def hash_password(password, salt=None):
    """Hash a password with an optional salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((password + salt).encode())
    return hash_obj.hexdigest(), salt

def register_user(username, password, role, full_name=None, instructor_id=None):
    """Register a new user
    
    Args:
        username: Unique username
        password: User's password
        role: 'student', 'instructor', or 'admin'
        full_name: User's full name (optional)
        instructor_id: ID of the instructor (required for students)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    print(f"Attempting to register user: {username}, role: {role}")  # Debug log
    
    if not username or not password or not role:
        print("Missing required fields")  # Debug log
        return False, "Missing required fields"
        
    conn = None
    try:
        conn = get_connection()
        c = conn.cursor()
        
        print("Checking for existing user...")  # Debug log
        c.execute("SELECT username FROM users WHERE username = ?", (username,))
        if c.fetchone() is not None:
            print(f"Username {username} already exists")  # Debug log
            return False, "Username already exists"
        
        if role == 'student' and not instructor_id:
            print("Missing instructor ID for student")  # Debug log
            return False, "Instructor ID is required for student registration"
        
        # Only allow one admin user
        if role == 'admin':
            print("Checking for existing admin...")  # Debug log
            c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if c.fetchone()[0] > 0:
                print("Admin user already exists")  # Debug log
                return False, "Admin user already exists"
        
        print("Hashing password...")  # Debug log
        password_hash, salt = hash_password(password)
        
        print("Inserting new user...")  # Debug log
        c.execute('''
            INSERT INTO users (username, password_hash, salt, role, full_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password_hash, salt, role, full_name or username))
        
        # If this is a student, link them to their instructor
        if role == 'student' and instructor_id:
            print(f"Linking student {c.lastrowid} to instructor {instructor_id}...")  # Debug log
            student_id = c.lastrowid
            try:
                c.execute('''
                    INSERT INTO instructor_students (instructor_id, student_id)
                    VALUES (?, ?)
                ''', (instructor_id, student_id))
                print(f"Successfully linked student {student_id} to instructor {instructor_id}")
            except sqlite3.IntegrityError as e:
                print(f"Error linking student to instructor: {e}")
                conn.rollback()
                return False, "Failed to link student to instructor. The student might already be assigned to an instructor."
        
        conn.commit()
        print(f"Successfully registered user: {username}")  # Debug log
        return True, f"Successfully registered {username} as {role}"
        
    except sqlite3.IntegrityError as e:
        error_msg = f"Database error: {str(e)}"
        print(error_msg)  # Debug log
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)  # Debug log
        return False, error_msg
    finally:
        if conn:
            conn.close()

def verify_login(username, password):
    """Verify user login credentials
    
    Args:
        username: The username to verify
        password: The password to verify
        
    Returns:
        tuple: (success: bool, role: str or None, message: str)
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT user_id, password_hash, salt, role 
            FROM users 
            WHERE username = ?
        ''', (username,))
        result = c.fetchone()
        
        if not result:
            return False, None, "Invalid username or password"
            
        user_id, stored_hash, salt, role = result
        
        # Hash the provided password with the stored salt
        calculated_hash, _ = hash_password(password, salt)
        
        if calculated_hash == stored_hash:
            # Ensure role is in lowercase for consistent comparison
            role_lower = role.lower() if role else None
            return True, role_lower, "Login successful"
        return False, None, "Invalid username or password"
    except Exception as e:
        return False, None, f"Login failed: {str(e)}"
    finally:
        conn.close()
