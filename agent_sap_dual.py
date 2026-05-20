"""
AI Email Agent - Dual SAP Consultants (Naga Ravi Kumar & Vamsee M)
Scans: sudheeritservices1@gmail.com (IMAP - Gmail)
Sends: sudheer@adeptscripts.com (SMTP - Zoho)

Replies to:
  - Naga Ravi Kumar : SAP S/4HANA Sales, SD, OTC, CVI, RAR roles
  - Vamsee M        : SAP SCM, SD, S/4HANA, Vistex, RAR, BRIM roles

REMOTE ONLY: Emails that contain on-site / hybrid / local keywords are skipped.

FEATURES (same as agent_siddarth):
 1. Dedup checked FIRST before anything else
 2. Dedup saved IMMEDIATELY after each send
 3. UTF-8-sig fix for dedup file (BOM handling)
 4. Skips own sent emails
 5. REMOVED "Re:" skip - recruiters use RE: in fresh emails
 6. SCAN from sudheeritservices1@gmail.com (Gmail IMAP)
 7. SEND from sudheer@adeptscripts.com (Zoho SMTP)
 8. Daily send cap (450) to avoid limit errors
 9. SINGLE SMTP connection reused for all emails
10. 5 second delay between sends (avoids spam detection)
11. certutil base64 header strip + padding fix
12. BROAD IMAP search: "sap" keyword - catches ALL SAP variants
13. REMOVED UNSEEN filter - catches read and unread emails
14. REMOTE ONLY filter - skips on-site / hybrid / local roles
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
        logging.FileHandler("logs/agent_sap_dual.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DAILY DEDUP - Resets every day at midnight
# ══════════════════════════════════════════════════════════════════════════════
DEDUP_FILE = Path("logs") / "daily_replied_senders_sap_dual.json"
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
# REMOTE-ONLY FILTER
# Keywords that indicate on-site / non-remote roles → SKIP
# ══════════════════════════════════════════════════════════════════════════════
ONSITE_KEYWORDS = [
    "on-site",
    "onsite",
    "on site",
    "in-office",
    "in office",
    "local only",
    "local candidate",
    "must be local",
    "office-based",
    "hybrid",          # remove this line if you want to accept hybrid roles too
    "no remote",
    "not remote",
]

REMOTE_POSITIVE_KEYWORDS = [
    "remote",
    "work from home",
    "work-from-home",
    "wfh",
    "fully remote",
    "100% remote",
    "telecommute",
    "virtual",
]

def is_remote_role(subject, body_snippet=""):
    """
    Returns True only if the email is clearly for a remote role.
    Logic:
      - If subject/body contains on-site keywords → NOT remote → skip
      - If subject/body contains remote keywords → remote → accept
      - If neither → assume remote-friendly and accept (recruiter may not specify)
    """
    text = (subject + " " + body_snippet).lower()

    if any(kw in text for kw in ONSITE_KEYWORDS):
        return False   # Explicitly on-site or hybrid → skip

    if any(kw in text for kw in REMOTE_POSITIVE_KEYWORDS):
        return True    # Explicitly remote → accept

    # No location type specified → accept (don't reject ambiguous emails)
    return True

# ══════════════════════════════════════════════════════════════════════════════
# REPLY TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════
REPLY_NAGA = """Hi,

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

