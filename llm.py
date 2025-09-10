import sqlite3
import time
from datetime import datetime
from db import get_connection
from llm_providers import generate_text


def ensure_llm_logs_table(conn):
    """Ensure the llm_logs table exists in the given connection"""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS llm_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        prompt TEXT NOT NULL,
        response TEXT,
        model TEXT NOT NULL,
        tokens_used INTEGER,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
    )''')
    conn.commit()

def log_llm_interaction(conn, prompt, response, model="gemini-flash", user_id=None, tokens_used=None):
    """Log an interaction with the LLM
    
    Args:
        conn: Database connection
        prompt: The prompt sent to the LLM
        response: The response received from the LLM
        model: The LLM model used (default: "gemini-flash")
        user_id: ID of the user making the request (optional)
        tokens_used: Number of tokens used in the interaction (optional)
    """
    ensure_llm_logs_table(conn)
    c = conn.cursor()
    c.execute('''
        INSERT INTO llm_logs (user_id, prompt, response, model, tokens_used, timestamp)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (user_id, str(prompt), str(response), model, tokens_used))
    conn.commit()

def validate_scene_structure(scene):
    """Validate that the scene has all required fields with proper types"""
    required_fields = {
        'title': str,
        'story': str,
        'question': str,
        'answer_sql': str
    }
    
    if not isinstance(scene, dict):
        raise ValueError("Scene must be a dictionary")
        
    for field, field_type in required_fields.items():
        if field not in scene:
            raise ValueError(f"Missing required field in scene: {field}")
        if not isinstance(scene[field], field_type):
            raise ValueError(f"Field '{field}' must be of type {field_type.__name__}")

def build_prompt(scene, quality='correct'):
    """
    Build a prompt for the Llama model to generate a SQL query.
    
    Args:
        scene: Dictionary containing scene details
        quality: 'correct', 'partial', or 'incorrect'
        
    Returns:
        str: Formatted prompt for the LLM
    """
    # Input validation
    validate_scene_structure(scene)
    if quality not in ['correct', 'partial', 'incorrect']:
        raise ValueError("Quality must be 'correct', 'partial', or 'incorrect'")
    
    # Sanitize inputs to prevent prompt injection
    title = str(scene['title']).replace('```', '').replace('\n', ' ').strip()
    story = str(scene['story']).replace('```', '').replace('\n', ' ').strip()
    question = str(scene['question']).replace('```', '').replace('\n', ' ').strip()
    
    # System message with clear instructions against cheating
    system_message = """You are a SQL teaching assistant for a supply chain investigation game. 
Your role is to help students learn SQL by providing educational responses. 

RULES:
1. ONLY generate SQL queries related to the given scenario
2. NEVER reveal the complete solution or answer directly
3. If asked about game mechanics or how to cheat, explain this is a learning exercise
4. Focus on teaching SQL concepts, not solving the puzzle
5. If a query seems suspicious, suggest learning resources instead

Your responses will be monitored for educational value."""

    base = f"""{system_message}

SCENARIO OVERVIEW:
- Title: {title}
- Context: {story}
- Task: {question}

INSTRUCTIONS: """
    
    if quality == 'correct':
        base += """
Generate a SQL query that would help investigate this scenario. 
The query should be educational and demonstrate good SQL practices.
Only output the SQL code with no additional explanation."""
    elif quality == 'partial':
        base += """
Create a SQL query that's close to being correct but has a small issue 
that a student might make. Only output the SQL code with no explanation."""
    else:
        base += """
Generate a SQL query that looks plausible but contains a common mistake 
or doesn't fully answer the question. Only output the SQL code."""
        
    return base

