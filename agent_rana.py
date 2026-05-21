"""
AI Email Agent - Rana Pagadam (SAP FICO / FSCM / Treasury / S/4HANA Architect)
Scans: sudheeritservices1@gmail.com (IMAP - Gmail)
Sends: sudheer@adeptscripts.com (SMTP - Zoho)
Replies to: SAP FICO, CO, COPA, Treasury, FSCM, Central Finance, Product Costing roles
REMOTE ONLY: On-site / hybrid / local roles are SKIPPED

FEATURES:
1. Dedup checked FIRST before anything else
2. Dedup saved IMMEDIATELY after each send (not at the end)
3. UTF-8-sig fix for dedup file (BOM handling)
4. Skips own sent emails
5. REMOVED "Re:" skip - recruiters use RE: in fresh emails
6. SCAN from sudheeritservices1@gmail.com (Gmail IMAP)
7. SEND from sudheer@adeptscripts.com (Zoho SMTP)
8. Daily send cap (450) to avoid limit errors
9. SINGLE SMTP connection reused for all emails
10. 8 second delay between sends (avoids 550 spam detection)
11. certutil base64 header strip + padding fix
12. BROAD IMAP search: "SAP" catches ALL SAP variants
13. REMOVED UNSEEN filter - catches read and unread emails
14. REMOTE ONLY filter - skips onsite/hybrid/local
"""

import os, base64, logging, re, smtplib, time, json
from pathlib import Path
from datetime import datetime, date, time as dtime
import imaplib
import email as emaillib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import pytz

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/agent_rana.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DAILY DEDUP - Resets every day at midnight
# ══════════════════════════════════════════════════════════════════════════════
DEDUP_FILE = Path("logs") / "daily_replied_senders_rana.json"
MAX_DAILY_SENDS = 450

def get_today_date():
    return str(date.today())

