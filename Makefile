.PHONY: help fetch stats build serve clean all ci

# Default target
help:
	@echo "Rykker Godset Opp? – Available commands"
	@echo ""
	@echo "  make fetch    – Fetch latest data from NIFS API"
	@echo "  make stats    – Generate statistics from raw data"
	@echo "  make build    – Build static site"
	@echo "  make all      – Run fetch → stats → build"
	@echo "  make serve    – Serve site/ locally on port 8000"
	@echo "  make clean    – Remove generated files"
	@echo "  make ci       – Full pipeline for CI (all + verify)"
	@echo ""

# Data pipeline
fetch:
	uv run python scripts/fetch_data.py

stats:
	uv run python scripts/generate_stats.py

build:
	uv run python scripts/build_site.py

# Combined
all: fetch stats build

# CI target (used by GitHub Actions)
ci: all
	@test -f data/stats.json || (echo "ERROR: data/stats.json not produced – API or stats step failed" && exit 1)
	@test -s data/stats.json || (echo "ERROR: data/stats.json is empty" && exit 1)
	@python3 -c "import json; d=json.load(open('data/stats.json')); assert 'godset' in d, 'Missing godset key'; assert 'table' in d, 'Missing table key'" || (echo "ERROR: data/stats.json has invalid structure" && exit 1)
	@test -f site/index.html || (echo "ERROR: site/index.html not built" && exit 1)
	@test -f site/style.css || (echo "ERROR: site/style.css not found" && exit 1)
	@echo "CI check passed – site is ready for deploy"

# Local preview
serve:
	@echo "Serving site/ at http://localhost:8000"
	@cd site && python -m http.server 8000

# Cleanup
clean:
	rm -rf data/raw/*.json data/stats.json site/index.html
