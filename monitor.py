"""
Checks every company in companies.json for new-grad-looking job postings on
levels.fyi, emails alerts for anything new, and regenerates docs/index.html
(the mobile dashboard, served via GitHub Pages).

Usage:
    python monitor.py
    python monitor.py --debug   # visible browser + verbose logs

First run just records a baseline (no email) so you don't get 100 companies'
worth of postings dumped in one message. Every run after that only alerts on
genuinely new postings.

Credentials come from environment variables (GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
ALERT_EMAIL) -- set as GitHub Actions repo Secrets when run in CI, or via a
local .env file when run on your own machine.
"""

import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
COMPANIES_FILE = BASE_DIR / "companies.json"
STATE_FILE = BASE_DIR / "state" / "seen_jobs.json"
LOG_FILE = BASE_DIR / "state" / "last_run.log"
DASHBOARD_FILE = BASE_DIR / "docs" / "index.html"

JOB_ID_RE = re.compile(r"jobId=(\d+)")

NEW_GRAD_KEYWORDS = [
    "new grad",
    "university grad",
    "recent grad",
    "graduate program",
    "graduate software",
    "entry level",
    "entry-level",
    "junior software",
    "junior engineer",
    "associate software engineer",
    "associate engineer",
    "early career",
    "early in career",
    "campus hire",
    "class of 20",
]

REQUEST_DELAY_SECONDS = 2.5


def load_companies() -> list[dict]:
    if not COMPANIES_FILE.exists():
        print(f"{COMPANIES_FILE.name} not found. Run `python get_companies.py` first.")
        sys.exit(1)
    return json.loads(COMPANIES_FILE.read_text())


def load_state() -> dict:
    """State shape: {slug: {job_id: {"title", "url", "first_seen"}}}"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def looks_like_new_grad(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in NEW_GRAD_KEYWORDS)


def scrape_company_jobs(page, slug: str, debug=False) -> list[dict]:
    url = f"https://www.levels.fyi/jobs/company/{slug}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(1.2)
    except Exception as e:
        if debug:
            print(f"    [{slug}] failed to load: {e}")
        return []

    anchors = page.eval_on_selector_all(
        "a[href*='jobId=']",
        "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))",
    )

    results, found_ids = [], set()
    for a in anchors:
        href = a.get("href") or ""
        m = JOB_ID_RE.search(href)
        if not m:
            continue
        job_id = m.group(1)
        if job_id in found_ids:
            continue
        title = (a.get("text") or "").strip()
        if not title or not looks_like_new_grad(title):
            continue
        found_ids.add(job_id)
        full_url = href if href.startswith("http") else f"https://www.levels.fyi{href}"
        results.append({"id": job_id, "title": title, "url": full_url})

    if debug:
        print(f"    [{slug}] {len(anchors)} job links, {len(results)} look new-grad")

    return results


def send_email(new_postings: list[dict], to_addr: str):
    load_dotenv(BASE_DIR / ".env")
    gmail_addr = os.getenv("GMAIL_ADDRESS")
    gmail_app_pw = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_addr or not gmail_app_pw:
        print("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set. Skipping email send.")
        return False

    lines = [f"{p['company']} -- {p['title']}\n{p['url']}\n" for p in new_postings]
    body = f"{len(new_postings)} new new-grad posting(s) found:\n\n" + "\n".join(lines)
    body += "\nFull dashboard: (see your GitHub Pages URL)\n"

    msg = MIMEText(body)
    msg["Subject"] = f"levels.fyi: {len(new_postings)} new new-grad posting(s)"
    msg["From"] = gmail_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_addr, gmail_app_pw)
            server.sendmail(gmail_addr, [to_addr], msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def generate_dashboard(companies: list[dict], state: dict, new_ids: set):
    """Writes a single self-contained, mobile-friendly HTML dashboard."""
    name_by_slug = {c["slug"]: c.get("name", c["slug"]) for c in companies}

    rows = []
    for slug, jobs in state.items():
        company_name = name_by_slug.get(slug, slug)
        for job_id, info in jobs.items():
            rows.append(
                {
                    "company": company_name,
                    "title": info["title"],
                    "url": info["url"],
                    "first_seen": info.get("first_seen", ""),
                    "is_new": job_id in new_ids,
                }
            )

    # Newest first
    rows.sort(key=lambda r: r["first_seen"], reverse=True)

    def esc(s):
        return html.escape(s, quote=True)

    cards = []
    for r in rows:
        badge = '<span class="badge">NEW</span>' if r["is_new"] else ""
        cards.append(
            f"""<a class="card" href="{esc(r['url'])}" target="_blank" rel="noopener">
  <div class="card-top">
    <span class="company">{esc(r['company'])}</span>
    {badge}
  </div>
  <div class="title">{esc(r['title'])}</div>
  <div class="date">first seen {esc(r['first_seen'])}</div>
