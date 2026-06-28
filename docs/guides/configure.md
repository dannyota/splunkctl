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

## Environment variables

| Variable | Maps to |
|---|---|
| `SPLUNK_HOST` | `host` |
| `SPLUNK_PORT` | `port` |
| `SPLUNK_TOKEN` | `token` |
| `SPLUNK_USER` | `username` |
| `SPLUNK_PASS` | `password` |

## Resolution priority

1. CLI flags (`--host`, `--port`, `--token`)
2. Environment variables
3. Config file

## Verify

```bash
splunkctl config show    # display config (secrets redacted)
splunkctl config test    # test connectivity + auth
```
