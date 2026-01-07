.PHONY: wheel develop test format

wheel:
	uv build --wheel

develop: wheel
	uv pip install -e . --force-reinstall
	@cp _build/mp4_ext.pyi src/mp4/ 2>/dev/null || true

test: develop
	uv run pytest tests/ --timeout=10

format:
	clang-format -i src/*.cpp
	uv run ruff format tests/
