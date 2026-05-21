"""
AI Email Agent - Rajesh (BI Reporting Specialist)
Scans: sudheeritservices1@gmail.com (IMAP - Gmail)
Sends: sudheer@adeptscripts.com (SMTP - Zoho)
Replies to: Tableau, Power BI, Alteryx, BI Developer, Reporting Analyst roles
*** REMOTE ROLES ONLY - skips any email without "remote" in subject ***

FIXES:
1. Dedup checked FIRST before anything else
2. Dedup saved IMMEDIATELY after each send (not at the end)
3. UTF-8-sig fix for dedup file (BOM handling)
4. Skips own sent emails
5. REMOVED "Re:" skip - recruiters use RE: in fresh emails
6. SCAN from sudheeritservices1@gmail.com (Gmail IMAP)
7. SEND from sudheer@adeptscripts.com (Zoho SMTP)
8. Daily send cap (450) to avoid limit errors
9. SINGLE SMTP connection reused for all emails
10. 5 second delay between sends (avoids spam detection)
11. certutil base64 header strip + padding fix
12. BROAD IMAP search: "tableau", "power bi", "alteryx" - catches ALL variants
13. REMOVED UNSEEN filter - catches read and unread emails
14. REMOTE ONLY filter - skips any email without "remote" in subject
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
    handlers=[logging.FileHandler("logs/agent_rajesh_bi.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DAILY DEDUP - Resets every day at midnight
# ══════════════════════════════════════════════════════════════════════════════
DEDUP_FILE = Path("logs") / "daily_replied_senders_rajesh_bi.json"
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
# REMOTE ONLY CHECK
# ══════════════════════════════════════════════════════════════════════════════
REMOTE_KEYWORDS = [
    "remote",
    "work from home",
    "wfh",
    "100% remote",
    "fully remote",
    "remote only",
    "remote position",
    "remote role",
    "remote opportunity",
    "remote job",
    "remote work",
]

def is_remote_role(subject):
    subject_lower = subject.lower()
    return any(kw in subject_lower for kw in REMOTE_KEYWORDS)

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
FRISCO TX 7503
Recruitment Manager

www.adeptscripts.com

"""

