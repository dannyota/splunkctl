# Configure

## Interactive setup

```bash
splunkctl config init
```

Prompts for host, port, auth method (token or username/password), tests the
connection, and writes `~/.splunkctl/config.yaml` with `0600` permissions.

## Config file

Location: `~/.splunkctl/config.yaml`

```yaml
host: "localhost"
port: 8089
scheme: "https"
username: "admin"
password: ""            # optional, can use token instead
token: ""               # bearer token (preferred)
verify_ssl: false       # self-signed certs common in Splunk
app: "search"           # default app context
owner: "nobody"         # default owner context
```

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

Env vars override fields of whichever profile is selected — same as they
override the flat config today.

## Resolution priority

1. CLI flags (`--host`, `--port`, `--token`)
2. Environment variables
3. Profile (config file)

## Verify

```bash
splunkctl config show    # display config (secrets redacted)
splunkctl config test    # test connectivity + auth
```
