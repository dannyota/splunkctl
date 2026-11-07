# Contributing

Issues and pull requests are welcome at
[github.com/dannyota/splunkctl](https://github.com/dannyota/splunkctl).

## Set up

```bash
git clone https://github.com/dannyota/splunkctl
cd splunkctl
python -m pip install -e '.[dev]'
git config core.hooksPath .githooks
```

Python 3.13 or newer is required. The pre-commit hook runs the same checks
as CI.

## Before you open a pull request

Run all of these from the repository root. CI runs the same set.

```bash
ruff check .
ruff format --check .
mypy splunkctl/
pytest
bash scripts/check-lengths.sh
splunkctl docs generate --check
```

- Keep every Python file at or under 500 lines and every Markdown guide at
  or under 450 lines. Split by topic instead of trimming tests.
- Tests must not need a live Splunk or SOAR instance. Mock the client.
- Pages under `docs/commands/` are generated. Run `splunkctl docs generate`
  after changing help text and commit the result.
- Prose in the repository is English, plain and direct. No em dashes.
- Every mutation command stays a dry run by default and must go through
  the guard in `splunkctl/guard.py`.

## Cutting a release

1. Update `__version__` in `splunkctl/__init__.py` and the expected value in
   `tests/test_version.py`.
2. Move the `Unreleased` section of `CHANGELOG.md` under the new version.
3. Commit as `chore: release X.Y.Z`, tag `vX.Y.Z`, and push the tag.
4. Publish a GitHub release for the tag. The publish workflow checks that
   the tag matches the package version, runs `twine check --strict`, and
   uploads to PyPI through trusted publishing.

## Security issues

See [SECURITY.md](SECURITY.md). Do not report vulnerabilities in public
issues.