</a>"""
        )

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_postings = len(rows)
    total_new = sum(1 for r in rows if r["is_new"])

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>New Grad Job Alerts</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 16px; max-width: 640px; margin-inline: auto;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f7f7f9; color: #1a1a1a;
  }}
  header {{ margin-bottom: 16px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  .meta {{ color: #666; font-size: 0.85rem; }}
  .stats {{ display: flex; gap: 12px; margin: 12px 0; }}
  .stat {{
    flex: 1; background: white; border-radius: 12px; padding: 12px;
    text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .stat .num {{ font-size: 1.5rem; font-weight: 700; }}
  .stat .label {{ font-size: 0.75rem; color: #666; }}
  .card {{
    display: block; background: white; border-radius: 12px; padding: 14px 16px;
    margin-bottom: 10px; text-decoration: none; color: inherit;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .card-top {{ display: flex; justify-content: space-between; align-items: center; }}
  .company {{ font-weight: 600; font-size: 0.85rem; color: #555; }}
  .badge {{
    background: #d1453b; color: white; font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; letter-spacing: 0.03em;
  }}
  .title {{ font-size: 1rem; margin-top: 4px; }}
  .date {{ font-size: 0.75rem; color: #888; margin-top: 6px; }}
  .empty {{ text-align: center; color: #888; padding: 40px 0; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #121212; color: #eee; }}
    .stat, .card {{ background: #1e1e1e; box-shadow: none; border: 1px solid #2a2a2a; }}
    .company {{ color: #aaa; }}
    .date {{ color: #999; }}
  }}
</style>
</head>
<body>
<header>
  <h1>New Grad Job Alerts</h1>
  <div class="meta">Top 100 levels.fyi companies &middot; updated {esc(updated)}</div>
</header>
<div class="stats">
  <div class="stat"><div class="num">{total_postings}</div><div class="label">tracked postings</div></div>
  <div class="stat"><div class="num">{total_new}</div><div class="label">new this run</div></div>
  <div class="stat"><div class="num">{len(companies)}</div><div class="label">companies checked</div></div>
</div>
{"".join(cards) if cards else '<div class="empty">No postings tracked yet.</div>'}
</body>
</html>
"""
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(html_doc)


def main():
    debug = "--debug" in sys.argv

    companies = load_companies()
    state = load_state()
    is_first_run = len(state) == 0

    new_postings = []
    new_ids = set()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )

        for i, company in enumerate(companies):
            slug = company["slug"]
            name = company.get("name", slug)
            print(f"[{i + 1}/{len(companies)}] Checking {name}...")

            postings = scrape_company_jobs(page, slug, debug=debug)
            company_state = state.get(slug, {})

            for posting in postings:
                job_id = posting["id"]
                if job_id not in company_state:
                    new_postings.append({**posting, "company": name})
                    new_ids.add(job_id)
                    company_state[job_id] = {
                        "title": posting["title"],
                        "url": posting["url"],
                        "first_seen": today,
                    }

            state[slug] = company_state
            time.sleep(REQUEST_DELAY_SECONDS)

        browser.close()

    save_state(state)
    generate_dashboard(companies, state, new_ids)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(
        f"Last run: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Companies checked: {len(companies)}\n"
        f"New postings found: {len(new_postings)}\n"
    )

    if is_first_run:
        total = sum(len(v) for v in state.values())
        print(f"First run -- recorded a baseline of {total} existing postings. No email sent.")
        return

    if not new_postings:
        print("No new postings this run.")
        return

    print(f"Found {len(new_postings)} new posting(s):")
    for p in new_postings:
        print(f"  - {p['company']}: {p['title']} ({p['url']})")

    load_dotenv(BASE_DIR / ".env")
    to_addr = os.getenv("ALERT_EMAIL", "alliyaahmad3@gmail.com")
    sent = send_email(new_postings, to_addr)
    if sent:
        print(f"Emailed {to_addr}.")


if __name__ == "__main__":
    main()
