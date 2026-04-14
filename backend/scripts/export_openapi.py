"""Print the FastAPI OpenAPI spec as JSON to stdout.

Used by CI to verify that ``frontend/src/lib/api-schema.ts`` is in sync
with the backend — see ``frontend/package.json`` ``check:api-types`` script
and the ``Frontend API type drift`` job in CI.

Doesn't start the HTTP server; just imports the FastAPI ``app`` and calls
its ``openapi()`` method, so it has no DB / Redis / RabbitMQ dependency
and can run in any CI environment that has the Python deps installed.

Usage::

    uv run python -m scripts.export_openapi > /tmp/openapi.json
"""

from __future__ import annotations

import json
import sys

from app.main import app


def main() -> None:
    spec = app.openapi()
    json.dump(spec, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
