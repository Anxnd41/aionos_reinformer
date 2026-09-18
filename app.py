#!/usr/bin/env python3
"""
app.py — Streamlit UI for the Executive Productivity Agent.

Features:
  - Run the extraction pipeline (extract → dedupe → store).
  - Display the daily action brief for a configurable "today" date.
  - Q&A chat interface to ask questions about commitments.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import datetime
import streamlit as st

from src import brief, deduper, dates, extractor, loader, qa, store

# ---------------------------------------------------------------------------
# Streamlit page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Executive Productivity Agent",
    page_icon="📋",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ---------------------------------------------------------------------------
# Sidebar: Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Controls")

    # Date picker for "today"
    default_today = dates.parse_today(None)
    selected_date = st.date_input(
        "Today's Date",
        value=default_today,
        min_value=dates.WEEK_START,
        max_value=dates.WEEK_END,
        help="All overdue/upcoming logic uses this reference date.",
    )

    st.divider()

    # Pipeline controls
    st.subheader("Pipeline")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("▶️ Run Pipeline", use_container_width=True):
            with st.spinner("Running extraction pipeline..."):
                sources = list(loader.iter_sources())
                st.write(f"Loaded {len(sources)} sources.")

                all_commitments = extractor.extract_all(sources)
                st.write(f"Extracted {len(all_commitments)} raw commitments.")

                deduplicated = deduper.dedupe(all_commitments)
                st.write(f"Deduplicated to {len(deduplicated)} unique commitments.")

                store.save_commitments(deduplicated)
                st.success("✓ Pipeline complete. Commitments saved.")

    with col2:
        if st.button("🗑️ Clear Cache", use_container_width=True):
            store.clear_cache()
            st.success("Extraction cache cleared.")

    st.divider()

    # Session controls
    st.subheader("Session")
    if st.button("Clear Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main area: Tabs
# ---------------------------------------------------------------------------

tab_brief, tab_qa, tab_raw = st.tabs(["📋 Daily Brief", "💬 Q&A", "📊 Raw Data"])

# --- Tab 1: Daily Brief ---
with tab_brief:
    st.header(f"Daily Brief — {dates.iso_date(selected_date)}")

    commitments = store.load_commitments()
    if not commitments:
        st.warning(
            "No commitments loaded yet. "
            "Click **Run Pipeline** in the sidebar to extract data."
        )
    else:
        with st.spinner("Generating brief..."):
            brief_text = brief.generate_brief(today=selected_date)
            st.markdown(brief_text)

# --- Tab 2: Q&A ---
with tab_qa:
    st.header("💬 Ask Me Anything")

    # Display chat history
    for entry in st.session_state.chat_history:
        role = entry["role"]
        content = entry["content"]
        with st.chat_message(role):
            st.markdown(content)

    # Chat input
    if question := st.chat_input("Ask about commitments, deadlines, or priorities..."):
        # Append user question
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Generate answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer_text = qa.answer(question, today=selected_date)
                st.markdown(answer_text)
                st.session_state.chat_history.append({"role": "assistant", "content": answer_text})

# --- Tab 3: Raw Data ---
with tab_raw:
    st.header("📊 Raw Commitments Data")
    commitments = store.load_commitments()

    if not commitments:
        st.info("No commitments loaded. Run the pipeline first.")
    else:
        st.write(f"**Total commitments:** {len(commitments)}")

        # Annotate with status
        annotated = []
        for c in commitments:
            status = dates.commitment_status(
                deadline_iso=c.get("deadline_iso"),
                completed=c.get("completed", False),
                today=selected_date,
            )
            annotated.append({**c, "status": status})

        # Display as a data table
        import pandas as pd

        df = pd.DataFrame(annotated)
        # Select key columns for display
        display_cols = [
            "id", "title", "owner", "raw_deadline", "deadline_iso",
            "completed", "status",
        ]
        existing_cols = [col for col in display_cols if col in df.columns]
        st.dataframe(df[existing_cols], use_container_width=True)

        # Expandable JSON view
        with st.expander("View full JSON"):
            st.json(annotated)
