#!/usr/bin/env python3
"""Build static site from per-round stats JSON files and Jinja2 template.

Renders one page per completed round (site/<n>.html) plus site/index.html
for the latest round.
"""

import glob
import json
import os
import re
import sys
from datetime import date
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
STATS_PATH = os.path.join(PROJECT_ROOT, "data", "stats.json")
ROUNDS_PATTERN = os.path.join(PROJECT_ROOT, "data", "stats_round_*.json")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
SITE_DIR = os.path.join(PROJECT_ROOT, "site")


def load_stats(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def round_number(path: str) -> int:
    match = re.search(r"stats_round_(\d+)\.json$", path)
    return int(match.group(1)) if match else -1


def main():
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("index.html.j2")
    os.makedirs(SITE_DIR, exist_ok=True)

    round_files = sorted(glob.glob(ROUNDS_PATTERN), key=round_number)
    if not round_files:
        # Fallback: single-page build from stats.json (backwards compatible).
        stats = load_stats(STATS_PATH)
        index_path = os.path.join(SITE_DIR, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(template.render(**stats))
        print(f"Site built to {index_path} (single round fallback)", file=sys.stderr)
        return

    latest_round = -1
    for path in round_files:
        stats = load_stats(path)
        number = round_number(path)
        latest_round = max(latest_round, number)
        out_path = os.path.join(SITE_DIR, f"{number}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(template.render(**stats))
        print(f"Round {number} page built to {out_path}", file=sys.stderr)

    # index.html always shows the latest round.
    latest_stats = load_stats(
        os.path.join(PROJECT_ROOT, "data", f"stats_round_{latest_round}.json")
    )
    index_path = os.path.join(SITE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(template.render(**latest_stats))

    print(f"Site built to {index_path} (+ {len(round_files)} round pages)", file=sys.stderr)

    write_sitemap(round_files, latest_round)


def write_sitemap(round_files: list[str], latest_round: int):
    """Write site/sitemap.xml listing index plus one URL per historical round.

    The latest round is covered by index.html (its canonical URL), so only
    older rounds get their own entries to avoid duplicate indexing.
    """
    today = date.today().isoformat()
    entries = [
        ("https://godset.mats.codes/", today, "daily", "1.0"),
    ]
    for path in sorted(round_files, key=round_number):
        number = round_number(path)
        if number == latest_round:
            continue
        stats = load_stats(path)
        lastmod = stats.get("season", {}).get("round_completed_at") or today
        entries.append((
            f"https://godset.mats.codes/{number}.html",
            lastmod,
            "monthly",
            "0.5",
        ))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, changefreq, priority in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{xml_escape(lastmod)}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    sitemap_path = os.path.join(SITE_DIR, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Sitemap with {len(entries)} URLs written to {sitemap_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
