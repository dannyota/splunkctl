# Macros, eventtypes, tags

Friendly, object-shaped verbs over `macros.conf`, `eventtypes.conf`, and
`tags.conf` — the knowledge objects detections lean on most. Only
`macros set` mutates; `eventtypes` and `tags` are **read-only**.

## Why this matters

Detections rarely stand alone: a correlation search calls a macro to
expand a reusable SPL fragment, an eventtype classifies raw events into
a named category, and a tag (via `tags.conf`) is what actually makes an
eventtype CIM-compliant. `conf` already reaches all three (and every
other conf file) generically, but its stanza-naming rules are file
-specific enough to be worth a friendlier surface: a macro with
arguments is stored as `name(argcount)`, not `name`, and a tags.conf
stanza is a `field=value` pair whose keys are tag names, not config
keys. `macros`/`eventtypes`/`tags` encode those two shapes so an agent
(or a human) doesn't have to.

These are **convenience verbs** — they share `conf`'s stanza core
(`conf_ops.py`) rather than re-implementing it, and `conf` remains the
tool for anything they don't cover (creating/editing an eventtype or
tag assignment, or any other conf file).

## Commands

```bash
splunkctl macros list --app Splunk_Security_Essentials   # macros with definitions
splunkctl macros list --filter Sort                       # name-substring filter
splunkctl macros get Sort_MITRE_Rows                       # resolves to Sort_MITRE_Rows(1)
splunkctl macros get "Sort_MITRE_Rows(1)"                  # exact arg-form name also works
splunkctl macros set my_macro --definition 'index=main' --yes
splunkctl macros set my_macro \
    --definition 'eval x=$a$+$b$' --args a,b --yes         # writes my_macro(2)

splunkctl eventtypes list                                  # name, search, app, disabled
splunkctl eventtypes get cim:authentication                # full stanza

splunkctl tags list                                        # field=value -> enabled tag names
splunkctl tags get "eventtype=cim%3Aauthentication"         # full enabled/disabled breakdown
```

## Macro argument-form resolution

Splunk stores a macro that takes arguments under a stanza named
`name(n)` (`n` = the argument count) — `Sort_MITRE_Rows(1)`, not
`Sort_MITRE_Rows`. `macros get <name>` tries an exact stanza match
first (this alone covers a no-arg macro or a name already spelled out
with its `(n)` suffix); if that misses and `name` has no `(...)` of its
own, it falls back to the macros.conf listing and picks the
argument-form stanza whose base name matches. If more than one
arg-count variant of the same base name exists (unusual, but legal),
the lowest arg count wins — pass the full `name(n)` to reach the others.

`macros set` does **not** do this resolution — it is a thin name-to
-stanza mapping, not a lookup: `--args a,b` computes `name(2)`, no
`--args` computes the bare `name`, and that's the stanza written,
whether or not it previously existed. To update an existing arg-form
macro, pass `--args` with the same argument count, or fall back to
`conf set macros "name(n)" definition=... --yes` directly.

## tags.conf shape

A `tags.conf` stanza is named `<field>=<value>` (e.g.
`eventtype=cim:authentication`) — not a free-form stanza name. Every
key inside that stanza is a tag name, and its value is `enabled` or
`disabled`; the top-level `disabled` key is the stanza's own
enable/disable flag, not a tag, and is excluded from both views below.

- `tags list` shows one row per stanza with only the **enabled** tag
  names (`;`-joined) — a quick "what does this event carry" summary.
- `tags get <field=value>` shows every tag key and its actual state
  (enabled or disabled), for full-detail auditing.

Splunk's REST layer leaves a colon inside a tag value percent-encoded
(`cim:authentication` becomes `cim%3Aauthentication` in the stanza
name) — copy the `field_value` exactly as `tags list` prints it when
passing it to `tags get`.

## Recipes

### Audit what a detection's macro actually expands to

```bash
splunkctl rules get my_detection --json | jq -r .search
splunkctl macros get my_detection_macro --json | jq -r .definition
```

### Find every eventtype backing a CIM data model

```bash
splunkctl eventtypes list --app Splunk_SA_CIM --filter cim: --json \
  | jq '[.[] | {name, search}]'
```

### Check whether an eventtype is actually tagged

```bash
splunkctl tags get "eventtype=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" 'cim:authentication')"
```

## Tips

- `--app` on any `list`/`get` matters the same way it does on `conf
  list`/`rules list`: the unscoped default can miss app-private
  stanzas, and `get` uses `--app` to disambiguate a name that exists in
  more than one app.
- `macros set` always previews a field-level diff before applying
  (`definition: add -> ...` for a new macro, `old -> new` for an
  update) — same mechanism as `conf set`.
- Long `definition`/`search` values are truncated for table display
  only (`… [+N chars]`); `--json`/`--format json` always carries the
  full text.
