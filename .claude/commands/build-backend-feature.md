Read `docs/skills/build-backend-feature.md` and follow it to build a new backend feature.

The skill file contains the full step-by-step recipe — migration, domain entity, ORM, repository, service, API routes, tests. Read it first, then:

1. Ask the user which feature they want to build (members, leads, classes, etc.) if not already specified.
2. Check the current migration state with `make migrate-status-dev` so you know what revision number to use.
3. Follow the skill's 8 steps in order. Don't skip the tests.
4. Run `uv run ruff check . && uv run ruff format --check . && make test-backend-all-dev` at the end.
5. Report back with the checklist at the bottom of the skill filled in.
