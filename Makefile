# Makefile for databricks-data-science
.PHONY: all install data fixture lint format typecheck test coverage gate clean help

PYTHON ?= python3
SRC := src tests notebooks

all: gate

install:
	$(PYTHON) -m pip install -e ".[dev]"

# Download the full database (sha256 pinned, about 300 MB, never committed) and export Parquet.
data:
	dbx-ds data

# Rebuild the small committed fixture from the downloaded file.
fixture:
	dbx-ds fixture

lint:
	ruff check $(SRC)
	ruff format --check $(SRC)

format:
	ruff format $(SRC)
	ruff check $(SRC) --fix

typecheck:
	mypy src

test:
	pytest -q

# 100% line and branch coverage or it fails (fail_under = 100 in pyproject.toml).
coverage:
	pytest -q --cov --cov-report=term-missing

gate: lint typecheck coverage

clean:
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

help:
	@echo "install data fixture lint format typecheck test coverage gate clean"
