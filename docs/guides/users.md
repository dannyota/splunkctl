<!-- summary: Create, update, and delete Splunk users and roles with a preview before every change. -->

# Manage users and roles

When to use: a new analyst needs a correctly scoped account, an auditor asks who holds admin privileges, a compliance framework (SOC 2, HIPAA) requires a periodic access review, or you need to create or adjust a role, all from a scriptable terminal instead of the web UI.

## Prerequisites

- A Splunk account with the `edit_user` and `edit_roles` capabilities (the `admin` role has both).
- Role names from `splunkctl users roles list`.
- For `create` in scripts: the password on stdin from a secret manager, not on the command line.

## Synopsis

```text
splunkctl users list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl users get <NAME>
splunkctl users create --name <NAME> --roles <ROLE,ROLE> [--password TEXT | --password-stdin] [--email TEXT] [--realname TEXT] [--yes]
splunkctl users update <NAME> [--roles ROLE,ROLE] [--email TEXT] [--realname TEXT] [--default-app APP] [--password TEXT | --password-stdin] [--set KEY=VALUE]... [--yes]
splunkctl users delete <NAME> [--yes]

splunkctl users roles list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl users roles get <NAME>
splunkctl users roles create <NAME> [--capabilities LIST] [--imported-roles LIST] [--search-indexes LIST] [--search-filter TEXT] [--default-app APP] [--set KEY=VALUE]... [--yes]
splunkctl users roles update <NAME> [same flags as roles create] [--yes]
splunkctl users roles delete <NAME> [--yes]
```

## Workflow

### List and inspect users and roles

```bash
splunkctl users list
splunkctl users list --filter svc
splunkctl users get admin
splunkctl users roles list
splunkctl users roles get power
```

Expected result: one row per user with `name`, `email`, and `roles`; one row per role with its capabilities (`roles get` shows the full, untruncated detail).

### Create a user

> **Safety:** Target is the Splunk host in the active profile. Impact: a new account that can log in with the given roles. Preview with `splunkctl users create --name jdoe --roles user --email jdoe@example.com`, apply by adding `--yes`, and verify with `splunkctl users get jdoe`.

```bash
splunkctl users create --name jdoe --roles user --email jdoe@example.com --yes
openssl rand -base64 16 \
  | splunkctl users create --name jdoe --password-stdin --roles user --email jdoe@example.com --yes
vault kv get -field=pw secret/splunk \
  | splunkctl users create --name jdoe --roles user --password-stdin --yes
splunkctl users create --name jdoe --password 's3cret' --roles user --yes
splunkctl users get jdoe
```

Expected result: the user exists with the `user` role. The password comes from one of three places:

| Method | Command | When to use |
|--------|---------|-------------|
| Interactive prompt | omit `--password` | TTY sessions (default); hidden prompt with confirmation |
| Stdin pipe | `--password-stdin` | Scripts, CI/CD, secret managers |
| CLI flag | `--password` | Quick one-offs only; the value is visible in `ps` and `/proc` |

### Update a user

> **Safety:** Target is the Splunk host in the active profile. Impact: the user's roles, email, display name, default app, or password change immediately. Preview with `splunkctl users update jdoe --roles 'user,power'`, apply by adding `--yes`, and verify with `splunkctl users get jdoe`.

```bash
splunkctl users update jdoe --roles 'user,power' --yes
splunkctl users update jdoe --email jdoe@corp.example --realname "Jane Doe" --default-app search --yes
openssl rand -base64 16 | splunkctl users update jdoe --password-stdin --yes
splunkctl users update jdoe --set tz=UTC --yes
```

Expected result: `--roles` replaces the whole role list. `update` prompts for a password only when you pass `--password` or `--password-stdin`. Role changes take effect on the user's next login; no restart is needed. `--set` passes any other user attribute as `KEY=VALUE`.

### Delete a user

> **Safety:** Target is the Splunk host in the active profile. Impact: the account is removed and can no longer log in. Preview with `splunkctl users delete jdoe`, apply by adding `--yes`, and verify with `splunkctl users list --filter jdoe`.

```bash
splunkctl users get jdoe --json > jdoe-before.json
splunkctl users delete jdoe
splunkctl users delete jdoe --yes
```

### Create or change a role

> **Safety:** Target is the Splunk host in the active profile. Impact: every user holding the role gains or loses capabilities and index access at next login; `roles delete` removes the role from the instance. Preview with `splunkctl users roles create soc_analyst --imported-roles user --search-indexes 'auth,firewall'`, apply by adding `--yes`, and verify with `splunkctl users roles get soc_analyst`.

```bash
splunkctl users roles create soc_analyst \
    --imported-roles user --search-indexes 'auth,firewall' \
    --capabilities 'schedule_search,edit_search_schedule_window' --default-app search --yes
splunkctl users roles update soc_analyst --search-filter 'NOT sourcetype=hr' --yes
splunkctl users roles update soc_analyst --set srchDiskQuota=500 --yes
splunkctl users roles delete soc_analyst --yes
```

Expected result: `roles get soc_analyst` shows the capabilities, imported roles, allowed indexes, search filter, and default app. Lists are comma-separated.

### Audit privileged accounts

```bash
splunkctl users roles list --json \
  | jq '[.[] | select(.capabilities | index("admin_all_objects")) | .name]'
```

Expected result: the names of every role that carries `admin_all_objects`; cross-check holders with `splunkctl users list --json`.

### Run a periodic access review

```bash
splunkctl users list --json | jq '.[] | {name, roles, email}' > review.json
splunkctl users roles list --json | jq '.[] | {name, capabilities}' >> review.json
```

Expected result: one file with every user, their roles, and every role's capabilities, ready to attach to the review ticket. `--json` output also suits compliance scripts and LLM agent tool chains.

## Troubleshooting

- `permission` on `create`, `update`, or `roles`: the account lacks `edit_user` or `edit_roles`.
- `not_found` on `get`, `update`, or `delete`: usernames are case-sensitive; find the exact name with `splunkctl users list --filter <part>`.
- `http` error on `create` mentioning the password: the server's password policy rejected it; generate a longer one.
- `http` error on `create` or `update` naming a role: the role does not exist; check `splunkctl users roles list`.
- `conflict` on `create` or `roles create`: the user or role already exists; use `update`.
- `--password-stdin` read an empty line: nothing was piped; the command reads exactly one line from stdin.
- Usage error (exit 2) on `create`: `--name` and `--roles` are required.

## See also

- [Audit changes and attest RBAC](audit.md)
- [Check server health and topology](server.md), for the authentication provider and role mapping
- [Log in through browser SAML](auth.md)
- [Administer SOAR users and roles](soar-admin.md)
- [Command reference: users](../commands/users.md)
