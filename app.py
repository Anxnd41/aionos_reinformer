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

    # Check if commitments already exist
    existing_commitments = store.load_commitments()
    if existing_commitments:
        st.info(f"ℹ️ {len(existing_commitments)} commitments loaded from cache")
    
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
                st.rerun()  # Refresh to show new data

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
        # Simple display without LLM (works offline)
        # Categorize commitments manually
        overdue = []
        due_today = []
        upcoming = []
        completed = []
        
        for c in commitments:
            status = dates.commitment_status(
                deadline_iso=c.get("deadline_iso"),
                completed=c.get("completed", False),
                today=selected_date,
            )
            if status == "done":
                completed.append(c)
            elif status == "overdue":
                overdue.append(c)
            elif status == "due_today":
                due_today.append(c)
            elif status == "upcoming":
                upcoming.append(c)
        
        # Display summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("⚠️ Overdue", len(overdue))
        with col2:
            st.metric("📅 Due Today", len(due_today))
        with col3:
            st.metric("🔜 Upcoming", len(upcoming))
        with col4:
            st.metric("✅ Completed", len(completed))
        
        st.divider()
        
        # Display categories
        if overdue:
            st.subheader("⚠️ Overdue")
            for c in overdue:
                with st.expander(f"{c['title']}"):
                    st.write(f"**Owner:** {c['owner']}")
                    st.write(f"**Deadline:** {c.get('raw_deadline', 'N/A')}")
                    st.write(f"**Description:** {c.get('description', 'N/A')}")
        
        if due_today:
            st.subheader("📅 Due Today")
            for c in due_today:
                with st.expander(f"{c['title']}"):
                    st.write(f"**Owner:** {c['owner']}")
                    st.write(f"**Description:** {c.get('description', 'N/A')}")
        
        if upcoming:
            st.subheader("🔜 Upcoming")
            for c in upcoming:
                with st.expander(f"{c['title']}"):
                    st.write(f"**Owner:** {c['owner']}")
                    st.write(f"**Deadline:** {c.get('raw_deadline', 'N/A')}")
                    st.write(f"**Description:** {c.get('description', 'N/A')}")
        
        if completed:
            st.subheader("✅ Completed")
            for c in completed:
                with st.expander(f"{c['title']}"):
                    st.write(f"**Owner:** {c['owner']}")
                    st.write(f"**Description:** {c.get('description', 'N/A')}")

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

        # Simple keyword-based response (no LLM needed)
        with st.chat_message("assistant"):
            commitments = store.load_commitments()
            question_lower = question.lower()
            
            # Keyword matching
            if "overdue" in question_lower:
                overdue = [c for c in commitments if dates.commitment_status(
                    c.get("deadline_iso"), c.get("completed", False), selected_date
                ) == "overdue"]
                answer = f"There are {len(overdue)} overdue commitments. " + (
                    f"They are: {', '.join([c['title'] for c in overdue[:3]])}" if overdue else ""
                )
            elif "today" in question_lower or "due" in question_lower:
                due_today = [c for c in commitments if dates.commitment_status(
                    c.get("deadline_iso"), c.get("completed", False), selected_date
                ) == "due_today"]
                answer = f"There are {len(due_today)} commitments due today. " + (
                    f"They are: {', '.join([c['title'] for c in due_today[:3]])}" if due_today else ""
                )
            else:
                answer = f"I found {len(commitments)} total commitments. Check the Daily Brief and Raw Data tabs for details."
            
            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

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
