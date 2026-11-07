<!-- summary: Set up splunkctl profiles for development, UAT, and production, and override them with environment variables or flags. -->

# Configure

When to use: splunkctl is installed and you need to point it at one or more Splunk instances, choose how credentials are supplied, and switch between development, UAT, and production without mutating the wrong host.

## Prerequisites

- splunkctl installed (see [Install](install.md)).
- The host, management port (8089 by default), and either a bearer token or a username and password for each instance.
- For SOAR, the SOAR host, REST port (8443 by default), and automation token; see [Set up and check SOAR](soar.md).

## Synopsis

```text
splunkctl config init [--host HOST] [--port PORT] [--username USER] [--password PASS] [--scheme https|http] [--verify|--no-verify] [--profile NAME] [--path FILE] [--web-url URL] [--auth-mode auto|token|password|browser]
splunkctl config init --soar [--sso-url URL] [--profile NAME]
splunkctl config show
splunkctl config use <NAME>
splunkctl config test
splunkctl --profile <NAME> <COMMAND>
splunkctl --config <FILE> <COMMAND>
splunkctl --watch <SECONDS> <READ_ONLY_COMMAND>
```

## Workflow

### Run interactive setup

```bash
splunkctl config init
splunkctl config test
```

Expected result: `config init` prompts for host (default `localhost`), port (8089), username (`admin`), password, and TLS verification (default yes), then writes `~/.splunkctl/config.yaml` with `0600` permissions and prints `Config saved to ...`. Every prompt can be answered with the matching flag instead. SAML detection runs only when `--web-url URL` is supplied (see [Log in through browser SAML](auth.md)). `config test` connects, authenticates, and prints the server name and version.

### Write the config file by hand

The file is `~/.splunkctl/config.yaml`:

```yaml
host: "localhost"
port: 8089
scheme: "https"
username: "admin"
password: ""            # optional, can use token instead
token: ""               # bearer token (preferred)
verify: true            # TLS cert verification (default: on)
app: "search"           # default app context
owner: "nobody"         # default owner context
```

TLS verification is on by default, so production instances with valid certificates work out of the box. For lab instances with self-signed certificates set `verify: false` explicitly; `config init` asks during setup.

### Add profiles for dev, UAT, and prod

For more than one instance, add a `profiles:` map and a `current:` pointer instead of the flat keys:

```yaml
profiles:
  dev:
    host: "dev.splunk.internal"
    username: "admin"
    password: "devpass"
  uat:
    host: "uat.splunk.internal"
    token: "..."
  prod:
    host: "prod.splunk.internal"
    token: "..."
current: "uat"           # active profile when nothing else selects one
```

```bash
splunkctl config init --profile uat
splunkctl config use uat
splunkctl config show
splunkctl --profile prod config show
splunkctl --profile prod rules list
```

Expected result: `config init --profile NAME` creates or updates one named profile; `config use` points `current` at it without a connectivity test; `config show` prints the active profile with secrets redacted plus the other profile names; the global `--profile` flag overrides the pointer for one invocation. Selection precedence: `--profile <name>` > `current:` pointer > `default`.

Legacy files keep working. A flat file (no `profiles:` key) is treated as an implicit profile named `default`, nothing to migrate. Bare `config init` writes that flat shape, unless the destination already has a `profiles:` key, in which case it folds the new values into `profiles.default` and leaves sibling profiles and `current` untouched, so it never clobbers a multi-profile file. The first `config init --profile <name>` against a legacy file upgrades it in place: the old flat keys move under `profiles.default`, the new profile is added beside it, and permissions stay `0600`.

Every dry-run preview and `--yes` confirmation prints which instance is about to be mutated, for example `[DRY RUN] Create index 'x' (profile: uat @ uat.splunk.internal:8089)`, so switching between dev, UAT, and prod never happens silently. The banner is built from local config only; it never opens a connection.

### Override with environment variables

