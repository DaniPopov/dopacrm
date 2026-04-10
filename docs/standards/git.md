# Git & Workflow Standards

> Conventions for branches, commits, and PRs.

## Branch Naming

```
{type}/{short-description}
```

| Type | When |
|------|------|
| `feature/` | New functionality |
| `fix/` | Bug fix |
| `chore/` | Config, CI, deps, tooling — no app logic change |
| `refactor/` | Code restructure with no behavior change |
| `docs/` | Documentation only |

**Examples:**

```
feature/whatsapp-webhook
feature/config-service
fix/session-expiry-timezone
chore/docker-compose-setup
refactor/split-agent-service
docs/api-standards
```

**Rules:**

- Lowercase, hyphen-separated
- Short but descriptive — someone reading the branch name should know what it's about
- Branch from `main`, merge back to `main`

## Commit Messages

### Format: Conventional Commits

```
{type}: {description}

{optional body}
```

**Types:**

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `chore` | Tooling, config, deps |
| `refactor` | Code restructure, no behavior change |
| `docs` | Documentation |
| `test` | Adding or fixing tests |
| `style` | Formatting, linting (no logic change) |

**Examples:**

```
feat: add whatsapp webhook validation
fix: session expiry not respecting timezone
chore: add ruff config to pyproject.toml
refactor: extract config resolution into separate method
docs: add api standards
test: add unit tests for conversation state machine
```

**Rules:**

- Subject line: imperative mood ("add", "fix", "extract" — not "added", "fixes", "extracted")
- Subject line: max 72 characters
- No period at the end of subject line
- Body (optional): explain **why**, not what. The diff shows what.
- One logical change per commit — don't mix a feature and a refactor

### When to Use a Body

```
fix: prevent duplicate conversations for same phone

The session lookup was using phone only, without company_id scope.
This caused cross-tenant session collisions when two companies
had residents with the same phone number.
```

## PR Workflow

### Before Opening a PR

1. Rebase on latest `main` (avoid merge commits)
2. Run linter: `uv run ruff check .`
3. Run formatter: `uv run ruff format .`
4. Run tests: `uv run pytest`
5. Review your own diff — catch the obvious stuff yourself

> If `pre-commit` is installed (`uv run pre-commit install`), steps 2-3 run
> automatically on every commit.

### PR Title

Same format as commit messages:

```
feat: add config service with redis caching
fix: rate limiter not resetting after TTL
```

### PR Description

```markdown
## Summary
- What this PR does and why (1-3 bullet points)

## Test Plan
- How it was tested (unit tests, manual testing, etc.)

## Notes
- Anything reviewers should pay attention to (optional)
```

### PR Size

- Target: under 400 lines of meaningful changes
- If larger — split into stacked PRs or separate concerns into multiple PRs
- Exception: initial setup PRs (project scaffolding, Docker Compose) can be larger

### Merge Strategy

- **Squash and merge** for feature branches — keeps main history clean
- PR branch is deleted after merge

## Protected Branch

`main` is the production branch.

**Rules:**

- Never push directly to `main`
- All changes go through PRs
- CI must pass before merge

## Tooling

### Pre-commit

`.pre-commit-config.yaml` runs the following on every commit:

- **ruff** (`--fix`) — lint + auto-fix (includes import sorting via the `I` rule, replacing `isort`)
- **ruff-format** — format
- **gitleaks** — block commits containing secrets
- **basic hygiene** — trailing whitespace, end-of-file fixer, check-yaml, check-toml, check-merge-conflict, check-added-large-files, detect-private-key

**One-time setup:**

```bash
uv run pre-commit install
```

### CI (`.github/workflows/ci.yml`)

Runs on every push to `main` and every PR. Four parallel jobs:

| Job | What it does |
|-----|--------------|
| `lint-and-test` | `uv sync` → `ruff check` → `ruff format --check` → `pytest` |
| `gitleaks` | Scans the diff for committed secrets |
| `pip-audit` | Scans `pyproject.toml` for dependencies with known CVEs |
| `docker-build` | Builds `backend/Dockerfile` to catch build failures early |

CI must be green before merge.

## .gitignore Essentials

```
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Environment
.env
.env.*

# IDE
.vscode/
.idea/

# OS
.DS_Store

# Docker
docker-compose.override.yml

# Secrets (never commit)
*.pem
*.key
credentials.json
```

## Sensitive Files — Never Commit

- `.env` / `.env.*` — environment variables
- `*.pem` / `*.key` — certificates and keys
- `credentials.json` — any credentials file
- AWS config with secrets
- Database connection strings with passwords

Use `.env.example` with placeholder values to document required environment variables.
