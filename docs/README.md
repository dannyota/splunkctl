<!-- summary: splunkctl is a CLI and MCP server for operating Splunk Enterprise, Enterprise Security, and Splunk SOAR with guarded, previewable changes. -->

# splunkctl

Operate Splunk Enterprise, Enterprise Security, and Splunk SOAR from a terminal, or give an AI agent the same commands through MCP.

Requires Python 3.13+ and credentials for your Splunk instance. splunkctl is an independent community project, not affiliated with or endorsed by Splunk Inc.

## Quickstart

```bash
python -m pip install splunkctl
splunkctl config init
splunkctl doctor
```

`config init` writes `~/.splunkctl/config.yaml`. `doctor` checks the connection, authentication, server health, and your permissions. See [Install](guides/install.md) for the optional SDK fork and shell completion, and [Configure](guides/configure.md) for profiles and environment variables.

## Safety

Every command that changes a remote Splunk or SOAR instance previews by default and exits without making a request. The preview names the active profile and host. Add `--yes` to apply. `state push --report FILE` writes a change report you can attach to a change ticket. Local configuration writes (`config init`, `config use`, `auth login`, `mcp install`) are not guarded.

## Investigate

Run SPL, read fired alerts, and triage Enterprise Security notables without leaving the terminal.

- [Run searches](guides/search.md)
- [Review fired alerts](guides/alerts.md)
- [Triage ES notables](guides/es.md)
- [Manage dashboards](guides/dashboards.md)

## Detect

Keep detections, knowledge objects, and parsing configuration in version control and deploy them across instances.

- [Manage detection rules](guides/rules.md)
- [Manage ES correlations and threat intel](guides/es-detections.md)
- [Manage macros, eventtypes, and tags](guides/knowledge.md)
- [Check data model acceleration](guides/datamodels.md)
- [Manage lookups](guides/lookups.md)
- [Manage source types and field extractions](guides/parsers.md)

## Respond with SOAR

Work containers, artifacts, playbooks, actions, and cases on Splunk SOAR with the same profiles and guard as the SIEM commands.

- [Set up and check SOAR](guides/soar.md)
- [Work SOAR incidents](guides/soar-incidents.md)
- [Run playbooks](guides/soar-playbooks.md)
- [Run actions](guides/soar-actions.md)
- [Manage cases and workbooks](guides/soar-cases.md)
- [Handle approvals](guides/soar-approvals.md)
- [Ingest SIEM results into SOAR](guides/soar-ingest.md)
- [Install SOAR apps](guides/soar-apps.md) and [configure assets](guides/soar-assets.md)
- [Maintain custom lists](guides/soar-lists.md), [custom functions](guides/soar-functions.md), and [indicators](guides/soar-indicators.md)

## Change safely

Pull live configuration, diff it against your repository, and push approved changes with a change report.

- [Manage configuration as code](guides/state.md)
- [Edit any conf file](guides/conf.md)

## Give it to an agent

Register the MCP server once and let an AI agent run the same commands with the same `yes=true` guard.

- [Set up the MCP server](guides/mcp.md)

## Operate and audit

Install, configure, authenticate, and check the health of the instances you manage, then produce audit evidence.

- [Install](guides/install.md) and [Configure](guides/configure.md)
- [Log in through browser SAML](guides/auth.md)
- [Diagnose a connection](guides/doctor.md)
- [Manage indexes](guides/indexes.md), [inputs](guides/inputs.md), [HEC tokens](guides/hec.md), [apps](guides/apps.md), and [users and roles](guides/users.md)
- [Check server health and topology](guides/server.md)
- [Manage KV store collections](guides/kvstore.md)
- [Audit changes and attest RBAC](guides/audit.md)
- [Administer SOAR users and roles](guides/soar-admin.md)

## Reference

- [Exit codes](guides/exit-codes.md)
- [Command reference](commands/README.md), generated from the command tree
- [Relationship to Splunk's splunkctl](guides/splunk-cli.md)
- [Contributor lab: Keycloak SAML](guides/keycloak-lab.md)
- [Architecture](design/architecture.md) and [catalog and status](design/catalog.md)
