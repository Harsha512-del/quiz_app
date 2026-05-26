import time
import streamlit as st


# ── Start timer ───────────────────────────────────────────────────────────────
def start_timer(seconds: int):
    """
    Records the start time and limit in session_state.
    Safe to call on every Streamlit rerun — only sets the keys
    if they don't already exist, so the clock isn't reset mid-question.
    """
    if "timer_start" not in st.session_state:
        st.session_state["timer_start"] = time.time()
    if "timer_limit" not in st.session_state:
        st.session_state["timer_limit"] = seconds


# ── Check expiry ──────────────────────────────────────────────────────────────
def is_expired() -> bool:
    """
    Returns True if the elapsed time has reached or exceeded the limit.
    Returns False if the timer hasn't been started yet.
    """
    if "timer_start" not in st.session_state:
        return False
    elapsed = time.time() - st.session_state["timer_start"]
    return elapsed >= st.session_state.get("timer_limit", 0)


# ── Get remaining seconds ─────────────────────────────────────────────────────
def remaining_seconds() -> int:
    """
    Returns how many whole seconds are left on the timer.
    Returns 0 if the timer has expired or hasn't been started.
    """
    if "timer_start" not in st.session_state:
        return 0
    limit   = st.session_state.get("timer_limit", 0)
    elapsed = time.time() - st.session_state["timer_start"]
    return max(0, int(limit - elapsed))


# ── Display countdown ─────────────────────────────────────────────────────────
def show_timer() -> int:
    """
    Renders a countdown bar and metric in the Streamlit UI.
    Returns the remaining seconds so the caller can act on it.

    Visual behaviour:
      - Green bar when > 50% time remains
      - Orange metric label when <= 10s remain
      - Red metric label when <= 5s remain
    """
    limit     = st.session_state.get("timer_limit", 0)
    remaining = remaining_seconds()

    # Progress bar (value must be 0.0 – 1.0)
    progress_value = remaining / limit if limit > 0 else 0.0

    # Colour-coded urgency label
    if remaining <= 5:
        label = f"⛔ {remaining}s left"
    elif remaining <= 10:
        label = f"⚠️ {remaining}s left"
    else:
        label = f"⏱ {remaining}s left"

    col_bar, col_metric = st.columns([4, 1])
    with col_bar:
        st.progress(progress_value)
    with col_metric:
        st.metric(label="Time", value=f"{remaining}s", label_visibility="collapsed")

    # Force a rerun every second so the countdown ticks live
    # Only do this while there is still time remaining
    if remaining > 0:
        time.sleep(1)
        st.rerun()

    return remaining


# ── Reset timer ───────────────────────────────────────────────────────────────
def reset_timer():
    """
    Clears the timer keys from session_state.
    Call this after every question submission, skip, or auto-submit
    so the next question starts with a fresh clock.
    """
    st.session_state.pop("timer_start", None)
    st.session_state.pop("timer_limit", None)


# ── Elapsed time ──────────────────────────────────────────────────────────────
def elapsed_seconds() -> float:
    """
    Returns total seconds elapsed since the timer was started.
    Useful for recording how long a user took on a question.
    Returns 0.0 if the timer was never started.
    """
    if "timer_start" not in st.session_state:
        return 0.0
    return time.time() - st.session_state["timer_start"]