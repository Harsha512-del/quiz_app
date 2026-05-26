import streamlit as st
from db import fetch_all, fetch_one, execute_query
from auth import require_admin


# ── Question CRUD ─────────────────────────────────────────────────────────────
def get_all_questions(conn, category=None, difficulty=None):
    """
    Returns all questions, optionally filtered by category and/or difficulty.
    """
    base  = "SELECT * FROM questions"
    where = []
    params = []

    if category:
        where.append("category = %s")
        params.append(category)
    if difficulty:
        where.append("difficulty = %s")
        params.append(difficulty)

    if where:
        base += " WHERE " + " AND ".join(where)

    base += " ORDER BY category, difficulty, id"
    return fetch_all(conn, base, tuple(params))


def add_question(conn, text, option_a, option_b, option_c, option_d,
                 correct, category, difficulty):
    """
    Inserts a new question row.
    Returns the new question's id on success, None on failure.
    """
    return execute_query(
        conn,
        """
        INSERT INTO questions
            (text, option_a, option_b, option_c, option_d,
             correct, category, difficulty)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (text.strip(), option_a.strip(), option_b.strip(),
         option_c.strip(), option_d.strip(),
         correct, category.strip(), difficulty),
    )


def update_question(conn, qid, text, option_a, option_b, option_c, option_d,
                    correct, category, difficulty):
    """Updates every field of an existing question row."""
    execute_query(
        conn,
        """
        UPDATE questions
        SET text      = %s,
            option_a  = %s,
            option_b  = %s,
            option_c  = %s,
            option_d  = %s,
            correct   = %s,
            category  = %s,
            difficulty = %s
        WHERE id = %s
        """,
        (text.strip(), option_a.strip(), option_b.strip(),
         option_c.strip(), option_d.strip(),
         correct, category.strip(), difficulty, qid),
    )


def delete_question(conn, qid):
    """Permanently removes a question by id."""
    execute_query(
        conn,
        "DELETE FROM questions WHERE id = %s",
        (qid,),
    )


# ── Admin stats helpers ───────────────────────────────────────────────────────
def get_stats(conn):
    """Returns aggregate counts used in the dashboard header."""
    total_q   = fetch_one(conn, "SELECT COUNT(*) AS n FROM questions")
    total_u   = fetch_one(conn, "SELECT COUNT(*) AS n FROM users WHERE role='user'")
    total_s   = fetch_one(conn, "SELECT COUNT(*) AS n FROM scores")
    avg_score = fetch_one(conn, "SELECT ROUND(AVG(score),1) AS avg FROM scores")
    return {
        "questions": total_q["n"]   if total_q   else 0,
        "users":     total_u["n"]   if total_u   else 0,
        "attempts":  total_s["n"]   if total_s   else 0,
        "avg_score": avg_score["avg"] if avg_score and avg_score["avg"] else 0,
    }


# ── UI helpers ────────────────────────────────────────────────────────────────
DIFFICULTIES = ["easy", "medium", "hard"]
CORRECT_OPTIONS = ["A", "B", "C", "D"]


def _question_form(prefix: str, defaults: dict = None):
    """
    Renders a shared question form and returns the field values.
    `prefix` namespaces the widget keys so add and edit forms don't clash.
    `defaults` pre-fills the form for editing.
    """
    d = defaults or {}

    text = st.text_area(
        "Question text",
        value=d.get("text", ""),
        key=f"{prefix}_text",
        height=100,
    )

    col1, col2 = st.columns(2)
    with col1:
        option_a = st.text_input("Option A", value=d.get("option_a", ""), key=f"{prefix}_a")
        option_c = st.text_input("Option C", value=d.get("option_c", ""), key=f"{prefix}_c")
    with col2:
        option_b = st.text_input("Option B", value=d.get("option_b", ""), key=f"{prefix}_b")
        option_d = st.text_input("Option D", value=d.get("option_d", ""), key=f"{prefix}_d")

    col3, col4, col5 = st.columns(3)
    with col3:
        correct = st.selectbox(
            "Correct answer",
            CORRECT_OPTIONS,
            index=CORRECT_OPTIONS.index(d["correct"]) if d.get("correct") else 0,
            key=f"{prefix}_correct",
        )
    with col4:
        category = st.text_input(
            "Category",
            value=d.get("category", ""),
            key=f"{prefix}_category",
            placeholder="e.g. Science",
        )
    with col5:
        difficulty = st.selectbox(
            "Difficulty",
            DIFFICULTIES,
            index=DIFFICULTIES.index(d["difficulty"]) if d.get("difficulty") else 0,
            key=f"{prefix}_difficulty",
        )

    return text, option_a, option_b, option_c, option_d, correct, category, difficulty


def _validate_form(text, option_a, option_b, option_c, option_d, category):
    """Returns a list of validation error strings (empty list = valid)."""
    errors = []
    if not text.strip():
        errors.append("Question text is required.")
    if not option_a.strip() or not option_b.strip() \
            or not option_c.strip() or not option_d.strip():
        errors.append("All four answer options are required.")
    if not category.strip():
        errors.append("Category is required.")
    return errors


# ── Main admin page ───────────────────────────────────────────────────────────
def admin_page(conn):
    """
    Full admin panel: dashboard stats, add question form,
    and an editable/deletable question list with optional filters.
    """
    require_admin()   # double-check role regardless of nav guards

    st.title("Admin panel")

    # ── Dashboard stats ───────────────────────────────────────────────────────
    stats = get_stats(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questions",   stats["questions"])
    c2.metric("Users",       stats["users"])
    c3.metric("Quiz attempts", stats["attempts"])
    c4.metric("Avg score",   stats["avg_score"])

    st.divider()

    # ── Add question ──────────────────────────────────────────────────────────
    with st.expander("Add new question", expanded=False):
        text, opt_a, opt_b, opt_c, opt_d, correct, category, difficulty = \
            _question_form("add")

        if st.button("Save question", key="btn_add"):
            errors = _validate_form(text, opt_a, opt_b, opt_c, opt_d, category)
            if errors:
                for err in errors:
                    st.error(err)
            else:
                new_id = add_question(
                    conn, text, opt_a, opt_b, opt_c, opt_d,
                    correct, category, difficulty,
                )
                if new_id:
                    st.success(f"Question #{new_id} added successfully.")
                    st.rerun()

    st.divider()

    # ── Filter bar ────────────────────────────────────────────────────────────
    st.subheader("Question bank")

    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
    with filter_col1:
        # Build category list dynamically from DB
        all_cats = sorted({
            r["category"]
            for r in fetch_all(conn, "SELECT DISTINCT category FROM questions")
        })
        cat_options = ["All categories"] + all_cats
        selected_cat = st.selectbox("Filter by category", cat_options, key="filter_cat")

    with filter_col2:
        diff_options = ["All difficulties"] + DIFFICULTIES
        selected_diff = st.selectbox("Filter by difficulty", diff_options, key="filter_diff")

    with filter_col3:
        search = st.text_input("Search text", placeholder="keyword…", key="filter_search")

    # Resolve filter values
    cat_filter  = None if selected_cat  == "All categories"  else selected_cat
    diff_filter = None if selected_diff == "All difficulties" else selected_diff

    questions = get_all_questions(conn, cat_filter, diff_filter)

    # Client-side keyword filter
    if search.strip():
        kw = search.strip().lower()
        questions = [
            q for q in questions
            if kw in q["text"].lower()
            or kw in q["category"].lower()
        ]

    st.caption(f"{len(questions)} question(s) found")

    if not questions:
        st.info("No questions match the current filters.")
        return

    # ── Question list with inline edit / delete ───────────────────────────────
    for q in questions:
        with st.expander(
            f"[{q['difficulty'].upper()}] [{q['category']}]  {q['text'][:80]}{'…' if len(q['text']) > 80 else ''}",
            expanded=False,
        ):
            tab_view, tab_edit, tab_delete = st.tabs(["View", "Edit", "Delete"])

            # ── View tab ──────────────────────────────────────────────────────
            with tab_view:
                st.markdown(f"**Question:** {q['text']}")
                st.markdown(
                    f"- **A:** {q['option_a']}\n"
                    f"- **B:** {q['option_b']}\n"
                    f"- **C:** {q['option_c']}\n"
                    f"- **D:** {q['option_d']}\n"
                )
                st.success(f"Correct answer: **{q['correct']}**")
                st.caption(
                    f"ID: {q['id']}  |  "
                    f"Category: {q['category']}  |  "
                    f"Difficulty: {q['difficulty']}  |  "
                    f"Added: {q['created_at']}"
                )

            # ── Edit tab ──────────────────────────────────────────────────────
            with tab_edit:
                text, opt_a, opt_b, opt_c, opt_d, correct, category, difficulty = \
                    _question_form(f"edit_{q['id']}", defaults=q)

                if st.button("Update question", key=f"btn_update_{q['id']}"):
                    errors = _validate_form(text, opt_a, opt_b, opt_c, opt_d, category)
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        update_question(
                            conn, q["id"],
                            text, opt_a, opt_b, opt_c, opt_d,
                            correct, category, difficulty,
                        )
                        st.success("Question updated.")
                        st.rerun()

            # ── Delete tab ────────────────────────────────────────────────────
            with tab_delete:
                st.warning(
                    "This will permanently delete the question and cannot be undone."
                )
                st.markdown(f"> {q['text']}")

                # Two-step confirmation: checkbox then button
                confirmed = st.checkbox(
                    "I understand this is permanent",
                    key=f"confirm_del_{q['id']}",
                )
                if confirmed:
                    if st.button(
                        "Delete question",
                        key=f"btn_del_{q['id']}",
                        type="primary",
                    ):
                        delete_question(conn, q["id"])
                        st.success("Question deleted.")
                        st.rerun()