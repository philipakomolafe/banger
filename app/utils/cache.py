"""
Caching utilities for the Banger application.
"""

import time
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
PERF_LOG_PATH = DATA_DIR / "perf_log.jsonl"

# Generation cache
_GEN_CACHE: Dict[Tuple[str, str, str, str], Tuple[float, List[str]]] = {}
_GEN_CACHE_TTL_SECONDS = 120  # 2 minutes


def get_cached_options(key: Tuple[str, str, str, str]) -> Optional[List[str]]:
    """Get cached generation results if still valid."""
    item = _GEN_CACHE.get(key)  # a tuple of (timestamp, options)
    if not item:
        return None
    ts, options = item
    if (time.time() - ts) > _GEN_CACHE_TTL_SECONDS:
        _GEN_CACHE.pop(key, None)
        return None
    return options


def set_cached_options(key: Tuple[str, str, str, str], options: List[str]) -> None:
    """Cache generation results."""
    _GEN_CACHE[key] = (time.time(), options)


def append_perf(entry: Dict) -> None:
    """Append performance metrics to log file."""
    try:
        PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PERF_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write perf log: {e}")


def read_perf_entries(limit: int = 20) -> List[Dict]:
    """Read the last N performance log entries."""
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    if not PERF_LOG_PATH.exists():
        return []

    lines = PERF_LOG_PATH.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:]
    items = []
    for line in tail:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items
