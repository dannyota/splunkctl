<!-- summary: Upload, download, define, and wire lookup tables so detections can enrich events from files you control. -->

# Manage lookups

When to use: a detection needs enrichment from a table you control, such as a threat-intel indicator feed, an asset or identity list, or a GeoIP database, and you need to push the file to a remote instance, keep it current, bind it to a lookup name, and have events enriched automatically at search time.

## Prerequisites

- The optional SDK fork, because table-file commands use its `LookupTableFile` entity classes:

  ```bash
  python -m pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
  ```

- A profile that passes `splunkctl doctor` including `Web UI reachable`: `upload` and `update` go through the Splunk Web form handler because the REST API requires a server-side path.
- Write access to the target app (`--app`, default `search` for `upload`, `update`, `delete`, and `download`).

## Synopsis

```text
splunkctl lookups list [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl lookups get <NAME> [--app APP]
splunkctl lookups upload <NAME> --file <FILE.csv> [--app APP] [--yes]
splunkctl lookups update <NAME> --file <FILE.csv> [--app APP] [--yes]
splunkctl lookups download <NAME> [--app APP] [--out FILE]
splunkctl lookups delete <NAME> [--app APP] [--yes]
splunkctl lookups definitions [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl lookups define <DEFNAME> (--file <FILE.csv> | --collection <COLLECTION>) [--app APP] [--max-matches N] [--min-matches N] [--case-sensitive|--no-case-sensitive] [--default-match VALUE] [--yes]
splunkctl lookups auto <DEFNAME> --sourcetype <SOURCETYPE> --input <FIELD[:LOOKUP_FIELD]>... --output <FIELD[:RENAMED]>... [--overwrite|--no-overwrite] [--app APP] [--name SUFFIX] [--yes]
```

Uploading a CSV creates a table file on the server, but Splunk does not treat it as a lookup until two more things exist: a lookup definition in `transforms.conf` that binds a name to the file (or, for a KV store collection, to `external_type=kvstore` and `collection=<name>`), which is what `| lookup <defname>` and `| inputlookup <defname>` reference; and optionally an automatic lookup in `props.conf` (`LOOKUP-*`) that wires the definition onto a sourcetype so every matching event is enriched at search time with no `| lookup` in the SPL. `lookups define` writes the first and `lookups auto` the second; both delegate the conf write to the same stanza core that `conf`, `parsers`, and `macros` use.

## Workflow

### List, inspect, and download

```bash
splunkctl lookups list
splunkctl lookups list --app SA-ThreatIntelligence
splunkctl lookups get threat_indicators.csv
splunkctl lookups download threat_indicators.csv --app SA-ThreatIntelligence --out current_threats.csv
splunkctl lookups definitions
splunkctl lookups definitions --app SA-ThreatIntelligence
```

Expected result: `list` and `get` cover table files across all apps by default; `download` writes the CSV to standard output or `--out`, so you can diff before updating. `definitions` lists only `transforms.conf` stanzas shaped like a lookup definition (a `filename` or `external_type` and `collection` key); `transforms.conf` also holds field-transform stanzas, which `splunkctl conf list transforms` shows unfiltered.

### Upload or refresh a table file

> **Safety:** Target is the Splunk host and app in the active profile. Impact: `upload` creates the table file; `update` overwrites the existing file's rows, and every search using it sees the new data at once. Preview with `splunkctl lookups upload threat_indicators.csv --file threat_indicators.csv --app SA-ThreatIntelligence`, apply by adding `--yes`, and verify with `splunkctl lookups download threat_indicators.csv --app SA-ThreatIntelligence`.

```bash
splunkctl lookups upload threat_indicators.csv --file threat_indicators.csv --app SA-ThreatIntelligence
splunkctl lookups upload threat_indicators.csv --file threat_indicators.csv --app SA-ThreatIntelligence --yes
splunkctl lookups update asset_lookup.csv --file asset_lookup.csv --app SA-IdentityManagement --yes
```

Expected result: the file appears in `splunkctl lookups list --app APP`. The upload goes from your machine through the Splunk Web form handler, the same mechanism the browser uses, so no SSH, SCP, or server filesystem access is needed. Download the current file first when you want a diff.

### Automate a feed update

```bash
curl -sO https://feeds.example.com/iocs_latest.csv
splunkctl lookups update threat_indicators.csv --file iocs_latest.csv --app SA-ThreatIntelligence --yes
```

