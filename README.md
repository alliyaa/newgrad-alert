# levels.fyi new-grad alert

Checks levels.fyi's Top 100 companies (by the "Entry Level Engineer" leaderboard —
the closest thing levels.fyi has to a new-grad ranking) for postings that look
like new-grad roles. Runs automatically in the cloud on GitHub Actions (free,
no laptop required), emails you when it finds something new, and publishes a
mobile-friendly dashboard via GitHub Pages so you can check it from your phone
any time.

**Your dashboard will live at:** `https://<your-github-username>.github.io/<repo-name>/`

## How it works

- `get_companies.py` scrapes the Top 100 companies from the levels.fyi
  leaderboard into `companies.json`. A GitHub Actions workflow re-runs this
  weekly so the list stays current.
- `monitor.py` visits each company's levels.fyi jobs page, matches titles
  against new-grad-style keywords (see `NEW_GRAD_KEYWORDS` near the top of the
  file — fully editable), tracks what it's seen in `state/seen_jobs.json`,
  emails you anything new, and regenerates `docs/index.html` — the dashboard.
- A second GitHub Actions workflow runs `monitor.py` every 2 hours, then
  commits the updated state + dashboard back to the repo, which GitHub Pages
  serves automatically.
- The **first run only records a baseline** and doesn't email you — otherwise
  you'd get 100 companies' worth of postings dumped in one message.

## Setup (one-time, ~10 minutes)

### 1. Get a Gmail App Password
- Turn on 2-Step Verification: https://myaccount.google.com/signinoptions/two-step-verification
- Generate an app password: https://myaccount.google.com/apppasswords
- Choose "Mail", name it "levelsfyi alert", copy the 16-character password

### 2. Create a GitHub repo
- Go to https://github.com/new, name it something like `newgrad-alert`
- Make it **public** (GitHub Pages is free for public repos; private works too
  but requires GitHub Pro)
- Don't initialize with a README (you already have one)

### 3. Push this project to it
From inside this folder:
```
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

### 4. Add your secrets
In your new repo: **Settings → Secrets and variables → Actions → New repository secret**
Add three secrets:
- `GMAIL_ADDRESS` — the Gmail address sending alerts
- `GMAIL_APP_PASSWORD` — the app password from step 1
- `ALERT_EMAIL` — `alliyaahmad3@gmail.com`

### 5. Turn on GitHub Pages
**Settings → Pages** → under "Build and deployment", set Source to
**Deploy from a branch**, branch `main`, folder `/docs` → Save.

GitHub will give you the live URL (something like
`https://yourusername.github.io/newgrad-alert/`) — bookmark that on your phone.

### 6. Kick off the first run
**Actions tab → "Check for new grad postings" → Run workflow** (the manual
trigger button). This builds the baseline. Give it a few minutes (checking
100 companies takes a while), then refresh your GitHub Pages URL — you should
see postings populate.

Also manually run **"Refresh top 100 company list"** once now, since the repo
ships with a starter list of ~20 companies — this fills it out to the full 100.

From here it's fully automatic: postings get checked every 2 hours, the
company list refreshes weekly, and you'll get an email + updated dashboard
whenever something new shows up. Nothing needs to stay running on your end.

## If something looks broken

Click into the **Actions** tab → the failed run → read the logs. The most
likely cause is levels.fyi tweaking their page layout, which would show up as
"0 companies found" or "0 postings found" in the logs. You can reproduce and
debug it locally too:
```
pip install -r requirements.txt
playwright install chromium
python get_companies.py --debug
python monitor.py --debug
```
`--debug` opens a real visible browser window so you can see what's happening.

## Running locally instead (optional)

You don't need this if you're using GitHub Actions, but if you'd rather run it
from your own machine on a schedule (Task Scheduler / cron), copy
`.env.example` to `.env` and fill in the same three values, then just run
`python monitor.py` on whatever schedule you like.

## Adjusting what counts as "new grad"

Edit the `NEW_GRAD_KEYWORDS` list in `monitor.py` — it's plain lowercase
substrings matched against job titles. Add or remove terms as you see fit.
