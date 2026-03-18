.PHONY: dev test test-cov lint format validate clean setup

dev:
	DOPPEL_DEBUG=1 python doppel.py chatter --debug

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=doppelchatter --cov-report=html

lint:
	ruff check src/ tests/
	mypy src/doppelchatter/

format:
	ruff format src/ tests/

validate:
	python doppel.py lint

clean:
	rm -rf sessions/ __pycache__ .pytest_cache .mypy_cache htmlcov/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

setup:
	pip install -e ".[dev]"
	@echo "✓ Setup complete. Set DOPPEL_API_KEY, then: make dev"
