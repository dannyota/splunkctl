<!-- summary: Pull live Splunk and SOAR configuration, diff it against version control, and push approved changes with a change report. -->

# Manage configuration as code

When to use: your change process needs an audit trail for detection content: pull a versioned snapshot of an instance, edit it like code, diff it against the live instance, then push with a before-and-after JSON report a change ticket can reference as evidence. `state` unifies the `rules` and `parsers` export and import loops with macros, lookups, dashboards, and the SOAR playbook, list, and asset types in one pull, edit, diff, push loop.

## Prerequisites

- A Splunk profile that passes `splunkctl doctor`; the account needs write access to every app you intend to push to.
- For `soar-playbooks`, `soar-lists`, and `soar-assets`: SOAR credentials in the profile (`splunkctl config init --soar` or `SOAR_HOST`). Mixed SIEM and SOAR types in one command work; each type is routed to its own client.
- The same `--app` scope (or none) on `pull`, `diff`, and `push` when lookups or dashboards are involved (see "Pull a snapshot").

## Synopsis

```text
splunkctl state pull --dir <DIR> [--app APP] [--types rules,parsers,macros,lookups,dashboards,soar-playbooks,soar-lists,soar-assets]
splunkctl state diff --dir <DIR> [--app APP] [--types LIST]
splunkctl state push --dir <DIR> [--app APP] [--types LIST] [--report FILE.json] [--yes]
```

`--types` defaults to all eight types. `--app` is accepted by all three commands but ignored for SOAR types, which are not scoped by Splunk app.

## Workflow

### Pull a snapshot

```bash
splunkctl state pull --dir ./snapshot
splunkctl state pull --dir ./snapshot --app my_app
splunkctl state pull --dir ./snapshot --types rules,macros
splunkctl state pull --dir ./snap --types soar-playbooks
splunkctl state pull --dir ./snap --types soar-lists,soar-assets
splunkctl state pull --dir ./snap --types rules,soar-playbooks
```

Expected result: a tree you can commit:

```text
snapshot/
  manifest.json       # tool version, host, per-type object counts
  rules.yml           # saved searches (rules_io's YAML shape)
  parsers.yml         # props/transforms stanzas with explicit keys
  macros.yml          # macros.conf stanzas with explicit keys
  lookups/<name>      # one CSV per lookup table file
  dashboards/<name>.xml  # one XML export per dashboard
  soar-playbooks/
    index.json                  # id/name/filename map for diff/push
    local__detect_malware.tgz   # one tgz per playbook (slash -> __)
  soar-lists/
    blocklist.json              # JSON array-of-arrays content
  soar-assets/
    firewall.json               # asset config (passwords masked)
```

`manifest.json` deliberately has no timestamp, only `version`, `host`, and `types` (object counts); a wall-clock stamp would make two pulls non-deterministic to diff, and the commit or file mtime already answers "when". `pull` owns and overwrites only the types it is asked for and is otherwise read-only against the instance.

Keep `--app` consistent across pull, diff, and push. `lookups/<name>` and `dashboards/<name>.xml` are a flat layout where the file name carries no app, unlike `rules.yml`, `parsers.yml`, and `macros.yml`, where every document records its own `app`. If you pull unscoped (or with one `--app`) and then diff or push with a different single `--app`, a lookup or dashboard from another app can be misattributed: it shows as `added` even though it exists live, and `push` would try to create it under the wrong app.

What each type supports:

| Type | Pull (read) | Diff | Push (apply) |
|---|---|---|---|
| `rules` | `rules_io` export | field-level | `rules_io` import |
| `parsers` | `parsers_io` export (explicit keys) | key-level | `parsers_io` import |
| `macros` | explicit-key conf read | key-level | `conf_ops.set_keys` |
| `lookups` | CSV download | content hash | CSV upload or update |
| `dashboards` | XML export | content hash | not supported |
| `soar-playbooks` | tgz export | content hash (SHA-256 of the tgz bytes) | tgz import via `POST /rest/import_playbook` |
| `soar-lists` | JSON content export | content hash | create or full replace |
| `soar-assets` | JSON config export (password fields masked as `****`) | field-level, masked fields ignored | fetch-merge-post, masked values skipped so server secrets survive |

Every path reuses the per-type machinery (`rules_io`, `parsers_io`, `conf_ops`, `client.upload_lookup`, the SOAR commands); `state` is orchestration only, never a second implementation.

### Edit the snapshot like code

```bash
git init ./snapshot && git -C ./snapshot add . && git -C ./snapshot commit -m "Baseline from prod"
$EDITOR ./snapshot/rules.yml
git -C ./snapshot commit -am "Raise brute force threshold to 30"
```

Expected result: every change is a reviewable commit. The YAML shapes are the ones `rules export` and `parsers export` write (see [Manage detection rules](rules.md) and [Manage source types and extractions](parsers.md)).

### Diff against the live instance

```bash
splunkctl state diff --dir ./snapshot
splunkctl state diff --dir ./snapshot --types rules --json
splunkctl state diff --dir ./snap --types soar-lists
```

