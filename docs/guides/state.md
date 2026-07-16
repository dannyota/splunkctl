# State (config-as-code, change evidence)

`state` is the bank change-management workflow: pull a versioned
snapshot of an instance's detection content, edit it like code, diff
it against the live instance, then push -- with a savable before→after
JSON artifact a change ticket can reference as evidence. It unifies
`rules`/`parsers` import-export and read-only introspection of macros,
lookups, and dashboards into one pull → edit → diff → push loop.

## Why this matters

A SOC running detections-as-code needs an audit trail: what changed,
who approved it, what it looked like before. `state push --report`
writes that record automatically -- the same JSON file works as the
dry-run artifact attached to a change ticket for approval, and the
`--yes` artifact recorded as what actually happened.

## Commands

```bash
splunkctl state pull --dir ./snapshot                    # everything, all apps
splunkctl state pull --dir ./snapshot --app my_app        # one app only
splunkctl state pull --dir ./snapshot --types rules,macros # a subset of types

splunkctl state diff --dir ./snapshot                     # structured drift report
splunkctl state diff --dir ./snapshot --json | jq .

splunkctl state push --dir ./snapshot                     # dry-run preview
splunkctl state push --dir ./snapshot --yes \
    --report change-12345.json                            # apply + evidence
```

## The pulled tree

```
snapshot/
  manifest.json       # tool version, host, per-type object counts
  rules.yml           # saved searches (rules_io's YAML shape)
  parsers.yml         # props/transforms stanzas with explicit keys
  macros.yml          # macros.conf stanzas with explicit keys
  lookups/<name>      # one CSV per lookup table file
  dashboards/<name>.xml  # one XML export per dashboard
```

`manifest.json` deliberately has **no timestamp** -- only `version`,
`host`, and `types` (object counts). A wall-clock stamp would make the
manifest, and anything diffing two pulls, non-deterministic; the
snapshot's own version-control commit (or filesystem mtime) already
answers "when". `--types` controls which of the five files/directories
get written; `pull` owns and overwrites only the types it's asked to
touch, and is otherwise read-only against the instance.

**Hard constraint: keep `--app` consistent across pull/diff/push.**
`lookups/<name>` and `dashboards/<name>.xml` are a *flat* layout --
the file name carries no app, unlike `rules.yml`/`parsers.yml`/
`macros.yml`, where every doc records its own `app`. If you `pull`
unscoped (or with one `--app`) and then `diff`/`push` with a
*different* single `--app`, a lookup or dashboard belonging to another
app can be misattributed: it shows as `added` even though it already
exists live, and `push` would try to *create* it under the wrong app.
Always use the same `--app` scope across pull, diff, and push (or
none, for all three) when lookups or dashboards are in play.

## Object type capability matrix

| Type | Pull (read) | Diff | Push (apply) |
|---|---|---|---|
| `rules` | `rules_io` export | field-level | `rules_io` import |
| `parsers` | `parsers_io` export (explicit keys) | key-level | `parsers_io` import |
| `macros` | explicit-key conf read | key-level | `conf_ops.set_keys` |
| `lookups` | CSV download | content hash | CSV upload/update |
| `dashboards` | XML export | content hash | **not supported** -- no import path |
| `soar-playbooks` | tgz export | content hash | tgz import |
| `soar-lists` | JSON content export | content hash | create/full-replace |
| `soar-assets` | JSON config export | field-level | fetch-merge-post |

Every read/diff/apply path reuses the existing per-type machinery
(`rules_io`, `parsers_io`, `conf_ops`, `client.upload_lookup`) -- `state`
is pure orchestration, never a second implementation of serialization
or apply logic.

## Drift classification

`state diff` reports **every** object in a type, not just deltas:

- `added` -- on disk, not on the instance (`push` would create it)
- `removed` -- on the instance, not on disk (`push` does **not**
  delete it -- see below)
- `modified` -- both exist and differ; rules/parsers/macros carry a
  structured `fields: [{field, old, new}]` diff, lookups/dashboards
  (blob-shaped) carry a `sha256` before/after instead
- `unchanged` -- both exist and match

```bash
splunkctl state diff --dir ./snapshot --types rules --json
```

```json
[
  {
    "type": "rules",
    "name": "Failed Logins",
    "change": "modified",
    "fields": [{"field": "search", "old": "index=old", "new": "index=new"}]
  }
]
```

`diff` always exits 0 -- it is a report, not a gate.

## push never deletes

`push` only ever creates or updates an object that is represented on
disk. An instance object with no on-disk counterpart is classified
`removed` by the underlying diff, surfaced as an informational note
(`note: rules: 2 object(s) on the instance only -- not deleted (push
never deletes)`), and never touched -- there is no delete path in
`state push`, by design. To actually remove something, use the
type-specific `delete` command (`rules delete`, `lookups delete`, ...)
directly, with its own guard.

## Dashboards: pull + diff only

Dashboards have no import path in the SDK fork or the CLI yet. `state
pull`/`state diff` work normally for dashboards; `state push` reports
drifted dashboards as apply-unsupported and skips them without
erroring:

