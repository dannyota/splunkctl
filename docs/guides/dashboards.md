<!-- summary: Export Splunk dashboards to files, keep them in version control, and create, update, share, or delete them with a preview before every change. -->

# Manage dashboards

When to use: you want dashboard XML or Studio JSON in version control, need to copy a dashboard between instances, or must change who can see one.

## Prerequisites

- The optional SDK fork, because dashboard commands use its `Dashboard` entity classes:

  ```bash
  python -m pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
  ```

- A Splunk account with write access to the target app (for example the `admin` or `power` role in `search`).

## Synopsis

```text
splunkctl dashboards list [--app APP] [--all] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl dashboards get <NAME> [--app APP] [--definition]
splunkctl dashboards export [NAME] [--app APP] [--out FILE] [--definition] [--all --dir DIR]
splunkctl dashboards create --name <NAME> --file <FILE> [--app APP] [--type classic|studio|auto] [--sharing user|app|global] [--yes]
splunkctl dashboards update <NAME> --file <FILE> [--app APP] [--type classic|studio|auto] [--yes]
splunkctl dashboards share <NAME> --sharing <user|app|global> [--owner USER] [--app APP] [--yes]
splunkctl dashboards delete <NAME> [--app APP] [--yes]
```

`--app` defaults to `search` for the mutation commands.

## Workflow

### List and inspect

```bash
splunkctl dashboards list
splunkctl dashboards list --app search --filter soc
splunkctl dashboards get soc_overview --app search
splunkctl dashboards get soc_studio --definition
```

`list` shows dashboards only; add `--all` to include other views. `--filter`, `--limit`, and `--offset` apply client side after the app and type filters. `get` prints the XML source; `--definition` extracts the Studio JSON and errors on a Classic dashboard.

### Export to files

```bash
splunkctl dashboards export soc_overview --out dashboards/soc_overview.xml
splunkctl dashboards export soc_studio --definition --out dashboards/soc_studio.json
splunkctl dashboards export --all --dir dashboards/
```

Expected result: one file per dashboard, ready to commit. `--out` overwrites without prompting.

### Create a dashboard from a file

> **Safety:** Target is the Splunk host and app in the active profile (`--app`, default `search`). Impact: a new dashboard appears in that app. Preview with `splunkctl dashboards create --name new_dash --file dash.xml --app search`, apply by adding `--yes`, and verify with `splunkctl dashboards get new_dash --app search`.

```bash
splunkctl dashboards create --name new_dash --file dash.xml --app search
splunkctl dashboards create --name new_dash --file dash.xml --app search --yes
splunkctl dashboards create --name new_dash --file dash.json --type studio --sharing app --yes
```

`--type auto` (the default) detects Classic XML or Studio JSON from the file.

### Update a dashboard

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the dashboard source is replaced with the file's content. Preview with `splunkctl dashboards update soc_overview --file updated.xml`, apply by adding `--yes`, and verify with `splunkctl dashboards get soc_overview`.

```bash
splunkctl dashboards update soc_overview --file updated.xml --app search
splunkctl dashboards update soc_overview --file updated.xml --app search --yes
```

Export first so you can restore the previous version if needed.

### Change sharing

> **Safety:** Target is the Splunk host and app in the active profile. Impact: who can see the dashboard changes; `global` makes it visible from every app. Preview with `splunkctl dashboards share soc_overview --sharing app`, apply by adding `--yes`, and verify with `splunkctl dashboards list --filter soc_overview --json` (check `sharing`).

```bash
splunkctl dashboards share soc_overview --sharing app --yes
splunkctl dashboards share soc_overview --sharing global --owner admin --yes
```

### Delete a dashboard

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the dashboard is removed and cannot be recovered except from an export. Preview with `splunkctl dashboards delete old_dash --app search`, apply by adding `--yes`, and verify with `splunkctl dashboards list --app search --filter old_dash`.

```bash
splunkctl dashboards export old_dash --out backup/old_dash.xml
splunkctl dashboards delete old_dash --app search
splunkctl dashboards delete old_dash --app search --yes
```

## Troubleshooting

- `ImportError` or a message about missing `Dashboard` classes: install the SDK fork listed under Prerequisites.
- `not_found` on `get` or `update`: pass `--app`; the dashboard may live outside `search`.
- `--definition` errors: the dashboard is Classic XML, not Studio.
- `permission` on create or share: the account lacks write access to the app, or `global` sharing needs the `admin_all_objects` capability.

## See also

- [Manage configuration as code](state.md), which pulls and diffs dashboards
- [Run searches](search.md)
- [Install](install.md)
- [Command reference: dashboards](../commands/dashboards.md)
