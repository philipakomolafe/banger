# Banger

Banger is a **FastAPI + vanilla web app** that helps builders turn rough daily notes into polished X (Twitter) posts.

It includes:
- AI-assisted post generation.
- Supabase auth + usage tracking.
- Free vs Pro gating (LemonSqueezy-backed subscription state).
- Optional X account connection for analytics and posting workflows.

---

## What this repo contains

- `app/` — FastAPI backend (generation, auth, payments, X integration, analytics).
- `web/` — static frontend pages (landing/auth/dashboard).
- `config/` — voice/style guidance + training tweet samples.
- `scripts/` — utility scripts (tweet scraping, Supabase export).
- `data/` — local ledger/perf logs (used in some local/dev flows).
- `run.py` — main entrypoint for server, CLI generation, and scraper.

---

## Core features

- **Structured post generation** from:
  - `today_context`
  - `current_mood`
  - `optional_angle`
- **Daily mode rotation** (`daily_wins`, `lesson_learned`, `shipping_update`) to keep output varied.
- **Auth-gated generation** with per-user usage checks.
- **Free plan limit:** 3 generations/day.
- **Pro plan:** unlimited generations (based on active subscription status).
- **X OAuth connect/disconnect** + tweet analytics endpoint.
- **LemonSqueezy webhook handler** for subscription state updates.
- **Email endpoint** (Resend) to send generated options.

---

## Tech stack

- **Backend:** FastAPI, Uvicorn, Pydantic
- **AI generation:** Google Generative AI (`google-generativeai`)
- **Data/Auth:** Supabase
- **Payments:** LemonSqueezy webhooks
- **X integration:** OAuth 2.0 + X API v2
- **Frontend:** Static HTML/CSS/JS served from `/web`

---

## Quick start

### 1) Clone & install

```bash
git clone <your-fork-or-origin-url>
cd banger
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Create `.env`

Create a `.env` file in the repo root. Minimal local setup usually needs:

```env
# AI
GOOGLE_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# App URLs
AUTH_REDIRECT_URL=http://localhost:8000/web/callback.html
X_AUTH_REDIRECT_URL=http://localhost:8000/web/x-callback.html

# Optional: billing and email
LEMONSQUEEZY_CHECKOUT_URL=
LEMONSQUEEZY_WEBHOOK_SECRET=
LEMONSQUEEZY_CUSTOMER_PORTAL_URL=
RESEND_API_KEY=
FROM_USER=
TO_EMAIL=

# Optional: X direct posting / community URL
CLIENT_ID=
CLIENT_SECRET=
X_BEARER_TOKEN=
X_API_KEY=
X_API_SECRET=
X_COMMUNITY_URL=
MAX_X_WRITES_PER_MONTH=480
```

> If Supabase keys are missing, auth/usage/subscription endpoints will fail.

### 3) Run the server

```bash
python run.py
```

Server starts on `http://localhost:8000` (default).

### 4) Open the app

- Landing: `http://localhost:8000/web/landing.html`
- Dashboard: `http://localhost:8000/web/dashboard.html`
- Health: `http://localhost:8000/health`

---

## Running modes

`run.py` supports three modes:

```bash
# API server (default)
python run.py

# API server on custom port
python run.py --port 9000

# CLI generation flow
python run.py --cli

# Update style profile/training signals via scraper script
python run.py --scrape
```

---

## API overview

Base API prefix: `/api`

### Generation
- `POST /api/generate`
  - Requires Bearer auth token.
  - Requires all three fields: `today_context`, `current_mood`, `optional_angle`.
  - Enforces free-tier daily limit unless user is paid.

### Post recording / publishing
- `POST /api/post`
  - `method: api | manual | community`
  - `api` method requires header `X-Use-X-API: 1`.
- `POST /api/record`
  - Records manually posted/community URLs.

### Auth
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `GET /api/auth/google`
- `GET /api/auth/me`

### X integration
- `GET /api/x/auth-url`
- `POST /api/x/callback`
- `GET /api/x/status`
- `DELETE /api/x/disconnect`

### Analytics
- `POST /api/analytics/tweet`
  - Requires connected X account token.

### Payments
- `POST /api/payments/webhook/lemonsqueezy`
- `GET /api/payments/checkout-url`
- `GET /api/payments/subscription-status`
- `POST /api/payments/cancel-subscription`

### Other
- `POST /api/email`
- `POST /api/waitlist`
- `GET /api/config`
- `GET /api/perf`

Interactive docs are available at:
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## Notes on data + limits

- Free-tier generation limit is currently **3/day** per user.
- Monthly X write cap defaults to **480** (`MAX_X_WRITES_PER_MONTH`).
- Some local/dev paths use JSON files in `data/`:
  - `data/post_ledger.json`
  - `data/perf_log.jsonl`
- In deployed mode, Supabase tables are used for core persistence.

---

## Deployment

The repo includes `render.yaml` for Render deployment.

At minimum, configure all required environment variables in your deployment provider before enabling production traffic.

---

## Troubleshooting

- **401 on `/api/generate`**: missing/invalid Bearer token.
- **429 on `/api/generate`**: free daily limit reached.
- **Supabase errors**: verify `SUPABASE_URL`, anon key, and service role key.
- **X OAuth issues**: check `CLIENT_ID`, optional `CLIENT_SECRET`, and redirect URL values.
- **Webhook signature failures**: confirm `LEMONSQUEEZY_WEBHOOK_SECRET` matches dashboard config.

---

## License

No license file is currently included in this repository. Add one before open-source distribution.