| Variable | Maps to |
|---|---|
| `SPLUNK_HOST` | `host` |
| `SPLUNK_PORT` | `port` |
| `SPLUNK_TOKEN` | `token` |
| `SPLUNK_USER` | `username` |
| `SPLUNK_PASS` | `password` |
| `SPLUNK_VERIFY` | `verify` |

`SOAR_HOST`, `SOAR_PORT`, `SOAR_TOKEN`, `SOAR_USER`, `SOAR_PASS`, and `SOAR_VERIFY` override the profile's `soar:` section the same way.

```bash
SPLUNK_HOST=ci.splunk.internal SPLUNK_TOKEN="$CI_TOKEN" splunkctl doctor
```

Resolution order, highest first: CLI flags, environment variables, the selected profile, built-in defaults. `--profile` and `--config` are the only root options that select configuration.

### Coexist with Splunk's own splunkctl

Splunk's Go CLI, [`splunk/splunkctl`](https://github.com/splunk/splunkctl), also writes `~/.splunkctl/config.yaml`, as a flat file with `host` (a full URL) and `token`. This tool never rewrites that file:

- When `~/.splunkctl/config.yaml` is in Splunk's format and no `--config` is given, this tool reads and writes `~/.splunkctl/profiles.yaml` instead and prints one notice on standard error: `Splunk-format config at ~/.splunkctl/config.yaml; using ~/.splunkctl/profiles.yaml`.
- `splunkctl config init` writes to the same fallback file, so one `config init` is enough on a host that already has Splunk's tool.
- An explicit `--config FILE` is never redirected. If that file is in Splunk's format the command fails with `Splunk-format config at FILE: this is a flat host/token file written by Splunk's splunkctl. Pass a profiles file with --config, or create one with: splunkctl config init --path FILE`.
- `splunkctl doctor` reports the config file in use as its first check.
- A hand-written file in this tool's own legacy flat format that contains only `host` and `token` is indistinguishable from Splunk's format and is treated the same way. Add `port` or `scheme`, or run `config init`, to keep using it.

Both tools install an executable named `splunkctl`. This package also installs `splunkctl-py`, which runs the same CLI, for hosts where Splunk's binary comes first on `PATH`.

### Watch a read-only command

```bash
splunkctl --watch 5 indexes list
splunkctl --watch 10 server health
splunkctl --watch 3 rules list --filter brute
```

Expected result: the command re-runs every N seconds, clearing the screen between runs like `watch(1)`. Errors are printed in place and the loop continues; Ctrl-C stops it. `--watch` requires an interactive terminal (TTY) and rejects mutation commands (those guarded by `--yes`).

### Verify

```bash
splunkctl config show
splunkctl config test
splunkctl doctor
```

Expected result: the active profile with secrets redacted, a successful connection and login, and a passing check list.

## Troubleshooting

- `config` error or `Config` check failing in `doctor`: the YAML is not a mapping or is unreadable; fix the file or pass `--config FILE`.
- `Splunk-format config at FILE` with `--config`: that file belongs to Splunk's CLI; pass a profiles file or create one with `splunkctl config init --path FILE`.
- A profile-not-found error: the name is not under `profiles:`; check `splunkctl config show` for the known names.
- `auth` from `config test`: wrong token or password for that profile; environment variables such as `SPLUNK_TOKEN` override the file, so unset them when testing a profile.
- `connection` from `config test`: host or port wrong, or the REST port is blocked; `curl -k https://HOST:8089/services/server/info` from this machine.
- TLS certificate error on a lab instance: set `verify: false` in that profile or `SPLUNK_VERIFY=false`.
- `--watch requires an interactive terminal (TTY)` or `--watch cannot be used with mutation commands`: run it in a terminal and only with read-only commands.

## See also

- [Install](install.md)
- [Diagnose a connection](doctor.md)
- [Log in through browser SAML](auth.md)
- [Set up and check SOAR](soar.md)
- [Relationship to Splunk's splunkctl](splunk-cli.md)
- [Command reference: config](../commands/config.md)
