.PHONY: run test lint clean help setup

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install deps
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run: ## Run the app
	python3 main.py

test: ## Run tests
	python3 -m pytest tests/ -v

lint: ## Lint with ruff
	python3 -m ruff check main.py 2>/dev/null || echo "Install ruff: pip install ruff"

clean: ## Clean generated files
	rm -rf __pycache__ .pytest_cache .ruff_cache .venv data/*.db
