Read `docs/skills/build-frontend-feature.md` and follow it to build a new frontend feature.

The skill file contains the full step-by-step recipe — folder structure, api.ts, hooks.ts, forms, list pages, row actions, tests. Read it first, then:

1. Ask the user which feature they want to build (members, leads, classes, etc.) if not already specified.
2. Verify the backend side is ready — the corresponding API endpoints must exist and respond from `http://localhost:8000/docs`.
3. Follow the skill's 11 steps in order. Don't skip the tests.
4. Run `cd frontend && npx tsc --noEmit && npx vitest run` at the end to verify.
5. Report back with the checklist at the bottom of the skill filled in.
