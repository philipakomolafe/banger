import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

# Ensure project root is on sys.path so "import app..." works
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.supabase import get_supabase


def to_iso(ts: Any) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def get_user_id_from_api(access_token: str, api_base: str) -> str:
    r = requests.get(
        f"{api_base.rstrip('/')}/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"Failed to resolve user via /api/auth/me: {r.status_code} {r.text}")
    return r.json()["user_id"]


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                rows.append(item)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {i}: {e}")

    return rows


def reshape_entry(raw: dict, user_id) -> dict:
    allowed = {"user_id", "ts", "mode", "cache_hit", "gen_time_ms", "options_count"}
    required = ("user_id", "mode", "gen_time_ms")

    shaped = {
        "user_id": user_id,
        "ts": raw.get("ts"),
        "mode": raw.get("mode"),
        "cache_hit": raw.get("cache_hit", False), 
        "gen_time_ms": raw.get("gen_time_ms"),
        "options_count": raw.get("options_count", 0),
    }

    shaped = {k: v for k, v in shaped.items() if k in allowed and v is not None}
    for req in required:
        if req not in shaped.keys():
            raise ValueError(f"Missing required field: {req}")
    
    return shaped

def main():
    p = argparse.ArgumentParser(description="Import data/post_ledger.json or data/perf_entries into Supabase public.post_ledger")
    p.add_argument("--file", default="data/post_ledger.json", help="Path to post_ledger.json")
    p.add_argument("--table", default="post_ledger", help="Supabase table name")
    p.add_argument("--user-id", default=None, help="Owner auth.users.id (uuid). Optional if --access-token is provided.")
    p.add_argument("--access-token", default=None, help="Access token to resolve user_id via /api/auth/me")
    p.add_argument("--api-base", default="http://localhost:8000", help="Backend base URL (default: http://localhost:8000)")
    p.add_argument("--batch", type=int, default=300)
    args = p.parse_args()

    # this fails to catch a case where the user-id is provided.
    if not args.user_id and not args.access_token:                      
        raise SystemExit("Provide either --user-id or --access-token")

    user_id = args.user_id
    if not user_id:
        user_id = get_user_id_from_api(args.access_token, args.api_base)

    path = Path(args.file)
    rows = read_jsonl(path)

    payload: List[Dict[str, Any]] = []
    for r in rows:
        payload.append(reshape_entry(r, user_id))
                

    supabase = get_supabase(admin=True)

    total = 0
    for i in range(0, len(payload), args.batch):
        # rolling through the dict indices. 
        # so, we move from the current idx-position through to [current-idx-posit + batch length].
        sample = payload[i : i + args.batch]
        # so here we refer to the supabase table: `perf_entries` to export data to.
        # since the .table() method in supabase calls the .from_() method which also calls postgrest so i think i'll just swap to using it directly.
        supabase.from_(args.table).upsert(sample).execute()
        total += len(sample)
        print(f"Upserted {total}/{len(payload)}")
    print("Done.")


if __name__ == "__main__":
    main()