ROLES = [
    {
        "name": "Tableau Developer / Specialist",
        "keywords": [
            "tableau developer",
            "tableau specialist",
            "tableau engineer",
            "tableau analyst",
            "tableau consultant",
            "senior tableau developer",
            "sr tableau developer",
            "lead tableau developer",
            "tableau desktop developer",
            "tableau reporting developer",
            "tableau bi developer",
            "tableau architect",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
    {
        "name": "Power BI Developer / Specialist",
        "keywords": [
            "power bi developer",
            "power bi specialist",
            "power bi engineer",
            "power bi analyst",
            "power bi consultant",
            "senior power bi developer",
            "sr power bi developer",
            "lead power bi developer",
            "power bi reporting developer",
            "power bi architect",
            "powerbi developer",
            "pbi developer",
            "microsoft power bi developer",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
    {
        "name": "Alteryx Developer / Specialist",
        "keywords": [
            "alteryx developer",
            "alteryx specialist",
            "alteryx engineer",
            "alteryx analyst",
            "alteryx consultant",
            "senior alteryx developer",
            "alteryx designer",
            "alteryx etl developer",
            "alteryx bi developer",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
    {
        "name": "BI Developer / Reporting Specialist",
        "keywords": [
            "bi developer",
            "bi reporting developer",
            "bi specialist",
            "bi analyst",
            "bi engineer",
            "bi consultant",
            "senior bi developer",
            "sr bi developer",
            "lead bi developer",
            "business intelligence developer",
            "business intelligence analyst",
            "business intelligence engineer",
            "business intelligence consultant",
            "reporting specialist",
            "reporting analyst",
            "reporting developer",
            "reporting engineer",
            "report developer",
            "senior reporting analyst",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
    {
        "name": "Data Visualization Developer",
        "keywords": [
            "data visualization developer",
            "data visualization engineer",
            "data visualization specialist",
            "data visualization analyst",
            "data viz developer",
            "visualization developer",
            "dashboard developer",
            "dashboard engineer",
            "dashboard analyst",
            "analytics developer",
            "analytics engineer",
            "analytics specialist",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
    {
        "name": "Tableau / Power BI Developer",
        "keywords": [
            "tableau/power bi",
            "power bi/tableau",
            "tableau and power bi",
            "power bi and tableau",
            "tableau or power bi",
            "power bi or tableau",
            "tableau power bi developer",
            "bi tools developer",
            "bi tools specialist",
        ],
        "resume_file": "resume_rajesh_bi_b64.txt",
        "cc_secret": "CC_RAJESH_BI",
        "reply": SHARED_REPLY,
    },
]

# Fallback: if subject has bi/tableau/power bi/alteryx but no keyword matched
FALLBACK_ROLE = {
    "name": "BI Reporting Specialist (General)",
    "keywords": [],
    "resume_file": "resume_rajesh_bi_b64.txt",
    "cc_secret": "CC_RAJESH_BI",
    "reply": SHARED_REPLY,
}

REPLIED_LABEL = "AutoReplied_Rajesh_BI"

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

def fetch_matching_emails():
    log.info("Connecting to Gmail via IMAP...")
    mail = connect_imap()
    ensure_label_exists(mail)
    replied_ids = get_replied_message_ids(mail)
    log.info("Gmail %s label: %d emails", REPLIED_LABEL, len(replied_ids))

    replied_senders, send_count = load_daily_dedup()
    today = datetime.now().strftime("%d-%b-%Y")

    # ── BROAD SEARCH: tableau, power bi, alteryx catch ALL BI variants ──
    all_uid_set = set()
    search_queries = [
        'SINCE "' + today + '" SUBJECT "tableau"',
        'SINCE "' + today + '" SUBJECT "power bi"',
        'SINCE "' + today + '" SUBJECT "alteryx"',
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
    log.info("Found %d matching emails today (tableau + power bi + alteryx)", len(ids))

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

def detect_role(email):
    subject = email["subject"].lower()

    # Check all roles by keyword
    for role in ROLES:
        if any(kw in subject for kw in role["keywords"]):
            log.info("Matched role: %s", role["name"])
            return role

    # Fallback: if subject contains tableau/power bi/alteryx
    if "tableau" in subject or "power bi" in subject or "alteryx" in subject:
        log.info("Fallback match: %s", FALLBACK_ROLE["name"])
        return FALLBACK_ROLE

    return None

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

def send_reply(email, role, server):
    smtp_email = os.environ["RAJESH_BI_SMTP_EMAIL"]  # sudheer@adeptscripts.com
    to_email = extract_address(email["reply_to"] or email["sender"])

    # Support multiple CC emails (comma-separated in secret)
    cc_raw = os.environ.get(role["cc_secret"], "")
    cc_list = [c.strip() for c in cc_raw.split(",") if c.strip()]

    subject = email["subject"]
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject

    msg = MIMEMultipart()
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.attach(MIMEText(role["reply"], "plain"))

    resume_bytes = get_resume(role)
    part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part.set_payload(resume_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'attachment; filename="Resume_Rajesh_BI_Reporting.docx"')
    msg.attach(part)

    recipients = [to_email] + cc_list

    server.sendmail(smtp_email, recipients, msg.as_string())

    log.info("Sent from : %s", smtp_email)
    log.info("Sent to   : %s", to_email)
    if cc_list:
        log.info("CCd       : %s", ", ".join(cc_list))

    time.sleep(10)

def log_sent(email, role):
    csv_path = "logs/sent_log_rajesh_bi.csv"
    is_new = not os.path.exists(csv_path)
    with open(csv_path, "a") as f:
        if is_new:
            f.write("timestamp,role,sender,subject,cc\n")
        cc = os.environ.get(role["cc_secret"], "none")
        f.write('{},"{}", "{}","{}","{}"\n'.format(
            datetime.now().isoformat(),
            role["name"],
            email["sender"],
            email["subject"],
            cc
        ))

def main():
    log.info("=" * 70)
    log.info("AI Email Agent - Rajesh (BI Reporting Specialist) - REMOTE ONLY")
    log.info("SCAN inbox : sudheeritservices1@gmail.com (Gmail IMAP)")
    log.info("SEND from  : sudheer@adeptscripts.com (Zoho SMTP)")
    log.info("Time       : %s", datetime.now().isoformat())
    log.info("=" * 70)

    if not is_within_run_window():
        log.info("Outside run window (6:30 PM - 4:30 AM IST). Skipping.")
        return
    log.info("Within run window (6:30 PM - 4:30 AM IST). Proceeding...")

    required = ["IMAP_EMAIL", "IMAP_APP_PASSWORD", "RAJESH_BI_SMTP_EMAIL", "RAJESH_BI_SMTP_APP_PASSWORD"]
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

    # Zoho SMTP settings
    smtp_email = os.environ["RAJESH_BI_SMTP_EMAIL"]
    smtp_server = None
    try:
        smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
        smtp_server.login(smtp_email, os.environ["RAJESH_BI_SMTP_APP_PASSWORD"])
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

    for email in emails:
        log.info("JOB EMAIL: %s", email["subject"])
        log.info("   From: %s", email["sender"])

        try:
            sender_addr = email.get("sender_addr", extract_address(email["reply_to"] or email["sender"]))

            # ── REMOTE ONLY FILTER ──
            if not is_remote_role(email["subject"]):
                log.info("SKIPPING - not a remote role: %s", email["subject"][:60])
                continue

            if sender_addr in replied_senders:
                log.info("SKIPPING - already replied to %s today", sender_addr)
                continue

            if sender_addr in sent_senders:
                log.info("SKIPPING - already replied to %s in this run", sender_addr)
                continue

            role = detect_role(email)
            if role is None:
                log.info("No BI role matched in subject - skipping")
                continue

            if daily_send_count >= MAX_DAILY_SENDS:
                log.warning("DAILY LIMIT REACHED (%d/%d) - stopping for today.", daily_send_count, MAX_DAILY_SENDS)
                break

            matched += 1
            log.info("REMOTE ROLE MATCHED ✓ (%d/%d) | Role: %s", daily_send_count + 1, MAX_DAILY_SENDS, role["name"])
            send_reply(email, role, smtp_server)
            log_sent(email, role)
            mail = mark_as_replied(mail, email["uid"])

            replied_senders.add(sender_addr)
            sent_senders.add(sender_addr)
            daily_send_count += 1

            # Save dedup immediately after every send
            save_daily_dedup(replied_senders, daily_send_count)

        except Exception as e:
            log.error("Error processing email: %s", e, exc_info=True)
            try:
                log.info("Reconnecting Zoho SMTP...")
                smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
                smtp_server.login(smtp_email, os.environ["RAJESH_BI_SMTP_APP_PASSWORD"])
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
    log.info("Done - Replied to %d remote BI job emails", matched)
    log.info("SCAN account : %s", os.environ.get("IMAP_EMAIL"))
    log.info("SEND account : %s", os.environ.get("RAJESH_BI_SMTP_EMAIL"))
    log.info("Daily sends  : %d/%d", daily_send_count, MAX_DAILY_SENDS)
    log.info("Daily dedup  : %s (resets at midnight)", str(DEDUP_FILE))
    log.info("Cost: 0.00")
    log.info("=" * 70)

if __name__ == "__main__":
    main()
