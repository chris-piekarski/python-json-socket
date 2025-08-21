.PHONY: test-behave

test-behave:
	PYTHONPATH=. behave -f progress2
