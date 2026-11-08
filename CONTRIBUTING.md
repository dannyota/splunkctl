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

Python 3.12 or newer is required. The pre-commit hook runs the same checks
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
  For a manual check against a real instance, run
  `SPLUNKCTL=splunkctl bash scripts/live-smoke.sh` with a throwaway profile.
  `LIVE_ONLY`/`LIVE_SKIP` select comma-separated groups; `LIVE_MONITOR_PATH`
  is an existing server path (default `/tmp`), monitored disabled initially;
  the inputs step skips if that exact input already exists.
  `CIM_TGZ` optionally supplies a Splunk_SA_CIM package;
  `LIVE_HEC_URL` overrides the HEC base URL; `LIVE_PYTHON` names the
  interpreter that has splunkctl installed (default `python3`).
  The `LIVE_HEC_URL` scheme must match `hec settings` `enableSSL`: use
  `https` on a default install, or `http` when SSL is disabled.
  For a mapped port, for example, set `LIVE_HEC_URL=https://127.0.0.1:18088`.
  `datamodels rebuild --yes` runs only when `CIM_TGZ` is set and the server
  reports acceleration enabled within 90 seconds; otherwise it reports
  SKIPPED. A populated acceleration summary is not awaited, so the
  populated-status fields stay covered by unit tests only.
  The `kvstore` export/import round trip requires a healthy KV store.
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
