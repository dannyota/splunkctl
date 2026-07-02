# Change audit & RBAC attestation

Regulator-facing evidence for bank SOC operations: who changed what
(`audit changes`) and who can do what (`audit rbac`). Both commands are
**read-only** — no `guard`, no `--yes` needed.

## Why this matters

Banks carry regulator obligations for change-management evidence ("who
changed this saved search / role / index, and when") and periodic access
recertification ("who has which capabilities, and why"). Today an agent
would have to hand-write `index=_audit` SPL and know that Splunk mixes
**two incompatible event shapes** in that one index — this group
normalizes both into one schema and joins the RBAC graph so neither
requires bespoke SPL per engagement.

## Commands

```bash
splunkctl audit changes                                   # last 24h, up to 500
splunkctl audit changes --since -7d --until -1d            # explicit window
splunkctl audit changes --user jdoe                        # exact-match user
splunkctl audit changes --action edit                      # substring-match action
splunkctl audit changes --object-type saved_search          # exact-match object type
splunkctl audit changes --limit 2000 --json                # raise the display cap

splunkctl audit rbac                                        # one row per user
splunkctl audit rbac --format csv --out recert-2026-07.csv  # recertification export
splunkctl audit rbac --roles-only                            # one row per role
```

## `audit changes`: normalized schema

Every row has exactly six keys, in this order: `time`, `user`, `action`,
`object`, `object_type`, `app`. Splunk's `_audit` index mixes two
sourcetypes and this command normalizes both:

| Sourcetype | Shape | Mapping |
|---|---|---|
| `audittrail` (legacy) | `Audit:[timestamp=..., user=..., action=..., <tail>]` plain text | `user`/`action` parsed directly; `object` only when the line carries a literal `object="..."` marker (common on capability checks like `edit_user`/`edit_roles`); `object_type` is always empty — the legacy format has no per-action type field; `app` from `app="..."` or unquoted `app=...`, when present |
| `audittrailv2` (structured) | one JSON object per line | `user` = `actor.name`; `action` = top-level `action`; `object` = `data.name`; `object_type` = `data.type`; `app` = `data.ownership.app` or `data.attributes.app` |

`time` always comes from Splunk's own indexed `_time` (not a re-parse of
either embedded timestamp format) — it's present on every event
regardless of shape and gives one consistent, sortable value.

There is no literal `data.object`/`data.object_type` key on real
`audittrailv2` events; `data.name`/`data.type` are the nearest
equivalents and confirmed present for object/system-category events
(config changes). Action/authn/check-category events (ad-hoc searches,
logins, capability grants) carry `data.type` sometimes but rarely
`data.name` — `object` stays empty for those, which is correct: they
aren't changes to a named object.

An event matching neither shape is **never dropped** — it comes back as
`action: "unparsed"` with the full raw line in `object`, so evidence
stays complete even for audit-log formats this parser doesn't yet know.

## `audit changes`: SPL safety

The dispatched search is always the constant `search index=_audit` —
nothing else, ever. `--since`/`--until` go through the oneshot job's
`earliest_time`/`latest_time` kwargs (not string-composed), and
`--user`/`--action`/`--object-type` filter the already-normalized rows
**client-side**, after the fetch. No flag value — however adversarial —
reaches the SPL string. Verified live with `--debug`:

```bash
$ splunkctl --debug audit changes --user 'x" | delete' --action 'y | outputlookup evil.csv'
...
POST .../search/v2/jobs/ (body: {'search': 'search index=_audit', ...})
```

`--limit` (default 500) applies **after** filtering, not to the raw
fetch — the raw fetch itself is unbounded (`count=0`) within the
`--since`/`--until` window, so a `--user`/`--action` filter never misses
a match just because it fell outside an arbitrary raw-fetch cutoff.
`--user`/`--object-type` are exact match; `--action` is substring match.

## `audit rbac`: aggregation

One row per user by default: `user`, `email`, `roles` (direct roles,
semicolon-joined), `capabilities`, `srch_indexes_allowed`. The last two
are aggregated across the user's direct roles **and the full transitive
closure of their imported roles** — deduplicated, sorted, and
semicolon-joined. `--roles-only` flips to one row per role instead:
`role`, `imported_roles` (direct only), `capabilities`,
`srch_indexes_allowed` (both aggregated the same transitive way, rooted
at that role).

Example: role `soc_analyst` imports `power`, which imports `user`. A
`soc_analyst` user's effective `capabilities` is the union of all three
roles' own capabilities — this is what a role with zero capabilities of
its own (e.g. Splunk's built-in `splunk-system-role`, which only imports
`admin`) needs to show its real effective grant, not an empty cell.

## CSV round-trip safety

Multi-value fields (`roles`, `capabilities`, `srch_indexes_allowed`,
`imported_roles`) join with `;`, never `\n` — Splunk role/capability/index
names can't contain a semicolon, so this is a safe, lossless join that
never produces an embedded newline inside a CSV cell. `--format csv`
output round-trips cleanly through Python's `csv` module.

## Options

| Flag | Applies to | Description |
|------|-----------|--------------|
| `--since` | `changes` | Earliest time (default `-24h`) |
| `--until` | `changes` | Latest time (default `now`) |
| `--user` | `changes` | Filter by user, exact match |
| `--action` | `changes` | Filter by action, substring match |
| `--object-type` | `changes` | Filter by object type, exact match |
| `--limit` | `changes` | Max results after client-side filtering (default 500) |
| `--roles-only` | `rbac` | One row per role instead of per user |

## Implementation notes

`changes` runs over the existing oneshot-search infrastructure
(`svc.jobs.oneshot`); the event-shape parsers live in a sibling module,
`splunkctl/commands/audit_parse.py`, kept separate from the click
commands since they're pure functions with their own fixture-driven test
suite. `rbac` is SDK reads only (`svc.roles`, `svc.users`) — no oneshot
search involved.
