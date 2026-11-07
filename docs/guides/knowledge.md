<!-- summary: Manage search macros, eventtypes, and tags as objects instead of editing conf files by hand. -->

# Manage macros, eventtypes, tags

When to use: a detection depends on a macro, an eventtype, or a CIM tag and you need to read or change it without remembering the stanza-naming rules of `macros.conf`, `eventtypes.conf`, and `tags.conf`. Only `macros set` mutates; `eventtypes` and `tags` are read-only.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- Write access to the app that owns `macros.conf` for `macros set`.
- For anything these verbs do not cover (creating or editing an eventtype or a tag assignment, or any other conf file), use [Edit any conf file](conf.md); these commands share `conf`'s stanza core rather than re-implementing it.

## Synopsis

```text
splunkctl macros list [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl macros get <NAME> [--app APP]
splunkctl macros set <NAME> --definition <SPL> [--args A,B] [--yes]
splunkctl eventtypes list [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl eventtypes get <NAME> [--app APP]
splunkctl tags list [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl tags get <FIELD=VALUE> [--app APP]
```

Two stanza shapes make these verbs worth having over raw `conf`: a macro with arguments is stored as `name(argcount)`, not `name`, and a `tags.conf` stanza is a `field=value` pair whose keys are tag names rather than config keys.

## Workflow

### Read macros

```bash
splunkctl macros list --app Splunk_Security_Essentials
splunkctl macros list --filter Sort
splunkctl macros get Sort_MITRE_Rows
splunkctl macros get "Sort_MITRE_Rows(1)"
```

Expected result: `list` shows each macro with its definition; `get` prints the full stanza. Splunk stores a macro that takes arguments under `name(n)` where `n` is the argument count (`Sort_MITRE_Rows(1)`, not `Sort_MITRE_Rows`). `macros get <name>` tries an exact stanza match first, which covers a no-arg macro or a name spelled out with its `(n)` suffix; if that misses and the name has no `(...)` of its own, it falls back to the `macros.conf` listing and picks the argument-form stanza whose base name matches. If more than one arg-count variant of the same base name exists (unusual, but legal), the lowest arg count wins; pass the full `name(n)` to reach the others.

### Audit what a detection's macro expands to

```bash
splunkctl rules get my_detection --json | jq -r .search
splunkctl macros get my_detection_macro --json | jq -r .definition
```

Expected result: the rule's SPL and the macro definition it calls. Long `definition` and `search` values are truncated for table display only (`... [+N chars]`); `--json` and `--format json` always carry the full text.

### Create or update a macro

> **Safety:** Target is the Splunk host in the active profile and `macros.conf` in the current app namespace. Impact: the stanza `NAME` (or `NAME(n)` with `--args`) is created or its `definition` replaced, and every search that calls the macro changes behaviour immediately. Preview with `splunkctl macros set my_macro --definition 'index=main'`, apply by adding `--yes`, and verify with `splunkctl macros get my_macro`.

```bash
splunkctl macros set my_macro --definition 'index=main'
splunkctl macros set my_macro --definition 'index=main' --yes
splunkctl macros set my_macro --definition 'eval x=$a$+$b$' --args a,b --yes
```

Expected result: the preview shows a field-level diff (`definition: add -> ...` for a new macro, `old -> new` for an update), the same mechanism as `conf set`; the apply prints `Created macro 'my_macro' (1 key(s)).` or `Updated ...`. The third example writes the stanza `my_macro(2)`.

`macros set` does no argument-form resolution: it is a thin name-to-stanza mapping, not a lookup. `--args a,b` computes `name(2)`, no `--args` computes the bare `name`, and that is the stanza written whether or not it existed. To update an existing arg-form macro, pass `--args` with the same argument count, or use `splunkctl conf set macros "name(n)" definition=... --yes` directly, which is also the way to change a macro's arg count.

### Read eventtypes

```bash
splunkctl eventtypes list
splunkctl eventtypes list --app Splunk_SA_CIM --filter cim: --json | jq '[.[] | {name, search}]'
splunkctl eventtypes get cim:authentication
```

Expected result: `list` shows `name`, `search`, `app`, and `disabled`; `get` prints the full stanza (search, tags, priority, color). The second example finds every eventtype backing a CIM data model.

### Check whether an eventtype is tagged

```bash
splunkctl tags list
splunkctl tags get "eventtype=cim:authentication"
splunkctl tags get "eventtype=cim%3Aauthentication"
```

Expected result: `tags list` shows one row per `field=value` stanza with only the enabled tag names (`;`-joined), a quick "what does this event carry" summary; `tags get` shows every tag key and its actual state, enabled or disabled, for full-detail auditing. Every key inside a `tags.conf` stanza is a tag name whose value is `enabled` or `disabled`; the top-level `disabled` key is the stanza's own flag, not a tag, and is excluded from both views. Splunk's REST layer percent-encodes a colon inside a tag value (`cim:authentication` becomes `cim%3Aauthentication`); `tags list` prints the decoded name, and `tags get` accepts either form.

## Troubleshooting

- `not_found` from `macros get`, `eventtypes get`, or `tags get`: the object lives in another app; pass `--app APP`. The unscoped default namespace can miss app-private stanzas, the same as `conf list` and `rules list`, and `get` uses `--app` to disambiguate a name that exists in more than one app.
- `macros set --yes` created a second stanza instead of updating: the existing macro is arg-form (`name(n)`) and you omitted `--args`, or passed a different count; rerun with the matching `--args`, then clear the stray stanza with `splunkctl conf unset macros NAME definition --yes`.
- `permission` from `macros set`: the account cannot write `macros.conf` in that app.
- `tags get` reports `Stanza 'X' not found in tags.conf`: copy the `field_value` exactly as `tags list` prints it, including the `field=` prefix.
- A macro change has no effect in searches: macros are read at search time, so the next search picks it up; check the definition with `macros get` and the calling rule with `rules get`.

## See also

- [Edit any conf file](conf.md)
- [Manage detection rules](rules.md)
- [Check data model acceleration](datamodels.md)
- [Manage configuration as code](state.md)
- [Command reference: macros](../commands/macros.md), [eventtypes](../commands/eventtypes.md), [tags](../commands/tags.md)
