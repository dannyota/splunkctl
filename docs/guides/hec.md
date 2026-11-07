<!-- summary: Create, enable, disable, and remove HTTP Event Collector tokens, adjust HEC settings, and send test events. -->

# Manage HEC tokens

When to use: a SOAR playbook, custom script, CI pipeline, or cloud webhook needs to push events into Splunk without a forwarder, and you must provision, rotate, or revoke the HTTP Event Collector (HEC) token it uses, or confirm that HEC is enabled and accepting events.

## Prerequisites

- The optional SDK fork, because token commands use its `HECToken` entity classes:

  ```bash
  python -m pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
  ```

- A profile that passes `splunkctl doctor` and an account allowed to manage HTTP inputs (the `admin` role covers it).
- For `send`: network access from this machine to the HEC port (8088 by default), which is separate from the 8089 management port.

## Synopsis

```text
splunkctl hec list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl hec get <NAME>
splunkctl hec create --name <NAME> [--index INDEX] [--indexes A,B] [--sourcetype SOURCETYPE] [--set KEY=VALUE]... [--yes]
splunkctl hec enable <NAME> [--yes]
splunkctl hec disable <NAME> [--yes]
splunkctl hec delete <NAME> [--yes]
splunkctl hec settings [--enable|--disable] [--yes]
splunkctl hec send <NAME> <EVENT> [--index INDEX] [--sourcetype SOURCETYPE] [--yes]
```

Splunk stores HEC token names with an `http://` prefix internally, so creating `my_token` produces a token named `http://my_token`. The CLI handles this for you; always use the short name.

## Workflow

### Audit existing tokens

```bash
splunkctl hec list
splunkctl hec get soar_enrichment
splunkctl hec list --json | jq '.[] | {name, index, disabled}'
```

Expected result: one row per token with `name`, `token`, `index`, `disabled`, and `sourcetype`; `get` adds `indexes` (the allowlist) and `useACK`. Both print the token value, so treat their output as a secret.

### Check or toggle HEC globally

```bash
splunkctl hec settings
```

Expected result: `disabled`, `port`, `enableSSL`, and `dedicatedIoThreads` for the HEC input as a whole. Tokens only work when HEC is enabled globally.

> **Safety:** Target is the Splunk host in the active profile. Impact: every HEC token on the instance starts or stops accepting events. Preview with `splunkctl hec settings --enable`, apply by adding `--yes`, and verify with `splunkctl hec settings` (check `disabled`).

```bash
splunkctl hec settings --enable --yes
splunkctl hec settings --disable --yes
```

### Provision a token for an integration

> **Safety:** Target is the Splunk host in the active profile. Impact: a new ingestion credential is created and can write to the named indexes immediately. Preview with `splunkctl hec create --name soar_enrichment --index notable_enrichments --sourcetype json`, apply by adding `--yes`, and verify with `splunkctl hec get soar_enrichment`.

```bash
splunkctl hec create --name soar_enrichment --index notable_enrichments --sourcetype json
splunkctl hec create --name soar_enrichment --index notable_enrichments --sourcetype json --yes
splunkctl hec create --name threat_feed_ingest --index threat_intel --indexes threat_intel --sourcetype stix_ioc --yes
splunkctl hec create --name deploy_events --index main --set useACK=1 --yes
```

Expected result: `HEC token 'NAME' created.`. `--index` is the default index, `--indexes` the comma-separated allowlist a sender may target, and `--set KEY=VALUE` passes any other token property (for example `useACK=1`).

### Rotate a compromised token

> **Safety:** Target is the Splunk host in the active profile. Impact: senders using the old token are rejected as soon as it is disabled. Preview with `splunkctl hec disable old_webhook_token`, apply by adding `--yes`, and verify with `splunkctl hec get old_webhook_token --json` (check `disabled`).

```bash
splunkctl hec disable old_webhook_token --yes
splunkctl hec create --name new_webhook_token --index webhook_events --sourcetype json --yes
splunkctl hec get new_webhook_token --json
```

Expected result: the old token shows `disabled: 1`; copy the new token value from `get` into the sender, then delete the old token once nothing uses it. `enable` reverses a disable.

### Send a test event

> **Safety:** Target is the HEC endpoint of the Splunk host in the active profile, on the port from `hec settings`. Impact: one event is indexed into the token's default index or `--index`. Preview with `splunkctl hec send soar_enrichment '{"test": true}'`, apply by adding `--yes`, and verify with `splunkctl search oneshot 'index=notable_enrichments test=true' --earliest -15m`.

```bash
splunkctl hec send soar_enrichment '{"test": true}'
splunkctl hec send soar_enrichment '{"test": true}' --index notable_enrichments --sourcetype json --yes
```

Expected result: `Event sent.`. The CLI reads the token value and the global HEC port and TLS setting, then POSTs to `/services/collector/event` with `Authorization: Splunk <token>`, honouring the profile's `verify` setting.

### Revoke a decommissioned integration

> **Safety:** Target is the Splunk host in the active profile. Impact: the token is deleted and cannot be recovered; any sender still using it is rejected. Preview with `splunkctl hec delete legacy_siem_bridge`, apply by adding `--yes`, and verify with `splunkctl hec list --filter legacy_siem_bridge`.

```bash
splunkctl hec delete legacy_siem_bridge
splunkctl hec delete legacy_siem_bridge --yes
```

## Troubleshooting

- `ImportError` mentioning `HECToken`: install the SDK fork listed under Prerequisites.
- `not_found` from `get`, `enable`, `disable`, `delete`, or `send`: use the short name without the `http://` prefix and check `splunkctl hec list`.
- `Create failed` naming an existing token: the name is taken; pick another or delete the old one.
- `HEC send failed` with a server message such as `Invalid token` or `Incorrect index`: the token is disabled, HEC is globally disabled, or `--index` is not in the token's allowed indexes.
- `connection` or `timeout` from `send` only: the HEC port (8088) is blocked while the management port is open; open it or send from a host that can reach it.
- `permission` from `create` or `delete`: the account cannot manage HTTP inputs; use an `admin` account.

## See also

- [Manage data inputs](inputs.md)
- [Manage indexes](indexes.md)
- [Run searches](search.md)
- [Install](install.md)
- [Command reference: hec](../commands/hec.md)
