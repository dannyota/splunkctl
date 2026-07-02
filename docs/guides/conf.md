# Conf

Generic conf file/stanza editor over the REST `confs` API — the escape
hatch for any Splunk conf file that doesn't have a dedicated command
group yet: `macros`, `eventtypes`, `tags`, `limits`, `authorize`,
`server`, `web`, and everything else under `$SPLUNK_HOME/etc/*/local`.

## Why this matters

Detections depend on more than saved searches: macros expand reusable
SPL fragments, eventtypes classify events, tags drive CIM compliance,
and calculated fields live in `props.conf` alongside sourcetypes.
`parsers` only reaches `props.conf`/`transforms.conf`; `conf` reaches
every other conf file the same way, so nothing detection-relevant is
locked out of code review or CI.

There is **no blocklist** — `conf` can edit `authorize.conf`,
`server.conf`, and `web.conf` just as readily as `macros.conf`. The
dry-run guard and `--yes` are the only safety net: every `set`/`unset`/
`reload` preview names the exact file and stanza before it touches
anything, so review the preview before applying to a sensitive file.

## Commands

```bash
splunkctl conf files                          # list conf files
splunkctl conf list macros                    # list stanzas in macros.conf
splunkctl conf list macros --app my_app       # scope to one app's stanzas
splunkctl conf get macros my_macro            # full stanza config
splunkctl conf get macros my_macro --key definition  # one key
splunkctl conf set macros my_macro \
    definition='index=main' --yes             # create/update keys
splunkctl conf unset macros my_macro definition --yes  # clear a key
splunkctl conf reload macros --yes            # reload the conf file
```

## Recipes

### Add a macro

Create a macro and verify it before rollout:

```bash
splunkctl conf set macros my_macro \
    definition='index=main sourcetype=syslog' --yes
splunkctl conf get macros my_macro
```

### Audit an eventtype

```bash
splunkctl conf get eventtypes authentication --json | jq .
```

### Review a stanza change before applying

`conf set` always previews a field-level diff — old value on the left,
new value on the right, `add` for a brand-new key:

```bash
splunkctl conf set macros my_macro definition='index=main'
# [DRY RUN] ...
#   definition: index=old -> index=main
```

### List conf files to find the right one

```bash
splunkctl conf files --filter tag
```

## Tips

- `conf set` creates the stanza if it doesn't exist yet — there's no
  separate create step.
- The REST API has no true per-key delete; `conf unset` sets keys to
  the empty string (same mechanism `parsers unset` uses). To fully
  remove a stanza, use the dedicated command group for that conf file
  when one exists (e.g. `parsers delete` for `props.conf`).
- `--app` on `conf list`/`conf files` matters: the unscoped default
  view can miss app-private stanzas, same as `rules list`/`dashboards
  list`.
- Reload the conf file after a `set`/`unset` if the change needs to
  take effect immediately (`conf reload <file> --yes`).
