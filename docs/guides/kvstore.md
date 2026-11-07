<!-- summary: Create KV store collections and read, write, and delete their documents for allowlists and enrichment data. -->

# Manage KV store collections

When to use: an allowlist, a threat-intel feed, or an enrichment table lives in Splunk's KV store (schema-less JSON documents scoped per app, the same storage behind Enterprise Security's asset and identity tables) and you need to create the collection, load or query documents, back it up, or remove it.

## Prerequisites

- A profile that passes `splunkctl doctor` with the `KV Store` check at `ready`; `splunkctl server kvstore` shows the status on its own.
- Write access to the target app (`--app`, default `search`); collection ownership is always `nobody`, the KV store convention, so every command addresses `servicesNS/nobody/<app>/storage/collections/{config|data}/...`.
- No SDK fork is needed: every command is a thin, typed wrapper around raw `GET`, `POST`, and `DELETE` calls.

## Synopsis

```text
splunkctl kvstore collections [--app APP]
splunkctl kvstore create <NAME> [--app APP] [--yes]
splunkctl kvstore delete <NAME> [--app APP] [--yes]
splunkctl kvstore query <COLLECTION> [--query JSON] [--limit N] [--skip N] [--sort SPEC] [--app APP]
splunkctl kvstore insert <COLLECTION> (--data JSON | --file DOC.json) [--app APP] [--yes]
splunkctl kvstore update <COLLECTION> <KEY> (--data JSON | --file DOC.json) [--app APP] [--yes]
splunkctl kvstore remove <COLLECTION> [KEY] [--query JSON] [--app APP] [--yes]
splunkctl kvstore export <COLLECTION> [--app APP] [--out FILE.jsonl]
splunkctl kvstore import <COLLECTION> --file <FILE.jsonl> [--app APP] [--yes]
```

## Workflow

### List collections

```bash
splunkctl kvstore collections
splunkctl kvstore collections --app Splunk_Security_Essentials
```

Expected result: the collection names in the app (default `search`).

### Create a collection

> **Safety:** Target is the Splunk host and app in the active profile. Impact: an empty collection is created in that app. Preview with `splunkctl kvstore create ip_allowlist`, apply by adding `--yes`, and verify with `splunkctl kvstore collections`.

```bash
splunkctl kvstore create ip_allowlist
splunkctl kvstore create ip_allowlist --yes
```

### Add or replace single documents

> **Safety:** Target is the Splunk host and app in the active profile. Impact: `insert` adds one document; `update` replaces the whole document stored under `KEY`, not just the fields you pass. Preview with `splunkctl kvstore insert ip_allowlist --data '{"host": "evil.example"}'`, apply by adding `--yes`, and verify with `splunkctl kvstore query ip_allowlist --query '{"host": "evil.example"}'`.

```bash
splunkctl kvstore insert ip_allowlist --data '{"host": "evil.example"}'
splunkctl kvstore insert ip_allowlist --data '{"host": "evil.example"}' --yes
splunkctl kvstore insert ip_allowlist --file doc.json --yes
splunkctl kvstore update ip_allowlist 64f1c0a2b3d4e5f601234567 --data '{"host": "new.example"}' --yes
```

Expected result: the document is stored unmodified; no field is added, renamed, or stripped. Both commands take exactly one of `--data '<json>'` (inline) or `--file f.json` (a file holding a single JSON object); passing both or neither, or invalid JSON, is a usage error (exit 2).

### Query documents

```bash
splunkctl kvstore query ip_allowlist
splunkctl kvstore query ip_allowlist --query '{"host": "evil.example"}'
splunkctl kvstore query ip_allowlist --limit 50 --skip 100 --sort '-_key'
```

Expected result: the matching documents, each with its `_key`. `--query` is raw JSON passed unmodified to the API's `query` parameter; `--limit`, `--skip`, and `--sort` map straight to the matching API parameters. There is no client-side re-filtering or re-paging: what the server returns is exactly what is rendered.

### Remove documents

