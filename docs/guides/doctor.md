# Doctor

Diagnose connection, authentication, server health, and user permissions
in a single command.

## Why this matters

`doctor` is the first command to run on a fresh setup, the first command
an LLM agent should call to bootstrap its session, and the fastest way
to isolate what broke when a previously working instance stops
responding. It validates every layer of the stack -- network, auth,
license, permissions, web UI -- so you do not waste time debugging the
wrong layer.

## Commands

```bash
splunkctl doctor                  # check everything
splunkctl doctor --json           # machine-readable output
```

## What it checks

1. **Connection** -- can we reach the REST API?
2. **Authentication** -- are credentials valid?
3. **Server health** -- version, OS, license status
4. **Permissions** -- 9 key capabilities: `search`, `admin_all_objects`,
   `edit_user`, `edit_roles`, `edit_tcp`, `edit_monitor`, `list_inputs`,
   `rest_apps_management`, `change_own_password`
5. **Web UI** -- is the Splunk Web interface reachable? (needed for
   lookup upload and app install)

## Exit codes

- `0` -- all checks passed
- `1` -- one or more checks failed

## Recipes

### First-run validation

After setting credentials in `.env` or `~/.splunkctl/config.yaml`, run
doctor to confirm everything is wired up:

```bash
splunkctl doctor
```

### CI pipeline gate

Fail a pipeline early if the Splunk instance is unreachable or the
service account lacks required permissions:

```bash
splunkctl doctor --json || exit 1
```

### LLM agent bootstrap

An agent should call `doctor --json` at session start, parse the
result, and abort with a clear message if any check fails:

```bash
splunkctl doctor --json | jq '.checks[] | select(.status == "FAIL")'
```

### Isolate a failure layer

When something breaks, `doctor` tells you whether the problem is
network, auth, license, or permissions -- so you fix the right thing.
