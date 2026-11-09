# AGENTS.md

Instructions for coding agents working in this repository. Human contributors
start with [CONTRIBUTING.md](CONTRIBUTING.md), which has the full detail.

## Setup

- Python 3.12 or newer. Create the dev environment once per checkout or
  worktree with `uv sync --extra dev`, then prefix commands with `uv run`.
  Without uv: `python -m pip install -e '.[dev]'` into a venv.
- Enable the leak guard: `git config core.hooksPath .githooks`. Put
  instance-specific strings (hostnames, domains) in the git-ignored
  `.githooks/denylist.local`.

## Verify before committing

All of these must pass. CI runs the same set.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy splunkctl
bash scripts/check-lengths.sh
uv run splunkctl docs generate --check
bash scripts/gen-seo.sh --check
```

## Rules

- Every mutation is a dry run by default and goes through
  `splunkctl/guard.py`. Only `--yes` (or `yes=true` over MCP) executes it.
- Unit tests never need a live Splunk or SOAR. Mock the client, but model the
  real response: check a new endpoint's shape against the lab or the
  first-party REST reference before writing the mock. SOAR 8.8 broke several
  mocks that assumed fields the server does not return.
- Python files stay at or under 500 lines and Markdown at or under 450.
  Split by topic. Move old CHANGELOG sections to `docs/changelog-archive.md`.
- After changing commands, options or help text, run
  `uv run splunkctl docs generate` and `bash scripts/gen-seo.sh`, and commit
  the generated files.
- Prose is English, plain and direct, with no em dashes. Commit messages use
  conventional prefixes (`fix(soar): ...`) and no `Co-Authored-By` or
  "Generated with" trailers.
- Never commit secrets or instance data: `.env`, lab passwords, tokens, real
  hostnames. Design notes and plans go in `docs/plans/` or
  `docs/superpowers/`, which are git-ignored.

## Live smoke tests

- SIEM: `bash scripts/live-smoke.sh`. SOAR: `bash scripts/live-smoke-soar.sh`.
  Options are in CONTRIBUTING.md.
- Point them at a throwaway profile or env-only config (`SPLUNK_*`,
  `SPLUNK_WEB_URL`, `SOAR_*`). They create only `sc_live_*` fixtures and
  clean them up; report any leftovers.
- Licensed SOAR actions run only with `LIVE_SOAR_ACTIONS=1` (Community
  edition allows 100 per day).

## Lab

The lab is one Linux host (Ubuntu 24.04, VMware Workstation) that others can
rebuild from `installers/vmlab/`. macOS is fine for development but does not
host the lab.

- VMs on vmnet8 `100.65.1.0/24`: SIEM `100.65.1.10` (Splunk Enterprise
  10.6.1.1 + SSE), SOAR `100.65.1.11` (SOAR 8.8.0.282). Keycloak SAML runs on
  the host at `100.65.1.1:8080`:
  `lab/keycloak/labctl.sh start|stop|status|configure|verify`.
- Build and check: `installers/vmlab/README.md`, then `fetch-installers.sh`,
  `check-lab.sh`, `provision-lab.sh` and `verify-lab.sh`. Real credentials go
  in the git-ignored `installers/vmlab/config.local.env`. Never print them.
- SSH with the `ssh_vm <ip> <command>` helper from `installers/vmlab/lib.sh`
  (user `labadmin`, key `$LAB_SSH_KEY`).
- Always shut the VMs down gracefully from inside the OS:
  `ssh_vm <ip> "sudo shutdown -h now"`. Never force a VMware power-off, and
  never take or revert snapshots.
