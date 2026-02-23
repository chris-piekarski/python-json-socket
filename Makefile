.PHONY: help clean wheel test-behave test test-behave-cov coverage lint publish version net-server net-client

help:
	@echo "Targets:"
	@echo "  help               Show this help message"
	@echo "  clean              Remove build/test artifacts"
	@echo "  wheel              Build a wheel into dist/"
	@echo "  test-behave        Run behave tests"
	@echo "  test               Run pytest with coverage (terminal report)"
	@echo "  test-behave-cov    Run behave with coverage (appends to .coverage)"
	@echo "  coverage           Run combined pytest + behave coverage and export reports"
	@echo "  lint               Run pylint with fail-under threshold"
	@echo "  net-server         Run echo server for network testing (IP required)"
	@echo "  net-client         Run client for network testing (IP required)"
	@echo "  publish            Upload dist/* to PyPI via twine"
	@echo "  version            Show package version and git SHA"

test-behave:
	PYTHONPATH=. behave -f progress2

PORT ?= 5491
MODE ?= ping
NUM ?= 1
MAX ?= 100
ERROR ?= 0
READ ?= 1

net-server:
	@if [ -z "$(IP)" ]; then echo "Usage: make net-server IP=<bind-ip> [PORT=$(PORT)]"; exit 1; fi
	PYTHONPATH=. python3 scripts/net_server.py $(IP) --port $(PORT)

net-client:
	@if [ -z "$(IP)" ]; then echo "Usage: make net-client IP=<server-ip> [PORT=$(PORT)] [MODE=$(MODE)] [NUM=$(NUM)] [MAX=$(MAX)] [ERROR=$(ERROR)] [READ=$(READ)]"; exit 1; fi
	PYTHONPATH=. python3 scripts/net_client.py $(IP) --port $(PORT) --mode $(MODE) --num $(NUM) --count $(MAX) --error $(ERROR) --read $(READ)

# Pytest coverage (terminal report)
test:
	pytest -q --cov=jsocket --cov-branch --cov-report=term-missing

# Behave coverage (appends to same .coverage data)
test-behave-cov:
	coverage run -a -m behave -f progress2

# Combined coverage: erase, run pytest+behave, show and export XML/HTML
coverage:
	coverage erase
	pytest -q --cov=jsocket --cov-branch --cov-report=term
	coverage run -a -m behave -f progress2
	coverage report -m
	coverage xml -o coverage.xml
	coverage html -d .coverage_html

# Static analysis with pylint; fail if score below threshold (duplicate-code is noisy in tests/headers)
lint:
	mkdir -p .pylint.d
	PYLINTHOME=.pylint.d pylint jsocket tests features/steps --fail-under=9.0 --persistent=n --disable=duplicate-code

clean:
	rm -rf build dist *.egg-info .pytest_cache .coverage coverage.xml .coverage_html

wheel:
	python3 -m build --wheel

publish:
	python3 -m build
	python3 -m twine check dist/*
	python3 -m twine upload dist/*

version:
	@python3 -c "import pathlib, re; p = pathlib.Path('jsocket/_version.py'); m = re.search(r'__version__\\s*=\\s*[\\\"\\']([^\\\"\\']+)[\\\"\\']', p.read_text(encoding='utf-8')); print(f\"version: {m.group(1) if m else 'unknown'}\")"
	@sha=$$(git log -1 --format=%h 2>/dev/null); \
	if [ -n "$$sha" ]; then \
		if [ -n "$$(git status --porcelain 2>/dev/null)" ]; then \
			echo "git: $$sha (dirty)"; \
		else \
			echo "git: $$sha"; \
		fi; \
	else \
		echo "git: unknown"; \
	fi
