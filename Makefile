.PHONY: wheel develop test format

wheel:
	uv build --wheel

develop: wheel
	uv pip install -e . --force-reinstall

test: develop
	uv run pytest tests/ --timeout=10

format:
	uv run ruff format tests/
