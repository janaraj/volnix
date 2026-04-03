# Contributing to Terrarium

Thank you for your interest in contributing to Terrarium. This guide covers the development setup, code standards, and process for submitting changes.

---

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/terrarium.git
   cd terrarium
   ```
3. Install dependencies (requires Python 3.12+):
   ```bash
   uv sync --all-extras
   ```
4. Verify your setup:
   ```bash
   uv run pytest tests/simulation/test_runner.py -v
   uv run ruff check terrarium/
   uv run mypy terrarium/
   ```

---

## Development Workflow

1. Create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes
3. Write or update tests
4. Run the full check suite:
   ```bash
   uv run pytest
   uv run ruff check terrarium/ tests/
   uv run ruff format --check terrarium/ tests/
   uv run mypy terrarium/
   ```
5. Commit and push to your fork
6. Open a pull request against `main`

---

## Running Tests

```bash
# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/simulation/test_runner.py -v

# Run a single test
uv run pytest tests/simulation/test_runner.py::TestEndConditions::test_empty_queue_stops -v

# Run with coverage
uv run pytest --cov=terrarium --cov-report=term-missing
```

Coverage minimum is **80%**. Tests that hit live LLM APIs are isolated in `tests/live/` and skipped by default. They only run when `TERRARIUM_RUN_REAL_API_TESTS=1` is set.

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` -- no `@pytest.mark.asyncio` decorators needed. Shared fixtures are in `tests/conftest.py`.

---

## Code Standards

Terrarium follows strict architectural principles. Read [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) for the full picture. Here are the essentials:

### Async everywhere
All I/O is async. Use `aiosqlite`, `httpx`, async SDK methods. Wrap sync libraries with `asyncio.to_thread()`.

### Frozen Pydantic models
All value objects and events use `model_config = ConfigDict(frozen=True)`. Events are immutable once created.

### Protocol-based interfaces
Inter-module contracts use `typing.Protocol` (runtime_checkable, structural). ABC is used only for `BaseEngine`. No cross-engine imports -- engines communicate through the event bus and protocols only.

### Typed IDs
Use `EntityId`, `ActorId`, `ServiceId`, etc. from `core/types.py`. Never pass raw strings for domain identifiers.

### No hardcoded values
Thresholds, timeouts, limits, and provider names come from TOML config. Engine code reads from its config, not from constants.

### Single source of truth
- All state changes go through the State Engine's commit interface
- All external requests go through the Gateway
- All LLM calls go through the LLM router (`llm/router.py`)
- The composition root (`registry/composition.py`) is the only place that imports concrete engine classes

### Linting and formatting
- **Ruff** for linting and formatting: Python 3.12 target, 100-char line length
- **Mypy** with strict mode

---

## Pull Request Process

1. **Describe what changed and why** -- not just what files were touched
2. **Include tests** -- new features need tests, bug fixes need regression tests
3. **Pass CI** -- lint, type check, and test suite must all pass
4. **Keep PRs focused** -- one feature or fix per PR. If a refactor is needed to support a feature, consider splitting into two PRs
5. **Update documentation** if the change affects user-facing behavior (CLI, config, API)

---

## Reporting Bugs

Open a [GitHub Issue](https://github.com/janaraj/terrarium/issues) with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Terrarium version (`terrarium --version`)
- Python version
- OS and platform

---

## Proposing Features

Open a [GitHub Issue](https://github.com/janaraj/terrarium/issues) with:

- The problem or use case you're trying to solve
- Your proposed solution
- Alternatives you considered
- Whether you're willing to implement it

For larger features, open the issue first to discuss the approach before writing code.

---

## Questions?

If you're unsure about anything, open an issue or start a discussion. We're happy to help.
