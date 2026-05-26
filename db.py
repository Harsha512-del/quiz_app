import mysql.connector
from mysql.connector import Error
import streamlit as st


def get_connection():
    try:
        conn = mysql.connector.connect(
            host=st.secrets["db"]["host"],        # key = "host"
            port=st.secrets["db"]["port"],        # key = "port"
            database=st.secrets["db"]["database"],# key = "database"
            user=st.secrets["db"]["user"],        # key = "user"
            password=st.secrets["db"]["password"],# key = "password"
            autocommit=False,
            connection_timeout=10,
        )
        return conn
    except Error as e:
        st.error(f"Database connection failed: {e}")
        st.stop()
def ensure_connected(conn):
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
    except Error:
        pass
    return conn


def execute_query(conn, query, params=()):
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


def init_schema(conn):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            username    VARCHAR(80)  NOT NULL UNIQUE,
            password    VARCHAR(255) NOT NULL,
            role        ENUM('user', 'admin') NOT NULL DEFAULT 'user',
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
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


def get_categories(conn):
    rows = fetch_all(conn, "SELECT DISTINCT category FROM questions ORDER BY category")
    return [r["category"] for r in rows]


def get_difficulties(conn):
    return ["easy", "medium", "hard"]


def close_connection(conn):
    try:
        if conn.is_connected():
            conn.close()
    except Error:
        pass