PYTHON ?= python3

.PHONY: judge-demo build test all fetch

# The screening command: offline build + tests, no install, no network.
judge-demo: build test

build:
	$(PYTHON) -m src.build

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

# Optional: needs network. Fetches into data/staging/, then swaps into data/raw/.
all: fetch build

fetch:
	$(PYTHON) -m src.fetch
