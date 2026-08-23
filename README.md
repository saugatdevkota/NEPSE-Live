# NEPSE Live — Scheduled Scraper + Static Website

Primary architecture: `GitHub Actions scraper -> frontend/data.json -> static frontend`

Supabase is optional. Without it, the scraper writes the latest market snapshot
straight into `frontend/data.json` and the frontend reads that file.

## Project structure

```text
nepse-live/
├── scraper/
│   ├── scrape_nepse.py
│   └── requirements.txt
├── .github/workflows/scrape.yml
├── sql/schema.sql
├── frontend/index.html
└── nepse_live_local_test.py
```

## 1. Test the NEPSE response locally

```bash
pip install -r scraper/requirements.txt
python scraper/scrape_nepse.py --debug
```

Debug mode prints one raw record and does not write any data. Confirm that
the response still contains `symbol`, `lastUpdatedPrice` or `closePrice`,
`previousDayClosePrice`, and `totalTradedQuantity`.

The scraper currently disables TLS certificate verification for the NEPSE
client because that endpoint has had certificate-chain problems. Do not treat
the scraped response as a trusted or licensed market feed.

## 2. Generate the static data

```bash
python scraper/scrape_nepse.py
```

This updates `frontend/data.json`. Serve the project through a local HTTP
server, such as VS Code Live Server, and open `frontend/index.html`. Opening the
HTML through a `file://` URL will not allow it to fetch the JSON file.

## 3. Optional: enable Supabase

Install the optional dependency:

```bash
pip install -r scraper/requirements-supabase.txt
```

1. Create a Supabase project.
2. Run `sql/schema.sql` in the SQL Editor. The script is safe to rerun.
3. Copy the project URL, anon public key, and service-role key.
4. Put only the project URL and anon key in `frontend/index.html`.
5. Never commit or expose the service-role key in frontend code.

The schema enables row-level security with public SELECT access. Writes require
the service-role key.

When both `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are present, the same
scraper run writes the static JSON first and then syncs Supabase.

### PowerShell

```powershell
$env:SUPABASE_URL = "https://xxxx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"
python scraper/scrape_nepse.py
```

### Bash

```bash
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
python scraper/scrape_nepse.py
```

## 4. Scheduled updates

The workflow runs every 15 minutes from 11:00 through 15:00 Nepal time,
Sunday–Thursday. It refreshes and commits `frontend/data.json`; no database
secrets are required. Supabase can still be synced from another configured run.

NEPSE schedules and holidays can change, so review the cron schedule when
trading hours change.

## 5. Deploy the frontend

Deploy the `frontend/` directory to GitHub Pages, Netlify, Vercel, or another
static host. There is no build step. Leave the Supabase constants blank unless
you want database fallback and history charts.

## Data behavior

- `frontend/data.json` keeps the latest snapshot and market status.
- Watchlists work locally in the browser without Supabase.
- With optional Supabase, history is stored while the market is open and charts
  display the newest 500 samples.

This is unofficial scraped data intended for educational or personal use. Do
not rely on it alone for trading decisions.
