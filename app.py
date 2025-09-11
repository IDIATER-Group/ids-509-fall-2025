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

# -------------------------------
# Game defaults + reset utilities
# -------------------------------
GAME_KEYS = {
    'score': 10,
    'strikes': 0,
    'level': 0,
    'last_feedback': '',
    'last_result': None,
    'generated_sql': '',
    'current_sql': '',
    'sql_quality': None,
    'last_prompt': '',
    'current_prompt': '',
    'last_sql_explanation': '',
    'render_count': 0,
}

def reset_game_state(keep_auth=True):
    """Reset only the game state, keep auth unless told otherwise."""
    keep_keys = {'authenticated', 'user_id', 'username', 'role', 'full_name'} if keep_auth else set()
    for k in list(st.session_state.keys()):
        if k not in keep_keys:
            del st.session_state[k]
    for k, v in GAME_KEYS.items():
        st.session_state[k] = v
    st.session_state.scenes = get_scenes()
    st.rerun()

# --- Setup ---
# Initialize database, logs, and auth
def initialize_database():
    """Initialize all database components"""
    conn = get_connection()
    try:
        setup_database(conn)
        setup_logs(conn)      # ensures logs table + feedback column
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
                        role = role.lower() if role else None
                        # Core auth/session
                        st.session_state.authenticated = True
                        st.session_state.user_id = user_id
                        st.session_state.username = login_username
                        st.session_state.role = role
                        st.session_state.full_name = full_name or login_username
                        print(f"User {login_username} logged in with role: {role}")
                        
                        # Initialize game state defaults if missing
                        for k, v in GAME_KEYS.items():
                            if k not in st.session_state:
                                st.session_state[k] = v
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
        register_username = st.text_input('Choose a username', key='reg_username')
        register_password = st.text_input('Choose a password', type='password', key='reg_password')
        full_name = st.text_input('Full Name', key='reg_full_name')
        register_role = st.radio('Account Type', ['student', 'instructor'], key='reg_role')
        
        instructor_id = None
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
                    instructor_map = {f"{name} ({username})": user_id for user_id, username, name in instructors}
                    selected_instructor = st.selectbox(
                        'Select your instructor',
                        options=sorted(instructor_map.keys()),
                        index=0
                    )
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
                    user_id = get_user_id(register_username)
                    if user_id:
                        st.session_state.authenticated = True
                        st.session_state.user_id = user_id
                        st.session_state.username = register_username
                        st.session_state.role = register_role
                        st.session_state.full_name = full_name or register_username
                        # Apply game defaults and scenes
                        reset_game_state(keep_auth=True)
                    else:
                        st.error("Failed to retrieve user ID after registration")
                else:
                    st.error(message)

def init_game_state():
    # Backwards-compatible initializer in case of missing keys
    if 'student_id' not in st.session_state:
        st.session_state.student_id = st.session_state.username
    if 'difficulty' not in st.session_state:
        st.session_state.difficulty = 1
    if 'scene_idx' not in st.session_state:
        st.session_state.scene_idx = 0
    if 'last_score' not in st.session_state:
        st.session_state.last_score = None
    for k, v in GAME_KEYS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if 'scenes' not in st.session_state:
        st.session_state.scenes = get_scenes()

