# Configure

## Interactive setup

```bash
splunkctl config init
```

Prompts for host, port, username, password, and TLS verification, then writes
`~/.splunkctl/config.yaml` with `0600` permissions. SAML detection runs only
when `--web-url URL` is supplied. Run `splunkctl config test` to check
connectivity and authentication after setup.

## Config file

Location: `~/.splunkctl/config.yaml`

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

**TLS verification is on by default.** Production instances with valid
certificates work out of the box. For lab/dev instances with self-signed
certs, set `verify: false` explicitly in the profile — `config init` asks
during setup (default: yes).

## Profiles (dev/UAT/prod)

For more than one Splunk instance, add a `profiles:` map and a `current:`
pointer instead of the flat keys above:

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
splunkctl config init --profile uat ...   # create/update one named profile
splunkctl config use uat                  # point 'current' at it (no connectivity test)
splunkctl config show                     # active profile (redacted) + other names
splunkctl config show --profile prod      # show a specific profile without switching
splunkctl --profile prod rules list       # override for a single invocation
```

**Selection precedence**: `--profile <name>` global flag > `current:`
pointer > `default`.

**Legacy files keep working.** A plain flat file (no `profiles:` key) is
treated as an implicit profile named `default` — nothing to migrate. Bare
`config init` writes that flat shape — unless the destination file already
has a `profiles:` key, in which case it folds the new values into
`profiles.default` instead, leaving sibling profiles and `current`
untouched (bare `config init` never clobbers an existing multi-profile
file). The first time you run `config init --profile <name>` against a
legacy file, it's upgraded to the `profiles:` schema in place: the old flat
keys move under `profiles.default`, the new named profile is added
alongside it, and file permissions stay `0600`.

**Guard banner.** Every dry-run preview and `--yes` confirmation prints
which instance is about to be mutated —
`[DRY RUN] ... (profile: uat @ uat.splunk.internal:8089)` — so switching
between dev/UAT/prod never happens silently. The banner is built from local
config only; it never opens a connection.

## Environment variables

| Variable | Maps to |
|---|---|
| `SPLUNK_HOST` | `host` |
| `SPLUNK_PORT` | `port` |
| `SPLUNK_TOKEN` | `token` |
| `SPLUNK_USER` | `username` |
| `SPLUNK_PASS` | `password` |

Environment variables override fields in the selected profile.

## Resolution priority

1. Environment variables
2. Selected profile
3. Built-in defaults

`--profile` and `--config` are the only root options that select configuration.

## Coexistence with Splunk's splunkctl

Splunk's own Go CLI, [`splunk/splunkctl`](https://github.com/splunk/splunkctl),
also writes `~/.splunkctl/config.yaml`, as a flat file with `host` (a full
URL) and `token`. This tool never rewrites that file.

- When `~/.splunkctl/config.yaml` is in Splunk's format and no `--config`
  is given, this tool reads and writes `~/.splunkctl/profiles.yaml`
  instead and prints one notice on standard error:
  `Splunk-format config at ~/.splunkctl/config.yaml; using ~/.splunkctl/profiles.yaml`.
- `splunkctl config init` writes to the same fallback file, so a single
  `config init` is enough on a host that already has Splunk's tool.
- An explicit `--config FILE` is never redirected. If that file is in
  Splunk's format, the command fails with
  `Splunk-format config at FILE. Use --config to select another file.`
- `splunkctl doctor` reports the config file in use as its first check.
- A hand-written file of this tool's own legacy flat format that contains
  only `host` and `token` is indistinguishable from Splunk's format and is
  treated the same way. Add `port` or `scheme`, or run `config init`, to
  keep using it.

Both tools install an executable named `splunkctl`. This package also
installs `splunkctl-py`, which runs the same CLI, for hosts where Splunk's
binary comes first on `PATH`.

## Watch mode

Re-run any read-only command at a fixed interval, clearing the screen
between runs (like `watch(1)` on Linux). Errors are printed in place and
the loop continues. Press Ctrl-C to stop.

```bash
splunkctl --watch 5 indexes list        # refresh every 5 seconds
splunkctl --watch 10 server health      # poll server health
splunkctl --watch 3 rules list --filter brute   # filtered view
```

Requires an interactive terminal (TTY). Mutation commands (those guarded
by `--yes`) are rejected.

## Verify

```bash
splunkctl config show    # display config (secrets redacted)
splunkctl config test    # test connectivity + auth
```