def load_daily_dedup():
    if DEDUP_FILE.exists():
        try:
            with open(DEDUP_FILE, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                file_date = data.get("date", "")
                today = get_today_date()
                if file_date == today:
                    senders = set(data.get("senders", []))
                    send_count = data.get("send_count", 0)
                    log.info("TODAY (%s): %d senders, %d/%d sent so far",
                             today, len(senders), send_count, MAX_DAILY_SENDS)
                    return senders, send_count
                else:
                    log.info("NEW DAY! (was %s, now %s) - Resetting dedup", file_date, today)
                    return set(), 0
        except Exception as e:
            log.warning("Could not load dedup file: %s", e)
    log.info("TODAY (%s): No dedup file yet - starting fresh", get_today_date())
    return set(), 0

def save_daily_dedup(senders, send_count=0):
    data = {
        "date": get_today_date(),
        "senders": sorted(list(senders)),
        "send_count": send_count
    }
    try:
        with open(DEDUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log.info("SAVED TO DEDUP: %d senders, %d/%d sent today",
                 len(senders), send_count, MAX_DAILY_SENDS)
    except Exception as e:
        log.error("Could not save dedup file: %s", e)

# ══════════════════════════════════════════════════════════════════════════════
# TIME WINDOW CHECK
# ══════════════════════════════════════════════════════════════════════════════
def is_within_run_window():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    current_time = now.time()
    start = dtime(18, 30)   # 6:30 PM IST
    end   = dtime(4, 30)    # 4:30 AM IST
    return current_time >= start or current_time <= end

# ══════════════════════════════════════════════════════════════════════════════
# ONSITE / HYBRID DETECTION  — skip these entirely
# ══════════════════════════════════════════════════════════════════════════════
ONSITE_PATTERNS = [
    r"\bonsite\b", r"\bon-site\b", r"\bon site\b",
    r"\bhybrid\b",
    r"\blocal\b", r"\blocals\b", r"\blocal candidate\b", r"\blocal only\b",
    r"\bday.?1 onsite\b", r"\bday one onsite\b",
    r"\bin.person\b",
    r"\bin person\b",
]

def is_onsite_or_hybrid(subject):
    subj_lower = subject.lower()
    for pattern in ONSITE_PATTERNS:
        if re.search(pattern, subj_lower):
            return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
# IRRELEVANT MODULE DETECTION — skip SAP roles outside Rana's expertise
# ══════════════════════════════════════════════════════════════════════════════
IRRELEVANT_MODULES = [
    "sap mm", "sap sd", "sap pp", "sap qm", "sap ewm", "sap wm",
    "sap ariba", "sap btp", "sap cpi", "sap pi", "sap po",
    "sap successfactors", "sap hcm", "sap basis", "sap abap",
    "sap bw", "sap bi", "sap datasphere", "sap datashere",
    "sap hana xsa", "sap is-u", "sap is utilities",
    "sap eam", "sap pm", "sap gts", "sap afs",
    "sap concur", "salesforce", "oracle", "workday",
    "sap analytics cloud", "sap data migration",
    "sap wm-le", "sap ewm", "warehouse management",
    "sap test", "testing lead", "uat tester", "sap qa",
    "sap project manager", "sap program manager",
    "sap developer", "abap developer",
    "sap convergent", "sap brim",
    "sap opentext vim",   # Rana knows VIM but it's not core - remove if you want VIM roles
]

def is_irrelevant_module(subject):
    subj_lower = subject.lower()
    for mod in IRRELEVANT_MODULES:
        if mod in subj_lower:
            return mod
    return None

# ══════════════════════════════════════════════════════════════════════════════
# REPLY TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
SHARED_REPLY = """Hi,



In response to your job posting.
Here I am attaching my consultant's updated resume.
Please review the resume and let me know if it matches your position.
Looking forward to working with you.

Thanks & Regards,

Sudheer Kumar, Mandava

Mail: sudheer@adeptscripts.com

Mobile: +1 940-209-1875

8501 WADE BOULEVARD SUITE 870
FRISCO TX 75033
Recruitment Manager

www.adeptscripts.com

"""

# ══════════════════════════════════════════════════════════════════════════════
# ROLES  — SAP FICO / FSCM / Treasury / S/4HANA focus
# ══════════════════════════════════════════════════════════════════════════════
ROLES = [
    {
        "name": "SAP FICO Consultant / Architect",
        "keywords": [
            "sap fico", "sap fi/co", "sap fi co",
            "sap financial accounting", "sap controlling",
            "sap fico lead", "sap fico architect", "sap fico consultant",
            "sap fico s4", "sap fico s/4",
            "sap fi consultant", "sap co consultant",
            "sap finance consultant", "sap finance lead",
            "sap finance architect",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP S/4HANA Finance Consultant",
        "keywords": [
            "sap s/4hana finance", "sap s4hana finance",
            "s/4 hana finance", "s4 hana finance",
            "s/4hana fico", "s4hana fico",
            "s/4 finance", "s4 finance",
            "sap s/4 hana financial", "sap s4hana financial",
            "s/4hana group reporting", "s4 group reporting",
            "sap s4 hana financial systems",
            "sap finance group reporting",
            "r2r", "record to report",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Treasury / TRM Consultant",
        "keywords": [
            "sap treasury", "sap trm", "treasury risk management",
            "sap in-house cash", "sap ihc", "in house cash",
            "bank communication management", "sap bcm",
            "cash management", "sap cash management",
            "liquidity management", "sap fscm treasury",
            "sap tm", "transaction manager sap",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP FSCM Consultant",
        "keywords": [
            "sap fscm", "fscm consultant",
            "credit management", "sap credit management",
            "dispute management", "sap dispute",
            "collections management", "sap collections",
            "sap brim fscm",
            "sap financial supply chain",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP COPA / Product Costing Consultant",
        "keywords": [
            "sap copa", "co-pa", "profitability analysis",
            "product costing", "sap product costing",
            "cost object controlling", "material ledger",
            "sap controlling", "cost center accounting",
            "profit center accounting", "internal orders sap",
            "sap copc", "co-pc",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Central Finance / Group Reporting",
        "keywords": [
            "central finance", "sap central finance",
            "cfin", "sap cfin",
            "group reporting", "sap group reporting",
            "financial consolidation", "sap consolidation",
            "intercompany", "sap intercompany",
            "sap p&l", "sap balance sheet",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Accounts Payable / Accounts Receivable Consultant",
        "keywords": [
            "sap accounts payable", "sap ap consultant",
            "sap accounts receivable", "sap ar consultant",
            "sap ap/ar", "sap ar/ap",
            "procure to pay", "p2p finance",
            "sap p2p finance", "sap payment",
            "sap vendor payment", "sap invoice",
            "sap fico p2p",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Asset Accounting / Fixed Assets Consultant",
        "keywords": [
            "asset accounting", "sap asset accounting",
            "sap fixed assets", "sap fi-aa",
            "capital projects", "sap capex",
            "auc", "asset under construction",
            "sap investment management",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP FICO Funds Management / Grants",
        "keywords": [
            "funds management", "sap funds management",
            "sap grant management", "grants management",
            "sap fico grant",
            "public sector finance", "sap public sector",
        ],
        "resume_file": "resume_rana_b64.txt",
        "cc_secret": "CC_RANA",
        "reply": SHARED_REPLY,
    },
]

# Fallback: subject has "sap" + finance/fico/co keywords but no exact match
FALLBACK_ROLE = {
    "name": "SAP FICO / Finance Consultant (General)",
    "keywords": [],
    "resume_file": "resume_rana_b64.txt",
    "cc_secret": "CC_RANA",
    "reply": SHARED_REPLY,
}

# Keywords that trigger the fallback (subject must contain SAP + one of these)
FALLBACK_FINANCE_KEYWORDS = [
    "finance", "financial", "fico", "fi/co", "accounting",
    "general ledger", "new gl", "controlling", "copa",
    "treasury", "fscm", "s/4hana", "s4hana", "s/4 hana", "s4 hana",
    "ecc", "hana finance", "sap r2r",
]

REPLIED_LABEL = "AutoReplied_SAP_Rana"

SKIP_SENDERS = [
    "noreply@",
    "mailer-daemon@",
    "notifications@github.com",
    "noreply.github.com",
    "notifications.monster.com",
    "github.com",
    "sudheeritservices1@gmail.com",
    "sudheer@adeptscripts.com",
]

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def extract_address(s):
    if not s:
        return ""
    m = re.search(r"<(.+?)>", s)
    return (m.group(1) if m else s).strip().lower()

def connect_imap():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(os.environ["IMAP_EMAIL"], os.environ["IMAP_APP_PASSWORD"])
    mail.select("inbox")
    return mail

def ensure_label_exists(mail):
    try:
        mail.create(REPLIED_LABEL)
    except Exception:
        pass

def get_replied_message_ids(mail):
    replied_ids = set()
    try:
        mail.select(REPLIED_LABEL)
        _, msg_ids = mail.search(None, "ALL")
        if msg_ids[0]:
            uid_list = ",".join(m.decode() for m in msg_ids[0].split())
            _, data = mail.fetch(uid_list, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
            for item in data:
                if isinstance(item, tuple):
                    raw = item[1].decode("utf-8", errors="ignore")
                    m = re.search(r"Message-ID:\s*(.+)", raw, re.IGNORECASE)
                    if m:
                        replied_ids.add(m.group(1).strip())
    except Exception:
        pass
    mail.select("inbox")
    return replied_ids

def mark_as_replied(mail, uid):
    for attempt in range(3):
        try:
            fresh = connect_imap()
            fresh.select("inbox")
            fresh.copy(uid, REPLIED_LABEL)
            fresh.logout()
            return mail
        except Exception as e:
            log.warning("Mark attempt %d failed: %s", attempt + 1, e)
            time.sleep(2)
    log.error("Failed to mark email as replied after 3 attempts")
    return mail

# ══════════════════════════════════════════════════════════════════════════════
# FETCH EMAILS
# ══════════════════════════════════════════════════════════════════════════════
def fetch_matching_emails():
    log.info("Connecting to Gmail via IMAP...")
    mail = connect_imap()
    ensure_label_exists(mail)
    replied_ids = get_replied_message_ids(mail)
    log.info("Gmail %s label: %d emails", REPLIED_LABEL, len(replied_ids))

    replied_senders, send_count = load_daily_dedup()
    today = datetime.now().strftime("%d-%b-%Y")

    # BROAD search — "SAP" catches all SAP variants
    all_uid_set = set()
    search_queries = [
        'SINCE "' + today + '" SUBJECT "SAP"',
    ]
    for q in search_queries:
        try:
            _, msg_ids = mail.search(None, q)
            if msg_ids[0]:
                for uid in msg_ids[0].split():
                    all_uid_set.add(uid)
        except Exception as e:
            log.warning("Search failed for query '%s': %s", q, e)

    ids = list(all_uid_set)
    log.info("Found %d matching emails today (SAP broad search)", len(ids))

    emails, seen_uids = [], set()
    for i, uid in enumerate(ids):
        uid_str = uid.decode()
        if uid_str in seen_uids:
            continue
        seen_uids.add(uid_str)

        if i > 0 and i % 50 == 0:
            try:
                mail.logout()
            except Exception:
                pass
            log.info("Reconnecting IMAP at email %d...", i)
            time.sleep(1)
            mail = connect_imap()

        try:
            _, hdr_data = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID REPLY-TO)])")
            if not hdr_data or hdr_data[0] is None:
                continue
            hdr_raw = hdr_data[0][1].decode("utf-8", errors="ignore")

            subj_match = re.search(
                r"Subject:\s*(.+?)(?:\r?\n(?!\s)|\Z)",
                hdr_raw, re.IGNORECASE | re.DOTALL
            )
            subject = subj_match.group(1).strip().replace("\r\n", " ").replace("\n", " ") if subj_match else ""

            mid_match = re.search(r"Message-ID:\s*(.+)", hdr_raw, re.IGNORECASE)
            message_id = mid_match.group(1).strip() if mid_match else uid_str

            sender_match = re.search(
                r"From:\s*(.+?)(?:\r?\n(?!\s)|\Z)",
                hdr_raw, re.IGNORECASE | re.DOTALL
            )
            sender = sender_match.group(1).strip() if sender_match else ""

            rt_match = re.search(
                r"Reply-To:\s*(.+?)(?:\r?\n(?!\s)|\Z)",
                hdr_raw, re.IGNORECASE | re.DOTALL
            )
            reply_to = rt_match.group(1).strip() if rt_match else sender

            if any(skip in sender.lower() for skip in SKIP_SENDERS):
                log.info("Skipping sender: %s", subject[:50])
                continue

            if message_id in replied_ids:
                log.info("Already replied (Message-ID): %s", subject[:50])
                continue

            sender_addr = extract_address(reply_to or sender)
            if not sender_addr:
                log.warning("Could not extract sender email from: %s", sender)
                continue

            emails.append({
                "uid": uid_str,
                "message_id": message_id,
                "subject": subject,
                "sender": sender,
                "reply_to": reply_to,
                "sender_addr": sender_addr,
            })
            log.info("Queued: %s from %s", subject[:50], sender_addr)
            time.sleep(0.2)

        except Exception as e:
            log.error("Error reading email %s: %s", uid_str, e)
            time.sleep(1)

    log.info("Ready to process %d emails", len(emails))
    return emails, mail, replied_senders, send_count

# ══════════════════════════════════════════════════════════════════════════════
# ROLE DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def detect_role(email_obj):
    subject = email_obj["subject"].lower()

    # Check all defined roles by keyword
    for role in ROLES:
        if any(kw in subject for kw in role["keywords"]):
            log.info("Matched role: %s", role["name"])
            return role

    # Fallback: "sap" in subject + any finance keyword
    if "sap" in subject:
        for kw in FALLBACK_FINANCE_KEYWORDS:
            if kw in subject:
                log.info("Fallback → %s (matched fallback keyword '%s')", FALLBACK_ROLE["name"], kw)
                return FALLBACK_ROLE

    return None

# ══════════════════════════════════════════════════════════════════════════════
# LOAD RESUME (base64 file → bytes)
# ══════════════════════════════════════════════════════════════════════════════
def get_resume(role):
    fname = role["resume_file"]
    if not Path(fname).exists():
        raise ValueError("Resume file '{}' not found!".format(fname))
    log.info("Resume: %s", fname)
    raw = Path(fname).read_bytes()
    # Handle UTF-16 BOM (certutil output)
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode('utf-16').strip()
    else:
        text = raw.decode('latin-1').strip()
    # Strip certutil BEGIN/END headers and whitespace
    lines = text.splitlines()
    lines = [l for l in lines if not l.startswith("-----")]
    b64 = re.sub(r'\s+', '', "".join(lines))
    # Fix base64 padding
    missing = len(b64) % 4
    if missing:
        b64 += "=" * (4 - missing)
    return base64.b64decode(b64)

# ══════════════════════════════════════════════════════════════════════════════
# SEND REPLY
# ══════════════════════════════════════════════════════════════════════════════
def send_reply(email_obj, role, server):
    smtp_email = os.environ["RANA_SMTP_EMAIL"]
    to_email = extract_address(email_obj["reply_to"] or email_obj["sender"])
    cc_email = os.environ.get(role["cc_secret"], "")

    subject = email_obj["subject"]
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject

    msg = MIMEMultipart()
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc_email:
        msg["Cc"] = cc_email

    msg.attach(MIMEText(role["reply"], "plain"))

    resume_bytes = get_resume(role)
    part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part.set_payload(resume_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'attachment; filename="Rana_Pagadam_SAP_FICO_Resume.docx"')
    msg.attach(part)

    recipients = [to_email]
    if cc_email:
        recipients.append(cc_email)

    server.sendmail(smtp_email, recipients, msg.as_string())

    log.info("Sent from : %s", smtp_email)
    log.info("Sent to   : %s", to_email)
    if cc_email:
        log.info("CCd       : %s", cc_email)

    time.sleep(10)   # 8s delay — avoids Zoho 550 rate-limit errors

def log_sent(email_obj, role):
    csv_path = "logs/sent_log_rana.csv"
    is_new = not os.path.exists(csv_path)
    with open(csv_path, "a") as f:
        if is_new:
            f.write("timestamp,role,sender,subject,cc\n")
        cc = os.environ.get(role["cc_secret"], "none")
        f.write('{},\"{}\",\"{}\",\"{}\",\"{}\"\n'.format(
            datetime.now().isoformat(),
            role["name"],
            email_obj["sender"],
            email_obj["subject"],
            cc
        ))

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 70)
    log.info("AI Email Agent - Rana Pagadam (SAP FICO/FSCM/Treasury/S4HANA)")
    log.info("SCAN inbox : %s (Gmail IMAP)", os.environ.get("IMAP_EMAIL", "***"))
    log.info("SEND from  : %s (Zoho SMTP)", os.environ.get("RANA_SMTP_EMAIL", "***"))
    log.info("REMOTE ONLY: On-site / hybrid / local roles are SKIPPED")
    log.info("Time       : %s", datetime.now().isoformat())
    log.info("=" * 70)

    if not is_within_run_window():
        log.info("Outside run window (6:30 PM - 4:30 AM IST). Skipping.")
        return
    log.info("Within run window (6:30 PM - 4:30 AM IST). Proceeding...")

    required = ["IMAP_EMAIL", "IMAP_APP_PASSWORD", "RANA_SMTP_EMAIL", "RANA_SMTP_APP_PASSWORD"]
    missing = [r for r in required if not os.environ.get(r)]
    if missing:
        log.error("Missing env vars: %s", ", ".join(missing))
        return

    emails, mail, replied_senders, daily_send_count = fetch_matching_emails()

    remaining = MAX_DAILY_SENDS - daily_send_count
    log.info("Daily send budget: %d/%d used, %d remaining today",
             daily_send_count, MAX_DAILY_SENDS, remaining)
    if remaining <= 0:
        log.warning("Daily send limit already reached (%d/%d). Stopping.",
                    daily_send_count, MAX_DAILY_SENDS)
        try:
            mail.logout()
        except Exception:
            pass
        return

    smtp_email = os.environ["RANA_SMTP_EMAIL"]
    smtp_server = None
    try:
        smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
        smtp_server.login(smtp_email, os.environ["RANA_SMTP_APP_PASSWORD"])
        log.info("SMTP connected (Zoho): %s", smtp_email)
    except Exception as e:
        log.error("Could not connect to Zoho SMTP: %s", e)
        try:
            mail.logout()
        except Exception:
            pass
        return

    sent_senders = set()
    matched = 0

    for email_obj in emails:
        log.info("JOB EMAIL: %s", email_obj["subject"])
        log.info("   From: %s", email_obj["sender"])

        try:
            # ── REMOTE ONLY FILTER ──
            if is_onsite_or_hybrid(email_obj["subject"]):
                log.info("SKIPPING (ON-SITE/HYBRID): %s", email_obj["subject"][:60])
                continue

            # ── IRRELEVANT MODULE FILTER ──
            irr = is_irrelevant_module(email_obj["subject"])
            if irr:
                log.info("SKIPPING (IRRELEVANT MODULE '%s'): %s", irr, email_obj["subject"][:60].lower())
                continue

            sender_addr = email_obj.get("sender_addr",
                          extract_address(email_obj["reply_to"] or email_obj["sender"]))

            # ── DEDUP CHECKS ──
            if sender_addr in replied_senders:
                log.info("SKIPPING - already replied to %s today", sender_addr)
                continue

            if sender_addr in sent_senders:
                log.info("SKIPPING - already replied to %s in this run", sender_addr)
                continue

            # ── ROLE DETECTION ──
            role = detect_role(email_obj)
            if role is None:
                log.info("SKIPPING (NO MATCH - scores both 0): %s", email_obj["subject"][:60].lower())
                log.info("No SAP FICO role matched in subject - skipping")
                continue

            if daily_send_count >= MAX_DAILY_SENDS:
                log.warning("DAILY LIMIT REACHED (%d/%d) - stopping for today.",
                             daily_send_count, MAX_DAILY_SENDS)
                break

            matched += 1
            log.info("SENDING REPLY... (%d/%d) | Role: %s",
                     daily_send_count + 1, MAX_DAILY_SENDS, role["name"])
            send_reply(email_obj, role, smtp_server)
            log_sent(email_obj, role)
            mail = mark_as_replied(mail, email_obj["uid"])

            replied_senders.add(sender_addr)
            sent_senders.add(sender_addr)
            daily_send_count += 1

            # Save dedup immediately after every successful send
            save_daily_dedup(replied_senders, daily_send_count)

        except Exception as e:
            log.error("Error processing email: %s", e, exc_info=True)
            try:
                log.info("Reconnecting Zoho SMTP...")
                smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
                smtp_server.login(smtp_email, os.environ["RANA_SMTP_APP_PASSWORD"])
                log.info("Zoho SMTP reconnected successfully")
            except Exception as se:
                log.error("Zoho SMTP reconnect failed: %s", se)
                break

    try:
        smtp_server.quit()
        log.info("SMTP connection closed")
    except Exception:
        pass

    try:
        mail.logout()
    except Exception:
        pass

    log.info("=" * 70)
    log.info("Done - Replied to %d job emails", matched)
    log.info("On-site/hybrid skipped : (see log above)")
    log.info("SCAN account           : %s", os.environ.get("IMAP_EMAIL", "***"))
    log.info("SEND account           : %s", os.environ.get("RANA_SMTP_EMAIL", "***"))
    log.info("Daily sends            : %d/%d", daily_send_count, MAX_DAILY_SENDS)
    log.info("Daily dedup            : %s (resets at midnight)", str(DEDUP_FILE))
    log.info("Cost: 0.00")
    log.info("=" * 70)

if __name__ == "__main__":
    main()
