import mysql.connector
from mysql.connector import Error
import streamlit as st


# ── Connection factory ────────────────────────────────────────────────────────
def get_connection():
    """
    Opens and returns a MySQL connection.
    Called once via @st.cache_resource in app.py so the connection
    is reused across Streamlit reruns rather than reopened every time.
    """
    try:
        conn = mysql.connector.connect(
            host=st.secrets["db"]["host"],
            port=st.secrets["db"]["port"],
            database=st.secrets["db"]["database"],
            user=st.secrets["db"]["user"],
            password=st.secrets["db"]["root@512"],
            autocommit=False,
            connection_timeout=10,
        )
        return conn
    except Error as e:
        st.error(f"Database connection failed: {e}")
        st.stop()


# ── Connection health check ───────────────────────────────────────────────────
def ensure_connected(conn):
    """
    Pings the server and reconnects if the connection has gone stale.
    Call this at the top of any function that uses the connection.
    """
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
    except Error:
        pass
    return conn


# ── Core query helpers ────────────────────────────────────────────────────────
def execute_query(conn, query, params=()):
    """
    Runs an INSERT / UPDATE / DELETE statement and commits.
    Returns the lastrowid so callers can get the new PK after an INSERT.
    """
    ensure_connected(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        conn.rollback()
        st.error(f"Query failed: {e}")
        return None
    finally:
        cursor.close()


def fetch_all(conn, query, params=()):
    """
    Runs a SELECT and returns all rows as a list of dicts.
    Returns an empty list on error so callers can safely iterate.
    """
    ensure_connected(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    except Error as e:
        st.error(f"Query failed: {e}")
        return []
    finally:
        cursor.close()


def fetch_one(conn, query, params=()):
    """
    Runs a SELECT and returns the first row as a dict, or None if not found.
    """
    ensure_connected(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    except Error as e:
        st.error(f"Query failed: {e}")
        return None
    finally:
        cursor.close()


# ── Schema initialisation ─────────────────────────────────────────────────────
def init_schema(conn):
    """
    Creates all tables if they don't already exist.
    Safe to call on every startup — uses IF NOT EXISTS throughout.
    """
    statements = [
        # Users
        """
        CREATE TABLE IF NOT EXISTS users (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            username    VARCHAR(80)  NOT NULL UNIQUE,
            password    VARCHAR(255) NOT NULL,
            role        ENUM('user', 'admin') NOT NULL DEFAULT 'user',
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Questions
        """
        CREATE TABLE IF NOT EXISTS questions (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            text        TEXT         NOT NULL,
            option_a    VARCHAR(255) NOT NULL,
            option_b    VARCHAR(255) NOT NULL,
            option_c    VARCHAR(255) NOT NULL,
            option_d    VARCHAR(255) NOT NULL,
            correct     ENUM('A','B','C','D') NOT NULL,
            category    VARCHAR(80)  NOT NULL,
            difficulty  ENUM('easy','medium','hard') NOT NULL,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # Scores
        """
        CREATE TABLE IF NOT EXISTS scores (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT          NOT NULL,
            score       INT          NOT NULL DEFAULT 0,
            total       INT          NOT NULL DEFAULT 10,
            category    VARCHAR(80),
            difficulty  ENUM('easy','medium','hard'),
            time_taken  FLOAT,
            taken_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
    ]

    ensure_connected(conn)
    cursor = conn.cursor()
    try:
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
    except Error as e:
        conn.rollback()
        st.error(f"Schema init failed: {e}")
    finally:
        cursor.close()


# ── Convenience: distinct category / difficulty lists ─────────────────────────
def get_categories(conn):
    """Returns a sorted list of distinct category strings from the questions table."""
    rows = fetch_all(conn, "SELECT DISTINCT category FROM questions ORDER BY category")
    return [r["category"] for r in rows]


def get_difficulties(conn):
    """Returns the three difficulty levels in logical order."""
    return ["easy", "medium", "hard"]


# ── Close connection (call on app shutdown if needed) ─────────────────────────
def close_connection(conn):
    try:
        if conn.is_connected():
            conn.close()
    except Error:
        pass