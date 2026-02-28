"""
AI Email Agent — 100% FREE VERSION
- No Claude, No API cost, Zero rupees
- Keyword detection to pick right resume
- Right CC email per role
- Fixed reply template per role
- Runs FREE on GitHub Actions every 10 minutes
"""

import os
import json
import base64
import logging
import re
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

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
# Each role has:
#   keywords       → detect in email subject/body
#   resume_secret  → GitHub Secret with base64 resume
#   cc_secret      → GitHub Secret with CC email
#   reply_template → fixed reply email text
#
# Add/remove roles as needed — no coding required
# ─────────────────────────────────────────────
ROLES = [
    {
        "name":           "DevOps Engineer",
        "keywords":       [
            "devops engineer", "devops lead", "devops",
            "ci/cd engineer", "build and release engineer",
            "devsecops", "release engineer",
        ],
        "resume_secret":  "RESUME_DEVOPS_B64",
        "cc_secret":      "CC_DEVOPS",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have hands-on experience in DevOps practices including CI/CD pipeline setup, infrastructure automation using Terraform and Ansible, container orchestration with Kubernetes and Docker, and cloud platforms (AWS/GCP/Azure). I have worked extensively with Jenkins, GitHub Actions, Prometheus, and Grafana.

I believe my skills align well with your requirements. Please find my resume attached for your review. I would love to discuss this opportunity further.

Looking forward to hearing from you."""
    },
    {
        "name":           "Cloud Engineer",
        "keywords":       [
            "cloud engineer", "aws engineer", "azure engineer",
            "gcp engineer", "cloud architect", "cloud infrastructure",
            "solutions architect", "cloud support",
        ],
        "resume_secret":  "RESUME_CLOUD_B64",
        "cc_secret":      "CC_CLOUD",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have strong hands-on experience in cloud platforms including AWS, Azure, and GCP. My expertise includes cloud infrastructure design, cost optimization, security best practices, IAM, VPC, and cloud-native services. I hold relevant cloud certifications and have worked on large-scale cloud migrations.

Please find my resume attached for your review. I look forward to discussing how I can contribute to your team.

Looking forward to hearing from you."""
    },
    {
        "name":           "Site Reliability Engineer",
        "keywords":       [
            "site reliability engineer", "sre", "reliability engineer",
            "production engineer", "platform reliability",
        ],
        "resume_secret":  "RESUME_SRE_B64",
        "cc_secret":      "CC_SRE",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have strong experience in SRE practices including defining and maintaining SLOs/SLIs/SLAs, incident management, on-call support, chaos engineering, and building reliable distributed systems. I am proficient in Prometheus, Grafana, ELK stack, PagerDuty, and automation scripting with Python and Bash.

Please find my resume attached for your review. I would be glad to connect and discuss this further.

Looking forward to hearing from you."""
    },
    {
        "name":           "Platform Engineer",
        "keywords":       [
            "platform engineer", "infrastructure engineer",
            "kubernetes engineer", "linux administrator",
            "systems engineer", "systems administrator",
        ],
        "resume_secret":  "RESUME_PLATFORM_B64",
        "cc_secret":      "CC_PLATFORM",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have solid experience in platform and infrastructure engineering including Kubernetes cluster management, Linux administration, networking, and infrastructure as code using Terraform and Ansible. I am experienced in building internal developer platforms and maintaining high-availability systems.

Please find my resume attached for your review. I look forward to discussing this opportunity.

Looking forward to hearing from you."""
    },
    {
        "name":           "SAP Consultant",
        "keywords":       [
            "sap pp", "sap mm", "sap sd", "sap fico", "sap fi",
            "sap co", "sap basis", "sap abap", "sap hana",
            "sap ewm", "sap wm", "sap consultant", "sap analyst",
            "sap functional", "sap technical",
        ],
        "resume_secret":  "RESUME_SAP_B64",
        "cc_secret":      "CC_SAP",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have extensive experience in SAP consulting including implementation, configuration, and support across multiple SAP modules. I have worked on end-to-end SAP project lifecycles including blueprinting, realization, testing, go-live, and post go-live support.

Please find my resume attached for your review. I would welcome the opportunity to discuss how my SAP expertise aligns with your requirements.

Looking forward to hearing from you."""
    },
    {
        "name":           "Java Developer",
        "keywords":       [
            "java developer", "java engineer", "java backend",
            "spring boot", "j2ee", "java full stack",
        ],
        "resume_secret":  "RESUME_JAVA_B64",
        "cc_secret":      "CC_JAVA",
        "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position. I have strong experience in Java development including Spring Boot, Microservices, REST APIs, Hibernate, and Maven. I have worked on high-traffic enterprise applications with a focus on performance and scalability.

Please find my resume attached for your review. I look forward to discussing this opportunity further.

Looking forward to hearing from you."""
    },
    # ── ADD MORE ROLES HERE ──────────────────────────────────
    # Just copy one block above, change the values, done!
    # ─────────────────────────────────────────────────────────
]

