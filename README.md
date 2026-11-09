# splunkctl

<a href="https://splunkctl.danny.vn"><img src="https://raw.githubusercontent.com/dannyota/splunkctl/master/docs/assets/banner.svg" alt="splunkctl: CLI and MCP server for Splunk Enterprise, Enterprise Security, and SOAR" width="600"></a>

Operate Splunk Enterprise, Enterprise Security, and Splunk SOAR from a terminal, or give an AI agent the same commands through MCP.

Requires Python 3.12+ and credentials for your Splunk instance.

## Quickstart

```bash
python -m pip install splunkctl
splunkctl config init
splunkctl doctor
```

[Documentation](https://splunkctl.danny.vn) · [Installation requirements](https://splunkctl.danny.vn/#/guides/install)

## Tasks

- Investigate: run SPL, read fired alerts, and triage Enterprise Security notables. [Search](https://splunkctl.danny.vn/#/guides/search), [Triage notables](https://splunkctl.danny.vn/#/guides/es)
- Deploy detections: export saved searches to YAML, review the diff, and import them on another instance. [Manage detection rules](https://splunkctl.danny.vn/#/guides/rules)
- Respond with SOAR: work containers, artifacts, vault files, notes, and playbook runs. [Work SOAR incidents](https://splunkctl.danny.vn/#/guides/soar-incidents)
- Review configuration drift: pull live state, diff it against version control, and push approved changes with a change report. [Manage configuration as code](https://splunkctl.danny.vn/#/guides/state)

## Safety

Every command that changes a remote Splunk or SOAR instance is guarded. Without `--yes` it prints a preview and exits without changing anything; some previews read the current state first to show a diff. The preview names the target host, and the active profile for Splunk Enterprise, so a change aimed at production is visible before it happens:

```text
$ splunkctl --profile uat rules delete 'My Rule'
[DRY RUN] Delete saved search 'My Rule' (profile: uat @ uat.splunk.internal:8089)
Pass --yes to apply.
```

Add `--yes` to apply. `splunkctl state push --report FILE` writes a change report with the before and after state for each object, which you can attach to a change ticket.

`--read-only` guarantees no application-data, configuration or authentication changes on any server. Search jobs and server audit/access logs are exceptions. Guarded previews still work; `--yes` mutations are refused. Local files may change. See [Read-only access](https://splunkctl.danny.vn/#/guides/read-only) and [Raw REST API](https://splunkctl.danny.vn/#/guides/api).

Local configuration writes are not guarded: `splunkctl config init`, `splunkctl config use`, `splunkctl auth login`, and `splunkctl mcp install` write to your own machine immediately.

## Agent access

The MCP server exposes the command tree to Claude Code, Claude Desktop, Cursor, or any other MCP client. Setup, transports, and the progressive tool-loading model are in the [MCP guide](https://splunkctl.danny.vn/#/guides/mcp).

```bash
splunkctl mcp install           # register the server in ./.mcp.json
splunkctl commands --json       # machine-readable command tree
```

`splunkctl mcp serve --read-only` (or `SPLUNKCTL_READ_ONLY=1`) hides mutation tools and enforces read-only policy in every CLI subprocess.

Guarded tools keep the same contract as the CLI: a call previews until the agent passes `yes=true` explicitly.

## Requirements and limitations

- Python 3.12 or newer.
- A Splunk account with REST API access on port 8089 (or your configured port). Each command needs the Splunk capability or SOAR permission its action requires; `splunkctl doctor` reports which checks pass for the active profile.
- Enterprise Security commands (`splunkctl es ...`) check for the `SplunkEnterpriseSecuritySuite` app and exit 1 with a `not_found` error when it is not installed.
- Browser SAML login needs the `browser` extra: `python -m pip install 'splunkctl[browser]'`.

## Project and support

splunkctl is an independent community project. It is not affiliated with or endorsed by Splunk Inc.

Splunk Inc. publishes an unrelated Go CLI with the same executable name, [`splunk/splunkctl`](https://github.com/splunk/splunkctl). This package also installs `splunkctl-py` and leaves a Splunk-format config file untouched, so both tools can be installed together; see [Relationship to Splunk's splunkctl](https://splunkctl.danny.vn/#/guides/splunk-cli).

- [Releases](https://github.com/dannyota/splunkctl/releases) and [changelog](https://github.com/dannyota/splunkctl/blob/master/CHANGELOG.md)
- [Issues](https://github.com/dannyota/splunkctl/issues) for bugs and feature requests; see [SECURITY.md](SECURITY.md) for vulnerabilities
- [CONTRIBUTING.md](CONTRIBUTING.md) for development setup
- License: [Apache-2.0](https://github.com/dannyota/splunkctl/blob/master/LICENSE)
