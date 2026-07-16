# soar apps -- App Catalog

Manage SOAR apps -- list installed and staged apps, view config schemas,
install from tgz packages, and uninstall.

## Quick reference

```bash
# List all apps (installed + staged)
splunkctl soar apps list
splunkctl soar apps list --limit 10

# Only installed apps (exclude staged)
splunkctl soar apps list --installed

# Filter by category
splunkctl soar apps list --category SIEM

# Get app details (config schema)
splunkctl soar apps get 5

# Get app details with supported actions
splunkctl soar apps get 5 --actions

# Install an app from a tgz (dry-run preview)
splunkctl soar apps install myapp.tgz

# Install an app (apply)
splunkctl soar apps install myapp.tgz --yes

# Uninstall by name (dry-run preview)
splunkctl soar apps uninstall DNS

# Uninstall by id (apply)
splunkctl soar apps uninstall 42 --yes
```

## Install

Accepts a local `.tgz` file (app package from the SOAR app store or a
developer build). The file is base64-encoded and POSTed to
`/rest/app`. Guarded: dry-run by default, `--yes` to apply.

## Uninstall

Accepts an app name or numeric id. If a name is given, it is resolved
to an id via the API. Uses `DELETE /rest/app/<id>`. SOAR refuses token
auth on DELETE for most endpoints, so username/password credentials must
be configured in the profile.

## Notes

- Staging: newly installed apps appear as "staged" until configured and
  activated through the SOAR UI.
- Credentials: uninstall requires Basic auth (username + password).
  Token-only profiles will fail on DELETE.
