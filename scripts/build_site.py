#!/usr/bin/env python3
"""Build static site from stats.json and Jinja2 template."""

import json
import os
import shutil
import sys

from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
STATS_PATH = os.path.join(PROJECT_ROOT, "data", "stats.json")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
SITE_DIR = os.path.join(PROJECT_ROOT, "site")


def load_stats() -> dict:
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    stats = load_stats()

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("index.html.j2")

    html = template.render(**stats)

    os.makedirs(SITE_DIR, exist_ok=True)
    index_path = os.path.join(SITE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Site built to {index_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
