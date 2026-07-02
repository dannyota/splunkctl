# KV store (collections + data CRUD)

Splunk's KV store backs allowlists, threat-intel feeds, and Enterprise
Security's asset/identity tables — schema-less JSON document storage
scoped per app. This group manages collections (`storage/collections/
config`) and their documents (`storage/collections/data`) directly over
the REST API — no SDK entity class exists for KV store, so every command
here is a thin, typed wrapper around raw `GET`/`POST`/`DELETE` calls.

**Live-verified status**: the local dev instance's KV store is down
(`server kvstore` reports `status: failed`) — round-trip CRUD is
unit-tested against a mocked REST layer only; live verification covers
the negative path (a down KV store fails cleanly, never blank/traceback).
Full live round-trip is **pending a healthy KV store**.

## Commands

```bash
splunkctl kvstore collections                       # list collection names (app: search)
splunkctl kvstore collections --app Splunk_Security_Essentials
splunkctl kvstore create my_allowlist --yes          # create an empty collection
splunkctl kvstore delete my_allowlist --yes          # delete collection + ALL its data

splunkctl kvstore query my_allowlist                 # all documents
splunkctl kvstore query my_allowlist --query '{"host": "evil.example"}'
splunkctl kvstore query my_allowlist --limit 50 --skip 100 --sort '-_key'

splunkctl kvstore insert my_allowlist --data '{"host": "evil.example"}' --yes
splunkctl kvstore insert my_allowlist --file doc.json --yes
splunkctl kvstore update my_allowlist <key> --data '{"host": "new.example"}' --yes
splunkctl kvstore remove my_allowlist <key> --yes            # by _key
splunkctl kvstore remove my_allowlist --query '{"host": "evil.example"}' --yes  # by query

splunkctl kvstore export my_allowlist                # JSONL to stdout, one doc per line
splunkctl kvstore export my_allowlist --out backup.jsonl
splunkctl kvstore import my_allowlist --file backup.jsonl --yes   # upserts by _key
```

## Namespace

Every command addresses `servicesNS/nobody/<app>/storage/collections/
{config|data}/...` — collection ownership is always `nobody` (the KV
store convention), scoped by app with `--app` (default `search`).

## `query`: server-side only

`--query` is raw JSON, passed through unmodified to the API's own
`query` param; `--limit`/`--skip`/`--sort` map straight to the matching
API params. There is no client-side re-filtering or re-paging — what the
server returns is exactly what's rendered.

## `insert`/`update`: exactly one document source

Both take exactly one of `--data '<json>'` (inline) or `--file f.json`
(a file holding a single JSON object) — passing both, or neither, is a
usage error (exit 2), same as invalid JSON in either. Documents pass
through unmodified: no field is added, renamed, or stripped.

## `remove`: exactly one target

`remove <collection> <key>` deletes by `_key`; `remove <collection>
--query '<json>'` deletes every document matching the query. Exactly
one of `KEY`/`--query` is required — supplying both, or neither, is a
usage error (exit 2).

## `export`/`import`: JSONL round-trip

`export` writes one JSON document per line — `_key` is preserved on
every line, so `import` can upsert straight back onto the same keys.
`import --file f.jsonl` reads the same shape and POSTs via `batch_save`
in chunks of up to 500 documents; a document whose `_key` already exists
in the collection is upserted (overwritten) — that's `batch_save`'s own
semantics, not something the CLI special-cases. Blank lines in the JSONL
file are skipped; any non-blank line that isn't a single valid JSON
object is a usage error (exit 2) — the whole import is rejected before
any request is sent, not partially applied.

## Worked example: allowlist from bulk intel

```bash
# 1. Create the collection
splunkctl kvstore create ip_allowlist --yes

# 2. Bulk-load a threat-intel export (one JSON doc per line)
splunkctl kvstore import ip_allowlist --file ip_allowlist.jsonl --yes

# 3. Query it back
splunkctl kvstore query ip_allowlist --query '{"source": "internal"}'

# 4. Use it from SPL — requires a lookup DEFINITION binding the
#    collection to a lookup name first (transforms.conf), which
#    'kvstore' doesn't manage; H4 (lookup definitions & automatic
#    lookups) wires that up. Once defined:
#    | inputlookup ip_allowlist
```

A raw collection name is **not** automatically usable via `|
inputlookup` — Splunk's lookup command resolves a *lookup definition*
(a `transforms.conf` stanza with `external_type = kvstore` pointing at
the collection), not the collection name itself. Until H4 ships that
wiring, define it manually via Splunk Web
(**Settings → Lookups → Lookup definitions**) or `parsers`/conf editing.

## Errors

KV-store-down and other HTTP failures are never caught locally — they
flow straight through the CLI's F1 error-envelope classification
(`splunkctl.errors.classify`), so a down KV store always surfaces a
clean `kind: "http"`, the real HTTP status (`503` observed live), and
the server's message — never a blank result or a raw traceback:

```bash
$ splunkctl --json kvstore query my_allowlist
{"error": {"kind": "http", "http_status": 503, "message": "... KV Store initialization failed ..."}}
```

## Implementation notes

No SDK entity class — `storage/collections/config` (collection CRUD,
form-encoded like most Splunk config endpoints) and `storage/
collections/data` (document CRUD, JSON body + `Content-Type:
application/json`) are both reached through small typed JSON helpers in
`client.py` (`rest_get_json`/`rest_post_json`) layered on the SDK's own
authenticated `service.get`/`service.post`/`service.delete` — no new
HTTP stack.
