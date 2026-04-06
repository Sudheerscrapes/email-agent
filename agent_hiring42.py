import os, base64, logging, re, json, time, smtplib
from pathlib import Path
from datetime import datetime, date, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import requests

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/agent_hiring42_api.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# =============================================================================
#  HIRING42 API
# =============================================================================
API_URL = "https://m9l0gpbw58.execute-api.ap-south-1.amazonaws.com/Prod/get-jobs"
HEADERS = {
    "Content-Type": "application/json",
    "Origin":       "https://www.hiring42.com",
    "Referer":      "https://www.hiring42.com/",
}

DEDUP_FILE      = Path("logs") / "daily_replied_senders_api.json"
MAX_DAILY_SENDS = 450

# =============================================================================
#  EMAIL BODY
# =============================================================================
SHARED_REPLY = """Hi,

In response to your job posting.
Here I am attaching my consultant's resume.
Please review the resume and let me know if it matches your position.
Looking forward to working with you.

Best regards,
Lingaraju Modhala
Phone: +1 940 281 5324
Email: rajumodhala777@gmail.com"""

# =============================================================================
#  JOB PROFILES
# =============================================================================
PROFILES = [
    {
        "name": "DevOps Engineer",
        "keywords": [
            "devops", "devsecops", "dev ops",
            "ci/cd", "build and release", "release engineer", "pipeline engineer",
        ],
        "cc_secret":  "CC_DEVOPS",
        "resume_file": "resume_lingaraju_b64.txt",
    },
    {
        "name": "Cloud Engineer",
        "keywords": [
            "cloud engineer", "cloud architect", "cloud infrastructure",
            "aws", "azure", "gcp", "platform engineer", "infrastructure engineer",
        ],
        "cc_secret":  "CC_CLOUD",
        "resume_file": "resume_lingaraju_b64.txt",
    },
    {
        "name": "Site Reliability Engineer",
        "keywords": ["site reliability", "sre", "reliability engineer"],
        "cc_secret":  "CC_SRE",
        "resume_file": "resume_lingaraju_b64.txt",
    },
    {
        "name": "Kubernetes / Container Engineer",
        "keywords": ["kubernetes", "k8s", "docker", "openshift", "container engineer"],
        "cc_secret":  "CC_DEVOPS",
        "resume_file": "resume_lingaraju_b64.txt",
    },
    {
        "name": "Terraform / Automation Engineer",
        "keywords": ["terraform", "ansible", "argocd", "gitops",
                     "infrastructure automation", "jenkins", "gitlab", "helm"],
        "cc_secret":  "CC_DEVOPS",
        "resume_file": "resume_lingaraju_b64.txt",
    },
]

SKIP_EMAILS = [
    "rajumodhala777@gmail.com",
    "sudheeritservices1@gmail.com",
    "noreply@",
    "mailer-daemon@",
]

def get_profile_for_title(title):
    t = title.lower()
    for profile in PROFILES:
        if any(kw in t for kw in profile["keywords"]):
            return profile
    return None

# =============================================================================
#  DATE FILTER
# =============================================================================
def get_today_utc_range():
    """Return (start_ts, end_ts) for today in UTC."""
    now   = datetime.now(timezone.utc)
    start = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
    end   = start + 86400
    return start, end

def get_date_utc_range(year, month, day):
    """Return (start_ts, end_ts) for a specific date in UTC."""
    start = int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())
    end   = start + 86400
    return start, end

def ts_to_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y %H:%M UTC")

# =============================================================================
#  API FETCH  —  paginate through ALL jobs
# =============================================================================
def fetch_all_jobs():
    """
    Fetch every active job from hiring42 API using pagination.
    Returns list of all job dicts.
    """
    all_items          = []
    last_evaluated_key = None
    page               = 1

    while True:
        payload = {
            "context":            "all_jobs",
            "last_evaluated_key": last_evaluated_key,
            "status":             "active",
            "uid":                None,
        }
        log.info("Fetching page %d ...", page)
        try:
            resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("API error on page %d: %s", page, e)
            break

        items = data.get("Items", [])
        all_items.extend(items)
        log.info("  Page %d: %d items (total so far: %d)", page, len(items), len(all_items))

        last_evaluated_key = data.get("LastEvaluatedKey")
        if not last_evaluated_key:
            log.info("No more pages. Done fetching.")
            break

        page     += 1
        time.sleep(0.3)   # be polite to the API

    return all_items

# =============================================================================
#  FILTER JOBS BY DATE
# =============================================================================
def filter_by_date(jobs, start_ts, end_ts):
    return [j for j in jobs if start_ts <= j.get("ts", 0) < end_ts]

