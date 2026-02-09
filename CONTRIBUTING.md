# Contributing to PriceScout

## Development Workflow

1. Create a feature branch from `main`
2. Make changes, ensure tests pass
3. Commit with descriptive messages (see conventions below)
4. Push and create a PR against `main`

## Commit Conventions

Format: `type(scope): description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`

Examples:
- `feat(baselines): add tax-aware surge comparison`
- `fix(scraper): handle missing showtime format`
- `security(api): add Bandit SAST to CI pipeline`

## Code Style

**Python (backend):**
- Type hints on public function signatures
- Use `logging` module (never `print()` in `api/` or `app/`)
- Pydantic V2: `model_dump()` not `dict()`, string dict keys only
- SQLAlchemy ORM for all database access
- New imports: use `app.db_session`, `app.db_models`, or `app.db.*` directly (not `app.db_adapter`)

**TypeScript (frontend):**
- Functional components with hooks
- TanStack Query for server state, Zustand for client state
- Explicitly import `beforeEach`/`afterEach` from vitest (no globals)

## Testing Requirements

All PRs must pass:

```bash
# Backend (510+ tests)
python -m pytest tests/ -x -q

# Frontend (631+ tests)
cd frontend && npx vitest run

# Type checking
mypy app api --ignore-missing-imports
cd frontend && npx tsc --noEmit

# Lint
cd frontend && npm run lint
```

Coverage thresholds: 70% (lines, branches, functions, statements).

## Known Gotchas

See `docs/CODEBASE_MAP.md` section "Known Quirks & Gotchas" for common pitfalls including:
- FastAPI route ordering (literal before parameterized)
- Mocking `builtins.open` breaks TestClient
- Theater name normalization across sources
