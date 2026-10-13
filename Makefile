# The Makefile only forwards to tools/fl.py so Linux, macOS and Windows behave the same.
# On Windows without make, run: python tools/fl.py <target>
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

.PHONY: up down test lint fixtures e2e check-pins gen-types check-types ci

up down test lint fixtures check-pins gen-types check-types ci:
	$(PY) tools/fl.py $@

e2e:
	$(PY) tools/fl.py e2e $(SCENARIO)
