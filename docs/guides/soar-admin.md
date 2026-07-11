# SOAR Admin — Users, Roles, Audit

Manage SOAR platform users, inspect role permissions, and query the
audit trail. User mutations are guarded (dry-run by default, `--yes` to
apply). SOAR user deletion is a soft-delete (`is_active=False`).

## Commands

```bash
splunkctl soar users list                        # list users
splunkctl soar users list --type automation      # include hidden automation user
splunkctl soar users get 5                       # user detail
splunkctl soar users create \
    --username analyst1 --password 'P@ss!' \
    --type normal --role Analyst --yes           # create user
splunkctl soar users update 5 \
    --password 'NewP@ss!' --yes                  # change password
splunkctl soar users update 5 \
    --add-role Observer --remove-role Analyst \
    --yes                                        # modify roles
splunkctl soar users delete 5 --yes              # soft-delete
splunkctl soar users token 5                     # show hashed token info

splunkctl soar roles list                        # all 7 built-in roles
splunkctl soar roles get 1                       # single role + permissions

splunkctl soar audit                             # full audit log
splunkctl soar audit --user admin                # filter by username
splunkctl soar audit --container 42              # filter by container
splunkctl soar audit --playbook dns_lookup       # filter by playbook
splunkctl soar audit --start 2026-01-01 \
    --end 2026-06-30                             # time range
splunkctl soar audit --format csv                # request CSV from server
splunkctl soar audit --limit 50                  # limit rows
```

## User management

### Listing users

By default, the system `automation` user is hidden from `/rest/ph_user`.
Use `--type automation` to surface it. Use `--type normal` for human
users only.

```bash
splunkctl soar users list --type automation --json
```

### Creating users

Both `normal` and `automation` types are supported. Roles and allowed
IPs can be specified at creation.

```bash
splunkctl soar users create \
    --username bot_user \
    --password 'StrongP@ss1' \
    --type automation \
    --role Automation \
    --allowed-ip 10.0.0.1 \
    --yes
```

For automation users, the CLI prints a notice: the automation token
plaintext is shown **once** in the SOAR UI at creation time. It cannot
be retrieved via REST. `GET .../token` returns only the hashed key.

### Updating users

Password changes, role modifications, and profile updates are supported.
Roles use a read-modify-write pattern: `--add-role` and `--remove-role`
fetch the current role list, merge changes, and POST the result.

```bash
splunkctl soar users update 5 \
    --add-role Observer \
    --remove-role Analyst \
    --first-name Jane \
    --yes
```

Passwords are masked in the dry-run preview (shown as `********`).

### Deleting users

SOAR user deletion is a **soft delete** (`is_active=False`). The user
record remains in the system; their automation token returns "User is
inactive" on subsequent API calls. The dry-run preview explains this.

```bash
splunkctl soar users delete 5 --yes
```

### Token inspection

`users token <id>` shows the hashed key and expiry date. This is
explicitly **not** the usable plaintext token.

```bash
splunkctl soar users token 5
```

## Roles

SOAR ships with 7 immutable built-in roles. `roles list` shows the full
permission matrix; `roles get <id>` shows a single role in detail.

```bash
splunkctl soar roles list --json | jq '.[].name'
```

## Audit log

The audit endpoint returns a bare array (normalized by `SOARClient`).
Supports time-range filtering (`--start`/`--end`), user/playbook/container
filters, server-side CSV format, and row limits.

```bash
splunkctl soar audit --user admin --start 2026-07-01 --limit 100
```
