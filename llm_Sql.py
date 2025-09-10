# llm_sql.py
import os
from typing import Optional
import re

# ----------- CONFIG -----------
MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
# Set to 0 for deterministic SQL (recommended for grading/autoscore)
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
# --------------------------------

SQL_SYSTEM = """You write safe, syntactically correct SQL for SQLite.
Return only the SQL query with no prose or commentary.
Do not include code fences.
If uncertain, return:
SELECT 'INSUFFICIENT_INFO';"""

_ONLY_SELECT_REGEX = re.compile(
    r"^\s*SELECT\b", flags=re.IGNORECASE | re.DOTALL
)

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # remove leading “sql” labels if present
    if text.lower().startswith("sql\n"):
        text = text[4:].lstrip()
    return text

def _enforce_select_only(sql: str) -> str:
    """
    Ensures we only return a SELECT for SQLite.
    Falls back to a sentinel when unsafe/unknown.
    """
    sql_clean = sql.strip().rstrip(";")
    if not _ONLY_SELECT_REGEX.match(sql_clean):
        return "SELECT 'INSUFFICIENT_INFO';"
    return sql_clean + ";"

def generate_sql(user_question: str, schema_markdown: str, system: Optional[str] = None) -> str:
    """
    Convert a natural-language question into a single SELECT statement.
    Returns only SQL; never prose.
    """
    import google.generativeai as genai

    # Configure Gemini (AI Studio)
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")
    genai.configure(api_key=api_key)

    # Build system + prompt
    sys_inst = system or SQL_SYSTEM
    prompt = f"""User question:
{user_question}

Database schema (SQLite):
{schema_markdown}

Rules:
- Output exactly one SQL query.
- Use only a SELECT statement.
- Do not include comments or explanations.
- Do not use code fences.
- If insufficient info: SELECT 'INSUFFICIENT_INFO';"""

    model = genai.GenerativeModel(model_name=MODEL, system_instruction=sys_inst)
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": TEMPERATURE}
    )

    sql = (resp.text or "").strip()
    sql = _strip_code_fences(sql)
    sql = _enforce_select_only(sql)
    return sql
