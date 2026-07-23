"""Export or verify the deterministic OpenAPI contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jarvis.api import create_app

DEFAULT_OUTPUT = Path("docs/openapi.v1.json")


def render_openapi() -> str:
    return (
        json.dumps(
            create_app().openapi(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    generated = render_openapi()

    if arguments.check:
        if not arguments.output.exists():
            print(f"OpenAPI snapshot is missing: {arguments.output}")
            return 1
        if arguments.output.read_text(encoding="utf-8") != generated:
            print(
                f"OpenAPI snapshot is stale: run "
                f"`uv run python scripts/export_openapi.py --output {arguments.output}`"
            )
            return 1
        print(f"OpenAPI snapshot is current: {arguments.output}")
        return 0

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(generated, encoding="utf-8")
    print(f"Wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
