.PHONY: help wheel test-behave test-pytest-cov test-behave-cov coverage lint

help:
	@echo "Targets:"
	@echo "  help               Show this help message"
	@echo "  wheel              Build a wheel into dist/"
	@echo "  test-behave        Run behave tests"
	@echo "  test-pytest-cov    Run pytest with coverage (terminal report)"
	@echo "  test-behave-cov    Run behave with coverage (appends to .coverage)"
	@echo "  coverage           Run combined pytest + behave coverage and export reports"
	@echo "  lint               Run pylint with fail-under threshold"

test-behave:
	PYTHONPATH=. behave -f progress2

# Pytest coverage (terminal report)
test-pytest-cov:
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

wheel:
	python setup.py bdist_wheel