```
note: dashboards: 1 drifted object(s) — apply not supported (export-only, no import path)
```

If `dashboards` is the only `--types` value and nothing else drifted,
`push` still runs cleanly (exit 0) and, with `--report`, still writes
an artifact (`changes: []`).

**Diff caveat.** `dashboards` drift is a raw-XML content hash, so
`state diff` can show a handful of dashboards as `modified` with zero
real edits -- Splunk's export is not always byte-identical across
requests, and (more commonly) two apps sharing a dashboard name
collide in the flat `dashboards/<name>.xml` layout (see the `--app`
constraint above). This is cosmetic -- dashboards are never pushed --
but don't treat a non-empty dashboard diff as evidence of a real
change without checking it.

## The change-ticket workflow

```bash
# 1. Snapshot the instance
splunkctl state pull --dir ./snapshot --types rules

# 2. Edit rules.yml like code -- change a search, a schedule, a threshold

# 3. See exactly what changed
splunkctl state diff --dir ./snapshot --types rules

# 4. Preview the push and save the plan for ticket approval
splunkctl state push --dir ./snapshot --types rules \
    --report change-12345-plan.json

# 5. Once approved, apply it and save the record
splunkctl state push --dir ./snapshot --types rules --yes \
    --report change-12345-applied.json
```

`--report` writes `{host, types, changes, applied}` on **both** runs:
`applied: false` for the dry-run plan (what would happen -- attach
this to the ticket for approval), `applied: true` for the `--yes` run
(what actually happened -- the change record). `changes` is the same
shape as `state diff`'s modified/added rows, plus `before`/`after`
maps built from the same field diff:

```json
{
  "host": "splunk.example.com:8089",
  "types": ["rules"],
  "changes": [
    {
      "type": "rules",
      "name": "Failed Logins",
      "change": "modified",
      "before": {"search": "index=old"},
      "after": {"search": "index=new"}
    }
  ],
  "applied": true
}
```

`changes` never includes `removed` or `unchanged` entries -- only what
was (or would be) actually created/updated. `removed` drift and
dashboard apply-unsupported drift are surfaced as console notes, not
as report entries, since neither is ever applied.

## SOAR types

Three SOAR types extend the state workflow to Splunk SOAR: playbooks,
custom lists, and assets. They require a configured SOAR profile
(`splunkctl config init --soar` or `SOAR_HOST` env var). If SOAR types
are requested without a configured SOAR host, the CLI exits with a
clear error. Mixed SIEM + SOAR types in a single command work -- the
orchestrator creates each client lazily and routes each type to the
correct backend.

```bash
# SOAR-only pulls
splunkctl state pull --dir ./snap --types soar-playbooks
splunkctl state pull --dir ./snap --types soar-lists,soar-assets

# Mixed SIEM + SOAR
splunkctl state pull --dir ./snap --types rules,soar-playbooks

# Diff and push work identically
splunkctl state diff --dir ./snap --types soar-lists
splunkctl state push --dir ./snap --types soar-assets --yes
```

### The pulled tree (SOAR types)

```
snapshot/
  soar-playbooks/
    index.json                  # id/name/filename map for diff/push
    local__detect_malware.tgz   # one tgz per playbook (slash -> __)
  soar-lists/
    blocklist.json              # JSON array-of-arrays content
  soar-assets/
    firewall.json               # asset config (passwords masked)
```

### soar-playbooks

Playbooks are opaque tgz archives. Pull exports each via the SOAR REST
API; diff compares content hashes (SHA-256 of the tgz bytes); push
imports via `POST /rest/import_playbook` with the tgz base64-encoded.
Filenames replace `/` with `__` (SOAR playbook names are scoped as
`<dir>/<module>`).

### soar-lists

Custom lists (decided lists) are JSON arrays-of-arrays. Pull downloads
the content; diff compares content hashes; push creates new lists or
full-replaces existing ones via the SOAR REST API.

### soar-assets

Assets are JSON config blobs. Pull exports each asset's configuration
with password-type fields masked as `****` so secrets never land on
disk. Diff does field-level comparison, ignoring masked fields to avoid
false-positive drift. Push uses fetch-merge-post semantics (same as
`soar assets update`): masked values are skipped during merge so
existing secrets are preserved on the server.

**Note on `--app`:** the `--app` flag is accepted by all commands for
signature consistency but is ignored for SOAR types -- SOAR objects are
not scoped by Splunk app.

## Implementation notes

`splunkctl/commands/state.py` is pure CLI orchestration (guard
integration, preview text, `--report`/`--types`/`--app` handling).
Every per-type read/diff/apply call is delegated to
`splunkctl/commands/state_io.py` and its topic siblings
(`state_io_confs.py` for parsers/macros, `state_io_blobs.py` for
lookups/dashboards, `state_io_soar.py` for SOAR playbooks/lists,
`state_io_soar_assets.py` for SOAR assets, `state_types.py` for the
shared TypedDicts and drift-classification helpers) -- split across
files to stay under the 500-line budget, but `state_io` re-exports
everything so `state_io.<name>` is the one import surface callers and
tests use.
