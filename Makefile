# Beanie — developer tooling.
#
# The venv is not persisted across environments; every target recreates it
# when missing so `make test` always works on a fresh checkout.

PY     ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PIP    := $(BIN)/pip
PYTEST := $(BIN)/python -m pytest

.PHONY: setup test demo suite verify repl status webui resume clean

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

# the weekly protocol in one command (ARCHITECTURE §8 / Q31): tests, then the
# tracked suite run (archives results/, prints suite delta, register movement,
# score composition, trailing-30-day window, calibration and usefulness)
verify: setup
	$(PYTEST) -q
	$(BIN)/python -m beanie.measure --suite-dir suites --track-dir results

repl: setup
	$(BIN)/python -m beanie.cli --state-dir .beanie_state

resume:
	@bash scripts/resume.sh

status: setup
	$(BIN)/python -m beanie.cli --state-dir .beanie_state --status

webui: setup
	$(BIN)/python -m beanie.webui --state-dir .beanie_state --host 0.0.0.0 --port 8080

clean:
	rm -rf $(VENV) .pytest_cache .beanie_state results
	find . -type d -name __pycache__ -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
