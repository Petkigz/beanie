# Beanie — developer tooling.
#
# The venv is not persisted across environments; every target recreates it
# when missing so `make test` always works on a fresh checkout.

PY     ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PIP    := $(BIN)/pip
PYTEST := $(BIN)/python -m pytest

.PHONY: setup test demo suite repl clean

setup:
	$(PY) -m venv $(VENV)
	$(PIP) install -q -U pip
	$(PIP) install -q pytest
	$(PIP) install -q -e .

test: setup
	$(PYTEST) -q

demo: setup
	$(BIN)/python examples/demo_mind.py

suite: setup
	$(BIN)/python -m beanie.measure --suite-dir suites --track-dir results

repl: setup
	$(BIN)/python -m beanie.cli --state-dir .beanie_state

clean:
	rm -rf $(VENV) .pytest_cache .beanie_state results
	find . -type d -name __pycache__ -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
