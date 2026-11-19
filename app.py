"""
Email Triage Dashboard (Streamlit)
Run:  python -m streamlit run app.py
Needs email_triage_gemini.py and .env in the same folder.
"""
import streamlit as st

from email_triage_gemini import DEMO_EMAILS, fetch_imap, triage

st.set_page_config(page_title="Email Triage Agent", page_icon="📧", layout="wide")

CATEGORY_COLORS = {
    "urgent": "🔴", "billing": "🟠", "sales": "🟢", "support": "🔵",
    "newsletter": "⚪", "spam": "⚫", "other": "🟣",
}


def run_triage(mails):
    results = []
    progress = st.progress(0, text="Analyzing emails...")
    for i, m in enumerate(mails):
        r = triage(m)
        r["from"], r["subject"] = m["from"], m["subject"]
        results.append(r)
        progress.progress((i + 1) / len(mails), text=f"Analyzed {i + 1} of {len(mails)}")
    progress.empty()
    results.sort(key=lambda r: r["urgency"], reverse=True)
    return results


def show_results(results):
    total = len(results)
    urgent = sum(1 for r in results if r["urgency"] >= 4)
    human = sum(1 for r in results if r["needs_human"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Emails analyzed", total)
    c2.metric("High urgency (4-5)", urgent)
    c3.metric("Needs human review", human)

    st.divider()

    categories = sorted({r["category"] for r in results})
    chosen = st.multiselect("Filter by category", categories, default=categories)

    for idx, r in enumerate(results):
        if r["category"] not in chosen:
            continue
        icon = CATEGORY_COLORS.get(r["category"], "🟣")
        flag = "  ⚠️ Needs human" if r["needs_human"] else ""
        title = f"{icon} [{r['urgency']}/5] {r['subject']}  —  {r['from']}{flag}"
        with st.expander(title, expanded=r["urgency"] >= 4):
            st.write(f"**Category:** {r['category']}")
            st.write(f"**Summary:** {r['summary']}")
            if r["draft_reply"]:
                reply = st.text_area("Draft reply (editable)", r["draft_reply"],
                                     key=f"reply_{idx}", height=120)
                if st.button("Approve draft", key=f"approve_{idx}"):
                    # Guardrail: the agent never sends anything by itself.
                    st.success("Approved. In a full version, this is where it would be sent.")
            else:
                st.caption("No reply needed.")


st.title("📧 Email Triage Agent")
st.caption("AI sorts your inbox by urgency and drafts replies. Nothing is sent without your approval.")

with st.sidebar:
    st.header("Settings")
    source = st.radio("Email source", ["Demo emails", "Real inbox (IMAP)"])
    st.caption("Real inbox is read-only. Use a test account.")

tab1, tab2 = st.tabs(["Inbox triage", "Try your own email"])

with tab1:
    if st.button("Run triage", type="primary"):
        try:
            mails = DEMO_EMAILS if source == "Demo emails" else fetch_imap()
        except SystemExit as e:
            st.error(str(e))
            mails = []
        except Exception as e:
            st.error(f"Could not read inbox: {e}")
            mails = []

        if source != "Demo emails" and not mails:
            st.info("No unread emails found.")
        elif mails:
            st.session_state["results"] = run_triage(mails)

    if "results" in st.session_state:
        show_results(st.session_state["results"])

with tab2:
    st.write("Paste any email and see how the agent handles it. Good for a live demo.")
    sender = st.text_input("From", "customer@example.com")
    subject = st.text_input("Subject", "Need a quote for a website")
    body = st.text_area("Body", "Hi, we need a 5 page website for our shop. What is the cost?", height=150)
    if st.button("Analyze this email"):
        with st.spinner("Thinking..."):
            r = triage({"from": sender, "subject": subject, "body": body})
        st.write(f"**Category:** {r['category']}  |  **Urgency:** {r['urgency']}/5"
                 f"  |  **Needs human:** {r['needs_human']}")
        st.write(f"**Summary:** {r['summary']}")
        if r["draft_reply"]:
            st.text_area("Draft reply", r["draft_reply"], height=120)
