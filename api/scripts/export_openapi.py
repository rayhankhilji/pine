"""Dump the FastAPI OpenAPI schema to web/openapi.json (no server needed)."""

import json
from pathlib import Path

from pine.main import create_app

OUT = Path(__file__).resolve().parents[2] / "web" / "openapi.json"


def main() -> None:
    schema = create_app().openapi()
    OUT.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
