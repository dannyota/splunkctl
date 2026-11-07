<!-- summary: Install, update, reload, and uninstall Splunk apps from local packages with a preview before every change. -->

# Manage apps

When to use: you need to deploy or upgrade a Technology Add-on, a content pack such as Enterprise Security content, or a custom detection app on a remote instance, disable an app during an incident, or audit what is installed, without SSH or the Web UI.

## Prerequisites

- A profile that passes `splunkctl doctor`, including the `Web UI reachable` check: `install` uploads the package through the Splunk Web UI handler.
- An account allowed to install and edit apps (for example the `admin` role).
- For `install`: a local `.spl` or `.tar.gz` package.

## Synopsis

```text
splunkctl apps list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl apps get <NAME>
splunkctl apps install --path <PACKAGE.spl|PACKAGE.tar.gz> [--force] [--yes]
splunkctl apps update <NAME> [--enabled|--disabled] [--visible|--hidden] [--yes]
splunkctl apps uninstall <NAME> [--yes]
splunkctl apps reload [--yes]
```

## Workflow

### List and inspect

```bash
splunkctl apps list
splunkctl apps list --filter TA-
splunkctl apps get SplunkForwarder
splunkctl apps list --json | jq '.[] | {name, version, disabled}'
```

Expected result: one row per installed app; `get` prints the app's full settings. `--filter`, `--limit`, and `--offset` apply client side.

### Install or upgrade from a local package

> **Safety:** Target is the Splunk host in the active profile. Impact: the package is uploaded through Splunk Web and installed; with `--force` an existing app of the same name is overwritten. Preview with `splunkctl apps install --path ./Splunk_TA_windows-8.9.0.spl`, apply by adding `--yes`, and verify with `splunkctl apps get Splunk_TA_windows`.

```bash
splunkctl apps install --path ./Splunk_TA_windows-8.9.0.spl
splunkctl apps install --path ./Splunk_TA_windows-8.9.0.spl --yes
splunkctl apps install --path ./DA-ESS-ContentUpdate-4.29.0.spl --force --yes
```

Expected result: the app appears in `splunkctl apps list`. The upload goes from your machine to the Splunk Web UI handler, so no SSH, SCP, or server filesystem access is needed. `--force` is required when the app already exists on the instance (reinstall or upgrade). An install may still need a Splunk restart to activate new modular inputs or scripted lookups; the CLI does not restart Splunk.

### Disable an app during an incident

> **Safety:** Target is the Splunk host in the active profile. Impact: the app's scheduled searches and knowledge objects stop running until re-enabled. Preview with `splunkctl apps update SplunkEnterpriseSecuritySuite --disabled`, apply by adding `--yes`, and verify with `splunkctl apps get SplunkEnterpriseSecuritySuite --json` (check `disabled`).

```bash
splunkctl apps update SplunkEnterpriseSecuritySuite --disabled
splunkctl apps update SplunkEnterpriseSecuritySuite --disabled --yes
splunkctl apps update SplunkEnterpriseSecuritySuite --enabled --yes
splunkctl apps update my_app --enabled --visible --yes
splunkctl apps update my_app --disabled --hidden --yes
```

Expected result: `Updated app 'NAME'.`. `--visible` and `--hidden` control whether the app shows in the Splunk Web app menu; at least one of the four flags is required.

### Uninstall an app

> **Safety:** Target is the Splunk host in the active profile. Impact: the app and its configuration are removed from the instance. Preview with `splunkctl apps uninstall my_app`, apply by adding `--yes`, and verify with `splunkctl apps list --filter my_app`.

```bash
splunkctl apps uninstall my_app
splunkctl apps uninstall my_app --yes
```

### Reload all apps after a bulk change

> **Safety:** Target is the Splunk host in the active profile. Impact: every app's configuration is re-read by splunkd. Preview with `splunkctl apps reload`, apply with `splunkctl apps reload --yes`, and verify with `splunkctl apps list`.

```bash
splunkctl apps reload --yes
```

## Troubleshooting

- `not_found` from `get`, `update`, or `uninstall`: the app id (directory name) differs from its label; find it with `splunkctl apps list --filter <text>`.
- `App install failed` or a `web` error: Splunk Web is not reachable from this machine; run `splunkctl doctor` and check `Web UI reachable`.
- Install fails because the app already exists: add `--force`.
- `No settings specified`: `update` needs `--enabled`, `--disabled`, `--visible`, or `--hidden`.
- `permission` on `update` or `uninstall`: the account lacks app administration rights; use an `admin` account.
- New inputs or lookups from an installed app do not run: restart Splunk from the server; the CLI does not restart it.

## See also

- [Diagnose a connection](doctor.md)
- [Manage detection rules](rules.md)
- [Manage configuration as code](state.md)
- [Command reference: apps](../commands/apps.md)
