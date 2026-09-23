.PHONY: install api web test lint typecheck generate

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

generate:
	uv run --directory api python scripts/export_openapi.py
	pnpm dlx openapi-typescript web/openapi.json -o web/src/lib/api/types.ts