# Fallback if no role matches but email looks like a job
DEFAULT_ROLE = {
    "name":           "Default",
    "resume_secret":  "RESUME_DEFAULT_B64",
    "cc_secret":      "CC_DEFAULT",
    "reply_template": """Dear Hiring Team,

Thank you for reaching out regarding the {role} opportunity at {company}.

I am very interested in this position and believe my experience aligns well with your requirements.

Please find my resume attached for your review. I look forward to discussing this opportunity further.

Looking forward to hearing from you."""
}

# General job email filter — catches anything before role matching
JOB_KEYWORDS = [
    "hiring", "job opportunity", "urgent requirement", "requirement",
    "opening", "position", "vacancy", "recruitment", "looking for",
    "immediate requirement", "greetings from", "we have an opening",
    "kindly share", "please share your resume", "relevant profile",
    "years of experience", "notice period",
]

SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly",
              "https://www.googleapis.com/auth/gmail.send",
              "https://www.googleapis.com/auth/gmail.modify"]
STATE_FILE = "logs/processed_ids.json"
BATCH_SIZE = 100   # emails scanned per run

# ─────────────────────────────────────────────
# STATE — track processed emails
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
# GMAIL AUTH
# ─────────────────────────────────────────────
def get_gmail_service():
    creds = Credentials.from_authorized_user_info(
        json.loads(os.environ["GMAIL_TOKEN_JSON"]), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        log.info("Gmail token refreshed")
    return build("gmail", "v1", credentials=creds)

# ─────────────────────────────────────────────
# EMAIL PARSING
# ─────────────────────────────────────────────
def get_body(payload):
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        body = get_body(part)
        if body:
            return body
    return ""

def parse_email(service, msg_id):
    msg     = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    return {
        "id":        msg_id,
        "thread_id": msg.get("threadId"),
        "subject":   headers.get("Subject", "(no subject)"),
        "sender":    headers.get("From", ""),
        "reply_to":  headers.get("Reply-To", headers.get("From", "")),
        "body":      get_body(msg["payload"])[:4000],
    }

def extract_address(s):
    m = re.search(r"<(.+?)>", s)
    return m.group(1) if m else s.strip()

def extract_name(s):
    m = re.match(r"^([^<]+)", s)
    return m.group(1).strip().strip('"') if m else ""

# ─────────────────────────────────────────────
# DETECTION — pure keyword matching, zero cost
# ─────────────────────────────────────────────
def is_job_email(email):
    """Step 1: Is this any kind of job email?"""
    text = (email["subject"] + " " + email["body"]).lower()
    # Check role keywords first
    for role in ROLES:
        if any(kw in text for kw in role["keywords"]):
            return True
    # Check generic job keywords
    return any(kw in text for kw in JOB_KEYWORDS)

def detect_role(email):
    """Step 2: Which specific role? Returns matched ROLE dict."""
    text = (email["subject"] + " " + email["body"]).lower()
    for role in ROLES:
        if any(kw in text for kw in role["keywords"]):
            log.info(f"  🎯 Role matched: {role['name']}")
            return role
    log.info("  🎯 No specific role matched → using Default")
    return DEFAULT_ROLE

def extract_role_title(email):
    """Try to extract actual job title from email text."""
    text = email["subject"] + " " + email["body"][:500]
    patterns = [
        r"(?:for|hiring|position|role|opening)[:\s]+([A-Z][^\n,.]{3,50})",
        r"([A-Z][a-z]+(?: [A-Z][a-z]+){1,4} (?:Engineer|Developer|Consultant|Analyst|Administrator|Lead|Manager))",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return "this position"

def extract_company(email):
    """Try to extract company name from email sender or body."""
    # Try sender domain
    addr = extract_address(email["sender"])
    domain = addr.split("@")[-1].split(".")[0].capitalize() if "@" in addr else ""
    # Skip generic domains
    generic = ["gmail", "yahoo", "hotmail", "outlook", "rediffmail", "naukri", "monster"]
    if domain.lower() not in generic and domain:
        return domain
    # Try from body
    m = re.search(r"(?:from|at|company)[:\s]+([A-Z][A-Za-z\s&]{2,30})", email["body"][:500])
    if m:
        return m.group(1).strip()
    return "your organization"

# ─────────────────────────────────────────────
# RESUME — decode from GitHub Secret
# ─────────────────────────────────────────────
def get_resume(role):
    secret_name = role["resume_secret"]
    b64 = os.environ.get(secret_name, "")
    if not b64:
        log.warning(f"  ⚠️ Secret '{secret_name}' not set → trying DEFAULT")
        b64 = os.environ.get(DEFAULT_ROLE["resume_secret"], "")
    if not b64:
        raise ValueError("No resume found! Add at least RESUME_DEFAULT_B64 to GitHub Secrets.")
    log.info(f"  📎 Resume: {secret_name}")
    return base64.b64decode(b64)

# ─────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────
def send_reply(service, email, role):
    your_name  = os.environ.get("YOUR_NAME", "")
    your_email = os.environ.get("YOUR_EMAIL", "")
    to_email   = extract_address(email["reply_to"] or email["sender"])
    cc_email   = os.environ.get(role["cc_secret"], "")
    role_title = extract_role_title(email)
    company    = extract_company(email)

    # Fill template
    body = role["reply_template"].format(
        role=role_title,
        company=company,
    ) + f"\n\nBest regards,\n{your_name}"

    subject = f"Re: {email['subject']}" if not email["subject"].lower().startswith("re:") else email["subject"]

    # Build MIME email
    msg = MIMEMultipart()
    msg["To"]      = to_email
    msg["From"]    = your_email
    msg["Subject"] = subject
    if cc_email:
        msg["Cc"] = cc_email

    msg.attach(MIMEText(body, "plain"))

    # Attach resume — exact file, zero changes
    resume_bytes = get_resume(role)
    part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part.set_payload(resume_bytes)
    encoders.encode_base64(part)
    fname = f"Resume_{your_name.replace(' ', '_')}.docx"
    part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
    msg.attach(part)

    raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if email.get("thread_id"):
        payload["threadId"] = email["thread_id"]

    result = service.users().messages().send(userId="me", body=payload).execute()
    log.info(f"  ✅ Sent to: {to_email}")
    if cc_email:
        log.info(f"  📋 CC'd to: {cc_email}")
    return result

# ─────────────────────────────────────────────
# LOG TO CSV
# ─────────────────────────────────────────────
def log_sent(email, role):
    csv_path = "logs/sent_log.csv"
    is_new   = not os.path.exists(csv_path)
    with open(csv_path, "a") as f:
        if is_new:
            f.write("timestamp,role_matched,sender,subject,cc_used\n")
        cc = os.environ.get(role["cc_secret"], "none")
        f.write(f'{datetime.now().isoformat()},"{role["name"]}","{email["sender"]}","{email["subject"]}","{cc}"\n')

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    log.info("=" * 55)
    log.info("🤖 AI Email Agent — 100% FREE (No Claude)")
    log.info(f"⏰ {datetime.now().isoformat()}")
    log.info("=" * 55)

    # Check required secrets
    missing = [k for k in ["GMAIL_TOKEN_JSON", "YOUR_NAME", "YOUR_EMAIL"] if not os.environ.get(k)]
    if missing:
        log.error(f"❌ Missing secrets: {', '.join(missing)}")
        return

    service   = get_gmail_service()
    processed = load_processed()

    # Fetch unread emails
    result   = service.users().messages().list(
        userId="me", q="is:unread in:inbox", maxResults=BATCH_SIZE
    ).execute()
    messages = result.get("messages", [])
    log.info(f"📬 Scanning {len(messages)} unread emails...")

    matched = 0
    for ref in messages:
        msg_id = ref["id"]
        if msg_id in processed:
            continue

        try:
            email = parse_email(service, msg_id)
            processed.add(msg_id)

            # Step 1: Is it a job email?
            if not is_job_email(email):
                continue

            log.info(f"\n🎯 JOB EMAIL: {email['subject']}")
            log.info(f"   From: {email['sender']}")
            matched += 1

            # Step 2: Which role?
            role = detect_role(email)

            # Step 3: Send right resume + right CC
            send_reply(service, email, role)
            log_sent(email, role)

        except Exception as e:
            log.error(f"❌ Error on {msg_id}: {e}", exc_info=True)

    save_processed(processed)
    log.info(f"\n✅ Done — Replied to {matched} job emails out of {len(messages)} scanned")
    log.info("💰 Cost this run: ₹0.00")

if __name__ == "__main__":
    main()
