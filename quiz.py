import streamlit as st
from db import fetch_all, fetch_one, execute_query
from auth import require_login, current_user
from utils.timer import start_timer, is_expired, show_timer, reset_timer


# ── Constants ─────────────────────────────────────────────────────────────────
QUESTIONS_PER_QUIZ = 10
SECONDS_PER_QUESTION = 30
OPTION_LABELS = ["A", "B", "C", "D"]


# ── Question fetching ─────────────────────────────────────────────────────────
def get_questions(conn, category, difficulty, n=QUESTIONS_PER_QUIZ):
    """
    Fetches n random questions for the given category and difficulty.
    ORDER BY RAND() ensures a different set each quiz attempt.
    """
    return fetch_all(
        conn,
        """
        SELECT id, text, option_a, option_b, option_c, option_d, correct
        FROM   questions
        WHERE  category   = %s
          AND  difficulty = %s
        ORDER  BY RAND()
        LIMIT  %s
        """,
        (category, difficulty, n),
    )


def get_categories(conn):
    """Returns sorted list of distinct categories in the question bank."""
    rows = fetch_all(conn, "SELECT DISTINCT category FROM questions ORDER BY category")
    return [r["category"] for r in rows]


def get_difficulties():
    return ["easy", "medium", "hard"]


# ── Score persistence ─────────────────────────────────────────────────────────
def save_score(conn, user_id, score, total, category, difficulty, time_taken):
    """Writes the quiz result to the scores table."""
    execute_query(
        conn,
        """
        INSERT INTO scores
            (user_id, score, total, category, difficulty, time_taken, taken_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
        (user_id, score, total, category, difficulty, round(time_taken, 2)),
    )


def get_user_history(conn, user_id, limit=10):
    """Returns the most recent quiz attempts for a user."""
    return fetch_all(
        conn,
        """
        SELECT score, total, category, difficulty, time_taken, taken_at
        FROM   scores
        WHERE  user_id = %s
        ORDER  BY taken_at DESC
        LIMIT  %s
        """,
        (user_id, limit),
    )


# ── Session state helpers ─────────────────────────────────────────────────────
def _init_quiz_state(questions, category, difficulty):
    """Initialises all quiz-related keys in session_state."""
    st.session_state["quiz_questions"]   = questions
    st.session_state["quiz_index"]       = 0
    st.session_state["quiz_score"]       = 0
    st.session_state["quiz_answers"]     = {}   # {index: chosen_option}
    st.session_state["quiz_category"]    = category
    st.session_state["quiz_difficulty"]  = difficulty
    st.session_state["quiz_active"]      = True
    st.session_state["quiz_start_time"]  = _now()
    st.session_state["quiz_done"]        = False
    reset_timer()


def _clear_quiz_state():
    """Removes all quiz keys so the setup screen shows again."""
    for key in [
        "quiz_questions", "quiz_index", "quiz_score", "quiz_answers",
        "quiz_category", "quiz_difficulty", "quiz_active",
        "quiz_start_time", "quiz_done",
    ]:
        st.session_state.pop(key, None)
    reset_timer()


def _now():
    import time
    return time.time()


def _elapsed():
    import time
    return time.time() - st.session_state.get("quiz_start_time", _now())


# ── Setup screen ──────────────────────────────────────────────────────────────
def _setup_screen(conn):
    """
    Shows category/difficulty selectors and a Start button.
    Validates that enough questions exist before starting.
    """
    st.header("Start a quiz")

    categories = get_categories(conn)
    if not categories:
        st.warning("No questions in the database yet. Ask an admin to add some.")
        return

    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox("Category", categories, key="setup_category")
    with col2:
        difficulty = st.selectbox(
            "Difficulty", get_difficulties(), key="setup_difficulty"
        )

    # Show question count available for this combination
    row = fetch_one(
        conn,
        "SELECT COUNT(*) AS n FROM questions WHERE category=%s AND difficulty=%s",
        (category, difficulty),
    )
    available = row["n"] if row else 0
    st.caption(f"{available} question(s) available for this selection.")

    if available < QUESTIONS_PER_QUIZ:
        st.info(
            f"Need at least {QUESTIONS_PER_QUIZ} questions to start. "
            f"Only {available} available — choose a different combination or ask an admin to add more."
        )
        return

    st.markdown(
        f"**{QUESTIONS_PER_QUIZ} questions · {SECONDS_PER_QUESTION}s per question · "
        f"{category} · {difficulty.capitalize()}**"
    )

    if st.button("Start quiz", use_container_width=True, type="primary"):
        questions = get_questions(conn, category, difficulty)
        _init_quiz_state(questions, category, difficulty)
        st.rerun()


# ── Question screen ───────────────────────────────────────────────────────────
def _question_screen(conn):
    """
    Renders the current question, starts the per-question timer,
    handles answer submission and auto-submit on expiry.
    """
    questions  = st.session_state["quiz_questions"]
    idx        = st.session_state["quiz_index"]
    q          = questions[idx]
    total      = len(questions)

    # ── Progress ──────────────────────────────────────────────────────────────
    st.progress((idx) / total, text=f"Question {idx + 1} of {total}")

    # ── Timer ─────────────────────────────────────────────────────────────────
    start_timer(SECONDS_PER_QUESTION)
    remaining = show_timer()

    # ── Question text ─────────────────────────────────────────────────────────
    st.subheader(f"Q{idx + 1}. {q['text']}")

    options = {
        "A": q["option_a"],
        "B": q["option_b"],
        "C": q["option_c"],
        "D": q["option_d"],
    }

    option_display = [f"{k}: {v}" for k, v in options.items()]

    # ── Answer selection ──────────────────────────────────────────────────────
    # Disable radio if already answered this question
    already_answered = idx in st.session_state["quiz_answers"]

    chosen_display = st.radio(
        "Choose your answer:",
        option_display,
        key=f"radio_{idx}",
        disabled=already_answered,
        index=None,
    )

    # ── Auto-submit on timer expiry ───────────────────────────────────────────
    if is_expired() and not already_answered:
        st.warning("Time's up! Moving to the next question.")
        _record_answer(idx, None, q["correct"])   # None = no answer = wrong
        reset_timer()
        _advance(conn, questions)
        st.rerun()
        return

    # ── Submit button ─────────────────────────────────────────────────────────
    submit_col, skip_col = st.columns([3, 1])
    with submit_col:
        submitted = st.button(
            "Submit answer",
            key=f"submit_{idx}",
            disabled=already_answered or chosen_display is None,
            use_container_width=True,
            type="primary",
        )
    with skip_col:
        skipped = st.button(
            "Skip",
            key=f"skip_{idx}",
            disabled=already_answered,
            use_container_width=True,
        )

    if submitted and chosen_display:
        chosen_letter = chosen_display[0]   # "A", "B", "C", or "D"
        _record_answer(idx, chosen_letter, q["correct"])
        reset_timer()
        _advance(conn, questions)
        st.rerun()

    if skipped:
        _record_answer(idx, None, q["correct"])
        reset_timer()
        _advance(conn, questions)
        st.rerun()

    # ── Live feedback if already answered (shouldn't normally show,
    #    but guards against edge-case double renders) ───────────────────────────
    if already_answered:
        chosen = st.session_state["quiz_answers"][idx]
        if chosen == q["correct"]:
            st.success(f"Correct! The answer is **{q['correct']}**.")
        else:
            st.error(
                f"Wrong. You chose **{chosen or 'nothing'}**. "
                f"Correct answer: **{q['correct']}**."
            )


def _record_answer(idx, chosen, correct):
    """
    Stores the chosen letter in quiz_answers and increments score if correct.
    """
    st.session_state["quiz_answers"][idx] = chosen
    if chosen is not None and chosen == correct:
        st.session_state["quiz_score"] += 1


def _advance(conn, questions):
    """
    Moves to the next question or triggers end-of-quiz save if all done.
    """
    next_idx = st.session_state["quiz_index"] + 1
    if next_idx >= len(questions):
        _finish_quiz(conn)
    else:
        st.session_state["quiz_index"] = next_idx


def _finish_quiz(conn):
    """Marks quiz as done and persists the result to the DB."""
    st.session_state["quiz_done"]   = True
    st.session_state["quiz_active"] = False
    user = current_user()
    save_score(
        conn,
        user_id    = user["id"],
        score      = st.session_state["quiz_score"],
        total      = len(st.session_state["quiz_questions"]),
        category   = st.session_state["quiz_category"],
        difficulty = st.session_state["quiz_difficulty"],
        time_taken = _elapsed(),
    )


# ── Results screen ────────────────────────────────────────────────────────────
def _results_screen(conn):
    """
    Shows the final score, per-question breakdown, and action buttons.
    """
    score     = st.session_state["quiz_score"]
    questions = st.session_state["quiz_questions"]
    answers   = st.session_state["quiz_answers"]
    total     = len(questions)
    pct       = round((score / total) * 100)

    st.header("Quiz complete!")

    # ── Score summary ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Score",       f"{score} / {total}")
    col2.metric("Percentage",  f"{pct}%")
    col3.metric("Time taken",  f"{round(_elapsed())}s")

    if pct == 100:
        st.success("Perfect score! Outstanding work.")
    elif pct >= 70:
        st.success("Great job! Well done.")
    elif pct >= 50:
        st.warning("Good effort. Keep practising!")
    else:
        st.error("Keep going — you'll improve with practice.")

    st.divider()

    # ── Per-question breakdown ────────────────────────────────────────────────
    st.subheader("Answer breakdown")
    for i, q in enumerate(questions):
        chosen  = answers.get(i)
        correct = q["correct"]
        icon    = "✓" if chosen == correct else "✗"
        label   = f"{icon}  Q{i+1}: {q['text'][:70]}{'…' if len(q['text']) > 70 else ''}"

        with st.expander(label, expanded=False):
            options = {
                "A": q["option_a"],
                "B": q["option_b"],
                "C": q["option_c"],
                "D": q["option_d"],
            }
            for letter, text in options.items():
                if letter == correct and letter == chosen:
                    st.success(f"**{letter}: {text}** ← your answer (correct)")
                elif letter == correct:
                    st.success(f"**{letter}: {text}** ← correct answer")
                elif letter == chosen:
                    st.error(f"**{letter}: {text}** ← your answer")
                else:
                    st.write(f"{letter}: {text}")

    st.divider()

    # ── Recent history ────────────────────────────────────────────────────────
    user = current_user()
    history = get_user_history(conn, user["id"], limit=5)
    if history:
        st.subheader("Your recent attempts")
        for h in history:
            pct_h = round((h["score"] / h["total"]) * 100)
            st.caption(
                f"{h['taken_at'].strftime('%d %b %Y %H:%M')}  ·  "
                f"{h['category']} / {h['difficulty']}  ·  "
                f"{h['score']}/{h['total']} ({pct_h}%)  ·  "
                f"{round(h['time_taken'])}s"
            )

    st.divider()

    # ── Action buttons ────────────────────────────────────────────────────────
    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("Play again", use_container_width=True, type="primary"):
            _clear_quiz_state()
            st.rerun()
    with btn2:
        if st.button("Back to home", use_container_width=True):
            _clear_quiz_state()
            st.session_state["page"] = "home"
            st.rerun()


# ── Main entry point ──────────────────────────────────────────────────────────
def quiz_page(conn):
    """
    Top-level page function called by app.py.
    Routes to setup → question loop → results based on session state.
    """
    require_login()

    quiz_active = st.session_state.get("quiz_active", False)
    quiz_done   = st.session_state.get("quiz_done",   False)

    if quiz_done:
        _results_screen(conn)
    elif quiz_active:
        _question_screen(conn)
    else:
        _setup_screen(conn)