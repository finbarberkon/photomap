PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help setup prep serve

help:
	@echo "make setup   install the photo tooling into .venv (once)"
	@echo "make prep    resize new photos and rebuild photos.json"
	@echo "make serve   preview the site at http://localhost:8000"

setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -r tools/requirements.txt

prep:
	$(BIN)/python tools/prep.py

serve:
	$(PYTHON) -m http.server 8000
