"""
AI Email Agent - 100% FREE
Uses Gmail SMTP (App Password) - No Google Cloud, No Credit Card
Detects job roles, sends correct resume, CC correct person
"""

import os
import json
import base64
import logging
import re
import smtplib
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import imaplib
import email as emaillib

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ROLE CONFIG
# Add/remove roles as needed
# Each role has:
#   keywords      → detect in email
#   resume_secret → GitHub Secret name for resume
#   cc_secret     → GitHub Secret name for CC email
#   reply         → your reply template
# ─────────────────────────────────────────────
ROLES = [
    {
        "name": "DevOps Engineer",
        "keywords": [
            "devops engineer", "devops lead", "devops",
            "ci/cd engineer", "build and release",
            "devsecops", "release engineer",
        ],
        "resume_secret": "RESUME_DEVOPS_B64",
        "cc_secret": "CC_DEVOPS",
        "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have hands-on experience in DevOps practices including CI/CD pipeline setup, infrastructure automation using Terraform and Ansible, container orchestration with Kubernetes and Docker, and cloud platforms (AWS/GCP/Azure).

Please find my resume attached for your review. I would love to discuss this opportunity further.

Looking forward to hearing from you."""
    },
    {
        "name": "Cloud Engineer",
        "keywords": [
            "cloud engineer", "aws engineer", "azure engineer",
            "gcp engineer", "cloud architect", "cloud infrastructure",
        ],
        "resume_secret": "RESUME_CLOUD_B64",
        "cc_secret": "CC_CLOUD",
        "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have strong hands-on experience in cloud platforms including AWS, Azure, and GCP. My expertise includes cloud infrastructure design, cost optimization, security best practices, and cloud-native services.

Please find my resume attached for your review. I look forward to discussing how I can contribute to your team.

Looking forward to hearing from you."""
    },
    {
        "name": "Site Reliability Engineer",
        "keywords": [
            "site reliability engineer", "sre",
            "reliability engineer", "production engineer",
        ],
        "resume_secret": "RESUME_SRE_B64",
        "cc_secret": "CC_SRE",
        "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have strong experience in SRE practices including SLO/SLI/SLA management, incident response, chaos engineering, and building reliable distributed systems using Prometheus, Grafana, and ELK stack.

Please find my resume attached for your review.

Looking forward to hearing from you."""
    },
    {
        "name": "SAP Consultant",
        "keywords": [
            "sap pp", "sap mm", "sap sd", "sap fico", "sap fi",
            "sap co", "sap basis", "sap abap", "sap hana",
            "sap ewm", "sap wm", "sap consultant", "sap analyst",
        ],
        "resume_secret": "RESUME_SAP_B64",
        "cc_secret": "CC_SAP",
        "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have extensive SAP consulting experience including implementation, configuration, and support across multiple SAP modules with end-to-end project lifecycle experience.

Please find my resume attached for your review.

Looking forward to hearing from you."""
    },
    {
        "name": "Platform Engineer",
        "keywords": [
            "platform engineer", "infrastructure engineer",
            "kubernetes engineer", "linux administrator",
            "systems engineer", "systems administrator",
        ],
        "resume_secret": "RESUME_PLATFORM_B64",
        "cc_secret": "CC_PLATFORM",
        "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have solid experience in platform engineering including Kubernetes, Linux administration, networking, and infrastructure as code using Terraform and Ansible.

Please find my resume attached for your review.

Looking forward to hearing from you."""
    },
]

# Fallback if no specific role matched
DEFAULT_ROLE = {
    "name": "Default",
    "resume_secret": "RESUME_DEFAULT_B64",
    "cc_secret": "CC_DEFAULT",
    "reply": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position and believe my experience aligns well with your requirements.

Please find my resume attached for your review. I look forward to discussing this opportunity.

Looking forward to hearing from you."""
}

# General job keywords — catches job emails
JOB_KEYWORDS = [
    "hiring", "job opportunity", "urgent requirement", "requirement",
    "opening", "position", "vacancy", "recruitment", "looking for",
    "immediate requirement", "greetings from", "we have an opening",
    "kindly share", "please share your resume", "relevant profile",
    "years of experience", "notice period", "current ctc",
    "expected ctc", "job description", "jd ",
]

STATE_FILE = "logs/processed_ids.json"

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
def load_processed():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()

def save_processed(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)

# ─────────────────────────────────────────────
# READ EMAILS VIA IMAP
# ─────────────────────────────────────────────
def fetch_unread_emails(your_email, app_password):
    log.info("📬 Connecting to Gmail via IMAP...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(your_email, app_password)
    mail.select("inbox")

    # Search unread emails
    _, msg_ids = mail.search(None, "UNSEEN")
    ids = msg_ids[0].split()
    log.info(f"📬 Found {len(ids)} unread emails")

    emails = []
    # Process latest 100 only to avoid timeout
    for uid in ids[-100:]:
        try:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = emaillib.message_from_bytes(raw)

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            emails.append({
                "uid":      uid.decode(),
                "subject":  msg.get("Subject", ""),
                "sender":   msg.get("From", ""),
                "reply_to": msg.get("Reply-To", msg.get("From", "")),
                "body":     body[:4000],
            })
        except Exception as e:
            log.error(f"Error reading email {uid}: {e}")

    mail.logout()
    return emails

# ─────────────────────────────────────────────
# DETECTION
# ─────────────────────────────────────────────
def is_job_email(email):
    text = (email["subject"] + " " + email["body"]).lower()
    for role in ROLES:
        if any(kw in text for kw in role["keywords"]):
            return True
    return any(kw in text for kw in JOB_KEYWORDS)

def detect_role(email):
    text = (email["subject"] + " " + email["body"]).lower()
    for role in ROLES:
        if any(kw in text for kw in role["keywords"]):
            log.info(f"  🎯 Matched: {role['name']}")
            return role
    log.info("  🎯 No specific role → Default")
    return DEFAULT_ROLE

def extract_address(s):
    m = re.search(r"<(.+?)>", s)
    return m.group(1) if m else s.strip()

def extract_role_title(email):
    text = email["subject"] + " " + email["body"][:300]
    m = re.search(
        r"([A-Z][a-z]+(?: [A-Z][a-z]+){1,4} (?:Engineer|Developer|Consultant|Analyst|Administrator|Lead|Manager))",
        text
    )
    return m.group(1).strip() if m else "this position"

def extract_company(email):
    addr = extract_address(email["sender"])
    domain = addr.split("@")[-1].split(".")[0].capitalize() if "@" in addr else ""
    generic = ["gmail", "yahoo", "hotmail", "outlook", "rediffmail", "naukri"]
    if domain.lower() not in generic and domain:
        return domain
    return "your organization"

# ─────────────────────────────────────────────
# GET RESUME FROM SECRET
# ─────────────────────────────────────────────
def get_resume(role):
    b64 = os.environ.get(role["resume_secret"], "")
    if not b64:
        log.warning(f"  ⚠️ {role['resume_secret']} not set → using default")
        b64 = os.environ.get(DEFAULT_ROLE["resume_secret"], "")
    if not b64:
        raise ValueError("No resume found! Add RESUME_DEFAULT_B64 to GitHub Secrets.")
    log.info(f"  📎 Resume: {role['resume_secret']}")
    return base64.b64decode(b64)

# ─────────────────────────────────────────────
# SEND EMAIL VIA SMTP
# ─────────────────────────────────────────────
def send_reply(email, role, your_name, your_email, app_password):
    to_email  = extract_address(email["reply_to"] or email["sender"])
    cc_email  = os.environ.get(role["cc_secret"], "")
    role_title = extract_role_title(email)
    company   = extract_company(email)

    subject = f"Re: {email['subject']}" if not email["subject"].lower().startswith("re:") else email["subject"]
    body    = role["reply"].format(role=role_title, company=company)
    body   += f"\n\nBest regards,\n{your_name}"

    msg = MIMEMultipart()
    msg["From"]    = your_email
    msg["To"]      = to_email
    msg["Subject"] = subject
    if cc_email:
        msg["Cc"] = cc_email

    msg.attach(MIMEText(body, "plain"))

    # Attach resume
    resume_bytes = get_resume(role)
    part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part.set_payload(resume_bytes)
    encoders.encode_base64(part)
    fname = f"Resume_{your_name.replace(' ', '_')}.docx"
    part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
    msg.attach(part)

    # Send via Gmail SMTP
    recipients = [to_email]
    if cc_email:
        recipients.append(cc_email)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(your_email, app_password)
        server.sendmail(your_email, recipients, msg.as_string())

    log.info(f"  ✅ Sent to: {to_email}")
    if cc_email:
        log.info(f"  📋 CC'd:    {cc_email}")

# ─────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────
def log_sent(email, role):
    csv_path = "logs/sent_log.csv"
    is_new   = not os.path.exists(csv_path)
    with open(csv_path, "a") as f:
        if is_new:
            f.write("timestamp,role,sender,subject,cc\n")
        cc = os.environ.get(role["cc_secret"], "none")
        f.write(f'{datetime.now().isoformat()},"{role["name"]}","{email["sender"]}","{email["subject"]}","{cc}"\n')

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    log.info("=" * 55)
    log.info("🤖 AI Email Agent — FREE (Gmail SMTP)")
    log.info(f"⏰ {datetime.now().isoformat()}")
    log.info("=" * 55)

    your_name    = os.environ.get("YOUR_NAME", "")
    your_email   = os.environ.get("YOUR_EMAIL", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    # Check required values
    missing = []
    if not your_name:     missing.append("YOUR_NAME")
    if not your_email:    missing.append("YOUR_EMAIL")
    if not app_password:  missing.append("GMAIL_APP_PASSWORD")
    if missing:
        log.error(f"❌ Missing secrets: {', '.join(missing)}")
        return

    processed = load_processed()

    # Fetch emails
    emails = fetch_unread_emails(your_email, app_password)

    matched = 0
    for email in emails:
        uid = email["uid"]
        if uid in processed:
            continue

        processed.add(uid)

        if not is_job_email(email):
            continue

        log.info(f"\n🎯 JOB EMAIL: {email['subject']}")
        log.info(f"   From: {email['sender']}")
        matched += 1

        try:
            role = detect_role(email)
            send_reply(email, role, your_name, your_email, app_password)
            log_sent(email, role)
        except Exception as e:
            log.error(f"❌ Error: {e}", exc_info=True)

    save_processed(processed)
    log.info(f"\n✅ Done — Replied to {matched} job emails out of {len(emails)} scanned")
    log.info("💰 Cost: ₹0.00")

if __name__ == "__main__":
    main()