# =============================================================================
#  DEDUP
# =============================================================================
def get_today_date():
    return str(date.today())

def load_daily_dedup():
    if DEDUP_FILE.exists():
        try:
            with open(DEDUP_FILE, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                if data.get("date") == get_today_date():
                    senders    = set(data.get("senders", []))
                    send_count = data.get("send_count", 0)
                    log.info("TODAY: %d already sent, %d/%d limit",
                             len(senders), send_count, MAX_DAILY_SENDS)
                    return senders, send_count
                else:
                    log.info("NEW DAY - Resetting dedup")
                    return set(), 0
        except Exception as e:
            log.warning("Could not load dedup: %s", e)
    return set(), 0

def save_daily_dedup(senders, send_count=0):
    data = {"date": get_today_date(), "senders": sorted(list(senders)), "send_count": send_count}
    with open(DEDUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    log.info("SAVED: %d senders, %d sent today", len(senders), send_count)

# =============================================================================
#  RESUME
# =============================================================================
def get_resume(fname="resume_lingaraju_b64.txt"):
    if not Path(fname).exists():
        raise ValueError(f"Resume file not found: {fname}")
    raw = Path(fname).read_bytes()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode('utf-16').strip()
    else:
        text = raw.decode('latin-1').strip()
    lines = [l for l in text.splitlines() if not l.startswith("-----")]
    b64   = re.sub(r'\s+', '', "".join(lines))
    missing = len(b64) % 4
    if missing:
        b64 += "=" * (4 - missing)
    return base64.b64decode(b64)

# =============================================================================
#  EMAIL
# =============================================================================
def connect_smtp():
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(os.environ["SMTP_EMAIL"], os.environ["SMTP_APP_PASSWORD"])
    return server

def reconnect_smtp(old):
    try: old.quit()
    except: pass
    try:
        s = connect_smtp()
        log.info("SMTP reconnected")
        return s
    except Exception as e:
        log.error("SMTP reconnect failed: %s", e)
        return None

def send_email(job, smtp_server):
    smtp_email = os.environ["SMTP_EMAIL"]
    to_email   = job["uid"]
    cc_email   = os.environ.get(job["cc_secret"], "")
    subject    = "Re: " + job["title"]

    msg            = MIMEMultipart()
    msg["From"]    = smtp_email
    msg["To"]      = to_email
    msg["Subject"] = subject
    if cc_email:
        msg["Cc"] = cc_email

    msg.attach(MIMEText(SHARED_REPLY, "plain"))

    resume_bytes = get_resume(job.get("resume_file", "resume_lingaraju_b64.txt"))
    part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
    part.set_payload(resume_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'attachment; filename="Resume_Lingaraju_Modhala.docx"')
    msg.attach(part)

    recipients = [to_email]
    if cc_email:
        for cc in cc_email.split(","):
            cc = cc.strip()
            if cc and cc not in recipients:
                recipients.append(cc)

    smtp_server.sendmail(smtp_email, recipients, msg.as_string())
    log.info(">>> SENT [%s]: %s | Subject: %s",
             job.get("profile_name", ""), to_email, subject)

def log_sent(job):
    csv_path = "logs/sent_log_api.csv"
    is_new   = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8") as f:
        if is_new:
            f.write("timestamp,email,title,profile,loc\n")
        f.write('{}, "{}","{}","{}","{}"\n'.format(
            datetime.now().isoformat(),
            job["uid"], job["title"],
            job.get("profile_name", ""), job.get("loc", ""),
        ))

# =============================================================================
#  MAIN  —  fetch all → filter today → match → send immediately
# =============================================================================
def main():
    log.info("=" * 70)
    log.info("AI Email Agent - Lingaraju Modhala (hiring42 API)")
    log.info("=" * 70)

    required = ["SMTP_EMAIL", "SMTP_APP_PASSWORD"]
    missing  = [r for r in required if not os.environ.get(r)]
    if missing:
        log.error("Missing env vars: %s", ", ".join(missing))
        return

    replied_senders, daily_send_count = load_daily_dedup()
    if daily_send_count >= MAX_DAILY_SENDS:
        log.warning("Daily limit already reached.")
        return

    # ── Fetch ALL jobs from API ───────────────────────────────────────────
    log.info("Fetching all jobs from API ...")
    all_jobs = fetch_all_jobs()
    log.info("Total active jobs in API: %d", len(all_jobs))

    # ── Filter to today only ──────────────────────────────────────────────
    start_ts, end_ts = get_today_utc_range()
    today_jobs       = filter_by_date(all_jobs, start_ts, end_ts)
    log.info("Jobs posted today: %d", len(today_jobs))

    if not today_jobs:
        log.info("No jobs posted today. Exiting.")
        return

    # ── Print all today's jobs ────────────────────────────────────────────
    log.info("-" * 70)
    log.info("ALL JOBS POSTED TODAY:")
    for j in today_jobs:
        log.info("  [%s] %s | %s | %s", ts_to_str(j["ts"]), j["title"], j.get("loc",""), j["uid"])
    log.info("-" * 70)

    # ── Connect SMTP ──────────────────────────────────────────────────────
    try:
        smtp_server = connect_smtp()
        log.info("SMTP connected")
    except Exception as e:
        log.error("SMTP failed: %s", e)
        return

    sent = 0

    # ── Match & send immediately ──────────────────────────────────────────
    for job in today_jobs:
        if daily_send_count >= MAX_DAILY_SENDS:
            log.warning("DAILY LIMIT REACHED.")
            break

        email_addr = job.get("uid", "").lower()
        title      = job.get("title", "")

        # Skip own / bad emails
        if not email_addr or any(s in email_addr for s in SKIP_EMAILS):
            continue

        # Skip already sent today
        if email_addr in replied_senders:
            log.info("SKIP (already sent): %s", email_addr)
            continue

        # Match profile
        profile = get_profile_for_title(title)
        if not profile:
            log.info("NO MATCH: %s | %s", title, email_addr)
            continue

        job["profile_name"] = profile["name"]
        job["cc_secret"]    = profile["cc_secret"]
        job["resume_file"]  = profile["resume_file"]

        log.info("MATCH [%s]: %s -> %s", profile["name"], title, email_addr)
        log.info("SENDING NOW [%d/%d] ...", daily_send_count + 1, MAX_DAILY_SENDS)

        try:
            send_email(job, smtp_server)
            log_sent(job)
            replied_senders.add(email_addr)
            daily_send_count += 1
            sent             += 1
            save_daily_dedup(replied_senders, daily_send_count)
            time.sleep(5)
        except Exception as e:
            log.error("Send error %s: %s", email_addr, e)
            smtp_server = reconnect_smtp(smtp_server)
            if smtp_server is None:
                break

    try:
        smtp_server.quit()
    except Exception:
        pass

    log.info("=" * 70)
    log.info("Done - Sent: %d | Daily total: %d/%d", sent, daily_send_count, MAX_DAILY_SENDS)
    log.info("=" * 70)


# =============================================================================
#  BONUS: run in "view only" mode to just see today's jobs without sending
#  Usage:  python agent_hiring42_api.py --view
#          python agent_hiring42_api.py --view --date 2026-04-03
# =============================================================================
if __name__ == "__main__":
    import sys

    if "--view" in sys.argv:
        # Find --date YYYY-MM-DD argument
        target_date = None
        if "--date" in sys.argv:
            idx = sys.argv.index("--date")
            if idx + 1 < len(sys.argv):
                try:
                    y, m, d   = sys.argv[idx + 1].split("-")
                    target_date = (int(y), int(m), int(d))
                except Exception:
                    print("Invalid date format. Use: --date YYYY-MM-DD")
                    sys.exit(1)

        if target_date:
            start_ts, end_ts = get_date_utc_range(*target_date)
            label = f"{target_date[0]}-{target_date[1]:02d}-{target_date[2]:02d}"
        else:
            start_ts, end_ts = get_today_utc_range()
            label = "TODAY"

        print(f"\n{'='*70}")
        print(f"  HIRING42 — ALL JOBS FOR: {label}")
        print(f"{'='*70}\n")

        all_jobs   = fetch_all_jobs()
        jobs       = filter_by_date(all_jobs, start_ts, end_ts)
        matched    = [(j, get_profile_for_title(j["title"])) for j in jobs]

        print(f"Total active jobs in API : {len(all_jobs)}")
        print(f"Jobs for {label}         : {len(jobs)}")
        print(f"Matching your profiles   : {sum(1 for _,p in matched if p)}")
        print()

        print(f"{'#':<4} {'TIME (UTC)':<22} {'TITLE':<45} {'EMAIL':<38} {'LOC':<20} PROFILE")
        print("-" * 160)
        for i, (j, profile) in enumerate(matched, 1):
            pname = profile["name"] if profile else "--- no match ---"
            print(f"{i:<4} {ts_to_str(j['ts']):<22} {j['title'][:44]:<45} "
                  f"{j['uid']:<38} {j.get('loc',''):<20} {pname}")

        # Save to JSON
        out = f"logs/jobs_{label}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)
        print(f"\n✅  Saved to {out}")

    else:
        main()
