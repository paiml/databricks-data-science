# Makefile for databricks-data-science
.PHONY: all install data fixture lint format typecheck test coverage gate clean help

PYTHON ?= python3
SRC := src tests notebooks

all: gate

install:
	$(PYTHON) -m pip install -e ".[dev]"

# Download the full database (sha256 pinned, about 300 MB, never committed) and export Parquet.
data:
	$(PYTHON) -c "import sys; from dbx_ds.cli import main; sys.exit(main(['data']))"

# Rebuild the small committed fixture from the downloaded file.
fixture:
	$(PYTHON) -c "import sys; from dbx_ds.cli import main; sys.exit(main(['fixture']))"

lint:
	$(PYTHON) -m ruff check $(SRC)
	$(PYTHON) -m ruff format --check $(SRC)

format:
	$(PYTHON) -m ruff format $(SRC)
	$(PYTHON) -m ruff check $(SRC) --fix

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -q

# 100% line and branch coverage or it fails (fail_under = 100 in pyproject.toml).
coverage:
	$(PYTHON) -m pytest -q --cov --cov-report=term-missing

video-gate-selftest:
	bash scripts/video_gate.sh --selftest

gate: lint typecheck coverage video-gate-selftest

clean:
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

help:
	@echo "install data fixture lint format typecheck test coverage gate clean"