> **Safety:** Target is the Splunk host and app in the active profile. Impact: `remove KEY` deletes one document; `remove --query` deletes every document matching the query, with no undo. Preview with `splunkctl kvstore remove ip_allowlist --query '{"host": "evil.example"}'`, apply by adding `--yes`, and verify with `splunkctl kvstore query ip_allowlist --query '{"host": "evil.example"}'`.

```bash
splunkctl kvstore remove ip_allowlist 64f1c0a2b3d4e5f601234567 --yes
splunkctl kvstore remove ip_allowlist --query '{"host": "evil.example"}'
splunkctl kvstore remove ip_allowlist --query '{"host": "evil.example"}' --yes
```

Exactly one of `KEY` or `--query` is required; supplying both or neither is a usage error (exit 2).

### Back up and restore with JSONL

```bash
splunkctl kvstore export ip_allowlist
splunkctl kvstore export ip_allowlist --out backup.jsonl
```

Expected result: one JSON document per line on standard output or in the global `--out` file, with `_key` preserved on every line so `import` can upsert straight back onto the same keys.

> **Safety:** Target is the Splunk host and app in the active profile. Impact: every document in the file is upserted; a document whose `_key` already exists is overwritten. Preview with `splunkctl kvstore import ip_allowlist --file backup.jsonl`, apply by adding `--yes`, and verify with `splunkctl kvstore query ip_allowlist --limit 5`.

```bash
splunkctl kvstore import ip_allowlist --file ip_allowlist.jsonl
splunkctl kvstore import ip_allowlist --file ip_allowlist.jsonl --yes
```

Expected result: the documents are POSTed through `batch_save` in chunks of up to 500. Overwriting on a matching `_key` is `batch_save`'s own semantics, not something the CLI adds. Blank lines are skipped; any non-blank line that is not a single JSON object is a usage error (exit 2) and the whole import is rejected before any request is sent, never partially applied.

### Use the collection from SPL

A raw collection name is not usable through `| inputlookup` or `| lookup`: Splunk resolves a lookup definition (a `transforms.conf` stanza with `external_type = kvstore` pointing at the collection), not the collection itself.

> **Safety:** Target is the Splunk host in the active profile and `transforms.conf` in the current app namespace. Impact: a lookup definition named `ip_allowlist` is created or updated. Preview with `splunkctl lookups define ip_allowlist --collection ip_allowlist`, apply by adding `--yes`, and verify with `splunkctl search oneshot '| inputlookup ip_allowlist | head 5'`.

```bash
splunkctl lookups define ip_allowlist --collection ip_allowlist --yes
splunkctl search oneshot '| inputlookup ip_allowlist | head 5'
```

See [Manage lookups](lookups.md) for automatic lookups onto a sourcetype.

### Delete a collection

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the collection and all of its documents are removed. Preview with `splunkctl kvstore delete ip_allowlist`, apply by adding `--yes`, and verify with `splunkctl kvstore collections`.

```bash
splunkctl kvstore export ip_allowlist --out ip_allowlist.jsonl
splunkctl kvstore delete ip_allowlist
splunkctl kvstore delete ip_allowlist --yes
```

Export first so the data can be re-imported.

## Troubleshooting

- `http` with status 503 and `KV Store initialization failed`: the KV store is down; `splunkctl doctor` reports it as `KV Store: failed`. Ask the Splunk admin to restart Splunk or check `mongod.log`. REST failures flow through the error envelope (`kind`, `http_status`, `message`), never a blank result or traceback.
- Exit 2 `exactly one of --data or --file is required` or `exactly one of KEY or --query is required`: pass one source or one target, not both.
- Exit 2 on `import`: a line in the JSONL file is not a single JSON object; fix the file, nothing was sent.
- `not_found` or an empty `query`: the collection is in another app; pass `--app`.
- `| inputlookup NAME` fails in SPL: define the lookup with `splunkctl lookups define NAME --collection NAME --yes`.
- `permission` on `create`, `insert`, or `delete`: the account cannot write to that app.

## See also

- [Manage lookups](lookups.md)
- [Check server health and topology](server.md)
- [Diagnose a connection](doctor.md)
- [Command reference: kvstore](../commands/kvstore.md)
