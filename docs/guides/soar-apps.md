<!-- summary: List, inspect, install, and uninstall Splunk SOAR apps, and read an app's configuration schema before creating an asset for it. -->

# Install SOAR apps

When to use: you need to see which apps a SOAR instance has, read the configuration keys an app expects before creating an asset, or install or remove an app package.

## Prerequisites

- SOAR credentials in the active profile (`splunkctl config init --soar`) and a passing `splunkctl soar test`.
- `uninstall` requires username and password credentials. SOAR refuses automation tokens on DELETE, so a token-only profile fails with a `kind: auth` error.
- `install` needs a local `.tgz` package from the Splunk SOAR app store or an app developer build.

## Synopsis

```text
splunkctl soar apps list [--installed] [--category TEXT] [--limit N]
splunkctl soar apps get <APP_ID> [--actions]
splunkctl soar apps install <PATH> [--yes]
splunkctl soar apps uninstall <NAME_OR_ID> [--yes]
```

## Workflow

### Find the app

```bash
splunkctl soar apps list --installed
splunkctl soar apps list --category SIEM
splunkctl soar apps list --json
```

`--installed` excludes staged apps (uploaded but not configured). `--category` filters by the app's category string. Expected result: one row per app with its id, name, version, and install status.

### Read the configuration schema

```bash
splunkctl soar apps get 5
splunkctl soar apps get 5 --actions
```

The `configuration` map lists each key with `data_type` (string, password, numeric, boolean), `required`, and `default`. These are the keys you pass to `soar assets create --set` (see [Configure assets and monitor ingestion](soar-assets.md)). `--actions` appends the supported actions from `/rest/app/<id>/actions` under an `actions` key.

### Install an app

> **Safety:** Target is the SOAR host in the active profile. Impact: a new app appears as staged on the instance. Preview with `splunkctl soar apps install myapp.tgz`, apply with `splunkctl soar apps install myapp.tgz --yes`, and verify with `splunkctl soar apps list`.

```bash
splunkctl soar apps install myapp.tgz
splunkctl soar apps install myapp.tgz --yes
```

The file is base64-encoded and posted to `/rest/app`. The new app shows as staged until you configure and activate it in the SOAR UI.

### Uninstall an app

> **Safety:** Target is the SOAR host in the active profile. Impact: the app and its assets stop working. Preview with `splunkctl soar apps uninstall DNS`, apply with `splunkctl soar apps uninstall DNS --yes`, and verify with `splunkctl soar apps list --installed`.

```bash
splunkctl soar apps uninstall DNS
splunkctl soar apps uninstall 42 --yes
```

A name is resolved to an id through the API before the DELETE.

## Troubleshooting

- `kind: auth` on uninstall: the profile has only an automation token. Add a username and password with `splunkctl config init --soar`.
- The app does not appear in `list --installed` after install: it is staged. Configure and activate it in the SOAR UI, or drop `--installed` to see it.
- `kind: not_found` on uninstall by name: run `splunkctl soar apps list` and use the numeric id.

## See also

- [Configure assets and monitor ingestion](soar-assets.md)
- [Run actions](soar-actions.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
