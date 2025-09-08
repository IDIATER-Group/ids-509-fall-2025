import sqlite3
import pandas as pd
import sqlparse

def validate_sql_syntax(sql):
    """Validate SQL syntax without executing the query."""
    try:
        # Parse the SQL statement
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False, "Empty query"
        
        # Basic syntax validation
        stmt = parsed[0]
        if not stmt.get_type():
            return False, "Invalid SQL statement type"
            
        # # Check for basic SQL keywords
        # tokens = [t.value.upper() for t in stmt.tokens if not t.is_whitespace]
        # if not any(keyword in tokens for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
        #     return False, "Missing required SQL keyword (SELECT/INSERT/UPDATE/DELETE)"
            
        return True, None
    except Exception as e:
        return False, str(e)

def evaluate_sql(conn, user_sql, correct_sql):
    # Clean up the SQL query
    user_sql = user_sql.strip()
    
    # Remove surrounding quotes if present
    if (user_sql.startswith('"') and user_sql.endswith('"')) or \
       (user_sql.startswith('\'') and user_sql.endswith('\'')):
        user_sql = user_sql[1:-1]
    
    # Replace backticks with standard quotes
    user_sql = user_sql.replace('`', '"')
    
    # Remove any markdown code block markers
    user_sql = user_sql.replace('```sql', '').replace('```', '')
    
    # First validate syntax
    is_valid, error_msg = validate_sql_syntax(user_sql)
    if not is_valid:
        return 'syntax_error', error_msg
    
    try:
        user_df = pd.read_sql_query(user_sql, conn)
    except pd.io.sql.DatabaseError as e:
        error_msg = str(e).lower()
        if 'no such table' in error_msg:
            table = error_msg.split(':')[-1].strip()
            return 'syntax_error', f'🔍 Table "{table}" not found\n\nAvailable tables are:\n- products\n- suppliers\n- warehouses\n- shipments\n- inventory\n\nCheck the schema in the sidebar for details.'
        elif 'no such column' in error_msg:
            col = error_msg.split(':')[-1].strip()
            return 'syntax_error', f'🔍 Column "{col}" not found\n\nTip: Review the schema to see available columns for each table.\nMake sure you\'re using the correct table prefix for JOINs.'
        elif 'ambiguous' in error_msg:
            col = error_msg.split('ambiguous')[0].strip().split()[-1]
            return 'syntax_error', f'🔍 Column "{col}" is ambiguous\n\nTip: Specify which table this column comes from:\n- {col} → table_name.{col}'
        elif 'foreign key constraint failed' in error_msg:
            return 'syntax_error', '🔍 Foreign key constraint failed\n\nTip: Make sure referenced values exist in the parent table.'
        else:
            return 'syntax_error', f'SQL Error:\n{str(e)}\n\nTip: Double-check your query syntax and table/column names.'
            
    except Exception as e:
        error_msg = str(e).lower()
        if 'syntax error' in error_msg:
            return 'syntax_error', f'🔍 SQL Syntax Error:\n{str(e)}\n\nCommon fixes:\n1. Keywords: SELECT, FROM, WHERE, etc.\n2. Quotes around text values\n3. Proper JOIN syntax\n4. Balanced parentheses'
        return 'syntax_error', f'Error: {str(e)}\n\nTip: Review your query structure and try again.'
        
    try:
        correct_df = pd.read_sql_query(correct_sql, conn)
    except Exception as e:
        return 'error', f'Internal error: {e}'
        
    # Compare results
    if user_df.equals(correct_df):
        return 'correct', user_df
    else:
        # Check if the student's query returns at least some correct data
        try:
            common_cols = set(user_df.columns) & set(correct_df.columns)
            if common_cols:
                student_subset = user_df[list(common_cols)]
                correct_subset = correct_df[list(common_cols)]
                if not student_subset.empty and student_subset.isin(correct_subset.values).any().any():
                    return 'partial', user_df
            return 'incorrect', user_df
        except:
            return 'incorrect', user_df
