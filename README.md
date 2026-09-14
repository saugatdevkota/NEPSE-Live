# NEPSE Tracker — Local and Online Operations Guide

This project combines:
- a live NEPSE market scraper
- an optional Supabase-backed database layer
- a family portfolio/account model
- an IPO alert scraper
- a Telegram bot for subscriber alerts and reminders
- a static frontend dashboard served from local files or a static host

The default flow is local-first and GitHub Actions-friendly:
- live price scraper writes the latest snapshot to frontend/data.json
- optional Supabase sync stores history and portfolio data
- IPO jobs and Telegram alerts run separately from the price scraper

## Project structure

```text
NEPSE Analysis/
├── .github/
│   └── workflows/
│       └── scrape.yml
├── frontend/
│   ├── data.json
│   └── index.html
├── scraper/
│   ├── scrape_nepse.py
│   ├── scrape_ipo.py
│   ├── telegram_bot.py
│   ├── requirements.txt
│   └── requirements-supabase.txt
├── sql/
│   └── schema.sql
├── tests/
│   ├── test_ipo_alerts.py
│   ├── test_import_meroshare.py
│   └── test_technical_signal.py
├── import_meroshare.py
├── nepse_live_local_test.py
├── README.md
└── .gitignore
```

## 1. Local setup

### Python dependencies

For the base market scraper only:

```bash
pip install -r scraper/requirements.txt
```

For the full stack including Supabase sync, portfolio workflows, and Telegram bot:

```bash
pip install -r scraper/requirements-supabase.txt
```

## 2. Local run: price scraper

### Quick test against NEPSE

```bash
python scraper/scrape_nepse.py --debug
```

This prints one raw record and does not write output. Confirm the response includes fields like `symbol`, `lastUpdatedPrice` or `closePrice`, `previousDayClosePrice`, and `totalTradedQuantity`.

### Generate the static snapshot

```bash
python scraper/scrape_nepse.py
```

This creates or updates `frontend/data.json`.

Serve the project locally with a static server (for example, VS Code Live Server or Python HTTP server), then open `frontend/index.html` in a browser.

Example:

```bash
python -m http.server 8000
```

Then visit:

```text
http://localhost:8000/frontend/index.html
```

> Opening the HTML directly as a file URL may fail because the page fetches JSON data.

## 3. Local run: IPO scraper

```bash
python scraper/scrape_ipo.py
```

This scrapes public IPO listings and tries to sync the results into the Supabase `ipo_alerts` table if the environment is configured.

You can also pass one or more custom URLs:

```bash
python scraper/scrape_ipo.py --url https://www.sharesansar.com/ipo
```

## 4. Local run: Telegram bot

### Create the bot

1. Open Telegram and talk to BotFather.
2. Create a new bot and save the token.
3. Set the token as an environment variable:

PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "<your-bot-token>"
```

Bash:

```bash
export TELEGRAM_BOT_TOKEN="<your-bot-token>"
```

### Start the bot

```bash
python scraper/telegram_bot.py --run-bot
```

### Register a family member to an account

Inside Telegram, send:

```text
/start 1
```

`1` is the account ID from the `accounts` table in Supabase. After registration, that chat receives IPO alerts and reminders.

### One-off bot actions

```bash
python scraper/telegram_bot.py --send-alerts
python scraper/telegram_bot.py --send-reminders
python scraper/telegram_bot.py --send-digest
```

These are useful for testing or running the bot from cron or CI.

## 5. Local Supabase setup

### Preferred local workflow with Supabase CLI

This repo now supports the local Supabase CLI flow you asked for:

```bash
npx supabase init
npx supabase start
npx supabase db push
```

That creates the local database and pushes the schema defined in `supabase/migrations/`.

### Required environment variables

PowerShell:

```powershell
$env:SUPABASE_URL = "https://xxxxx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"
```

Bash:

```bash
export SUPABASE_URL="https://xxxxx.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
```

### Run the schema

1. Create a Supabase project.
2. Open the SQL Editor.
3. Run the contents of `sql/schema.sql`.
4. The script is safe to rerun and creates the required tables for:
   - prices
   - market status
   - price history
   - technical signals
   - accounts and holdings
   - transactions
   - IPO alerts
   - Telegram subscribers

### Optional frontend config

If the frontend uses Supabase reads, add the project URL and anon key in the frontend file as needed. Do not commit the service role key to browser code.

### Push to remote Supabase

If you want to sync the local migration schema to your hosted Supabase project:

```bash
npx supabase link --project-ref <project-ref>
npx supabase db push
```

This is the recommended project workflow for local development and remote sync.

## 6. Online / GitHub Actions operation

The repo includes a scheduled GitHub Actions workflow in [.github/workflows/scrape.yml](.github/workflows/scrape.yml).

### Workflow behavior

- the price scraper job runs on schedule and updates JSON snapshots
- the IPO alerts job runs independently and syncs IPO data to Supabase
- Telegram alerts are sent only when the bot token and Supabase config are available

### Required GitHub secrets

Add these in GitHub repository settings -> Secrets and variables -> Actions:

```text
SUPABASE_URL
SUPABASE_SERVICE_KEY
TELEGRAM_BOT_TOKEN
```

### Scheduling

The workflow is configured for the NEPSE market schedule and can also be triggered manually with workflow_dispatch.

If you want to run the bot continuously in the cloud, you can also host a small Python process that calls:

```bash
python scraper/telegram_bot.py --run-bot
```

with the same secrets configured in the environment.

## 7. How the data flows

### Pure local mode

```text
NEPSE website -> scraper/scrape_nepse.py -> frontend/data.json -> frontend/index.html
```

### Optional Supabase mode

```text
NEPSE website -> scraper/scrape_nepse.py -> Supabase tables -> frontend/index.html
```

### IPO alert flow

```text
IPO source -> scraper/scrape_ipo.py -> Supabase ipo_alerts -> Telegram bot -> family subscribers
```

## 8. Notes and cautions

- NEPSE data is scraped and intended for personal analysis or educational use.
- Telegram bot credentials must remain secret and should never be committed to the repo.
- The scraper suppresses TLS verification for the NEPSE endpoint because of known certificate-chain issues in the upstream service.
- The portfolio and signal logic is intentionally transparent and rule-based, not a black-box model.

## 9. Useful commands summary

```bash
# install dependencies
pip install -r scraper/requirements-supabase.txt

# run market scraper locally
python scraper/scrape_nepse.py

# run IPO sync locally
python scraper/scrape_ipo.py

# start Telegram bot
python scraper/telegram_bot.py --run-bot

# test the bot actions
python scraper/telegram_bot.py --send-alerts
python scraper/telegram_bot.py --send-reminders
python scraper/telegram_bot.py --send-digest
```

## 10. Recommended operating pattern

For a normal household/family setup:

1. Keep the price scraper on the normal GitHub Action schedule.
2. Keep the IPO job on the same workflow, independently.
3. Add each family member to Telegram with `/start <account_id>`.
4. Let the bot send alerts on new IPOs and one-day reminders before close.
5. Review the account portfolio and price signals in the dashboard.

This gives you a low-maintenance operational system without needing a full backend service for the static frontend.
