<!-- summary: Manage Splunk SOAR users, inspect role permissions, and query the platform audit trail. -->

# Administer SOAR users and roles

When to use: you need to create or deactivate a SOAR user, rotate a password, change role membership, provision an automation account, review the built-in role permission matrix, or pull the platform audit trail for a user, container, playbook, or time range.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- An account whose role may manage users and roles (the built-in Administrator role does).
- Role names from `splunkctl soar roles list`.

## Synopsis

```text
splunkctl soar users list [--type normal|automation]
splunkctl soar users get <USER_ID>
splunkctl soar users create --username <NAME> [--password TEXT] [--type normal|automation] [--role ROLE]... [--allowed-ip IP]... [--first-name TEXT] [--last-name TEXT] [--yes]
splunkctl soar users update <USER_ID> [--password TEXT] [--add-role ROLE]... [--remove-role ROLE]... [--first-name TEXT] [--last-name TEXT] [--allowed-ip IP]... [--yes]
splunkctl soar users delete <USER_ID> [--yes]
splunkctl soar users token <USER_ID>

splunkctl soar roles list
splunkctl soar roles get <ROLE_ID>

splunkctl soar audit [--user NAME] [--container CONTAINER_ID] [--playbook NAME] [--start ISO8601] [--end ISO8601] [--format csv] [--limit N]
```

## Workflow

### List and inspect users

```bash
splunkctl soar users list
splunkctl soar users list --type normal
splunkctl soar users list --type automation --json
splunkctl soar users get 5
splunkctl soar users token 5
```

Expected result: one row per user. The system `automation` user is hidden from `/rest/ph_user` by default; `--type automation` surfaces it, `--type normal` shows human users only. `token` shows the hashed key and expiry date for a user, which is explicitly not the usable plaintext token.

### Create a user

> **Safety:** Target is the SOAR host in the active profile. Impact: a new account that can log in (or call the REST API, for `--type automation`) with the roles you grant. Preview with `splunkctl soar users create --username analyst1 --type normal --role Analyst`, apply by adding `--yes`, and verify with `splunkctl soar users list`.

```bash
splunkctl soar users create \
    --username analyst1 --password 'P@ss!' \
    --type normal --role Analyst --yes
splunkctl soar users create \
    --username bot_user \
    --password 'StrongP@ss1' \
    --type automation \
    --role Automation \
    --allowed-ip 10.0.0.1 \
    --yes
```

Expected result: the user exists with the given roles and, for automation users, the allowed IPs. Omit `--password` to be prompted securely; the preview masks it as `********`. For automation users the CLI prints a notice: the automation token plaintext is shown once in the SOAR UI at creation time and cannot be retrieved through REST (`users token` returns only the hashed key).

### Update a user

> **Safety:** Target is the SOAR host in the active profile. Impact: the password, roles, profile fields, or allowed IPs change for that account immediately. Preview with `splunkctl soar users update 5 --add-role Observer --remove-role Analyst`, apply by adding `--yes`, and verify with `splunkctl soar users get 5`.

```bash
splunkctl soar users update 5 --password 'NewP@ss!' --yes
splunkctl soar users update 5 \
    --add-role Observer \
    --remove-role Analyst \
    --first-name Jane \
    --yes
splunkctl soar users update 7 --allowed-ip 10.0.0.1 --allowed-ip 10.0.0.2 --yes
```

Expected result: roles use a read-modify-write pattern: `--add-role` and `--remove-role` fetch the current role list, merge the change, and post the result. `--allowed-ip` replaces the whole list. Passwords are masked in the dry-run preview.

### Deactivate a user

> **Safety:** Target is the SOAR host in the active profile. Impact: SOAR user deletion is a soft delete (`is_active=False`); the record stays, logins stop, and the user's automation token returns "User is inactive" on every later API call. Preview with `splunkctl soar users delete 5` (the preview explains the soft delete), apply by adding `--yes`, and verify with `splunkctl soar users get 5`.

```bash
splunkctl soar users delete 5
splunkctl soar users delete 5 --yes
```

### Review roles

```bash
splunkctl soar roles list
splunkctl soar roles list --json | jq '.[].name'
splunkctl soar roles get 1
```

Expected result: SOAR ships with 7 immutable built-in roles; `list` shows the full permission matrix and `get` shows one role in detail. Use the names here for `--role`, `--add-role`, and `--remove-role`.

### Query the audit log

```bash
splunkctl soar audit
splunkctl soar audit --user admin
splunkctl soar audit --container 42
splunkctl soar audit --playbook dns_lookup
splunkctl soar audit --start 2026-01-01 --end 2026-06-30
splunkctl soar audit --user admin --start 2026-07-01 --limit 100
splunkctl soar audit --format csv
```

Expected result: audit rows filtered by user, container, playbook, or time range (`--start` and `--end` are ISO 8601). The endpoint returns a bare array, which the CLI normalizes like every other list. `--format csv` asks the server for CSV; `--limit` caps the rows.

## Troubleshooting

- `permission` on `users` or `roles`: the account's role cannot manage users; use an Administrator account or token.
- `not_found` on `users get`, `update`, or `delete`: commands take the numeric id from `splunkctl soar users list`, not the username.
- `http` 400 on `create` or `update`: the server rejected a field; check that each `--role` matches a name from `splunkctl soar roles list` and read the message for the failing field.
- `auth` error from an automation user after `delete`: expected, the account is inactive; create a new one, the token cannot be revived.
- The automation token is not in any output: by design; copy it from the SOAR UI at creation. `users token` only confirms the hash and expiry.
- `--start` rejected: use ISO 8601 (`2026-07-01` or `2026-07-01T00:00:00`).

## See also

- [Set up and check SOAR](soar.md)
- [Work SOAR incidents](soar-incidents.md)
- [Audit changes and attest RBAC](audit.md)
- [Manage users and roles](users.md)
- [Command reference: soar](../commands/soar.md)
