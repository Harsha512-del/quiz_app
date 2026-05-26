import streamlit as st
from db import get_connection, fetch_one, fetch_all
from auth import login_page, register_page, logout
from quiz import quiz_page
from leaderboard import leaderboard_page
from admin import admin_page


# ── Helper functions for home stats ──────────────────────────────────────────
def _get_best_score(conn, user_id):
    row = fetch_one(
        conn,
        "SELECT MAX(score) AS best FROM scores WHERE user_id = %s",
        (user_id,),
    )
    return row["best"] if row and row["best"] is not None else 0


def _get_quiz_count(conn, user_id):
    row = fetch_one(
        conn,
        "SELECT COUNT(*) AS total FROM scores WHERE user_id = %s",
        (user_id,),
    )
    return row["total"] if row else 0


def _get_rank(conn, user_id):
    rows = fetch_all(
        conn,
        """
        SELECT user_id,
               RANK() OVER (ORDER BY MAX(score) DESC) AS rnk
        FROM scores
        GROUP BY user_id
        """,
    )
    for row in rows:
        if row["user_id"] == user_id:
            return f"#{row['rnk']}"
    return "N/A"


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quiz App",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── DB connection (cached so it's reused across reruns) ───────────────────────
@st.cache_resource
def init_connection():
    return get_connection()

conn = init_connection()

# ── Session state defaults ────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state["user"] = None

if "page" not in st.session_state:
    st.session_state["page"] = "login"

# ── Auth gate ─────────────────────────────────────────────────────────────────
if st.session_state["user"] is None:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login", use_container_width=True):
            st.session_state["page"] = "login"
    with col2:
        if st.button("Register", use_container_width=True):
            st.session_state["page"] = "register"

    st.divider()

    if st.session_state["page"] == "register":
        register_page(conn)
    else:
        login_page(conn)

    st.stop()  # Nothing below renders until logged in

# ── Sidebar navigation (authenticated users only) ─────────────────────────────
with st.sidebar:
    user = st.session_state["user"]

    st.markdown(f"### Hi, {user['username']} 👋")
    st.caption(f"Role: {user['role'].capitalize()}")
    st.divider()

    nav_options = ["Home", "Take Quiz", "Leaderboard"]
    if user["role"] == "admin":
        nav_options.append("Admin Panel")

    selected_page = st.radio(
        "Navigate",
        nav_options,
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("Logout", use_container_width=True):
        logout()

# ── Page dispatch ─────────────────────────────────────────────────────────────
if selected_page == "Home":
    st.title("Welcome to Quiz App")
    st.markdown(
        """
        Test your knowledge across multiple categories and difficulty levels.

        **What you can do:**
        - Take timed quizzes by category and difficulty
        - Track your scores over time
        - Compete on the leaderboard
        """
    )

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Your best score", _get_best_score(conn, user["id"]))
    with col2:
        st.metric("Quizzes taken", _get_quiz_count(conn, user["id"]))
    with col3:
        st.metric("Leaderboard rank", _get_rank(conn, user["id"]))

elif selected_page == "Take Quiz":
    quiz_page(conn)

elif selected_page == "Leaderboard":
    leaderboard_page(conn)

elif selected_page == "Admin Panel":
    admin_page(conn)