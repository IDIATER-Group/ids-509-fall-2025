# evaluator.py
import pandas as pd
import numpy as np
import sqlparse
import re
import unicodedata
from collections import Counter

_ZERO_WIDTH = re.compile(r"[\u200B-\u200D\uFEFF]")

def _normalize_sql(sql: str) -> str:
    """Normalize unicode & whitespace; executor uses first stmt."""
    s = unicodedata.normalize("NFKC", sql or "")
    s = _ZERO_WIDTH.sub("", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _first_statement(sql: str) -> str:
    parts = [p.strip() for p in sqlparse.split(sql or "") if p and p.strip()]
    return parts[0] if parts else ""

def validate_sql_syntax(sql: str):
    try:
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False, "Empty query"
        return True, None
    except Exception as e:
        return False, f"Parse error: {e}"

def _canon_series(s: pd.Series) -> pd.Series:
    """Make a series comparable across dtypes and whitespace; round floats; coerce numeric-looking strings."""
    if pd.api.types.is_float_dtype(s):
        return s.round(6)
    if pd.api.types.is_numeric_dtype(s):
        return s
    # Strings/objects: trim, standardize None/NaN, and coerce numeric-looking
    s = s.astype(str).str.strip()
    s = s.replace({"None": np.nan, "nan": np.nan})
    s_num = pd.to_numeric(s, errors="ignore")  # "12" -> 12, "12.0" -> 12.0; others stay strings
    if pd.api.types.is_numeric_dtype(s_num):
        return s_num
    return s

def _canon_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DF for robust, order-insensitive comparison."""
    if df is None:
        return df
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        df[col] = _canon_series(df[col])
    # Sort columns alphabetically for label-based compare
    df = df.reindex(sorted(df.columns), axis=1)
    # Then sort rows by all columns
    if len(df.columns) > 0:
        try:
            df = df.sort_values(by=list(df.columns), kind="mergesort").reset_index(drop=True)
        except Exception:
            df = df.astype(str).sort_values(by=list(df.columns), kind="mergesort").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    return df

def _as_value_matrix(df: pd.DataFrame) -> np.ndarray:
    """Return a value-only matrix tolerant to dtype; floats rounded; strings trimmed."""
    if df is None:
        return None
    vals = []
    for col in df.columns:
        s = _canon_series(df[col])
        vals.append(s.to_numpy())
    if not vals:
        return np.empty((len(df), 0))
    mat = np.vstack(vals).T  # rows x cols
    return mat.astype(object)  # allow mixed types

def _same_shape(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    return a.shape == b.shape

def evaluate_sql(conn, user_sql: str, correct_sql: str):
    """
    Returns: ('correct'|'partial'|'incorrect'|'syntax_error'|'error', DataFrame|str)
    - 'correct': results match (order-insensitive, dtype/whitespace tolerant)
    - 'partial': overlapping rows/values exist on shared columns
    - 'incorrect': executed but doesn't match
    - 'syntax_error': SQL failed to parse/execute
    - 'error': internal error running reference query
    """
    # Normalize and take only first statement for both user and gold
    user_sql = _first_statement(_normalize_sql(user_sql))
    correct_sql = _first_statement(_normalize_sql(correct_sql))

    if not isinstance(user_sql, str) or not user_sql.strip():
        return 'syntax_error', 'Empty query'
    if not isinstance(correct_sql, str) or not correct_sql.strip():
        return 'error', 'Internal error: answer SQL missing'

    # Light syntax validation
    ok, err = validate_sql_syntax(user_sql)
    if not ok:
        return 'syntax_error', err

    # Execute both queries
    try:
        user_df = pd.read_sql_query(user_sql, conn)
    except Exception as e:
        # Clear any half-open transaction so the very next run is clean
        try:
            conn.rollback()
        except Exception:
            pass
        return 'syntax_error', f"SQL execution failed: {e}"

    try:
        gold_df = pd.read_sql_query(correct_sql, conn)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return 'error', f"Internal error running reference query: {e}"

    # Canonicalize for comparison
    u = _canon_df(user_df)
    g = _canon_df(gold_df)

    # 1) Exact equality (labels+values)
    if u.equals(g):
        return 'correct', user_df  # return original for display

    # 2) Value-only compare if shapes match (multiset to respect duplicates)
    if _same_shape(u, g):
        u_mat = _as_value_matrix(u)
        g_mat = _as_value_matrix(g)
        try:
            u_rows = Counter(tuple(row) for row in u_mat.tolist())
            g_rows = Counter(tuple(row) for row in g_mat.tolist())
            if u_rows == g_rows:
                return 'correct', user_df
        except Exception:
            pass  # fall through to partial/incorrect

    # 3) Partial credit: intersection on common columns
    common = [c for c in u.columns if c in g.columns]
    if common:
        u_sub = _canon_df(user_df[common])
        g_sub = _canon_df(gold_df[common])
        try:
            u_rows = Counter(tuple(row) for row in _as_value_matrix(u_sub).tolist())
            g_rows = Counter(tuple(row) for row in _as_value_matrix(g_sub).tolist())
            overlap = sum((u_rows & g_rows).values())
            if overlap > 0:
                return 'partial', user_df
        except Exception:
            # Fallback merge if hashing/comparison gets tricky
            try:
                merged = pd.merge(u_sub.drop_duplicates(), g_sub.drop_duplicates(), on=common, how="inner")
                if not merged.empty:
                    return 'partial', user_df
            except Exception:
                pass

    return 'incorrect', user_df
