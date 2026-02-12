# Banger

Banger is an AI-powered tool that helps indie hackers, developers, and creators turn messy daily build notes into engaging X (Twitter) posts. It combines a FastAPI backend with a modern web frontend for a seamless content generation experience.

## Features

- **AI Tweet/Post Generator:** Paste your rough notes and get polished, authentic posts optimized for X.
- **Multiple Options:** Generate up to 3 variations per session (free tier), unlimited with Pro.
- **Voice Preservation:** Posts sound like you, not generic AI.
- **Direct Posting:** Pro users can connect their X account and post directly.
- **Tweet Analytics:** Analyze tweet performance (Pro feature).
- **Screenshot Sharing:** Create shareable before/after images.
- **Usage Tracking:** Free users get 3 generations/day; Pro unlocks unlimited.
- **Account Management:** Sign up, log in, and manage your plan.

## Project Structure

```
app/           # FastAPI backend (API, core logic, utils)
web/           # Frontend (HTML, CSS, JS)
scripts/       # Utility scripts (Supabase export, tweet scraping)
config/        # Style profile and training data
data/          # Logs and ledgers
run.py         # Main entry point
requirements.txt
README.md
```

## Getting Started

### 1. Install Dependencies

```sh
pip install -r requirements.txt
```

### 2. Environment Setup

Copy `.env.example` to `.env` and fill in your keys (Supabase, X API, etc).

### 3. Run the Server

```sh
python run.py
```

The backend will start on [http://localhost:8000](http://localhost:8000).

### 4. Access the Web App

Open [http://localhost:8000/web/landing.html](http://localhost:8000/web/landing.html) in your browser.

## Usage

- **Generate Posts:** Enter your build notes, mood, and what's next. Click "Generate" to get options.
- **Copy/Email:** Copy options or email them to yourself.
- **Post Directly:** Pro users can connect X and post with one click.
- **Track Usage:** See your daily generation count and upgrade if needed.

## Free vs Pro

| Feature                | Free           | Pro           |
|------------------------|---------------|---------------|
| Generations/day        | 3             | Unlimited     |
| Direct X Posting       | yes           | Yes           |
| Tweet Analytics        | No            | Yes           |
| Priority Support       | No            | Yes           |

Upgrade in the dashboard for unlimited access.

## Scripts

- **Tweet Scraper:** `python run.py --scrape` updates style profiles.
- **Supabase Export:** Use scripts in `scripts/` to export ledgers and logs.

## Contact & Support

- Built by [Philip Akomolafe](https://x.com/PhilipAkomolaf_)
- Email: info@getbanger.tech

---

No jargon, just ship your story. 🚀