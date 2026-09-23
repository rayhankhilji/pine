.PHONY: install api web test lint typecheck

install:
	uv sync --directory api
	pnpm -C web install

api:
	uv run --directory api pine serve

web:
	pnpm -C web dev

test:
	uv run --directory api pytest -q

lint:
	uv run --directory api ruff check .
	uv run --directory api mypy pine tests
	pnpm -C web lint

typecheck:
	uv run --directory api mypy pine tests
