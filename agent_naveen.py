"""
AI Email Agent - Naveen Kumar Kadiyala (SAP SD / OTC / Logistics Consultant)
Scans: sudheeritservices1@gmail.com (IMAP - Gmail)
Sends: sudheer@adeptscripts.com (SMTP - Gmail)
Replies to: SAP SD, OTC, Order-to-Cash, Pricing, Shipping, WM, LE roles
REMOTE ONLY: On-site / hybrid / local roles are SKIPPED

FIXES:
1. Dedup checked FIRST before anything else
2. Dedup saved IMMEDIATELY after each send (not at the end)
3. UTF-8-sig fix for dedup file (BOM handling)
4. Skips own sent emails
5. REMOVED "Re:" skip - recruiters use RE: in fresh emails
6. SCAN from sudheeritservices1@gmail.com (Gmail IMAP)
7. SEND from sudheer@adeptscripts.com (Gmail SMTP)
8. Daily send cap (450) to avoid limit errors
9. SINGLE SMTP connection reused for all emails
10. 5 second delay between sends (avoids spam detection)
11. certutil base64 header strip + padding fix
12. BROAD IMAP search: "SAP" - catches ALL SAP variants
13. REMOVED UNSEEN filter - catches read and unread emails
14. REMOTE ONLY - skips onsite / hybrid / local roles
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
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/agent_naveen.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DAILY DEDUP - Resets every day at midnight
# ══════════════════════════════════════════════════════════════════════════════
DEDUP_FILE = Path("logs") / "daily_replied_senders_naveen.json"
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
                    log.info("TODAY (%s): %d senders, %d/%d sent so far", today, len(senders), send_count, MAX_DAILY_SENDS)
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
        log.info("SAVED TO DEDUP: %d senders, %d/%d sent today", len(senders), send_count, MAX_DAILY_SENDS)
    except Exception as e:
        log.error("Could not save dedup file: %s", e)

# ══════════════════════════════════════════════════════════════════════════════
# TIME WINDOW CHECK
# ══════════════════════════════════════════════════════════════════════════════
def is_within_run_window():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    current_time = now.time()
    start = dtime(18, 30)
    end = dtime(4, 30)
    return current_time >= start or current_time <= end

# ══════════════════════════════════════════════════════════════════════════════
# REMOTE ONLY - onsite/hybrid/local detection
# ══════════════════════════════════════════════════════════════════════════════
ONSITE_PATTERNS = [
    r"\bonsite\b", r"\bon-site\b", r"\bon site\b",
    r"\bhybrid\b",
    r"\blocal\b", r"\blocals\b", r"\blocal only\b", r"\blocal candidate\b",
    r"\bday.?1 onsite\b", r"\bday one onsite\b",
    r"\bin.person\b", r"\bin person\b",
]

def is_onsite_or_hybrid(subject):
    s = subject.lower()
    for pattern in ONSITE_PATTERNS:
        if re.search(pattern, s):
            return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
# IRRELEVANT MODULE FILTER - skip roles outside Naveen's expertise
# ══════════════════════════════════════════════════════════════════════════════
IRRELEVANT_MODULES = [
    "sap fico", "sap fi/co", "sap fi co", "sap finance", "sap treasury",
    "sap fscm", "sap copa", "sap co ", "sap fi ", "sap ap ", "sap ar ",
    "sap hcm", "sap successfactors", "sap basis", "sap abap",
    "sap bw", "sap bi", "sap datasphere", "sap datashere",
    "sap hana xsa", "sap is-u", "sap is utilities",
    "sap eam", "sap pm", "sap gts", "sap btp", "sap cpi", "sap pi",
    "sap concur", "sap ariba", "sap mdg", "sap master data",
    "sap analytics cloud", "sap data conversion",
    "sap test", "testing lead", "uat tester", "sap qa",
    "sap project manager", "sap program manager",
    "sap developer", "abap developer",
    "sap convergent", "sap brim",
    "salesforce", "oracle", "workday",
    "sap pp ", "sap qm",
]

def is_irrelevant_module(subject):
    s = subject.lower()
    for mod in IRRELEVANT_MODULES:
        if mod in s:
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
# ROLES - SAP SD / OTC / Logistics focus
# ══════════════════════════════════════════════════════════════════════════════
ROLES = [
    {
        "name": "SAP SD / OTC Consultant",
        "keywords": [
            "sap sd",
            "sap sales and distribution",
            "sap sales & distribution",
            "order to cash",
            "order-to-cash",
            "otc consultant",
            "sap otc",
            "quote to cash",
            "quote-to-cash",
            "sap sd consultant",
            "sap sd lead",
            "sap sd functional",
            "sap sd otc",
            "senior sap sd",
            "sr sap sd",
            "lead sap sd",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP SD Pricing / Condition Technique Consultant",
        "keywords": [
            "sap pricing",
            "sap sd pricing",
            "condition technique",
            "pricing procedure",
            "sap condition",
            "sap rebate",
            "sap discount",
            "sap free goods",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP SD Billing / Revenue Consultant",
        "keywords": [
            "sap billing",
            "sap sd billing",
            "revenue account determination",
            "sap invoice",
            "sap invoicing",
            "sap billing consultant",
            "sap credit memo",
            "sap debit memo",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Logistics Execution / Shipping Consultant",
        "keywords": [
            "sap logistics execution",
            "sap le consultant",
            "sap shipping",
            "sap delivery",
            "sap transportation",
            "sap shipment",
            "post goods issue",
            "sap pgi",
            "sap outbound delivery",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP WM / Warehouse Management Consultant",
        "keywords": [
            "sap wm",
            "sap wm-le",
            "sap warehouse management",
            "sap ewm",
            "warehouse management consultant",
            "sap wm consultant",
            "sap storage bin",
            "sap picking",
            "sap wm le",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP S/4HANA Sales / Simple Logistics Consultant",
        "keywords": [
            "sap s/4hana sales",
            "sap s4hana sales",
            "s/4hana sd",
            "s4hana sd",
            "s/4 hana sd",
            "s4 hana sd",
            "sap simple logistics",
            "sap s/4 sales",
            "sap s4 sales",
            "sap s/4hana otc",
            "s4hana otc",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP Credit Management Consultant",
        "keywords": [
            "sap credit management",
            "sap credit check",
            "sap fscm credit",
            "credit management consultant",
            "sap credit limit",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
    {
        "name": "SAP AFS / Variant Configuration Consultant",
        "keywords": [
            "sap afs",
            "sap variant configuration",
            "sap vc consultant",
            "variant configuration consultant",
            "sap avc",
            "advanced variant configuration",
        ],
        "resume_file": "resume_naveen_b64.txt",
        "cc_secret": "CC_NAVEEN",
        "reply": SHARED_REPLY,
    },
]

# Fallback: subject has "sap sd" or "sap" + sales/logistics keyword
FALLBACK_ROLE = {
    "name": "SAP SD / Sales Consultant (General)",
    "keywords": [],
    "resume_file": "resume_naveen_b64.txt",
    "cc_secret": "CC_NAVEEN",
    "reply": SHARED_REPLY,
}

FALLBACK_KEYWORDS = [
    "sap sd", "sales distribution", "order to cash", "otc",
    "sap sales", "sap logistics", "sap shipping", "sap delivery",
    "sap wm", "sap ewm", "warehouse management",
    "sap s/4hana", "sap s4hana", "s/4 hana", "s4 hana",
]

REPLIED_LABEL = "AutoReplied_SAP_Naveen"

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

    # BROAD SEARCH - "SAP" catches all SAP variants
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

            subj_match = re.search(r"Subject:\s*(.+?)(?:\r?\n(?!\s)|\Z)", hdr_raw, re.IGNORECASE | re.DOTALL)
            subject = subj_match.group(1).strip().replace("\r\n", " ").replace("\n", " ") if subj_match else ""

            mid_match = re.search(r"Message-ID:\s*(.+)", hdr_raw, re.IGNORECASE)
            message_id = mid_match.group(1).strip() if mid_match else uid_str

            sender_match = re.search(r"From:\s*(.+?)(?:\r?\n(?!\s)|\Z)", hdr_raw, re.IGNORECASE | re.DOTALL)
            sender = sender_match.group(1).strip() if sender_match else ""

            rt_match = re.search(r"Reply-To:\s*(.+?)(?:\r?\n(?!\s)|\Z)", hdr_raw, re.IGNORECASE | re.DOTALL)
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
                "sender_addr": sender_addr
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

    # Fallback: "sap" in subject + any SD/logistics keyword
    if "sap" in subject:
        for kw in FALLBACK_KEYWORDS:
            if kw in subject:
                log.info("Fallback → %s (matched '%s')", FALLBACK_ROLE["name"], kw)
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
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode('utf-16').strip()
    else:
        text = raw.decode('latin-1').strip()
    # Strip certutil BEGIN/END headers and all whitespace
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
    smtp_email = os.environ["NAVEEN_GMAIL_EMAIL"]
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
    part.add_header("Content-Disposition", 'attachment; filename="Naveen_Kumar_SAP_SD_Resume.docx"')
    msg.attach(part)

    recipients = [to_email]
    if cc_email:
        recipients.append(cc_email)

    server.sendmail(smtp_email, recipients, msg.as_string())

    log.info("Sent from : %s", smtp_email)
    log.info("Sent to   : %s", to_email)
    if cc_email:
        log.info("CCd       : %s", cc_email)

    time.sleep(5)

def log_sent(email_obj, role):
    csv_path = "logs/sent_log_naveen.csv"
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
    log.info("AI Email Agent - Naveen Kumar Kadiyala (SAP SD / OTC / Logistics)")
    log.info("SCAN inbox : %s (Gmail IMAP)", os.environ.get("IMAP_EMAIL", "***"))
    log.info("SEND from  : %s (Gmail SMTP)", os.environ.get("NAVEEN_GMAIL_EMAIL", "***"))
    log.info("REMOTE ONLY: On-site / hybrid / local roles are SKIPPED")
    log.info("Time       : %s", datetime.now().isoformat())
    log.info("=" * 70)

    if not is_within_run_window():
        log.info("Outside run window (6:30 PM - 4:30 AM IST). Skipping.")
        return
    log.info("Within run window (6:30 PM - 4:30 AM IST). Proceeding...")

    required = ["IMAP_EMAIL", "IMAP_APP_PASSWORD", "NAVEEN_GMAIL_EMAIL", "NAVEEN_GMAIL_APP_PASSWORD"]
    missing = [r for r in required if not os.environ.get(r)]
    if missing:
        log.error("Missing env vars: %s", ", ".join(missing))
        return

    emails, mail, replied_senders, daily_send_count = fetch_matching_emails()

    remaining = MAX_DAILY_SENDS - daily_send_count
    log.info("Daily send budget: %d/%d used, %d remaining today", daily_send_count, MAX_DAILY_SENDS, remaining)
    if remaining <= 0:
        log.warning("Daily send limit already reached (%d/%d). Stopping.", daily_send_count, MAX_DAILY_SENDS)
        try:
            mail.logout()
        except Exception:
            pass
        return

    smtp_email = os.environ["NAVEEN_GMAIL_EMAIL"]
    smtp_server = None
    try:
        smtp_server = smtplib.SMTP("smtp.gmail.com", 587)
        smtp_server.starttls()
        smtp_server.login(smtp_email, os.environ["NAVEEN_GMAIL_APP_PASSWORD"])
        log.info("SMTP connected (Gmail): %s", smtp_email)
    except Exception as e:
        log.error("Could not connect to Gmail SMTP: %s", e)
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

            sender_addr = email_obj.get("sender_addr", extract_address(email_obj["reply_to"] or email_obj["sender"]))

            if sender_addr in replied_senders:
                log.info("SKIPPING - already replied to %s today", sender_addr)
                continue

            if sender_addr in sent_senders:
                log.info("SKIPPING - already replied to %s in this run", sender_addr)
                continue

            role = detect_role(email_obj)
            if role is None:
                log.info("No SAP SD / OTC role matched in subject - skipping")
                continue

            if daily_send_count >= MAX_DAILY_SENDS:
                log.warning("DAILY LIMIT REACHED (%d/%d) - stopping for today.", daily_send_count, MAX_DAILY_SENDS)
                break

            matched += 1
            log.info("SENDING REPLY... (%d/%d) | Role: %s", daily_send_count + 1, MAX_DAILY_SENDS, role["name"])
            send_reply(email_obj, role, smtp_server)
            log_sent(email_obj, role)
            mail = mark_as_replied(mail, email_obj["uid"])

            replied_senders.add(sender_addr)
            sent_senders.add(sender_addr)
            daily_send_count += 1

            # Save dedup immediately after every send
            save_daily_dedup(replied_senders, daily_send_count)

        except Exception as e:
            log.error("Error processing email: %s", e, exc_info=True)
            try:
                log.info("Reconnecting Gmail SMTP...")
                smtp_server = smtplib.SMTP("smtp.gmail.com", 587)
                smtp_server.starttls()
                smtp_server.login(smtp_email, os.environ["NAVEEN_GMAIL_APP_PASSWORD"])
                log.info("Gmail SMTP reconnected successfully")
            except Exception as se:
                log.error("Gmail SMTP reconnect failed: %s", se)
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
    log.info("SEND account           : %s", os.environ.get("NAVEEN_GMAIL_EMAIL", "***"))
    log.info("Daily sends            : %d/%d", daily_send_count, MAX_DAILY_SENDS)
    log.info("Daily dedup            : %s (resets at midnight)", str(DEDUP_FILE))
    log.info("Cost: 0.00")
    log.info("=" * 70)

if __name__ == "__main__":
    main()
