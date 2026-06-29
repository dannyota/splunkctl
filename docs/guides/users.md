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
    --password 'pass' --roles user \
    --email user@example.com --yes            # create user
splunkctl users update newuser \
    --roles 'user,power' --yes                # change roles
splunkctl users delete newuser --yes          # delete user
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
splunkctl users create --name jdoe \
    --password "$(openssl rand -base64 16)" \
    --roles user --email jdoe@example.com --yes
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