def check_rate_limit(conn, user_id, max_requests=10, time_window=300, daily_limit=100):
    """Check if user has exceeded rate limits
    
    Args:
        conn: Database connection
        user_id: ID of the user making the request
        max_requests: Maximum requests allowed in time_window (default: 10/5min)
        time_window: Time window in seconds (default: 300s = 5 minutes)
        daily_limit: Maximum requests allowed per day (default: 100)
        
    Returns:
        tuple: (bool, str) - (True, None) if allowed, (False, error_message) if rate limited
    """
    if not user_id:
        return True, None  # Shouldn't happen in practice
    
    c = conn.cursor()
    
    # Check user's role (instructors get higher limits)
    c.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result and result[0] == 'instructor':
        max_requests = 20  # Higher limit for instructors
        daily_limit = 200
    
    # Check short-term rate limit (last 5 minutes)
    c.execute('''
        SELECT COUNT(*) FROM llm_logs 
        WHERE user_id = ? AND 
              timestamp > datetime('now', ? || ' seconds')
    ''', (user_id, -time_window))
    recent_requests = c.fetchone()[0]
    
    # Check daily limit (last 24 hours)
    c.execute('''
        SELECT COUNT(*) FROM llm_logs 
        WHERE user_id = ? AND 
              timestamp > datetime('now', '-1 day')
    ''', (user_id,))
    daily_requests = c.fetchone()[0]
    
    # Check for rapid bursts (more than 3 in 30 seconds)
    c.execute('''
        SELECT COUNT(*) FROM llm_logs 
        WHERE user_id = ? AND 
              timestamp > datetime('now', '-30 seconds')
    ''', (user_id,))
    burst_requests = c.fetchone()[0]
    
    # Apply rate limits
    if daily_requests >= daily_limit:
        return False, "Daily request limit reached. Please try again tomorrow."
    elif recent_requests >= max_requests:
        return False, "Too many requests. Please wait a few minutes before trying again."
    elif burst_requests > 3 and recent_requests > 3:
        return False, "Please slow down your requests."
    
    return True, None

def filter_suspicious_content(prompt, response):
    """Check for and filter out potentially malicious or off-topic content"""
    suspicious_keywords = [
        'cheat', 'hack', 'exploit', 'bypass', 'solution', 'answer',
        'game mechanics', 'how to win', 'trick', 'loophole', 'cheat code',
        'admin', 'root', 'password', 'token', 'secret', 'key', 'backdoor'
    ]
    
    # Check if response contains suspicious content
    if any(keyword in response.lower() for keyword in suspicious_keywords):
        return "I'm sorry, I can't provide that information. Let's focus on learning SQL!"
    return response


def generate_sql(scene, quality='correct', user_id=None):
    """
    Generate SQL using Gemini Flash via AI Studio.
    Args:
        scene: The scene dictionary containing title, story, question, etc.
        quality: The quality of SQL to generate ('correct', 'partial', 'incorrect')
        user_id: ID of the user making the request (optional)
    Returns:
        str: Generated SQL query
    """
    print("\n=== Starting SQL Generation ===")
    print(f"Scene: {scene.get('title', 'No title')}")
    print(f"Quality: {quality}")
    print(f"User ID: {user_id}")

    try:
        prompt = build_prompt(scene, quality)
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Prompt preview: {prompt[:200]}...")

        # Use Gemini Flash for SQL generation
        sql = generate_text(prompt, temperature=0.0)
        print(f"\nRaw Gemini response: {sql}")

        # Clean up the response (remove code fences, explanations, etc.)
        cleaned_sql = sql.strip()
        if '```' in cleaned_sql:
            parts = cleaned_sql.split('```')
            if len(parts) > 1:
                sql_part = parts[1]
                if sql_part.startswith('sql\n'):
                    sql_part = sql_part[4:]
                cleaned_sql = sql_part.strip()
        elif 'SELECT ' in cleaned_sql:
            sql_start = cleaned_sql.find('SELECT ')
            cleaned_sql = cleaned_sql[sql_start:].strip()

        print("\n✅ Successfully generated and cleaned SQL from Gemini")
        print(f"Cleaned SQL: {cleaned_sql}")
        return cleaned_sql

    except Exception as e:
        print(f"\n❌ Error in generate_sql: {str(e)}")
        mock_sql = get_mock_sql(scene, quality)
        print(f"Generated mock SQL: {mock_sql}")
        return mock_sql

def get_mock_sql(scene, quality):
    """Generate mock SQL for fallback purposes"""
    try:
        if quality == 'correct':
            return scene['answer_sql']
        elif quality == 'partial':
            # Remove a key condition or join
            sql = scene['answer_sql']
            if 'WHERE' in sql:
                sql = sql.split('WHERE')[0]
            return sql
        else:
            # Return a very basic incorrect query
            table_name = scene['title'].split()[0].lower()
            if not table_name.endswith('s'):
                table_name += 's'
            return f"SELECT * FROM {table_name} LIMIT 5;"
    except Exception as e:
        print(f"Error in get_mock_sql: {str(e)}")
        return "SELECT * FROM products LIMIT 5;"  # Fallback to a safe default

def get_random_quality():
    """
    Randomly choose query quality with weights:
    - 40% correct
    - 40% partial
    - 20% incorrect
    """
    import random
    r = random.random()
    if r < 0.4:
        return 'correct'
    elif r < 0.8:
        return 'partial'
    else:
        return 'incorrect'
