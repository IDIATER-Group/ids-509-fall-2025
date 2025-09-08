import requests
import sqlite3
import time
from datetime import datetime
from db import get_connection

OLLAMA_URL = "http://localhost:11434/api/generate"  # Default Ollama endpoint
LLAMA_MODEL = "llama3"  # Change to your model name if needed

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

def log_llm_interaction(conn, prompt, response, model=LLAMA_MODEL, user_id=None, tokens_used=None):
    """Log an interaction with the LLM
    
    Args:
        conn: Database connection
        prompt: The prompt sent to the LLM
        response: The response received from the LLM
        model: The LLM model used (default: LLAMA_MODEL)
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

def call_ollama(prompt, model=LLAMA_MODEL, max_tokens=256, user_id=None):
    """Call the Ollama API with safety checks and logging
    
    Args:
        prompt: The prompt to send to the LLM
        model: The model to use (default: LLAMA_MODEL)
        max_tokens: Maximum number of tokens to generate (default: 256)
        user_id: ID of the user making the request (required for rate limiting)
        
    Returns:
        str: The generated response, or None if an error occurred
    """
    conn = get_connection()
    response_text = None
    error_msg = "An unknown error occurred"
    tokens_used = 0  # Initialize tokens_used with a default value
    
    try:
        # Rate limiting check
        allowed, message = check_rate_limit(conn, user_id)
        if not allowed:
            return message or "Rate limit exceeded. Please wait before making more requests."
        
        # Prepare the payload with safety parameters
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": min(max_tokens, 512),  # Enforce max token limit
            "temperature": 0.7,  # Lower temperature for more focused responses
            "top_p": 0.9,  # Nucleus sampling for better quality
            "repeat_penalty": 1.1,  # Slightly discourage repetition
            "stop": ["\n\n"],  # Stop on double newlines
            "stream": False  # Ensure we get a complete response
        }
        
        print(f"Sending request to Ollama API at {OLLAMA_URL} with model {model}")
        print(f"Payload: {payload}")
        
        # Make the API call with timeout
        start_time = time.time()
        try:
            response = requests.post(
                OLLAMA_URL, 
                json=payload, 
                timeout=30,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'SQL-Mystery-Game/1.0'
                }
            )
            response_time = time.time() - start_time
            print(f"Ollama API response status: {response.status_code} (took {response_time:.2f}s)")
            
            # Log raw response for debugging
            print(f"Raw response: {response.text[:500]}..." if len(response.text) > 500 else f"Raw response: {response.text}")
            
            response.raise_for_status()
            
            # Extract and clean the response
            data = response.json()
            print(f"Raw API response: {data}")  # Debug print
            
            # Handle both streaming and non-streaming response formats
            if 'response' in data:
                response_text = data['response'].strip()
                tokens_used = data.get('eval_count', 0)
            else:
                response_text = data.get('choices', [{}])[0].get('text', '').strip()
                tokens_used = data.get('usage', {}).get('total_tokens', 0)
            
            print(f"Ollama API response: {response_text[:200]}...")
            
            if not response_text:
                print("Warning: Empty response from Ollama API")
                response_text = "-- No response from the AI assistant. Please try again."
            else:
                # Apply content filtering only if we have a response
                response_text = filter_suspicious_content(prompt, response_text)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            print(f"Error: {error_msg}")
            raise
            
        except ValueError as e:
            error_msg = f"Invalid response format: {str(e)}"
            print(f"Error: {error_msg}")
            raise
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"Error: {error_msg}")
            raise
            
        # Log the successful interaction
        log_llm_interaction(
            conn=conn,
            prompt=prompt,
            response=response_text,
            model=model,
            user_id=user_id,
            tokens_used=tokens_used
        )
        
        return response_text
        
    except Exception as e:
        # Log the error
        log_llm_interaction(
            conn=conn,
            prompt=prompt,
            response=f"Error: {error_msg}",
            model=model,
            user_id=user_id,
            tokens_used=0
        )
        return f"I encountered an error while processing your request: {error_msg}"
        
    finally:
        conn.close()

def generate_sql(scene, quality='correct', user_id=None):
    """
    Generate SQL using local Llama (Ollama) with logging.
    
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
    
    conn = None
    try:
        # Get database connection for logging
        conn = get_connection()
        
        print("\n1. Building prompt...")
        prompt = build_prompt(scene, quality)
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Prompt preview: {prompt[:200]}...")
        
        print("\n2. Calling Ollama API...")
        try:
            print(f"\nCalling Ollama with prompt length: {len(prompt)} characters")
            print(f"Prompt preview: {prompt[:200]}...")
            
            sql = call_ollama(prompt, user_id=user_id)
            print(f"\nRaw Ollama response: {sql}")
            
            # Check if the response contains an error message from our error handling
            if sql and isinstance(sql, str) and sql.startswith("I encountered an error"):
                print("\n⚠️ Error response from Ollama API")
                raise Exception(f"API Error: {sql}")
                
            if not sql or not sql.strip():
                print("\n⚠️ Empty response from Ollama API")
                raise Exception("Received empty response from Ollama API")
            
            # Initialize explanatory text
            explanation = ""
            cleaned_sql = sql.strip()
            
            # Extract explanation before the code block
            if '```' in cleaned_sql:
                parts = cleaned_sql.split('```')
                explanation = parts[0].strip()
                if len(parts) > 1:
                    # Get the SQL part (inside the code block)
                    sql_part = parts[1]
                    if sql_part.startswith('sql\n'):
                        sql_part = sql_part[4:]  # Remove 'sql\n' prefix
                    cleaned_sql = sql_part.strip()
            
            # If there's no code block but there's explanatory text
            elif 'SELECT ' in cleaned_sql:
                # Try to separate explanation from SQL
                sql_start = cleaned_sql.find('SELECT ')
                if sql_start > 0:
                    explanation = cleaned_sql[:sql_start].strip()
                    cleaned_sql = cleaned_sql[sql_start:].strip()
            
            # Store explanation in session state if available
            if explanation:
                st.session_state.last_sql_explanation = explanation
            
            print("\n✅ Successfully generated and cleaned SQL from Ollama")
            print(f"Explanation: {explanation}")
            print(f"Cleaned SQL: {cleaned_sql}")
            return cleaned_sql
                
        except Exception as e:
            print(f"\n⚠️ Error calling Ollama API: {str(e)}")
            print("Falling back to mock SQL generation...")
            raise  # Re-raise to be caught by outer exception handler
            
    except Exception as e:
        import traceback
        print("\n❌ Error in generate_sql:")
        traceback.print_exc()
        print("\n⚠️ Falling back to mock SQL due to error")
        mock_sql = get_mock_sql(scene, quality)
        print(f"Generated mock SQL: {mock_sql}")
        
        # Log the error
        if conn:
            try:
                log_llm_interaction(
                    conn=conn,
                    prompt=f"Error in generate_sql: {str(e)}\n\nOriginal prompt: {prompt}",
                    response=f"Fell back to mock SQL: {mock_sql}",
                    model="error",
                    user_id=user_id
                )
            except Exception as log_error:
                print(f"Failed to log error: {log_error}")
            
        return mock_sql
    
    finally:
        print("=== End of SQL Generation ===\n")
        if conn:
            try:
                conn.close()
            except:
                pass

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
        return sql
    # Fallback to mock logic
    if quality == 'correct':
        return scene['answer_sql'].strip()
    elif quality == 'partial':
        if 'WHERE' in scene['answer_sql']:
            return scene['answer_sql'].split('WHERE')[0] + 'WHERE 1=1;'
        else:
            return scene['answer_sql'].replace('JOIN', '-- JOIN')
    else:
        return 'SELECT * FROM suppliers;'