def show_student_view():
    # Initialize render count if it doesn't exist
    if 'render_count' not in st.session_state:
        st.session_state.render_count = 0
    st.session_state.render_count += 1
    
    # Sidebar
    with st.sidebar:
        col1, col2 = st.columns([3, 2])
        with col1:
            st.write(f'👋 Welcome, {st.session_state.full_name or st.session_state.username}!')
        with col2:
            if st.button('🚪 Logout', key='logout_button'):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
        
        st.divider()
        st.subheader('📚 Database Schema')
        st.markdown('''
        **Products**
        ```sql
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            unit_price DECIMAL(10,2)
        )
        ```
        **Suppliers**
        ```sql
        CREATE TABLE suppliers (
            supplier_id INTEGER PRIMARY KEY,
            name TEXT,
            country TEXT,
            reliability_score INTEGER
        )
        ```
        **Warehouses**
        ```sql
        CREATE TABLE warehouses (
            warehouse_id INTEGER PRIMARY KEY,
            location TEXT,
            capacity INTEGER
        )
        ```
        **Shipments**
        ```sql
        CREATE TABLE shipments (
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
        )
        ```
        **Inventory**
        ```sql
        CREATE TABLE inventory (
            inventory_id INTEGER PRIMARY KEY,
            product_id INTEGER,
            warehouse_id INTEGER,
            stock INTEGER,
            last_updated TEXT,
            FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
            FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id) ON DELETE CASCADE
        )
        ```
        ''')
        
        st.subheader('🔎 Investigation Tips')
        st.markdown('''
        1. Start by examining basic inventory records
        2. Cross-reference with shipment data
        3. Check supplier reliability scores
        4. Verify warehouse capacities
        5. Look for patterns in dates and quantities
        ''')

    # Welcome text
    if st.session_state.level == 0 and st.session_state.last_feedback == '':
        st.markdown('''
        ### Welcome to the Supply Chain Investigation Unit!
        As our newest data analyst, you'll be investigating a series of supply chain anomalies.
        **Your Mission:**
        - Level 1: Investigate product inventory discrepancies
        - Level 2: Analyze supplier reliability patterns
        - Level 3: Examine warehouse operations
        - Level 4: Track suspicious shipments
        - Level 5: Connect all the evidence
        ''')

    # Game over
    if st.session_state.strikes >= 3:
        st.error('Game Over! Too many incorrect attempts.')
        if st.button('Start New Game', key='new_game_button'):
            reset_game_state(keep_auth=True)
        st.stop()

    # Victory
    if st.session_state.level >= len(st.session_state.scenes):
        st.balloons()
        st.success(f'Congratulations! You solved the mystery with {st.session_state.score} points!')
        if st.button('Play Again', key='play_again_final'):
            reset_game_state(keep_auth=True)
        st.stop()

    # Display game state
    col1, col2, col3 = st.columns(3)
    col1.metric('Score', st.session_state.score)
    col2.metric('Level', st.session_state.level + 1)
    col3.metric('Strikes', st.session_state.strikes)

    # Current scene (once per render)
    if 'last_render_count' not in st.session_state or st.session_state.last_render_count != st.session_state.render_count:
        scene = st.session_state.scenes[st.session_state.level]
        st.markdown(f'### Level {st.session_state.level + 1}: {scene["title"]}')
        st.write(scene["story"])
        st.session_state.last_render_count = st.session_state.render_count

    # SQL builder + submit
    col1, col2 = st.columns([3, 1])
    with col1:
        if 'current_prompt' not in st.session_state:
            st.session_state.current_prompt = ""
        prompt = st.text_input(
            'Describe what you want to query:',
            key='prompt_input',
            placeholder='E.g., Show me all products with low inventory'
        )
        st.session_state.current_prompt = prompt
        form_key = f'sql_form_{st.session_state.level}'
        with st.form(key=form_key):
            submit_button = st.form_submit_button(
                'Generate SQL',
                help='Click to generate SQL based on your description'
            )
            if submit_button:
                if not prompt or not prompt.strip():
                    st.warning("Please enter a description of what you want to query")
                    st.session_state.generated_sql = "-- Please enter a description above and try again"
                    st.rerun()
                else:
                    with st.spinner('Generating SQL...'):
                        try:
                            quality = get_random_quality()
                            generated_sql = generate_sql(scene, quality, user_id=st.session_state.user_id)
                            st.session_state.generated_sql = generated_sql
                            st.session_state.sql_quality = quality
                            st.session_state.current_prompt = prompt
                            st.session_state.last_render_count = st.session_state.render_count
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error generating SQL: {str(e)}")
                            st.session_state.generated_sql = "-- Error generating SQL. Please try again."

        if 'generated_sql' not in st.session_state:
            st.session_state.generated_sql = "-- Enter a description and click 'Generate SQL' to get started"
    with col2:
        st.markdown('### Query Tips')
        st.markdown('''
        1. Use JOINs to connect tables
        2. Filter with WHERE
        3. Check the schema
        4. Think about the story
        ''')

    # Submit SQL
    form_key = f'sql_form_level_{st.session_state.level}'
    with st.form(key=form_key):
        st.markdown('**SQL Query:**')
        if hasattr(st.session_state, 'last_sql_explanation') and st.session_state.last_sql_explanation:
            with st.expander("💡 Explanation", expanded=True):
                st.markdown(st.session_state.last_sql_explanation)

        sql_help = st.empty()
        with sql_help.expander("💡 SQL Query Help", expanded=False):
            st.markdown('''
            - Modify the generated SQL or write your own query
            - Use the schema reference below for table and column names
            - Click "Submit SQL" when you're ready to test your query
            ''')

        sql_input = st.text_area(
            label='SQL Query',
            value=st.session_state.generated_sql,
            height=150,
            key=f'sql_input_{st.session_state.level}',
            label_visibility='collapsed'
        )
        submitted = st.form_submit_button('Submit SQL')

        if submitted and f'sql_input_{st.session_state.level}' in st.session_state:
            st.session_state.generated_sql = st.session_state[f'sql_input_{st.session_state.level}']

        if submitted:
            if not sql_input or not sql_input.strip():
                st.error('⚠️ Please enter a SQL query first')
                st.stop()

            st.session_state.current_sql = sql_input
            st.session_state.generated_sql = sql_input

            conn = get_connection()
            try:
                # Evaluate
                quality, result = evaluate_sql(conn, sql_input, scene['answer_sql'])

                # LLM feedback text
                feedback_text = ''
                if quality == 'correct':
                    feedback_text = 'Great job! Your query returned the expected result.'
                elif quality == 'partial':
                    feedback_text = 'Partially correct — compare your output to the expected columns/rows and refine joins/filters.'
                elif quality == 'incorrect':
                    feedback_text = 'Not quite — double-check table names, join keys, and WHERE conditions.'
                elif quality == 'syntax_error':
                    feedback_text = str(result)

                if quality == 'syntax_error':
                    st.error('❌ SQL Error')
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
                    # no log on syntax error

                elif quality == 'correct':
                    st.session_state.last_result = result
                    st.success('🎉 Excellent work, detective! You found a crucial lead:')
                    with st.expander('LLM Feedback'):
                        st.write(feedback_text)
                    try:
                        if isinstance(result, pd.DataFrame):
                            st.dataframe(result, width='stretch')
                        else:
                            st.code(str(result))
                    except Exception:
                        st.write(result)
                    st.info(f'💡 Investigation Update: {scene["story"]}')
                    st.session_state.score += 2
                    st.session_state.last_feedback = 'advance'
                    # Log attempt WITH feedback
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 2, feedback=feedback_text)

                elif quality == 'partial':
                    st.warning('🤔 You\'re onto something, but the evidence is inconclusive...')
                    st.info('Your query revealed some information, but there might be more to uncover.')
                    with st.expander('LLM Feedback'):
                        st.write(feedback_text)
                    if isinstance(result, str):
                        st.code(result, language='sql')
                    st.session_state.last_feedback = 'retry'
                    # Log attempt WITH feedback
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 1, feedback=feedback_text)

                else:  # incorrect
                    st.error('❌ This lead turned out to be a dead end.')
                    with st.expander('LLM Feedback'):
                        st.write(feedback_text)
                    st.session_state.strikes += 1
                    st.warning(f'⚠️ Investigation setback! ({st.session_state.strikes}/3 strikes)')
                    # Log attempt WITH feedback
                    log_attempt(conn, st.session_state.user_id, st.session_state.level, sql_input, 0, feedback=feedback_text)

            except Exception as e:
                st.error(f'An error occurred: {e}')
                print(f"Error in SQL evaluation: {str(e)}")
            finally:
                conn.close()
                if not submitted or st.session_state.last_feedback != 'advance':
                    st.session_state.last_feedback = ''

    # Victory check (again) and actions
    if st.session_state.level >= len(st.session_state.scenes):
        st.balloons()
        st.success(f'🎉 Congratulations! You solved the mystery with {st.session_state.score} points!')
        if st.button('Play Again', key='play_again_final'):
            reset_game_state(keep_auth=True)
        st.stop()

    # Progression
    if st.session_state.last_feedback == 'advance':
        if st.button('Next Level', key=f'next_level_button_{st.session_state.level}'):
            st.session_state.level += 1
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
        c.execute('SELECT user_id FROM users WHERE user_id = ? AND role = ?', (student_id, 'student'))
        if not c.fetchone():
            return False, f"Student with ID {student_id} not found or not a student"
        c.execute('SELECT instructor_id FROM instructor_students WHERE student_id = ?', (student_id,))
        existing = c.fetchone()
        if existing:
            return False, f"Student is already assigned to instructor ID {existing[0]}"
        c.execute('INSERT INTO instructor_students (instructor_id, student_id) VALUES (?, ?)', (instructor_id, student_id))
        conn.commit()
        return True, "Student assigned successfully"
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Database error: {str(e)}"

