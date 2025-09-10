import streamlit as st
# Set page config must be the first Streamlit command
st.set_page_config(layout="wide", page_title="SQL Mystery Game")

import sqlite3
import pandas as pd
import time
from db import get_connection, setup_database
from scenes import get_scenes
from auth import setup_auth, register_user, verify_login
from evaluator import evaluate_sql
from logs import setup_logs, log_attempt, get_logs
from adaptive import adjust_difficulty
from llm import generate_sql, get_random_quality

# --- Setup ---
# Initialize database, logs, and auth
def initialize_database():
    """Initialize all database components"""
    conn = get_connection()
    try:
        setup_database(conn)
        setup_logs(conn)
        setup_auth(conn)
        conn.commit()
    finally:
        conn.close()

# Run database initialization
initialize_database()

def get_user_id(username):
    """Get user ID from username"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        result = c.fetchone()
        return result[0] if result else None
    finally:
        conn.close()

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None
if 'full_name' not in st.session_state:
    st.session_state.full_name = None

# --- UI ---
st.title('🔍 Inventory Heist: Supply Chain Mystery Game')

def show_auth_page():
    tab1, tab2 = st.tabs(['Login', 'Sign Up'])
    
    with tab1:
        st.header('Login')
        login_username = st.text_input('Username', key='login_username_field')
        login_password = st.text_input('Password', type='password', key='login_password_field')
        
        if st.button('Login', key='login_button'):
            print(f"Attempting login for user: {login_username}")
            success, role, message = verify_login(login_username, login_password)
            print(f"Login result - Success: {success}, Role: {role}, Message: {message}")
            if success: 
                conn = get_connection()
                try:
                    c = conn.cursor()
                    # Get additional user info
                    c.execute('''
                        SELECT user_id, full_name, role 
                        FROM users 
                        WHERE username = ?
                    ''', (login_username,))
                    user_data = c.fetchone()
                    
                    if user_data:
                        user_id, full_name, role = user_data
                        # Ensure role is in lowercase for consistent comparison
                        role = role.lower() if role else None
                        # Initialize all session state variables
                        st.session_state.authenticated = True
                        st.session_state.user_id = user_id
                        st.session_state.username = login_username
                        st.session_state.role = role
                        st.session_state.full_name = full_name or login_username
                        print(f"User {login_username} logged in with role: {role}")
                        
                        # Initialize all game state variables with default values
                        if 'score' not in st.session_state:
                            st.session_state.score = 10  # Starting score
                        if 'strikes' not in st.session_state:
                            st.session_state.strikes = 0
                        if 'level' not in st.session_state:
                            st.session_state.level = 0
                        if 'last_feedback' not in st.session_state:
                            st.session_state.last_feedback = ''
                        if 'last_result' not in st.session_state:
                            st.session_state.last_result = None
                        if 'generated_sql' not in st.session_state:
                            st.session_state.generated_sql = ''
                        if 'current_sql' not in st.session_state:
                            st.session_state.current_sql = ''
                        if 'current_prompt' not in st.session_state:
                            st.session_state.current_prompt = ''
                        if 'sql_quality' not in st.session_state:
                            st.session_state.sql_quality = None
                        if 'last_prompt' not in st.session_state:
                            st.session_state.last_prompt = ''
                        if 'last_sql_explanation' not in st.session_state:
                            st.session_state.last_sql_explanation = ''
                        if 'render_count' not in st.session_state:
                            st.session_state.render_count = 0
                        
                        # Load scenes
                        st.session_state.scenes = get_scenes()
                        
                        st.success(message)
                        st.rerun()
                    else:
                        st.error("User data not found")
                finally:
                    conn.close()
            else:
                st.error(message)
    
    with tab2:
        st.header('Create Account')
        # Use unique keys for form inputs to prevent session state conflicts
        register_username = st.text_input('Choose a username', key='reg_username')
        register_password = st.text_input('Choose a password', type='password', key='reg_password')
        full_name = st.text_input('Full Name', key='reg_full_name')
        register_role = st.radio('Account Type', ['student', 'instructor'], key='reg_role')
        
        # Initialize instructor_id as None
        instructor_id = None
        
        # Show instructor selection only for students
        if register_role == 'student':
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute('''
                    SELECT user_id, username, COALESCE(full_name, username) as display_name
                    FROM users 
                    WHERE role = 'instructor'
                    ORDER BY display_name
                ''')
                instructors = c.fetchall()
                
                if not instructors:
                    st.warning('No instructors available. Please ask an instructor to create an account first.')
                else:
                    # Create a mapping of display name to user_id
                    instructor_map = {f"{name} ({username})": user_id for user_id, username, name in instructors}
                    
                    # Show dropdown with formatted display names
                    selected_instructor = st.selectbox(
                        'Select your instructor',
                        options=sorted(instructor_map.keys()),  # Sort by display name
                        index=0
                    )
                    
                    # Get the selected instructor's ID from the mapping
                    instructor_id = instructor_map[selected_instructor] if selected_instructor else None
            finally:
                conn.close()
        
        if st.button('Create Account', key='reg_button'):
            if not register_username or not register_password or not full_name:
                st.error('Please fill in all required fields')
            elif register_role == 'student' and not instructor_id:
                st.error('Please select an instructor')
            else:
                success, message = register_user(
                    register_username, 
                    register_password, 
                    register_role,
                    full_name=full_name.strip(),
                    instructor_id=instructor_id if register_role == 'student' else None
                )
                if success:
                    # Get the new user's ID
                    user_id = get_user_id(register_username)
                    if user_id:
                        # Initialize all session state variables
                        st.session_state.authenticated = True
                        st.session_state.user_id = user_id
                        st.session_state.username = register_username
                        st.session_state.role = register_role
                        st.session_state.full_name = full_name or register_username
                        
                        # Initialize game state variables
                        game_state_defaults = {
                            'score': 10,  # Starting score
                            'strikes': 0,
                            'level': 0,
                            'last_feedback': '',
                            'last_result': None,
                            'generated_sql': '',
                            'current_sql': '',
                            'sql_quality': None,
                            'last_prompt': '',
                            'last_sql_explanation': '',
                            'render_count': 0,
                            'scenes': get_scenes()
                        }
                        
                        # Set defaults for any missing keys
                        for key, value in game_state_defaults.items():
                            if key not in st.session_state:
                                st.session_state[key] = value
                        
                        st.success(message)
                        st.rerun()
                    else:
                        st.error("Failed to retrieve user ID after registration")
                else:
                    st.error(message)

def init_game_state():
    if 'student_id' not in st.session_state:
        st.session_state.student_id = st.session_state.username
    if 'difficulty' not in st.session_state:
        st.session_state.difficulty = 1
    if 'scene_idx' not in st.session_state:
        st.session_state.scene_idx = 0
    if 'last_score' not in st.session_state:
        st.session_state.last_score = None
    if 'score' not in st.session_state:
        st.session_state.score = 10
    if 'strikes' not in st.session_state:
        st.session_state.strikes = 0
    if 'level' not in st.session_state:
        st.session_state.level = 0
    if 'last_feedback' not in st.session_state:
        st.session_state.last_feedback = ''
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    if 'last_quality' not in st.session_state:
        st.session_state.last_quality = None
    # LLM-related states
    if 'generated_sql' not in st.session_state:
        st.session_state.generated_sql = ''
    if 'sql_quality' not in st.session_state:
        st.session_state.sql_quality = None
    if 'last_prompt' not in st.session_state:
        st.session_state.last_prompt = ''
    if 'current_prompt' not in st.session_state:
        st.session_state.current_prompt = ''
    if 'current_sql' not in st.session_state:
        st.session_state.current_sql = ''

def show_student_view():
    # Initialize render count if it doesn't exist
    if 'render_count' not in st.session_state:
        st.session_state.render_count = 0
    st.session_state.render_count += 1
    
    # Show welcome message and logout button in sidebar
    with st.sidebar:
        # Welcome and logout at the top
        col1, col2 = st.columns([3, 2])
        with col1:
            st.write(f'👋 Welcome, {st.session_state.full_name or st.session_state.username}!')
        with col2:
            if st.button('🚪 Logout', key='logout_button'):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
        
        st.divider()
        
        # Database schema section
        st.subheader('📚 Database Schema')
        
        st.markdown('''
        **Products**
        ```sql
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,  -- Unique identifier
            name TEXT,                      -- Product name
            category TEXT,                  -- Product category
            unit_price DECIMAL(10,2)        -- Price per unit
        )
        ```
        
        **Suppliers**
        ```sql
        CREATE TABLE suppliers (
            supplier_id INTEGER PRIMARY KEY, -- Unique identifier
            name TEXT,                      -- Supplier name
            country TEXT,                   -- Supplier country
            reliability_score INTEGER       -- Reliability score (0-100)
        )
        ```
        
        **Warehouses**
        ```sql
        CREATE TABLE warehouses (
            warehouse_id INTEGER PRIMARY KEY, -- Unique identifier
            location TEXT,                   -- Warehouse location
            capacity INTEGER                 -- Storage capacity
        )
        ```
        
        **Shipments**
        ```sql
        CREATE TABLE shipments (
            shipment_id INTEGER PRIMARY KEY,  -- Unique identifier
            product_id INTEGER,              -- Product being shipped
            supplier_id INTEGER,             -- Supplier sending
            warehouse_id INTEGER,            -- Destination warehouse
            quantity INTEGER,               -- Number of units
            shipment_date TEXT,             -- Date shipped
            received_date TEXT,             -- Date received
            status TEXT,                    -- Current status
            FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
            FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE
        )
        ```
        
        **Inventory**
        ```sql
        CREATE TABLE inventory (
            inventory_id INTEGER PRIMARY KEY, -- Unique identifier
            product_id INTEGER,              -- Product in stock
            warehouse_id INTEGER,            -- Storage location
            stock INTEGER,                   -- Current quantity
            last_updated TEXT,              -- Last count date
            FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
            FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE
        )
        ```
        ''')
        
        # Show investigation tips
        st.subheader('🔎 Investigation Tips')
        st.markdown('''
        1. Start by examining basic inventory records
        2. Cross-reference with shipment data
        3. Check supplier reliability scores
        4. Verify warehouse capacities
        5. Look for patterns in dates and quantities
        ''')
    
    # Show welcome message for new game
    if st.session_state.level == 0 and st.session_state.last_feedback == '':
        st.markdown('''
        ### Welcome to the Supply Chain Investigation Unit!
        
        As our newest data analyst, you'll be investigating a series of supply chain anomalies 
        that have been flagged by our automated systems. Your task is to use SQL queries to 
        analyze our database and uncover what's really going on.
        
        **Your Mission:**
        - Level 1: Investigate product inventory discrepancies
        - Level 2: Analyze supplier reliability patterns
        - Level 3: Examine warehouse operations
        - Level 4: Track suspicious shipments
        - Level 5: Connect all the evidence
        
        Use the database schema in the sidebar to help formulate your queries. Good luck, detective!
        ''')
    
    # Game over check
    if st.session_state.strikes >= 3:
        st.error('Game Over! Too many incorrect attempts.')
        if st.button('Start New Game', key='new_game_button'):
            st.session_state.score = 10
            st.session_state.strikes = 0
            st.session_state.level = 0
            st.session_state.last_feedback = None
            st.session_state.last_result = None
            st.session_state.generated_sql = ''
            st.session_state.current_sql = ''
            st.session_state.current_prompt = ''
            st.rerun()
        st.stop()

    # Victory check
    if st.session_state.level >= len(st.session_state.scenes):
        st.balloons()
        st.success(f'Congratulations! You solved the mystery with {st.session_state.score} points!')
        if st.button('Play Again', key='play_again_final'):
            st.session_state.score = 10
            st.session_state.strikes = 0
            st.session_state.level = 0
            st.session_state.last_feedback = None
            st.session_state.last_result = None
            st.session_state.generated_sql = ''
            st.session_state.current_sql = ''
            st.session_state.current_prompt = ''
            st.session_state.last_prompt = ''
            st.rerun()
        st.stop()

    # Display game state
    col1, col2, col3 = st.columns(3)
    col1.metric('Score', st.session_state.score)
    col2.metric('Level', st.session_state.level + 1)
    col3.metric('Strikes', st.session_state.strikes)

    # Display current scene - only once per render
    if 'last_render_count' not in st.session_state or st.session_state.last_render_count != st.session_state.render_count:
        scene = st.session_state.scenes[st.session_state.level]
        st.markdown(f'### Level {st.session_state.level + 1}: {scene["title"]}')
        st.write(scene["story"])
        st.session_state.last_render_count = st.session_state.render_count

    # SQL input area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Initialize session state
        if 'current_prompt' not in st.session_state:
            st.session_state.current_prompt = ""
        
        # Get the prompt from the text input
        prompt = st.text_input('Describe what you want to query:', 
                             key='prompt_input',
                             placeholder='E.g., Show me all products with low inventory')
        
        # Update current prompt in session state
        st.session_state.current_prompt = prompt
        
        # Create a unique form key for the button
        form_key = f'sql_form_{st.session_state.level}'
        
        # Use a form to properly capture the button click
        with st.form(key=form_key):
            submit_button = st.form_submit_button('Generate SQL', 
                                               help='Click to generate SQL based on your description')
            
            if submit_button:
                print("\n=== Generate SQL button clicked! ===")
                print(f"Current prompt: '{prompt}'")
                
                if not prompt or not prompt.strip():
                    st.warning("Please enter a description of what you want to query")
                    st.session_state.generated_sql = "-- Please enter a description above and try again"
                    st.rerun()
                else:
                    with st.spinner('Generating SQL...'):
                        print(f"Generating SQL with prompt: {prompt}")
                        try:
                            quality = get_random_quality()
                            print(f"Using quality: {quality}")
                            generated_sql = generate_sql(scene, quality, user_id=st.session_state.user_id)
                            print(f"Generated SQL: {generated_sql}")
                            st.session_state.generated_sql = generated_sql
                            st.session_state.sql_quality = quality
                            st.session_state.current_prompt = prompt  # Save the current prompt
                            st.session_state.last_render_count = st.session_state.render_count
                            st.rerun()
                        except Exception as e:
                            print(f"Error generating SQL: {str(e)}")
                            st.error(f"Error generating SQL: {str(e)}")
                            st.session_state.generated_sql = "-- Error generating SQL. Please try again."
        
        # Initialize generated_sql if it doesn't exist
        if 'generated_sql' not in st.session_state:
            st.session_state.generated_sql = "-- Enter a description and click 'Generate SQL' to get started"
            
        # SQL input will be moved inside the form
    
    with col2:
        st.markdown('### Query Tips')
        st.markdown('''
        1. Use JOINs to connect tables
        2. Filter with WHERE
        3. Check the schema
        4. Think about the story
        ''')
    
    # Create a form for the SQL submission with a simpler key
    form_key = f'sql_form_level_{st.session_state.level}'
    with st.form(key=form_key):
        # SQL editor with help text outside the text area
        st.markdown('**SQL Query:**')
        
        # Display SQL explanation if it exists
        if hasattr(st.session_state, 'last_sql_explanation') and st.session_state.last_sql_explanation:
            with st.expander("💡 Explanation", expanded=True):
                st.markdown(st.session_state.last_sql_explanation)
        
        # Help section
        sql_help = st.empty()
        with sql_help.expander("💡 SQL Query Help", expanded=False):
            st.markdown('''
            - Modify the generated SQL or write your own query
            - Use the schema reference below for table and column names
            - Click "Submit SQL" when you're ready to test your query
            ''')
        
        # The actual text area without help text
        sql_input = st.text_area(
            label='SQL Query',
            value=st.session_state.generated_sql,
            height=150,
            key=f'sql_input_{st.session_state.level}',
            label_visibility='collapsed'  # Hide the default label since we added our own
        )
        
        # Submit button - this will handle the form submission
        submitted = st.form_submit_button('Submit SQL')
        
        # If form is submitted, update the session state with the current input
        if submitted and f'sql_input_{st.session_state.level}' in st.session_state:
            st.session_state.generated_sql = st.session_state[f'sql_input_{st.session_state.level}']
        
        # Debug information
        print(f"\n=== DEBUG: Form State ===")
        print(f"Form key: {form_key}")
        print(f"Submitted: {submitted}")
        print(f"SQL Input: {sql_input[:100]}..." if sql_input else "SQL Input: (empty)")
        
        # Always update the generated_sql in session state when the form is submitted
        if submitted:
            print("Form submitted!")
            if not sql_input or not sql_input.strip():
                st.error('⚠️ Please enter a SQL query first')
                st.stop()
                
            print("SQL input is valid, proceeding with submission...")
            
            # Store the current SQL in session state
            st.session_state.current_sql = sql_input
            st.session_state.generated_sql = sql_input  # Keep the generated SQL in sync
            
            # Process the submission
            conn = get_connection()
            try:
                # Evaluate the SQL query
                print(f"Evaluating SQL: {sql_input[:100]}...")
                quality, result = evaluate_sql(conn, sql_input, scene['answer_sql'])
                print(f"Evaluation result - Quality: {quality}, Result type: {type(result)}")
                
                if quality == 'syntax_error':
                    st.error('❌ SQL Error')
                    # Show error details in an expandable section
                    with st.expander('Error Details'):
                        st.code(str(result), language='sql')
                        st.markdown('### Common Fixes:')
                        st.markdown('''
                        1. Check for missing keywords (SELECT, FROM, etc.)
                        2. Verify table names match the schema exactly
                        3. Ensure all columns exist in their tables
                        4. Check that parentheses and quotes are balanced
                        5. Verify JOIN conditions use existing columns
                        ''')
                    # Don't log syntax errors or penalize the student
                    
                elif quality == 'correct':
                    st.session_state.last_result = result
                    st.success('🎉 Excellent work, detective! You found a crucial lead:')
                    # Show the query result in a clean format
                    try:
                        if isinstance(result, pd.DataFrame):
                            st.dataframe(result, width='stretch')
                        else:
                            st.code(str(result))
                    except Exception as e:
                        st.write(result)
                    st.info(f'💡 Investigation Update: {scene["story"]}')
                    st.session_state.score += 2
                    st.session_state.last_feedback = 'advance'
                    # Log successful attempt
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 2)  # 2 points for correct answer
                
                elif quality == 'partial':
                    st.warning('🤔 You\'re onto something, but the evidence is inconclusive...')
                    st.info('Your query revealed some information, but there might be more to uncover.')
                    if isinstance(result, str):
                        st.code(result, language='sql')
                    st.session_state.last_feedback = 'retry'
                    # Log partial attempt
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 1)  # 1 point for partial answer
                
                else:  # incorrect
                    st.error('❌ This lead turned out to be a dead end.')
                    st.session_state.strikes += 1
                    st.warning(f'⚠️ Investigation setback! ({st.session_state.strikes}/3 strikes)')
                    # Log incorrect attempt
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 0)  # 0 points for incorrect answer
            
            except Exception as e:
                st.error(f'An error occurred: {e}')
                print(f"Error in SQL evaluation: {str(e)}")
            finally:
                conn.close()
                # Only reset last_feedback if we're not in the middle of a successful submission
                if not submitted or st.session_state.last_feedback != 'advance':
                    st.session_state.last_feedback = ''

    # Victory check
    if st.session_state.level >= len(st.session_state.scenes):
        st.balloons()
        st.success(f'🎉 Congratulations! You solved the mystery with {st.session_state.score} points!')
        if st.button('Play Again', key='play_again_final'):
            # Reset game state
            st.session_state.score = 10
            st.session_state.strikes = 0
            st.session_state.level = 0
            # Clear SQL-related states
            st.session_state.generated_sql = ''
            st.session_state.current_sql = ''
            st.session_state.sql_quality = None
            st.session_state.last_prompt = ''
            st.session_state.current_prompt = ''
            st.session_state.last_result = None
            st.session_state.last_feedback = ''
            # Force refresh
            st.rerun()
        st.stop()

    # Progression
    if st.session_state.last_feedback == 'advance':
        if st.button('Next Level', key=f'next_level_button_{st.session_state.level}'):
            st.session_state.level += 1
            # Clear SQL states for next level
            st.session_state.generated_sql = ''
            st.session_state.current_sql = ''
            st.session_state.sql_quality = None
            st.session_state.last_prompt = ''
            st.session_state.current_prompt = ''
            st.session_state.last_result = None
            st.session_state.last_feedback = ''
            st.rerun()

    st.progress((st.session_state.level) / 5)
    st.write(f"**Score:** {st.session_state.score} | **Strikes:** {st.session_state.strikes}")

def verify_instructor_students(conn):
    """Verify and fix any issues with instructor-student relationships"""
    try:
        c = conn.cursor()
        
        # Check if any students are missing from instructor_students
        c.execute('''
            SELECT user_id, username, full_name 
            FROM users 
            WHERE role = 'student' 
            AND user_id NOT IN (SELECT student_id FROM instructor_students)
        ''')
        unassigned_students = c.fetchall()
        
        if unassigned_students:
            st.write("Debug: Found unassigned students:", unassigned_students)
            
        return True, "Verification complete"
    except Exception as e:
        return False, f"Verification failed: {str(e)}"

def assign_student_to_instructor(conn, student_id, instructor_id):
    """Assign a student to an instructor"""
    try:
        c = conn.cursor()
        
        # First, verify the student exists and is a student
        c.execute('SELECT user_id FROM users WHERE user_id = ? AND role = ?', 
                 (student_id, 'student'))
        if not c.fetchone():
            return False, f"Student with ID {student_id} not found or not a student"
            
        # Check if the student is already assigned to an instructor
        c.execute('SELECT instructor_id FROM instructor_students WHERE student_id = ?', (student_id,))
        existing = c.fetchone()
        
        if existing:
            return False, f"Student is already assigned to instructor ID {existing[0]}"
            
        # Assign the student to the instructor
        c.execute('''
            INSERT INTO instructor_students (instructor_id, student_id)
            VALUES (?, ?)
        ''', (instructor_id, student_id))
        
        conn.commit()
        return True, "Student assigned successfully"
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Database error: {str(e)}"

def show_instructor_view():
    """Display instructor dashboard with student progress overview and detailed views"""
    # Verify user is logged in and is an instructor
    if 'user_id' not in st.session_state or 'role' not in st.session_state:
        st.error("You must be logged in to access this page.")
        return
        
    if st.session_state.role != 'instructor':
        st.error("You do not have permission to access the instructor panel.")
        return
        
    # Initialize session state for selected student if not exists
    if 'selected_student' not in st.session_state:
        st.session_state.selected_student = None
    
    # Sidebar with user info and controls
    with st.sidebar:
        st.title(f"👨\u200d🏫 Instructor Dashboard")
        st.write(f"Welcome, {st.session_state.get('full_name', 'Instructor')}")
        
        # Quick stats
        conn = get_connection()
        try:
            c = conn.cursor()
            
            # Total students
            c.execute('''
                SELECT COUNT(DISTINCT student_id) 
                FROM instructor_students 
                WHERE instructor_id = ?
            ''', (st.session_state.user_id,))
            total_students = c.fetchone()[0]
            
            # Total attempts
            c.execute('''
                SELECT COUNT(*) 
                FROM logs l
                JOIN instructor_students ins ON l.student_id = ins.student_id
                WHERE ins.instructor_id = ?
            ''', (st.session_state.user_id,))
            total_attempts = c.fetchone()[0]
            
            # Average score
            c.execute('''
                SELECT AVG(CAST(score AS FLOAT))
                FROM logs l
                JOIN instructor_students ins ON l.student_id = ins.student_id
                WHERE ins.instructor_id = ? AND l.score IS NOT NULL
            ''', (st.session_state.user_id,))
            avg_score = c.fetchone()[0] or 0
            
            st.metric("Total Students", total_students)
            st.metric("Total Attempts", total_attempts)
            st.metric("Average Score", f"{avg_score:.1f}%")
            
        except sqlite3.Error as e:
            st.error(f"Database error: {str(e)}")
        finally:
            conn.close()
            
        st.markdown("---")
        if st.button('🔄 Refresh Data'):
            st.rerun()
            
        if st.button('🚪 Logout', type='primary'):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
    # Main content
    st.title("Student Progress Overview")
    
    # Get all assigned students with their progress
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Get all students assigned to this instructor with their progress
        c.execute('''
            SELECT 
                u.user_id,
                u.username,
                u.full_name,
                (SELECT COUNT(*) FROM logs WHERE student_id = u.user_id) as total_attempts,
                (SELECT MAX(timestamp) FROM logs WHERE student_id = u.user_id) as last_activity,
                (SELECT AVG(CAST(score AS FLOAT)) FROM logs WHERE student_id = u.user_id) as avg_score,
                (SELECT COUNT(DISTINCT scene_id) FROM logs WHERE student_id = u.user_id) as scenes_attempted,
                (SELECT COUNT(DISTINCT id) FROM scenes) as total_scenes
            FROM users u
            JOIN instructor_students ins ON u.user_id = ins.student_id
            WHERE ins.instructor_id = ?
            ORDER BY u.full_name
        ''', (st.session_state.user_id,))
        
        students = c.fetchall()
        
        if not students:
            st.info("No students are currently assigned to you.")
            return
            
        # Display student progress in a table
        st.subheader("Student Progress")
        
        # Create a DataFrame for the table
        import pandas as pd
        df = pd.DataFrame(students, columns=[
            'ID', 'Username', 'Name', 'Attempts', 'Last Active', 
            'Avg Score', 'Scenes Attempted', 'Total Scenes'
        ])
        
        # Format the data
        df['Progress'] = (df['Scenes Attempted'] / df['Total Scenes'] * 100).round(1).astype(str) + '%'
        df['Avg Score'] = df['Avg Score'].round(1).astype(str) + '%'
        
        # Display the table
        st.dataframe(
            df[['Name', 'Username', 'Attempts', 'Avg Score', 'Progress', 'Last Active']],
            column_config={
                'Name': 'Student Name',
                'Username': 'Username',
                'Attempts': st.column_config.NumberColumn('Attempts'),
                'Avg Score': 'Avg Score',
                'Progress': 'Progress',
                'Last Active': 'Last Active'
            },
            hide_index=True,
            width='stretch'
        )
        
        # Student selection for detailed view
        st.markdown("---")
        st.subheader("Student Details")
        
        # Create a mapping of student names to IDs for the dropdown
        student_options = {f"{row[2]} ({row[1]})": row[0] for row in students}
        selected_student_name = st.selectbox(
            "Select a student to view detailed progress",
            options=[""] + list(student_options.keys()),
            index=0
        )
        
        if selected_student_name:
            selected_student_id = student_options[selected_student_name]
            show_student_details(conn, selected_student_id)
        
    except sqlite3.Error as e:
        st.error(f"Database error: {str(e)}")
    finally:
        conn.close()

def show_student_details(conn, student_id):
    """Display detailed progress for a specific student"""
    c = conn.cursor()
    
    # Get student info
    c.execute('''
        SELECT username, full_name 
        FROM users 
        WHERE user_id = ?
    ''', (student_id,))
    student = c.fetchone()
    
    if not student:
        st.error("Student not found")
        return
        
    username, full_name = student
    
    # Display student info
    st.markdown(f"### {full_name} ({username})")
    
    # Get overall progress
    c.execute('''
        SELECT 
            COUNT(DISTINCT scene_id) as scenes_attempted,
            (SELECT COUNT(*) FROM scenes) as total_scenes,
            AVG(CAST(score AS FLOAT)) as avg_score,
            COUNT(*) as total_attempts,
            MIN(timestamp) as first_attempt,
            MAX(timestamp) as last_attempt
        FROM logs 
        WHERE student_id = ?
    ''', (student_id,))
    
    progress = c.fetchone()
    
    if progress and progress[0] > 0:
        scenes_attempted, total_scenes, avg_score, total_attempts, first_attempt, last_attempt = progress
        progress_percent = (scenes_attempted / total_scenes * 100) if total_scenes > 0 else 0
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Scenes Completed", f"{scenes_attempted} of {total_scenes}")
            st.progress(progress_percent / 100, text=f"{progress_percent:.1f}%")
        with col2:
            st.metric("Average Score", f"{avg_score:.1f}%")
        with col3:
            st.metric("Total Attempts", total_attempts)
        
        # Scene-by-scene progress
        st.subheader("Scene Progress")
        c.execute('''
            SELECT 
                s.id,
                s.title,
                COUNT(l.log_id) as attempts,
                MAX(CAST(l.score AS FLOAT)) as best_score,
                MIN(l.timestamp) as first_attempt,
                MAX(l.timestamp) as last_attempt
            FROM scenes s
            LEFT JOIN logs l ON s.id = l.scene_id AND l.student_id = ?
            GROUP BY s.id, s.title
            ORDER BY s.id
        ''', (student_id,))
        
        scene_progress = c.fetchall()
        
        if scene_progress:
            for scene in scene_progress:
                scene_id, title, attempts, best_score, first_attempt, last_attempt = scene
                
                with st.expander(f"{title} - {best_score if best_score is not None else '0'}%"):
                    if attempts > 0:
                        st.metric("Best Score", f"{best_score}%")
                        st.metric("Attempts", attempts)
                        st.caption(f"First attempt: {first_attempt}")
                        st.caption(f"Last attempt: {last_attempt}")
                        
                        # Show attempts for this scene
                        c.execute('''
                            SELECT timestamp, score, hints_used, feedback
                            FROM logs
                            WHERE student_id = ? AND scene_id = ?
                            ORDER BY timestamp DESC
                        ''', (student_id, scene_id))
                        
                        attempts = c.fetchall()
                        for attempt in attempts:
                            timestamp, score, hints_used, feedback = attempt
                            with st.container(border=True):
                                st.write(f"**{timestamp}** - Score: {score}%")
                                st.write(f"Hints used: {hints_used}")
                                if feedback:
                                    with st.expander("View Feedback"):
                                        st.write(feedback)
                    else:
                        st.info("Not attempted yet")
    else:
        st.info("This student hasn't attempted any scenes yet.")
    
    conn.close()
    return
if not st.session_state.authenticated:
    show_auth_page()
    st.stop()  # Stop execution if not authenticated

# At this point, user is authenticated
# Show appropriate view based on role
if st.session_state.role == 'admin':
    # Admin sidebar with welcome and logout
    with st.sidebar:
        st.title('Admin Panel')
        st.write(f'Welcome, {st.session_state.full_name} (Admin)')
        
        # Add some space
        st.write('---')
        
        # Navigation options
        st.button('Dashboard', disabled=True)
        
        # Logout button
        if st.button('Logout', key='admin_logout'):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Main content
    st.title('Admin Dashboard')
    
    with get_connection() as conn:
        try:
            # User Management Section
            st.subheader('User Management')
            # Show all users
            users_df = pd.read_sql('''
                SELECT 
                    user_id,
                    username,
                    role,
                    full_name,
                    strftime('%Y-%m-%d %H:%M', created_at) as created_at
                FROM users
                ORDER BY role, username
            ''', conn)
            
            st.dataframe(users_df, width='stretch')
            
            # Add new user form
            with st.expander('Add New User'):
                with st.form('add_user_form'):
                    # Create form inputs
                    new_username = st.text_input('Username', key='new_user_username')
                    new_password = st.text_input('Password', type='password', key='new_user_password')
                    new_role = st.selectbox('Role', ['student', 'instructor', 'admin'], key='new_user_role')
                    new_full_name = st.text_input('Full Name', key='new_user_fullname')
                    
                    # Add instructor selection for students
                    instructor_id = None
                    if new_role == 'student':
                        instructors = pd.read_sql('''
                            SELECT user_id, username, full_name 
                            FROM users 
                            WHERE role = 'instructor'
                            ORDER BY username
                        ''', conn)
                            
                        if not instructors.empty:
                            instructor_options = [f"{row['username']} ({row['full_name'] or 'No name'})" for _, row in instructors.iterrows()]
                            selected_instructor = st.selectbox('Select Instructor', instructor_options, key='instructor_select')
                            if selected_instructor:
                                selected_username = selected_instructor.split(' (')[0]
                                instructor_id = instructors[instructors['username'] == selected_username].iloc[0]['user_id']
                        else:
                            st.warning('No instructors available. Please create an instructor account first.')
                    
                    if st.form_submit_button('Add User'):
                        if new_username and new_password:
                            if new_role == 'student' and not instructor_id and not instructors.empty:
                                st.error('Please select an instructor for the student')
                            else:
                                with st.spinner('Adding user...'):
                                    success, message = register_user(
                                        new_username, 
                                        new_password, 
                                        new_role,
                                        full_name=new_full_name or None,
                                        instructor_id=instructor_id if new_role == 'student' else None
                                    )
                                    
                                    if success:
                                        st.success(message)
                                        # Clear the form by forcing a rerun
                                        st.rerun()
                                    else:
                                        st.error(message)
                        else:
                            st.error('Please fill in all required fields')
            
            # System Statistics
            st.subheader('System Statistics')
            
            # User statistics
            user_stats = pd.read_sql('''
                SELECT 
                    role,
                    COUNT(*) as count,
                    strftime('%Y-%m', created_at) as month,
                    COUNT(*) as new_users
                FROM users
                GROUP BY role, strftime('%Y-%m', created_at)
                ORDER BY month
            ''', conn)
            
            if not user_stats.empty:
                st.bar_chart(user_stats.pivot(index='month', columns='role', values='count').fillna(0))
            
            # Activity logs
            st.subheader('Recent Activity')
            logs = pd.read_sql('''
                SELECT 
                    l.timestamp,
                    u.username,
                    l.scene_id,
                    l.score,
                    l.hint_used
                FROM logs l
                JOIN users u ON l.student_id = u.user_id
                ORDER BY l.timestamp DESC
                LIMIT 50
            ''', conn)
            
            if not logs.empty:
                st.dataframe(logs, width='stretch')
            else:
                st.info('No activity logs found')
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
        # Stop execution here since we've handled the admin view
        st.stop()

# Handle instructor view
if st.session_state.role == 'instructor':
    show_instructor_view()
    st.stop()

# Handle student view
if st.session_state.role == 'student':
    show_student_view()
    st.stop()

# If we get here, the role is invalid
st.error('Invalid role. Please contact administrator.')
# Clear session and redirect to login
for key in list(st.session_state.keys()):
    del st.session_state[key]
st.rerun()
