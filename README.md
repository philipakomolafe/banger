# Banger - X/Twitter Post Generator

AI-powered post generation for authentic builder content on X (Twitter).

## Project Structure

```
banger/
├── run.py                    # Main entry point
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (create from .env.example)
│
├── src/                      # Core application code
│   ├── __init__.py
│   ├── generator.py          # AI post generation logic
│   ├── x_api.py              # X/Twitter API integration
│   ├── email_utils.py        # Email notification utilities
│   └── server.py             # FastAPI HTTP server
│
├── config/                   # Configuration files
│   ├── style_profile.json    # Writing style parameters
│   └── training_tweets.json  # Example tweets for tone matching
│
├── scripts/                  # Utility scripts
│   └── tweet_scraper.py      # Fetch and analyze tweets for style
│
├── data/                     # Runtime data (auto-created)
│   ├── post_ledger.json      # Record of posted content
│   └── perf_log.jsonl        # Performance metrics
│
└── web/                      # Frontend static files
    ├── index.html
    ├── app.js
    └── styles.css
```

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   Create a `.env` file with:
   ```env
   # Google AI
   GOOGLE_API_KEY=your_key_here
   MODEL_NAME=gemini-pro
   
   # X/Twitter API
   X_API_KEY=your_key
   X_API_SECRET=your_secret
   X_ACCESS_TOKEN=your_token
   X_ACCESS_SECRET=your_secret
   X_BEARER_TOKEN=your_bearer
   X_COMMUNITY_URL=https://twitter.com/i/communities/your_id
   
   # Email (optional)
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email
   SMTP_PASS=your_password
   TO_EMAIL=recipient@email.com
   
   # Rate limiting
   MAX_X_WRITES_PER_MONTH=280
   ```

3. **Run the server:**
   ```bash
   python run.py
   ```
   
   Open http://localhost:8000/web in your browser.

## Usage Modes

### Web Server (default)
```bash
python run.py
# or
python run.py --port 8080
```

### CLI Mode
```bash
python run.py --cli
```

### Update Style Profile
```bash
python run.py --scrape
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET | Get remaining writes and config |
| `/api/generate` | POST | Generate post options |
| `/api/post` | POST | Post to X or record manual post |
| `/api/email` | POST | Email generated options |
| `/api/perf` | GET | Get performance metrics |

## Development

The codebase is organized for production:

- **src/**: All application logic, cleanly separated
- **config/**: External configuration, easy to modify
- **scripts/**: One-off utilities, run independently
- **data/**: Runtime state, gitignored in production
