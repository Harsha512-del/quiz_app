import streamlit as st
from db import fetch_all, fetch_one
from auth import require_login, current_user


# ── Constants ─────────────────────────────────────────────────────────────────
DIFFICULTIES  = ["easy", "medium", "hard"]
TOP_N         = 20   # max rows shown in the leaderboard table


# ── Data helpers ──────────────────────────────────────────────────────────────
def get_leaderboard(conn, category=None, difficulty=None, limit=TOP_N):
    """
    Returns ranked scores.
    Filters by category and/or difficulty when provided.
    Each row: username, score, total, category, difficulty, time_taken, taken_at.
    """
    base = """
        SELECT  u.username,
                s.score,
                s.total,
                s.category,
                s.difficulty,
                s.time_taken,
                s.taken_at
        FROM    scores  s
        JOIN    users   u ON s.user_id = u.id
    """
    where  = []
    params = []

    if category:
        where.append("s.category = %s")
        params.append(category)
    if difficulty:
        where.append("s.difficulty = %s")
        params.append(difficulty)

    if where:
        base += " WHERE " + " AND ".join(where)

    base += " ORDER BY s.score DESC, s.time_taken ASC LIMIT %s"
    params.append(limit)

    return fetch_all(conn, base, tuple(params))


def get_user_rank(conn, user_id, category=None, difficulty=None):
    """
    Returns the rank (1-based) of the current user's best score,
    optionally scoped to a category and difficulty.
    Returns None if the user has no scores in the given scope.
    """
    base = """
        SELECT  user_id,
                MAX(score) AS best,
                MIN(time_taken) AS fastest
        FROM    scores
    """
    where  = []
    params = []

    if category:
        where.append("category = %s")
        params.append(category)
    if difficulty:
        where.append("difficulty = %s")
        params.append(difficulty)

    if where:
        base += " WHERE " + " AND ".join(where)

    base += " GROUP BY user_id ORDER BY best DESC, fastest ASC"

    rows = fetch_all(conn, base, tuple(params))
    for rank, row in enumerate(rows, start=1):
        if row["user_id"] == user_id:
            return rank
    return None


def get_categories(conn):
    """Returns sorted list of distinct categories that have scores."""
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT s.category
        FROM   scores s
        ORDER  BY s.category
        """,
    )
    return [r["category"] for r in rows]


def get_user_stats(conn, user_id):
    """
    Returns aggregate stats for the current user:
    total attempts, best score, average score, fastest time.
    """
    return fetch_one(
        conn,
        """
        SELECT  COUNT(*)          AS attempts,
                MAX(score)        AS best,
                ROUND(AVG(score), 1) AS avg_score,
                MIN(time_taken)   AS fastest
        FROM    scores
        WHERE   user_id = %s
        """,
        (user_id,),
    )


# ── Rendering helpers ─────────────────────────────────────────────────────────
def _medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")


def _pct(score, total) -> str:
    if not total:
        return "—"
    return f"{round((score / total) * 100)}%"


def _fmt_time(seconds) -> str:
    if seconds is None:
        return "—"
    return f"{round(float(seconds))}s"


def _render_table(rows, highlight_username=None):
    """
    Renders the leaderboard as a styled Streamlit table.
    Highlights the current user's row if their username appears.
    """
    if not rows:
        st.info("No scores yet for this selection.")
        return

    # Header row
    cols = st.columns([1, 3, 2, 2, 2, 2, 3])
    for col, label in zip(
        cols, ["Rank", "Player", "Score", "%", "Time", "Difficulty", "Date"]
    ):
        col.markdown(f"**{label}**")

    st.divider()

    for rank, row in enumerate(rows, start=1):
        is_me = (
            highlight_username
            and row["username"] == highlight_username
        )
        cols = st.columns([1, 3, 2, 2, 2, 2, 3])

        name_display = f"**{row['username']}** ← you" if is_me else row["username"]

        cols[0].write(_medal(rank))
        cols[1].markdown(name_display)
        cols[2].write(f"{row['score']} / {row['total']}")
        cols[3].write(_pct(row["score"], row["total"]))
        cols[4].write(_fmt_time(row["time_taken"]))
        cols[5].write(row["difficulty"].capitalize())
        cols[6].write(
            row["taken_at"].strftime("%d %b %Y %H:%M")
            if row["taken_at"] else "—"
        )


# ── Main leaderboard page ─────────────────────────────────────────────────────
def leaderboard_page(conn):
    """
    Full leaderboard page called by app.py.
    Shows personal stats, filter controls, and the ranked table.
    """
    require_login()

    user     = current_user()
    username = user["username"]
    user_id  = user["id"]

    st.title("Leaderboard")

    # ── Personal stats banner ─────────────────────────────────────────────────
    stats = get_user_stats(conn, user_id)
    if stats and stats["attempts"]:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Your attempts",  stats["attempts"])
        c2.metric("Your best",      stats["best"])
        c3.metric("Your average",   stats["avg_score"])
        c4.metric("Fastest time",   _fmt_time(stats["fastest"]))
    else:
        st.info("You haven't completed any quizzes yet. Take one to appear here!")

    st.divider()

    # ── Filter controls ───────────────────────────────────────────────────────
    st.subheader("Rankings")

    categories   = get_categories(conn)
    cat_options  = ["All categories"]  + categories
    diff_options = ["All difficulties"] + DIFFICULTIES

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_cat  = st.selectbox("Category",   cat_options,  key="lb_cat")
    with filter_col2:
        selected_diff = st.selectbox("Difficulty", diff_options, key="lb_diff")

    cat_filter  = None if selected_cat  == "All categories"  else selected_cat
    diff_filter = None if selected_diff == "All difficulties" else selected_diff

    # ── Fetch and render ──────────────────────────────────────────────────────
    rows = get_leaderboard(conn, cat_filter, diff_filter)

    # Show the current user's rank in the filtered scope
    my_rank = get_user_rank(conn, user_id, cat_filter, diff_filter)
    if my_rank:
        st.caption(f"Your rank in this view: **{_medal(my_rank)}**")
    else:
        st.caption("You don't have a score in this category/difficulty yet.")

    st.markdown(f"Showing top {TOP_N} scores")
    _render_table(rows, highlight_username=username)