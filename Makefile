.PHONY: help fetch stats build validate serve clean all ci

# Default target
help:
	@echo "Rykker Godset Opp? – Available commands"
	@echo ""
	@echo "  make fetch    – Fetch latest data from NIFS API"
	@echo "  make stats    – Generate statistics from raw data"
	@echo "  make build    – Build static site"
	@echo "  make validate – Run data-integrity checks"
	@echo "  make all      – Run fetch → stats → build"
	@echo "  make serve    – Serve site/ locally on port 8000"
	@echo "  make clean    – Remove generated files"
	@echo "  make ci       – Full pipeline for CI (all + validate + verify)"
	@echo ""

# Data pipeline
fetch:
	uv run python scripts/fetch_data.py

stats:
	uv run python scripts/generate_stats.py

build:
	uv run python scripts/build_site.py

validate:
	@uv run python scripts/validate_ci.py

# Combined
all: fetch stats build

# CI target (used by GitHub Actions)
ci: all validate
	@test -f site/index.html || (echo "ERROR: site/index.html not built" && exit 1)
	@test -f site/style.css || (echo "ERROR: site/style.css not found" && exit 1)
	@test -f site/robots.txt || (echo "ERROR: site/robots.txt not found" && exit 1)
	@test -f site/sitemap.xml || (echo "ERROR: site/sitemap.xml not built" && exit 1)
	@ls site/[0-9]*.html >/dev/null 2>&1 || (echo "ERROR: no round pages built" && exit 1)
	@echo "CI check passed – site is ready for deploy"

# Local preview
serve:
	@echo "Serving site/ at http://localhost:8000"
	@cd site && python -m http.server 8000

# Cleanup
clean:
	rm -rf data/raw/*.json data/stats.json data/stats_round_*.json site/index.html site/[0-9]*.html site/sitemap.xml
