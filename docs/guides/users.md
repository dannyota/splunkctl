# Users and roles

Manage Splunk users and roles via the REST API.

## Why this matters

Access control is the backbone of any SecOps deployment. Auditors ask
who has admin privileges, compliance frameworks (SOC 2, HIPAA) require
periodic access reviews, and every new analyst needs a correctly scoped
account on day one. Running these checks through the CLI gives you
a repeatable, scriptable workflow instead of clicking through the web UI.

## Commands

```bash
splunkctl users list                          # list all users
splunkctl users get admin                     # user details
splunkctl users roles                         # list all roles
splunkctl users create --name newuser \
    --roles user --email user@example.com \
    --yes                                     # create (prompts for password)
splunkctl users update newuser \
    --roles 'user,power' --yes                # change roles
splunkctl users delete newuser --yes          # delete user
```

### Password input

Three ways to supply a password (for `users create` or `users update
--password-stdin`):

| Method | Command | When to use |
|--------|---------|-------------|
| Interactive prompt | _(omit `--password`)_ | TTY sessions (default) |
| Stdin pipe | `--password-stdin` | Scripts, CI/CD |
| CLI flag | `--password` | Quick one-offs (visible in `ps`) |

```bash
# Interactive (hidden prompt with confirmation):
splunkctl users create --name jdoe --roles user --yes

# Pipe from a secret manager:
vault kv get -field=pw secret/splunk \
  | splunkctl users create --name jdoe --roles user --password-stdin --yes

# CLI flag (password visible in process list -- avoid in production):
splunkctl users create --name jdoe --password 's3cret' --roles user --yes
```

## Recipes

### Audit privileged accounts

List every user with `admin_all_objects` capability:

```bash
splunkctl users roles --json \
  | jq '[.[] | select(.capabilities | index("admin_all_objects")) | .name]'
```

### Onboard a new SOC analyst

Create a user with the `user` role, then verify:

```bash
openssl rand -base64 16 \
  | splunkctl users create --name jdoe \
      --password-stdin --roles user \
      --email jdoe@example.com --yes
splunkctl users get jdoe
```

### Periodic access review

Dump all users and roles to a file for compliance review:

```bash
splunkctl users list --json | jq '.[] | {name, roles, email}' > review.json
splunkctl users roles --json | jq '.[] | {name, capabilities}' >> review.json
```

## Tips

- Role changes take effect on the user's next login; no restart needed.
- The `--json` flag produces machine-readable output suitable for piping
  into `jq`, compliance scripts, or LLM agent tool chains.
