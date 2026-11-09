# AGENTS.md

Instructions for coding agents working in this repository. The full
contributor guide, including every live smoke option, is
[CONTRIBUTING.md](CONTRIBUTING.md); this file adds the agent-specific rules.

## Setup

- Python 3.12 or newer. Create the dev environment once per checkout or
  worktree with `uv sync --extra dev`, then prefix commands with `uv run`.
  Without uv: `python -m pip install -e '.[dev]'` into a venv.
- Enable the leak guard: `git config core.hooksPath .githooks`. Put
  instance-specific strings (hostnames, domains) in the git-ignored
  `.githooks/denylist.local`.

## Verify before committing

All of these must pass locally. CI runs them too, plus a wheel install with an
MCP guide check, `pip-audit` and gitleaks (see `.github/workflows/ci.yml`).

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

- Commands that change a Splunk or SOAR instance are decorated with
  `@guarded` and call `guard.check` (SIEM) or `guard.soar_check` (SOAR)
  before any write. Without `--yes` (or `yes=true` over MCP) they only
  preview. Never add a write path that skips the guard.
- Unit tests never need a live Splunk or SOAR. Mock the client, but model the
  real response: check a new endpoint's shape against the lab or the
  first-party REST reference before writing the mock. SOAR 8.8 broke several
  mocks that assumed fields the server does not return.
- Python files stay at or under 500 lines and Markdown at or under 450, as
  `scripts/check-lengths.sh` enforces (it skips generated `docs/commands/`
  and local plans). Split by topic. Move old CHANGELOG sections to
  `docs/changelog-archive.md`.
- After changing commands, options or help text, run
  `uv run splunkctl docs generate`. After any change under `docs/`, run
  `bash scripts/gen-seo.sh`; a new sidebar page needs the
  `<!-- summary: ... -->` comment that script requires. Commit the
  generated files.
- Prose is English, plain and direct, with no em dashes. Commit messages use
  conventional prefixes (`fix(soar): ...`) and no `Co-Authored-By` or
  "Generated with" trailers.
- Never commit secrets or instance data: `.env`, lab passwords, tokens, real
  hostnames. Design notes and plans go in `docs/plans/` or
  `docs/superpowers/`, which are git-ignored.

## Live smoke tests

- Run them inside the dev environment so they use this checkout:
  `uv run bash scripts/live-smoke.sh` (SIEM) and
  `uv run bash scripts/live-smoke-soar.sh` (SOAR). Options and caveats are
  in CONTRIBUTING.md.
- Use a disposable instance, such as the lab or a throwaway container.
  Most fixtures are `sc_live_*` objects that the runners clean up, but the
  SIEM smoke also changes server state: it turns HEC on if it is off
  (restored at exit), adds a monitor input (`LIVE_MONITOR_PATH`, default
  `/tmp`) and, with `CIM_TGZ`, installs `Splunk_SA_CIM`. Report any
  leftovers.
- The SOAR smoke can consume licensed actions (Community edition allows 100
  per day). Read the licensed-action and active-playbook paragraph in
  CONTRIBUTING.md before setting `LIVE_SOAR_ACTIONS=1` or
  `LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS=1`.

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
