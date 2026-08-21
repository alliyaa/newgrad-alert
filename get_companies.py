"""
Refreshes companies.json with the current Top 100 companies from levels.fyi's
"Entry Level Engineer" leaderboard (the closest proxy levels.fyi has to a
"new grad" ranking).

Run standalone:
    python get_companies.py
    python get_companies.py --debug   # visible browser + verbose logs
"""

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LEADERBOARD_URL = (
    "https://www.levels.fyi/leaderboard/Software-Engineer/Entry-Level-Engineer/"
    "country/United-States/"
)
TARGET_COUNT = 100
OUTPUT_FILE = Path(__file__).parent / "companies.json"

COMPANY_LINK_RE = re.compile(r"^/company/([a-z0-9\-]+)/salaries/?")


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def collect_companies(page, debug=False) -> list[dict]:
    seen = {}

    def harvest():
        anchors = page.eval_on_selector_all(
            "a[href*='/company/']",
            "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))",
        )
        for a in anchors:
            href = a.get("href") or ""
            m = COMPANY_LINK_RE.match(href)
            if not m:
                continue
            slug = m.group(1)
            if slug not in seen:
                # Some cards (the top-3 highlighted ones) cram rank + comp
                # figures into the same link text as the company name, so
                # we don't trust scraped text for the name -- derive a clean
                # one from the slug instead.
                seen[slug] = slug_to_name(slug)

    harvest()
    if debug:
        print(f"  after initial load: {len(seen)} companies")

    stagnant_rounds = 0
    for round_i in range(60):
        if len(seen) >= TARGET_COUNT:
            break
        before = len(seen)

        for label in ["Show More", "Load More", "View More", "See More"]:
            try:
                btn = page.get_by_text(label, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=1000)
                    time.sleep(0.6)
            except Exception:
                pass

        page.mouse.wheel(0, 3000)
        time.sleep(0.8)
        harvest()

        if debug:
            print(f"  round {round_i}: {len(seen)} companies")

        stagnant_rounds = stagnant_rounds + 1 if len(seen) == before else 0
        if stagnant_rounds >= 6:
            break

    ranked = list(seen.items())[:TARGET_COUNT]
    return [{"name": name, "slug": slug} for slug, name in ranked]


def main():
    debug = "--debug" in sys.argv

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page.goto(LEADERBOARD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        companies = collect_companies(page, debug=debug)
        browser.close()

    if not companies:
        print(
            "Got 0 companies -- levels.fyi likely changed their page layout, "
            "or blocked this request. Try --debug to watch it happen."
        )
        sys.exit(1)

    OUTPUT_FILE.write_text(json.dumps(companies, indent=2))
    print(f"Wrote {len(companies)} companies to {OUTPUT_FILE}")
    if len(companies) < TARGET_COUNT:
        print(f"(Only found {len(companies)}/{TARGET_COUNT} -- re-run if you want more.)")


if __name__ == "__main__":
    main()
