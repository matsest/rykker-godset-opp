#!/usr/bin/env python3
"""Fetch latest data from NIFS API and save to data/raw/."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# NIFS API endpoints for OBOS-ligaen 2026
STAGE_ID = 700912
BASE_URL = "https://api.nifs.no"
ENDPOINTS = {
    "table": f"/stages/{STAGE_ID}/table/",
    "matches": f"/stages/{STAGE_ID}/matches/",
    "teams": f"/stages/{STAGE_ID}/teams/",
}

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def fetch_json(url: str) -> dict | list:
    """Fetch JSON from NIFS API."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "rykkergodsetopp/0.1 (+https://github.com)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def save_json(data, path: str):
    """Save data as pretty-printed JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    metadata = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stage_id": STAGE_ID,
        "endpoints": {},
    }

    for name, endpoint in ENDPOINTS.items():
        url = BASE_URL + endpoint
        print(f"Fetching {name} from {url} ...", file=sys.stderr)
        try:
            data = fetch_json(url)
        except urllib.error.HTTPError as e:
            print(f"HTTP error for {name}: {e.code} {e.reason}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"URL error for {name}: {e.reason}", file=sys.stderr)
            sys.exit(1)

        path = os.path.join(RAW_DIR, f"{name}.json")
        save_json(data, path)
        metadata["endpoints"][name] = {
            "url": url,
            "saved_to": path,
            "records": len(data) if isinstance(data, list) else None,
        }
        print(f"  → saved {path}", file=sys.stderr)

    # Save metadata
    meta_path = os.path.join(RAW_DIR, "metadata.json")
    save_json(metadata, meta_path)
    print(f"Metadata saved to {meta_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
