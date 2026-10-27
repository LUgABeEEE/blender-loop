# Contributing

Thanks for taking a look! This project is small on purpose — keep changes
focused and reproducible.

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

Blender is only needed for `blender-loop demo` / `blender-loop bench`; the
unit tests must pass without it.

## Ground rules

- **No binary model assets, no API keys, no credentials** in commits.
- Unit tests must not require Blender or network access.
- Keep the evaluator contract stable: `(params, workdir) -> Evaluation`.
- New behaviour gets a test; bug fixes get a regression test.
- Prefer small, typed modules in `src/blender_loop/` over clever one-liners.

## Pull requests

1. Branch from `main`, one topic per PR.
2. `pytest -q` and `ruff check .` must pass.
3. Describe *why* the change is needed, and how you verified it (commands,
   sample numbers).
4. If you touched rendering or process limits, include a `blender-loop bench`
   before/after snippet.

## Commit messages

Conventional Commits, e.g.:

```
feat: add random search baseline
fix: keep lock file open for the duration of the child
docs: describe Cycles CPU trade-offs
```

## License

By contributing you agree that your contribution is licensed under the MIT
License (see `LICENSE`).