REPLY_VAMSEE = """Hi,

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
# ROLES - Naga Ravi Kumar (SAP S/4HANA Sales / SD / OTC / CVI / RAR)
# ══════════════════════════════════════════════════════════════════════════════
ROLES_NAGA = [
    {
        "name": "SAP S/4HANA Sales / SD Consultant",
        "keywords": [
            "sap s/4hana sales",
            "sap s4hana sales",
            "sap s4 hana sales",
            "sap sd consultant",
            "sap sd functional",
            "sap sales distribution",
            "sap sales and distribution",
            "sap sd lead",
            "sap sd manager",
            "sap s/4hana sd",
            "sap s4 sd",
        ],
        "resume_file": "resume_naga_b64.txt",
        "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
        "cc_secret": "CC_NAGA",
        "reply": REPLY_NAGA,
    },
    {
        "name": "SAP OTC / Order to Cash Consultant",
        "keywords": [
            "sap otc",
            "sap order to cash",
            "order-to-cash consultant",
            "order to cash sap",
            "sap o2c",
            "sap otc consultant",
            "sap otc lead",
            "sap otc functional",
        ],
        "resume_file": "resume_naga_b64.txt",
        "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
        "cc_secret": "CC_NAGA",
        "reply": REPLY_NAGA,
    },
    {
        "name": "SAP CVI / Business Partner Consultant",
        "keywords": [
            "sap cvi",
            "sap business partner",
            "sap bp migration",
            "customer vendor integration",
            "sap customer vendor",
            "sap bp consultant",
        ],
        "resume_file": "resume_naga_b64.txt",
        "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
        "cc_secret": "CC_NAGA",
        "reply": REPLY_NAGA,
    },
    {
        "name": "SAP RAR / Revenue Accounting Consultant",
        "keywords": [
            "sap rar",
            "sap revenue accounting",
            "sap revenue recognition",
            "sap asc 606",
            "sap revenue accounting and reporting",
            "sap rar consultant",
            "sap rar functional",
        ],
        "resume_file": "resume_naga_b64.txt",
        "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
        "cc_secret": "CC_NAGA",
        "reply": REPLY_NAGA,
    },
    {
        "name": "SAP Pricing / Condition Technique Consultant",
        "keywords": [
            "sap pricing consultant",
            "sap condition technique",
            "sap pricing configuration",
            "sap rebate management",
            "sap promotions",
            "sap pricing functional",
        ],
        "resume_file": "resume_naga_b64.txt",
        "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
        "cc_secret": "CC_NAGA",
        "reply": REPLY_NAGA,
    },
]

# Fallback for Naga: any SAP SD / sales email not caught above
FALLBACK_NAGA = {
    "name": "SAP SD / S4HANA Sales (General) - Naga",
    "keywords": [],
    "resume_file": "resume_naga_b64.txt",
    "resume_filename": "Resume_NagaRaviKumar_SAP_SD.docx",
    "cc_secret": "CC_NAGA",
    "reply": REPLY_NAGA,
}

# ══════════════════════════════════════════════════════════════════════════════
# ROLES - Vamsee M (SAP SCM / SD / S4HANA / Vistex / RAR / BRIM)
# ══════════════════════════════════════════════════════════════════════════════
ROLES_VAMSEE = [
    {
        "name": "SAP SCM / Supply Chain Consultant",
        "keywords": [
            "sap scm consultant",
            "sap supply chain",
            "sap scm functional",
            "sap supply chain management",
            "sap scm lead",
            "sap scm manager",
        ],
        "resume_file": "resume_vamsee_b64.txt",
        "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
        "cc_secret": "CC_VAMSEE",
        "reply": REPLY_VAMSEE,
    },
    {
        "name": "SAP Vistex Consultant",
        "keywords": [
            "sap vistex",
            "vistex consultant",
            "vistex developer",
            "vistex functional",
            "vistex implementation",
            "sap vistex lead",
        ],
        "resume_file": "resume_vamsee_b64.txt",
        "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
        "cc_secret": "CC_VAMSEE",
        "reply": REPLY_VAMSEE,
    },
    {
        "name": "SAP BRIM / Subscription Management Consultant",
        "keywords": [
            "sap brim",
            "sap subscription order management",
            "brim consultant",
            "sap billing revenue innovation",
            "sap convergent invoicing",
            "sap ci consultant",
        ],
        "resume_file": "resume_vamsee_b64.txt",
        "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
        "cc_secret": "CC_VAMSEE",
        "reply": REPLY_VAMSEE,
    },
    {
        "name": "SAP Condition Contract Management / Rebates Consultant",
        "keywords": [
            "sap condition contract",
            "sap ccm consultant",
            "sap settlement management",
            "sap rebate management",
            "sap incentive management",
            "condition contract management",
        ],
        "resume_file": "resume_vamsee_b64.txt",
        "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
        "cc_secret": "CC_VAMSEE",
        "reply": REPLY_VAMSEE,
    },
    {
        "name": "SAP S/4HANA Functional Consultant",
        "keywords": [
            "sap s/4hana functional",
            "sap s4hana functional",
            "sap s4 hana functional",
            "s/4hana consultant",
            "s4hana consultant",
            "sap s4 hana consultant",
            "sap s4hana lead",
            "s4hana implementation",
            "sap hana functional",
            "sap s4 implementation",
            "sap greenfield",
            "sap brownfield",
        ],
        "resume_file": "resume_vamsee_b64.txt",
        "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
        "cc_secret": "CC_VAMSEE",
        "reply": REPLY_VAMSEE,
    },
]

# Fallback for Vamsee: any SAP SCM / functional email not caught above
FALLBACK_VAMSEE = {
    "name": "SAP Functional Consultant (General) - Vamsee",
    "keywords": [],
    "resume_file": "resume_vamsee_b64.txt",
    "resume_filename": "Resume_VamseeM_SAP_SCM.docx",
    "cc_secret": "CC_VAMSEE",
    "reply": REPLY_VAMSEE,
}

# ══════════════════════════════════════════════════════════════════════════════
# SUBJECT KEYWORDS for Naga vs Vamsee discrimination
# ══════════════════════════════════════════════════════════════════════════════
# These indicate the email is more suited for Naga (S/4 Sales / OTC / CVI / RAR)
NAGA_PRIMARY_KEYWORDS = [
    "otc", "order to cash", "order-to-cash", "o2c",
    "cvi", "customer vendor integration", "business partner migration",
    "rar", "revenue accounting", "asc 606", "revenue recognition",
    "sap sales", "sap sd",
    "s/4hana sales", "s4hana sales", "s4 hana sales",  # Naga-specific S/4HANA Sales
]

# These indicate Vamsee (SCM / Vistex / BRIM / S4HANA broad)
VAMSEE_PRIMARY_KEYWORDS = [
    "scm", "supply chain", "vistex", "brim", "subscription order",
    "condition contract", "ccm", "settlement management",
    "s/4hana", "s4hana", "s4 hana", "greenfield", "brownfield",
]

# ── Modules outside BOTH consultants' expertise → skip entirely ──────────────
# These are SAP-branded but neither Naga (SD/OTC) nor Vamsee (SCM/BRIM) covers them.
IRRELEVANT_KEYWORDS = [
    # Finance / Controlling (not SD or SCM)
    "fico", "fi/co", "fi co", "sap fi", "sap co ", "accounts payable",
    "accounts receivable", "general ledger", "asset accounting",
    "grant management", "funds management", "p2p finance",
    "cfin", "central finance",
    # Warehouse / Logistics (not SD)
    "ewm", "wm-le", "warehouse management", "sap wm ", " wm ",
    # Data / Analytics / Platform
    "datasphere", "datashere", "hana xsa", "hana wam", "sap btp",
    "sap cpi", "sap pi", "process integration", "sap po ", "sap avc",
    "sap analytics cloud", "sap bi ", "sap bw ",
    "data migration", "data conversion", "cutover lead",
    # HR
    "sap hcm", "sap successfactors", "sap ec ", "sap ecp",
    # Manufacturing / Quality
    "sap pp", "sap qm", "pp qm", "pp-pi", "production planning",
    "quality management",
    # Procurement (non-OTC)
    "sap ariba", "sap mdg", "indirect procurement", "sap mm ",
    "sap eam", "sap is-u", "sap isu", "is utilities",
    "sap gts", "sap drc", "sap concur", "sap sybase",
    # Oracle (completely different product)
    "oracle", "oracle cloud", "oracle ebs", "oracle fusion",
    "jde ", "peoplesoft",
    # Technical / ABAP
    "sap abap", "abap developer", "sap developer", "sap architect",
    "sap program manager", "sap project manager",
    "sap test", "sap uat", "sap qa", "test lead", "testing lead",
    "sit and uat",
]

# ══════════════════════════════════════════════════════════════════════════════
# IMAP search terms for SAP emails
# ══════════════════════════════════════════════════════════════════════════════
SAP_SEARCH_TERMS = ["sap", "s4hana", "s/4hana", "scm", "otc"]

REPLIED_LABEL = "AutoReplied_SAP_Dual"

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
# FETCH MATCHING EMAILS
# ══════════════════════════════════════════════════════════════════════════════
def fetch_matching_emails():
    log.info("Connecting to Gmail via IMAP...")
    mail = connect_imap()
    ensure_label_exists(mail)
    replied_ids = get_replied_message_ids(mail)
    log.info("Gmail %s label: %d emails", REPLIED_LABEL, len(replied_ids))

    replied_senders, send_count = load_daily_dedup()
    today = datetime.now().strftime("%d-%b-%Y")

    all_uid_set = set()
    for term in SAP_SEARCH_TERMS:
        q = 'SINCE "{}" SUBJECT "{}"'.format(today, term)
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
# ROLE DETECTION (returns role dict with consultant assignment)
# ══════════════════════════════════════════════════════════════════════════════
def detect_role(email_obj):
    subject = email_obj["subject"].lower()

    # 1. Check Naga-specific roles first
    for role in ROLES_NAGA:
        if any(kw in subject for kw in role["keywords"]):
            log.info("Matched NAGA role: %s", role["name"])
            return role

    # 2. Check Vamsee-specific roles
    for role in ROLES_VAMSEE:
        if any(kw in subject for kw in role["keywords"]):
            log.info("Matched VAMSEE role: %s", role["name"])
            return role

    # 3. Skip roles that are clearly outside both consultants' expertise
    irrelevant_hit = next((kw for kw in IRRELEVANT_KEYWORDS if kw in subject), None)
    if irrelevant_hit:
        log.info("SKIPPING (IRRELEVANT MODULE '%s'): %s", irrelevant_hit.strip(), subject[:60])
        return None

    # 4. Fallback discrimination: if subject has any SAP keyword, decide consultant
    sap_present = "sap" in subject or any(t in subject for t in SAP_SEARCH_TERMS)
    if sap_present:
        naga_score = sum(1 for kw in NAGA_PRIMARY_KEYWORDS if kw in subject)
        vamsee_score = sum(1 for kw in VAMSEE_PRIMARY_KEYWORDS if kw in subject)

        # Only use fallback if at least one consultant has a positive signal
        if naga_score > 0 and naga_score >= vamsee_score:
            log.info("Fallback → NAGA (naga_score=%d, vamsee_score=%d)", naga_score, vamsee_score)
            return FALLBACK_NAGA
        elif vamsee_score > 0:
            log.info("Fallback → VAMSEE (vamsee_score=%d, naga_score=%d)", vamsee_score, naga_score)
            return FALLBACK_VAMSEE
        else:
            # Both scores are 0 — no recognisable signal for either consultant → skip
            log.info("SKIPPING (NO MATCH - scores both 0): %s", subject[:60])
            return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
# RESUME LOADER (base64 txt file)
# ══════════════════════════════════════════════════════════════════════════════
def get_resume(role):
    fname = role["resume_file"]
    if not Path(fname).exists():
        raise ValueError("Resume file '{}' not found! Place the base64-encoded .txt file in the same directory.".format(fname))
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
    smtp_email = os.environ["SAP_SMTP_EMAIL"]       # sudheer@adeptscripts.com
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
    part.add_header("Content-Disposition", 'attachment; filename="{}"'.format(role["resume_filename"]))
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
    csv_path = "logs/sent_log_sap_dual.csv"
    is_new = not os.path.exists(csv_path)
    with open(csv_path, "a") as f:
        if is_new:
            f.write("timestamp,consultant,role,sender,subject,cc\n")
        cc = os.environ.get(role["cc_secret"], "none")
        consultant = "Naga" if "naga" in role["resume_file"] else "Vamsee"
        f.write('{},"{}", "{}","{}","{}","{}"\n'.format(
            datetime.now().isoformat(),
            consultant,
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
    log.info("AI Email Agent - Dual SAP Consultants (Naga Ravi Kumar & Vamsee M)")
    log.info("SCAN inbox : sudheeritservices1@gmail.com (Gmail IMAP)")
    log.info("SEND from  : sudheer@adeptscripts.com (Zoho SMTP)")
    log.info("REMOTE ONLY: On-site / hybrid / local roles are SKIPPED")
    log.info("Time       : %s", datetime.now().isoformat())
    log.info("=" * 70)

    if not is_within_run_window():
        log.info("Outside run window (6:30 PM - 4:30 AM IST). Skipping.")
        return
    log.info("Within run window (6:30 PM - 4:30 AM IST). Proceeding...")

    required = ["IMAP_EMAIL", "IMAP_APP_PASSWORD", "SAP_SMTP_EMAIL", "SAP_SMTP_APP_PASSWORD"]
    missing = [r for r in required if not os.environ.get(r)]
    if missing:
        log.error("Missing env vars: %s", ", ".join(missing))
        log.error("Required env vars:")
        log.error("  IMAP_EMAIL              - Gmail address to scan")
        log.error("  IMAP_APP_PASSWORD       - Gmail app password")
        log.error("  SAP_SMTP_EMAIL          - Zoho send-from address")
        log.error("  SAP_SMTP_APP_PASSWORD   - Zoho SMTP app password")
        log.error("  CC_NAGA   (optional)    - CC address for Naga emails")
        log.error("  CC_VAMSEE (optional)    - CC address for Vamsee emails")
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

    # Connect Zoho SMTP
    smtp_email = os.environ["SAP_SMTP_EMAIL"]
    smtp_server = None
    try:
        smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
        smtp_server.login(smtp_email, os.environ["SAP_SMTP_APP_PASSWORD"])
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
    skipped_onsite = 0

    for email_obj in emails:
        log.info("JOB EMAIL: %s", email_obj["subject"])
        log.info("   From: %s", email_obj["sender"])

        try:
            sender_addr = email_obj.get("sender_addr", extract_address(email_obj["reply_to"] or email_obj["sender"]))

            if sender_addr in replied_senders:
                log.info("SKIPPING - already replied to %s today", sender_addr)
                continue

            if sender_addr in sent_senders:
                log.info("SKIPPING - already replied to %s in this run", sender_addr)
                continue

            # ── REMOTE-ONLY CHECK ──────────────────────────────────────────
            if not is_remote_role(email_obj["subject"]):
                log.info("SKIPPING (ON-SITE/HYBRID): %s", email_obj["subject"][:60])
                skipped_onsite += 1
                continue

            role = detect_role(email_obj)
            if role is None:
                log.info("No SAP role matched in subject - skipping")
                continue

            if daily_send_count >= MAX_DAILY_SENDS:
                log.warning("DAILY LIMIT REACHED (%d/%d) - stopping for today.", daily_send_count, MAX_DAILY_SENDS)
                break

            matched += 1
            log.info(
                "SENDING REPLY... (%d/%d) | Consultant: %s | Role: %s",
                daily_send_count + 1,
                MAX_DAILY_SENDS,
                "Naga" if "naga" in role["resume_file"] else "Vamsee",
                role["name"]
            )
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
                log.info("Reconnecting Zoho SMTP...")
                smtp_server = smtplib.SMTP_SSL("smtp.zoho.com", 465)
                smtp_server.login(smtp_email, os.environ["SAP_SMTP_APP_PASSWORD"])
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
    log.info("On-site/hybrid skipped : %d", skipped_onsite)
    log.info("SCAN account           : %s", os.environ.get("IMAP_EMAIL"))
    log.info("SEND account           : %s", os.environ.get("SAP_SMTP_EMAIL"))
    log.info("Daily sends            : %d/%d", daily_send_count, MAX_DAILY_SENDS)
    log.info("Daily dedup            : %s (resets at midnight)", str(DEDUP_FILE))
    log.info("Cost: 0.00")
    log.info("=" * 70)

if __name__ == "__main__":
    main()