Expected result: every object in each type, not just deltas, classified as:

- `added`: on disk, not on the instance (`push` would create it)
- `removed`: on the instance, not on disk (`push` does not delete it)
- `modified`: both exist and differ; rules, parsers, macros, and SOAR assets carry a structured `fields: [{field, old, new}]` diff, while lookups, dashboards, playbooks, and lists (blob-shaped) carry a `sha256` before and after instead
- `unchanged`: both exist and match

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

`diff` always exits 0; it is a report, not a gate.

Dashboard drift is a raw-XML content hash, so `diff` can show a few dashboards as `modified` with zero real edits: Splunk's export is not always byte-identical across requests, and two apps sharing a dashboard name collide in the flat `dashboards/<name>.xml` layout. This is cosmetic, because dashboards are never pushed, but do not treat a non-empty dashboard diff as evidence of a real change without checking.

### Preview the push and save the plan

```bash
splunkctl state push --dir ./snapshot
splunkctl state push --dir ./snapshot --types rules --report change-12345-plan.json
```

Expected result: exactly what `--yes` would create or update, nothing applied. `--report` writes `{host, types, changes, applied}` with `applied: false`; attach it to the change ticket for approval.

### Apply the approved push

> **Safety:** Target is the Splunk host (and, for SOAR types, the SOAR host) in the active profile. Impact: every `added` object is created and every `modified` object is updated on the live instance; `removed` objects are never deleted. Preview with `splunkctl state push --dir ./snapshot --types rules --report change-12345-plan.json`, apply with `splunkctl state push --dir ./snapshot --types rules --yes --report change-12345-applied.json`, and verify with `splunkctl state diff --dir ./snapshot --types rules` (expect only `unchanged`).

```bash
splunkctl state push --dir ./snapshot --types rules --yes --report change-12345-applied.json
splunkctl state push --dir ./snap --types soar-assets --yes
splunkctl state diff --dir ./snapshot --types rules
```

Expected result: the report is written again with `applied: true` as the change record. `changes` has the same shape as `diff`'s modified and added rows plus `before` and `after` maps built from the field diff:

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

`changes` never includes `removed` or `unchanged` entries, only what was (or would be) created or updated. `removed` drift and dashboard apply-unsupported drift are console notes, not report entries, because neither is ever applied.

`push` never deletes. An instance object with no on-disk counterpart is classified `removed`, surfaced as a note (`note: rules: 2 object(s) on the instance only -- not deleted (push never deletes)`), and never touched; there is no delete path in `state push` by design. To remove something, use the type-specific `delete` command (`rules delete`, `lookups delete`, and so on) with its own guard.

Dashboards are pull and diff only. `state push` has no apply path for them: drifted dashboards are reported as apply-unsupported and skipped without erroring:

```text
note: dashboards: 1 drifted object(s), apply not supported (export-only, no import path)
```

If `dashboards` is the only `--types` value and nothing else drifted, `push` still exits 0 and, with `--report`, still writes an artifact with `changes: []`. To change a dashboard, use `splunkctl dashboards update` directly (see [Manage dashboards](dashboards.md)).

### Run the change-ticket loop end to end

> **Safety:** Target is the Splunk host in the active profile. Impact: step 5 creates and updates every drifted rule on the instance. Preview with step 4 and attach its report to the ticket, apply with step 5 once approved, and verify with `splunkctl state diff --dir ./snapshot --types rules` (expect only `unchanged`).

```bash
splunkctl state pull --dir ./snapshot --types rules
$EDITOR ./snapshot/rules.yml
splunkctl state diff --dir ./snapshot --types rules
splunkctl state push --dir ./snapshot --types rules --report change-12345-plan.json
splunkctl state push --dir ./snapshot --types rules --yes --report change-12345-applied.json
```

Expected result: a plan artifact for approval and an applied artifact as the record, from the same file; the same JSON works as the dry-run attachment and as the evidence of what actually happened.

## Troubleshooting

- Usage error "No SOAR host configured" when a SOAR type is requested: run `splunkctl config init --soar` or set `SOAR_HOST`.
- A lookup or dashboard shows `added` although it exists: `--app` differs between `pull` and `diff` or `push`; rerun all three with the same scope.
- `permission` on `push`: the account cannot write to the app that owns the object; narrow the run with `--types` or `--app` and fix the role.
- `push` printed "not deleted (push never deletes)": expected; delete with the type's own `delete` command if that is intended.
- Dashboards appear `modified` on every `diff`: cosmetic hash drift (see "Diff against the live instance"); verify with `splunkctl dashboards get <NAME>` before acting.

## See also

- [Manage detection rules](rules.md)
- [Manage source types and extractions](parsers.md)
- [Manage macros, eventtypes, tags](knowledge.md)
- [Manage lookups](lookups.md)
- [Manage dashboards](dashboards.md)
- [Run playbooks](soar-playbooks.md)
- [Maintain custom lists](soar-lists.md)
- [Configure assets and monitor ingestion](soar-assets.md)
- [Audit changes and attest RBAC](audit.md)
- [Command reference: state](../commands/state.md)
