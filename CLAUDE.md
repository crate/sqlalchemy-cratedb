# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`sqlalchemy-cratedb` is a SQLAlchemy dialect for CrateDB, a distributed SQL database. It supports SQLAlchemy 1.3 through 2.1 (with ongoing 2.1 compatibility work on the current branch).

## Development Setup

```bash
source bootstrap.sh   # Creates .venv with Python 3.11, installs all deps in editable mode
```

Environment variables that influence bootstrap:
- `SQLALCHEMY_VERSION` (default: `<2.2`) — SQLAlchemy version constraint
- `PIP_ALLOW_PRERELEASE=true` — allow pre-release packages

## Common Commands

```bash
poe format    # Auto-format code (ruff + black)
poe lint      # Run linters (ruff, validate-pyproject)
poe test      # Run pytest, including the doctests
poe check     # lint + test combined

# Run specific tests
pytest tests/dict_test.py
pytest -k SqlAlchemyCompilerTest
pytest -k test_score

# Run integration/doctests
pytest tests/test_documentation.py
```

Tests require a live CrateDB instance via Docker, started automatically by the `cratedb_service` fixture through `testcontainers.community.cratedb`.
Select the CrateDB version with `CRATEDB_VERSION`, an image tag (default: `latest`), e.g. `CRATEDB_VERSION=5.10.16 pytest`. `nightly` uses `crate/crate:nightly`, any other tag the official `crate` image.

## Architecture

### Source layout (`src/sqlalchemy_cratedb/`)

- **`dialect.py`** — Core dialect: type mappings, Date/DateTime handling, schema reflection
- **`compiler.py`** — SQL/DDL compilation: `CrateDDLCompiler`, `CrateTypeCompiler`, `CrateIdentifierPreparer`, and `rewrite_update()` for partial object updates
- **`predicate.py`** — `match()` predicate for full-text search
- **`sa_version.py`** — Version detection; exports `SA_VERSION`, `SA_1_4`, `SA_2_0`, `SA_2_1` constants
- **`compat/`** — Multi-version SQLAlchemy compatibility: `core10.py`, `core14.py`, `core20.py`, `core21.py`, `api13.py`
- **`type/`** — Custom CrateDB types: `ObjectType` (JSON objects), `ObjectArray`, `FloatVector`, `Geopoint`, `Geoshape`
- **`support/`** — Integrations and polyfills: `pandas.py` (bulk insert), `polyfill.py` (refresh-after-DML, uniqueness, autoincrement timestamps), `util.py`

### Key architectural patterns

**Multi-version compatibility:** The `compat/` directory contains separate modules for each major SQLAlchemy version. `sa_version.py` detects the installed version at runtime using `verlib2`, and code conditionally imports from the appropriate compat module. When adding features, check whether they need version-specific handling.

**Custom types:** CrateDB types (ObjectType, FloatVector, etc.) implement SQLAlchemy's bind/result processor pattern — `bind_processor()` converts Python → SQL, `result_processor()` converts SQL → Python. The `CrateTypeCompiler` generates the SQL type strings.

**Update rewriting:** `compiler.py::rewrite_update()` transforms partial dictionary updates on `ObjectType` columns into CrateDB's subscript assignment syntax (e.g., `obj['key'] = value`).

**Polyfills:** `support/polyfill.py` monkey-patches SQLAlchemy internals to add features CrateDB doesn't natively support (e.g., `refresh_after_dml`, `uniqueness_strategy`).

### Testing

Tests in `tests/` follow two patterns:
- `*_test.py` and `test_*.py` files: pytest tests. Integration tests use the `cratedb_service` fixture; unit tests mock the driver's cursor and run offline
- `tests/test_documentation.py`: runs the doctests in `docs/*.rst` against the same CrateDB instance

The `conftest.py` provides:
- `cratedb_service`: session-scoped, starts one CrateDB container (`crate:$CRATEDB_VERSION`, or `crate/crate:nightly` for `nightly`) with `tests/assets` mounted at `/assets`
- `crate_host`: the container's `host:port`, used by the doctests
- `offline_default_server`: autouse, answers the driver's connect-time server version probe for the default address `localhost:4200`.
## Code Style

- Line length: 100 characters (ruff + black)
- Ruff rules enforced: A, B, C4, E, ERA, F, I, PD, RET, S, T20, W, YTT
- Mypy strict mode is configured but not always enforced in CI
