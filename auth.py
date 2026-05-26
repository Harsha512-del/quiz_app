import streamlit as st
import bcrypt
from db import fetch_one, execute_query


# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(plain: str) -> bytes:
    """Returns a bcrypt hash of the plain-text password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())


def verify_password(plain: str, hashed: bytes) -> bool:
    """Returns True if plain matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed)
    except Exception:
        return False


# ── Registration ──────────────────────────────────────────────────────────────
def register_user(conn, username: str, password: str) -> bool:
    """
    Inserts a new user with role='user'.
    Returns True on success, False if the username is already taken.
    """
    existing = fetch_one(
        conn,
        "SELECT id FROM users WHERE username = %s",
        (username,),
    )
    if existing:
        return False  # username already taken

    hashed = hash_password(password)
    execute_query(
        conn,
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        (username, hashed, "user"),
    )
    return True


def register_page(conn):
    """
    Streamlit UI for new user registration.
    On success sets session_state and reruns into the main app.
    """
    st.title("Create an account")

    username = st.text_input("Username", max_chars=80, key="reg_username")
    password = st.text_input("Password", type="password", key="reg_password")
    confirm  = st.text_input("Confirm password", type="password", key="reg_confirm")

    if st.button("Register", use_container_width=True):
        # ── Validation ────────────────────────────────────────────────────────
        if not username or not password:
            st.warning("Username and password are required.")
            return

        if len(username) < 3:
            st.warning("Username must be at least 3 characters.")
            return

        if len(password) < 6:
            st.warning("Password must be at least 6 characters.")
            return

        if password != confirm:
            st.error("Passwords do not match.")
            return

        # ── Attempt registration ──────────────────────────────────────────────
        success = register_user(conn, username.strip(), password)

        if not success:
            st.error("That username is already taken. Please choose another.")
            return

        # Auto-login after successful registration
        user = fetch_one(
            conn,
            "SELECT id, username, role FROM users WHERE username = %s",
            (username.strip(),),
        )
        st.session_state["user"] = user
        st.success("Account created! Redirecting...")
        st.rerun()


# ── Login ─────────────────────────────────────────────────────────────────────
def authenticate(conn, username: str, password: str):
    """
    Looks up the user by username and verifies the password.
    Returns the user dict (id, username, role) on success, or None on failure.
    """
    row = fetch_one(
        conn,
        "SELECT id, username, password, role FROM users WHERE username = %s",
        (username.strip(),),
    )
    if not row:
        return None

    stored_hash = row["password"]

    # mysql-connector returns BLOB columns as bytes; VARCHAR may come as str.
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode("utf-8")

    if not verify_password(password, stored_hash):
        return None

    # Return only safe fields — never expose the password hash
    return {
        "id":       row["id"],
        "username": row["username"],
        "role":     row["role"],
    }


def login_page(conn):
    """
    Streamlit UI for user login.
    On success sets session_state['user'] and reruns into the main app.
    """
    st.title("Sign in")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    # Track failed attempts in session state to throttle brute-force
    if "login_attempts" not in st.session_state:
        st.session_state["login_attempts"] = 0

    if st.button("Login", use_container_width=True):
        if not username or not password:
            st.warning("Please enter both username and password.")
            return

        if st.session_state["login_attempts"] >= 5:
            st.error("Too many failed attempts. Please restart the app.")
            return

        user = authenticate(conn, username, password)

        if user is None:
            st.session_state["login_attempts"] += 1
            remaining = 5 - st.session_state["login_attempts"]
            st.error(
                f"Invalid username or password. "
                f"{remaining} attempt(s) remaining."
            )
            return

        # Success — store user and reset attempt counter
        st.session_state["user"] = user
        st.session_state["login_attempts"] = 0
        st.rerun()


# ── Logout ────────────────────────────────────────────────────────────────────
def logout():
    """
    Clears all session state and reruns back to the login screen.
    Wipes quiz progress, timer state, and user identity in one call.
    """
    st.session_state.clear()
    st.rerun()


# ── Role checks (used by other modules) ───────────────────────────────────────
def current_user() -> dict | None:
    """Returns the logged-in user dict from session_state, or None."""
    return st.session_state.get("user")


def is_admin() -> bool:
    """Returns True if the current user has the admin role."""
    user = current_user()
    return user is not None and user.get("role") == "admin"


def require_login():
    """
    Call at the top of any page function that needs authentication.
    Stops rendering and shows a warning if no user is in session.
    """
    if current_user() is None:
        st.warning("Please log in to access this page.")
        st.stop()


def require_admin():
    """
    Call at the top of any page function that needs admin privileges.
    Stops rendering with an error if the user is not an admin.
    """
    require_login()
    if not is_admin():
        st.error("Access denied. Admin privileges required.")
        st.stop()