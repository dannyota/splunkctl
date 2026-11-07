<!-- summary: Produce change-audit and role-based access control attestation reports from Splunk for regulators and reviewers. -->

# Audit changes and attest RBAC

When to use: a regulator or reviewer asks who changed a saved search, role, or index and when (`audit changes`), or who holds which capabilities and index access for periodic access recertification (`audit rbac`). Both commands are read-only: no guard, no `--yes`.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- For `changes`: search access to `index=_audit` (the `admin` role has it by default).
- For `rbac`: read access to users and roles (`edit_user` and `edit_roles`, or an `admin` account).

## Synopsis

```text
splunkctl audit changes [--since TIME] [--until TIME] [--user USER] [--action SUBSTRING] [--object-type TYPE] [--limit N]
splunkctl audit rbac [--roles-only] [--format csv] [--out FILE]
```

## Workflow

### Pull the change log for a window

```bash
splunkctl audit changes
splunkctl audit changes --since -7d --until -1d
splunkctl audit changes --limit 2000 --json
```

Expected result: one row per `_audit` event, newest first, with exactly six keys in this order: `time`, `user`, `action`, `object`, `object_type`, `app`. The default window is the last 24 hours (`--since -24h`, `--until now`) and the display cap is 500 rows. Splunk mixes two incompatible event shapes in `_audit`; this command normalizes both:

| Sourcetype | Shape | Mapping |
|---|---|---|
| `audittrail` (legacy) | `Audit:[timestamp=..., user=..., action=..., <tail>]` plain text | `user` and `action` parsed directly; `object` only when the line carries a literal `object="..."` marker (common on capability checks like `edit_user` and `edit_roles`); `object_type` always empty, the legacy format has no per-action type field; `app` from `app="..."` or unquoted `app=...` when present |
| `audittrailv2` (structured) | one JSON object per line | `user` = `actor.name`; `action` = top-level `action`; `object` = `data.name`; `object_type` = `data.type`; `app` = `data.ownership.app` or `data.attributes.app` |

`time` always comes from Splunk's indexed `_time`, not a re-parse of either embedded timestamp, so every row has one consistent, sortable value. Real `audittrailv2` events have no `data.object` or `data.object_type` key; `data.name` and `data.type` are the nearest equivalents and are present on object and system category events (config changes). Action, authn, and check category events (ad-hoc searches, logins, capability grants) carry `data.type` sometimes but rarely `data.name`, so `object` stays empty for them, which is correct: they are not changes to a named object. An event matching neither shape is never dropped; it comes back as `action: "unparsed"` with the full raw line in `object`, so evidence stays complete for formats the parser does not know yet.

### Filter by user, action, or object type

```bash
splunkctl audit changes --user jdoe
splunkctl audit changes --action edit
splunkctl audit changes --object-type saved_search
splunkctl audit changes --since -30d --user svc_deploy --action edit --format csv --out changes.csv
```

Expected result: only matching rows. `--user` and `--object-type` are case-insensitive exact matches; `--action` is a case-insensitive substring match. Filters run client side on the normalized rows after the fetch, and `--limit` applies after filtering. The raw fetch is unbounded (`count=0`) within the `--since` and `--until` window, so a filter never misses a match because of an arbitrary raw-fetch cutoff. A very wide `--since` over a large `_audit` index fetches every event in that range before limiting, which can be slow; narrow `--since` when you can.

### Confirm no flag value reaches the SPL

```bash
splunkctl --debug audit changes --user 'x" | delete' --action 'y | outputlookup evil.csv'
```

Expected result: the debug log shows `POST .../search/v2/jobs/ (body: {'search': 'search index=_audit', ...})`. The dispatched search is always the constant `search index=_audit`; `--since` and `--until` go through the job's `earliest_time` and `latest_time` arguments, and the other flags filter rows client side. No flag value, however adversarial, is composed into the SPL string.

### Export an RBAC recertification report

```bash
splunkctl audit rbac
splunkctl audit rbac --format csv --out recert-2026-07.csv
```

Expected result: one row per user with `user`, `email`, `roles` (direct roles, semicolon-joined), `capabilities`, and `srch_indexes_allowed`. The last two are aggregated across the user's direct roles and the full transitive closure of their imported roles, deduplicated, sorted, and semicolon-joined. Example: role `soc_analyst` imports `power`, which imports `user`; a `soc_analyst` user's effective `capabilities` is the union of all three roles' own capabilities. This is what a role with zero capabilities of its own needs (Splunk's built-in `splunk-system-role` only imports `admin`) to show its real effective grant instead of an empty cell. `rbac` reads roles and users through the SDK only; it dispatches no search.

### Attest per role instead of per user

```bash
splunkctl audit rbac --roles-only
splunkctl audit rbac --roles-only --format csv --out roles-2026-07.csv
```

Expected result: one row per role with `role`, `imported_roles` (direct only), `capabilities`, and `srch_indexes_allowed`, the last two aggregated the same transitive way, rooted at that role.

Multi-value fields (`roles`, `capabilities`, `srch_indexes_allowed`, `imported_roles`) join with `;`, never a newline. Splunk role, capability, and index names cannot contain a semicolon, so the join is lossless and never produces an embedded newline inside a CSV cell; `--format csv` output round-trips through Python's `csv` module.

## Troubleshooting

- `permission` or an empty result from `changes`: your role cannot search `index=_audit`; use an `admin` account or add `_audit` to the role's allowed indexes.
- `timeout` on `changes`: the window is too wide; narrow `--since` or raise the global `--timeout`.
- Rows show `action: "unparsed"`: the event matched neither audit shape; the raw line is in `object`, so the evidence is still complete.
- `object_type` is empty on every row: the instance writes only the legacy `audittrail` shape, which has no type field; filter on `--action` instead.
- `permission` from `rbac`: the account cannot list users or roles; it needs `edit_user` and `edit_roles` or an `admin` role.
- Fewer rows than expected: `--limit` defaults to 500 after filtering; raise it.

## See also

- [Manage users and roles](users.md)
- [Run searches](search.md)
- [Exit codes](exit-codes.md)
- [Command reference: audit](../commands/audit.md)
