# splunkctl

CLI tool for Splunk Enterprise SIEM operations.

Query, inspect, and manage a Splunk Enterprise instance from the terminal.
Built on the [splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python)
fork with [Click](https://click.palletsprojects.com/).

## Install

```bash
pip install splunkctl
```

## Quick start

```bash
splunkctl config init              # interactive setup
splunkctl config test              # verify connectivity
splunkctl search run 'index=main | head 10'
splunkctl rules list
splunkctl dashboards list
```

## Features

- **Search**: run, export, oneshot, job management
- **Rules**: detection rule (saved search) CRUD
- **Alerts**: fired alerts, alert actions
- **Dashboards**: dashboard CRUD
- **Indexes**: index management
- **Inputs**: data input management
- **Lookups**: lookup table management
- **Parsers**: source types and field extractions
- **Apps**: installed app management
- **Users**: user and role management
- **Agent integration**: embedded SKILL.md for Claude Code

All write operations are **dry-run by default**. Pass `--yes` to apply.

## License

Apache-2.0
