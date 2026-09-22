.PHONY: install test lint format clean demo

install:
	pip install -e .[dev]

test:
	pytest -v

lint:
	ruff check .

format:
	ruff check --fix .
	ruff format .

demo:
	python examples/demo_whatsapp_timeline.py

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info recall.db recall_demo.db
	find . -type d -name __pycache__ -exec rm -rf {} +
