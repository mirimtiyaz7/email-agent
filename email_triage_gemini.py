"""
Email Triage Agent - FREE version (Google Gemini), reads settings from .env
- Reads emails (demo samples, or a real inbox via IMAP)
- Gemini classifies each one, scores urgency, drafts a reply
- Guardrail: replies are only DRAFTED, never sent without human approval

Setup:
    python -m pip install google-genai python-dotenv
    copy .env.example .env     (then fill in your values)
    python email_triage_gemini.py            # demo mode
    python email_triage_gemini.py --imap     # real inbox
"""
import os
import sys
import json
import imaplib
import email
from email.header import decode_header

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load variables from the .env file in this folder
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
MAX_EMAILS = int(os.getenv("MAX_EMAILS", "10"))

if not GEMINI_API_KEY:
    sys.exit("GEMINI_API_KEY is missing. Add it to your .env file.")

client = genai.Client(api_key=GEMINI_API_KEY)

CATEGORIES = ["urgent", "sales", "support", "billing", "newsletter", "spam", "other"]

SYSTEM_PROMPT = f"""You are an email triage assistant for a small business owner.
For each email return ONLY valid JSON with these keys:
  category: one of {CATEGORIES}
  urgency: integer 1 (ignore) to 5 (act now)
  summary: one sentence
  needs_human: true if the email involves money, legal issues, complaints,
               or you are not confident
  draft_reply: a short, polite reply, or "" if no reply is needed
Never invent facts, prices or promises in the draft reply."""

DEMO_EMAILS = [
    {"from": "client@acme.com", "subject": "Website is down!!",
     "body": "Our site has been showing a 500 error since morning. We are losing orders. Please fix ASAP."},
    {"from": "deals@randomshop.biz", "subject": "WIN a free iPhone now",
     "body": "Click this link to claim your prize before midnight!!!"},
    {"from": "priya@startup.io", "subject": "Quote for ERP + automation",
     "body": "Hi, we are a 20 person company and want an ERP with WhatsApp automation. Can you share a quote and timeline?"},
    {"from": "accounts@vendor.com", "subject": "Invoice #4821 overdue",
     "body": "Invoice 4821 for 45,000 INR is 10 days overdue. Please confirm payment date."},
]


def decode(value):
    parts = decode_header(value or "")
    return "".join(
        p.decode(enc or "utf-8", errors="ignore") if isinstance(p, bytes) else p
        for p, enc in parts
    )


def fetch_imap(limit=MAX_EMAILS):
    if not (EMAIL_USER and EMAIL_PASS):
        sys.exit("EMAIL_USER and EMAIL_PASS are missing. Add them to your .env file.")
    box = imaplib.IMAP4_SSL(IMAP_HOST)
    box.login(EMAIL_USER, EMAIL_PASS)
    box.select("INBOX", readonly=True)  # readonly: never changes your mailbox
    _, data = box.search(None, "UNSEEN")
    emails = []
    for num in data[0].split()[-limit:]:
        _, msg_data = box.fetch(num, "(BODY.PEEK[])")  # PEEK: does not mark as read
        msg = email.message_from_bytes(msg_data[0][1])
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore")
        emails.append({"from": decode(msg["From"]),
                       "subject": decode(msg["Subject"]),
                       "body": body[:3000]})
    box.logout()
    return emails


def triage(mail):
    prompt = f"From: {mail['from']}\nSubject: {mail['subject']}\n\n{mail['body']}"
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        return json.loads(resp.text)
    except Exception as e:
        print("ERROR:", e)  # shows the real reason while you are testing
        # Guardrail: if the call or the parsing fails, send to a human
        return {"category": "other", "urgency": 3,
                "summary": f"Could not process ({type(e).__name__})",
                "needs_human": True, "draft_reply": ""}


def main():
    mails = fetch_imap() if "--imap" in sys.argv else DEMO_EMAILS
    if not mails:
        print("No unread emails found.")
        return

    results = []
    for m in mails:
        r = triage(m)
        r["from"], r["subject"] = m["from"], m["subject"]
        results.append(r)

    # Show most urgent first
    results.sort(key=lambda r: r["urgency"], reverse=True)
    for r in results:
        flag = "  [NEEDS HUMAN]" if r["needs_human"] else ""
        print(f"\n[{r['urgency']}/5] {r['category'].upper()}{flag}")
        print(f"From: {r['from']} | Subject: {r['subject']}")
        print(f"Summary: {r['summary']}")
        if r["draft_reply"]:
            print(f"Draft reply:\n  {r['draft_reply']}")

    with open("triage_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nSaved to triage_results.json")


if __name__ == "__main__":
    main()
