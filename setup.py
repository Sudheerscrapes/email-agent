"""
ONE-TIME SETUP SCRIPT
Run this on your PC once. It will:
  1. Connect to your Gmail (opens browser)
  2. Encode all your resumes to base64

Then paste the outputs into GitHub Secrets.

Usage:
  pip install google-auth-oauthlib google-api-python-client
  python setup.py
"""

import json, base64, os, sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

def step1_gmail_token():
    print("\n" + "="*55)
    print("STEP 1 — Gmail Authorization")
    print("="*55)

    if not os.path.exists("credentials.json"):
        print("""
❌ credentials.json not found!

To get it:
1. Go to https://console.cloud.google.com/
2. Create project → Enable Gmail API
3. APIs & Services → Credentials
4. Create OAuth Client ID → Desktop App
5. Download JSON → rename to credentials.json
6. Place in this folder and run setup.py again
""")
        sys.exit(1)

    print("\n✅ credentials.json found!")
    print("🌐 Opening browser for Gmail login...")
    input("   Press ENTER to continue...")

    flow  = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    token = creds.to_json()
    with open("SECRET_GMAIL_TOKEN_JSON.txt", "w") as f:
        f.write(token)

    print("\n✅ Gmail token generated!")
    print("📄 Saved to: SECRET_GMAIL_TOKEN_JSON.txt")
    print("\n👉 GitHub Secret Name : GMAIL_TOKEN_JSON")
    print("👉 GitHub Secret Value: (copy contents of SECRET_GMAIL_TOKEN_JSON.txt)")

def step2_encode_resumes():
    print("\n" + "="*55)
    print("STEP 2 — Encode Your Resumes")
    print("="*55)

    # Map: resume file → GitHub Secret name
    resume_files = {
        "devops_resume.docx":   "RESUME_DEVOPS_B64",
        "cloud_resume.docx":    "RESUME_CLOUD_B64",
        "sre_resume.docx":      "RESUME_SRE_B64",
        "platform_resume.docx": "RESUME_PLATFORM_B64",
        "sap_resume.docx":      "RESUME_SAP_B64",
        "java_resume.docx":     "RESUME_JAVA_B64",
        "default_resume.docx":  "RESUME_DEFAULT_B64",
    }

    print("\nPlace your resume .docx files in this folder:")
    for fname, secret in resume_files.items():
        print(f"  {fname}  →  GitHub Secret: {secret}")

    print()
    input("Press ENTER when resumes are placed in this folder...")

    found = False
    with open("SECRET_RESUMES_B64.txt", "w") as out:
        for fname, secret in resume_files.items():
            if os.path.exists(fname):
                with open(fname, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                out.write(f"Secret Name : {secret}\n")
                out.write(f"Secret Value: {b64}\n")
                out.write("-"*60 + "\n")
                print(f"  ✅ Encoded: {fname} → {secret}")
                found = True
            else:
                print(f"  ⚠️  Not found (skipped): {fname}")

    if found:
        print("\n✅ All encoded resumes saved to: SECRET_RESUMES_B64.txt")
        print("👉 Open that file and add each Secret to GitHub")
    else:
        print("\n⚠️  No resume files found — place .docx files and run again")

def step3_instructions():
    print("\n" + "="*55)
    print("STEP 3 — Add Secrets to GitHub")
    print("="*55)
    print("""
Go to: Your GitHub Repo → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

  GMAIL_TOKEN_JSON      → contents of SECRET_GMAIL_TOKEN_JSON.txt
  YOUR_NAME             → Your Full Name
  YOUR_EMAIL            → your@gmail.com

  RESUME_DEVOPS_B64     → from SECRET_RESUMES_B64.txt
  RESUME_SAP_B64        → from SECRET_RESUMES_B64.txt
  RESUME_DEFAULT_B64    → from SECRET_RESUMES_B64.txt
  (add others as needed)

  CC_DEVOPS             → email to CC for DevOps jobs (e.g. manager@company.com)
  CC_SAP                → email to CC for SAP jobs
  CC_DEFAULT            → email to CC for other jobs
  (add others as needed)
""")

    print("="*55)
    print("STEP 4 — Push to GitHub & Run")
    print("="*55)
    print("""
  git init
  git add .
  git commit -m "AI Email Agent"
  git branch -M main
  git remote add origin https://github.com/YOUR_USERNAME/email-agent.git
  git push -u origin main

Then go to GitHub → Actions → AI Email Agent → Run workflow

✅ Done! Runs automatically every 10 minutes FOREVER for FREE!
""")

if __name__ == "__main__":
    print("="*55)
    print("  AI Email Agent — One Time Setup")
    print("  100% FREE | No Claude | No API Cost")
    print("="*55)
    step1_gmail_token()
    step2_encode_resumes()
    step3_instructions()
    print("🚀 Setup complete! Your agent is ready.")