Expected result: a lightweight feed pipeline; schedule it with cron or CI after a dry run has been reviewed once. The same safety note as the previous step applies.

### Define the lookup

> **Safety:** Target is the Splunk host in the active profile and `transforms.conf` in `--app` (default: current namespace). Impact: the definition `DEFNAME` is created or updated; searches that reference it change behaviour. Preview with `splunkctl lookups define threat_intel --file threat_indicators.csv`, apply by adding `--yes`, and verify with `splunkctl lookups definitions --filter threat_intel`.

```bash
splunkctl lookups define threat_intel --file threat_indicators.csv
splunkctl lookups define threat_intel --file threat_indicators.csv --yes
splunkctl lookups define asset_intel --collection assets --yes
splunkctl lookups define threat_intel --file threat_indicators.csv --max-matches 1 --case-sensitive --default-match unknown --yes
```

Expected result: `| inputlookup threat_intel` works. `define` requires exactly one of `--file` or `--collection` (otherwise exit 2) and warns, without blocking, when `--file` names a table that does not exist yet in that app, so a scripted define-then-upload flow still works. `--collection` is how a KV store collection becomes queryable (see [Manage KV store collections](kvstore.md)). `--max-matches`, `--min-matches`, `--case-sensitive`, and `--default-match` tune how strict the match is and what to emit on a miss.

### Wire an automatic lookup onto a sourcetype

> **Safety:** Target is the Splunk host in the active profile and `props.conf` in `--app`. Impact: every event of `--sourcetype` is enriched at search time from now on, which changes field values in existing detections. Preview with `splunkctl lookups auto threat_intel --sourcetype firewall_logs --input dest_ip:ip --output threat_level`, apply by adding `--yes`, and verify with `splunkctl search oneshot 'sourcetype=firewall_logs | table dest_ip threat_level' --earliest -15m`.

```bash
splunkctl lookups auto threat_intel --sourcetype firewall_logs --input dest_ip:ip --output threat_level --output threat_category
splunkctl lookups auto threat_intel --sourcetype firewall_logs --input dest_ip:ip --output threat_level --output threat_category --yes
splunkctl search oneshot 'sourcetype=firewall_logs | table dest_ip threat_level threat_category'
```

Expected result: events of that sourcetype carry `threat_level` and `threat_category` with no `| lookup` in the search. `--input` and `--output` are repeatable and at least one of each is required (otherwise exit 2). `--input` is `event_field[:lookup_table_field]`: the field you already have, then the lookup column only if it differs. `--output` is `lookup_table_field[:event_field]`: the column you pull in, then what to call it on the event. `--overwrite` (default) emits `OUTPUT`, always overwriting; `--no-overwrite` emits `OUTPUTNEW`, filling only fields the event lacks. `--name` changes the `LOOKUP-` key suffix (default `DEFNAME`). The definition must already exist.

### Delete a table file

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the table file is removed and definitions that reference it start failing. Preview with `splunkctl lookups delete old_table.csv --app search`, apply by adding `--yes`, and verify with `splunkctl lookups list --filter old_table`.

```bash
splunkctl lookups download old_table.csv --out backup/old_table.csv
splunkctl lookups delete old_table.csv --app search
splunkctl lookups delete old_table.csv --app search --yes
```

## Troubleshooting

- `ImportError` mentioning `LookupTableFile`: install the SDK fork listed under Prerequisites.
- `Lookup upload failed` or a `web` error: Splunk Web is not reachable from this machine; check `Web UI reachable` in `splunkctl doctor`.
- `not_found` from `get`, `download`, or `delete`: the file is in another app; `list` spans all apps but `download` and `delete` default to `search`, so pass `--app`.
- `upload` fails because the file exists: use `update` to overwrite.
- A warning from `define` that the table does not exist: upload it with `lookups upload`, or check the filename; the definition was still written.
- Exit 2 from `define` or `auto`: `define` needs exactly one of `--file` or `--collection`; `auto` needs at least one `--input` and one `--output`.
- `| lookup threat_intel` reports an unknown lookup: the definition is in another app or not shared; check `splunkctl lookups definitions --app APP`.
- `permission` from `define` or `auto`: the account cannot write `transforms.conf` or `props.conf` in that app.

## See also

- [Manage KV store collections](kvstore.md)
- [Manage source types and extractions](parsers.md)
- [Manage detection rules](rules.md)
- [Install](install.md)
- [Command reference: lookups](../commands/lookups.md)