def show_instructor_view():
    """Display instructor dashboard with student progress overview and detailed views"""
    if 'user_id' not in st.session_state or 'role' not in st.session_state:
        st.error("You must be logged in to access this page.")
        return
    if st.session_state.role != 'instructor':
        st.error("You do not have permission to access the instructor panel.")
        return
        
    if 'selected_student' not in st.session_state:
        st.session_state.selected_student = None
    
    with st.sidebar:
        st.title(f"👨‍🏫 Instructor Dashboard")
        st.write(f"Welcome, {st.session_state.get('full_name', 'Instructor')}")
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute('''
                SELECT COUNT(DISTINCT student_id) 
                FROM instructor_students 
                WHERE instructor_id = ?
            ''', (st.session_state.user_id,))
            total_students = c.fetchone()[0]
            c.execute('''
                SELECT COUNT(*) 
                FROM logs l
                JOIN instructor_students ins ON l.student_id = ins.student_id
                WHERE ins.instructor_id = ?
            ''', (st.session_state.user_id,))
            total_attempts = c.fetchone()[0]
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
        
    st.title("Student Progress Overview")
    conn = get_connection()
    try:
        c = conn.cursor()
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
        
        st.subheader("Student Progress")
        df = pd.DataFrame(students, columns=[
            'ID', 'Username', 'Name', 'Attempts', 'Last Active', 
            'Avg Score', 'Scenes Attempted', 'Total Scenes'
        ])
        df['Progress'] = (df['Scenes Attempted'] / df['Total Scenes'] * 100).round(1).astype(str) + '%'
        df['Avg Score'] = df['Avg Score'].round(1).astype(str) + '%'
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
        
        st.markdown("---")
        st.subheader("Student Details")
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
    c.execute('SELECT username, full_name FROM users WHERE user_id = ?', (student_id,))
    student = c.fetchone()
    if not student:
        st.error("Student not found")
        return
        
    username, full_name = student
    st.markdown(f"### {full_name} ({username})")
    
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
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Scenes Completed", f"{scenes_attempted} of {total_scenes}")
            st.progress(progress_percent / 100, text=f"{progress_percent:.1f}%")
        with col2:
            st.metric("Average Score", f"{avg_score:.1f}%")
        with col3:
            st.metric("Total Attempts", total_attempts)
        
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
                        c.execute('''
                            SELECT timestamp, score, hint_used, feedback
                            FROM logs
                            WHERE student_id = ? AND scene_id = ?
                            ORDER BY timestamp DESC
                        ''', (student_id, scene_id))
                        attempts_rows = c.fetchall()
                        for attempt in attempts_rows:
                            timestamp, score, hint_used, feedback = attempt
                            with st.container(border=True):
                                st.write(f"**{timestamp}** - Score: {score}%")
                                st.write(f"Hints used: {hint_used}")
                                if feedback:
                                    with st.expander("View Feedback"):
                                        st.write(feedback)
                    else:
                        st.info("Not attempted yet")
    else:
        st.info("This student hasn't attempted any scenes yet.")
    
    conn.close()
    return

# -------------------------------
# App entrypoint by role
# -------------------------------
if not st.session_state.authenticated:
    show_auth_page()
    st.stop()

if st.session_state.role == 'admin':
    # (Admin view omitted for brevity—keep your existing admin logic if needed)
    st.write("Admin view not shown in this trimmed version.")
    st.stop()

if st.session_state.role == 'instructor':
    show_instructor_view()
    st.stop()

if st.session_state.role == 'student':
    init_game_state()
    show_student_view()
    st.stop()

st.error('Invalid role. Please contact administrator.')
for key in list(st.session_state.keys()):
    del st.session_state[key]
st.rerun()
