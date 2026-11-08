<!-- summary: Read and edit any Splunk configuration file and stanza over the REST confs API when no dedicated command group covers it. -->

# Edit any conf file

When to use: you need to read or change a stanza in a conf file that has no dedicated command group (`limits`, `authorize`, `server`, `web`, `savedsearches` keys the `rules` group does not expose, and anything else under `$SPLUNK_HOME/etc/*/local`), and you want a field-level preview before the write.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- An account allowed to edit the target conf file; sensitive files such as `authorize.conf` and `server.conf` need `admin_all_objects`.
- There is no blocklist: `conf` edits `authorize.conf`, `server.conf`, and `web.conf` as readily as `macros.conf`. The dry-run guard and `--yes` are the only safety net, so read the preview before applying to a sensitive file.

## Synopsis

```text
splunkctl conf files [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl conf list <FILE> [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl conf get <FILE> <STANZA> [--app APP] [--key KEY]
splunkctl conf set <FILE> <STANZA> <KEY=VALUE>... [--yes]
splunkctl conf unset <FILE> <STANZA> <KEY>... [--yes]
splunkctl conf reload <FILE> [--yes]
```

`FILE` is the conf name without `.conf` (`macros`, `limits`, `authorize`). `parsers` covers `props.conf` and `transforms.conf`, and `macros`, `eventtypes`, and `tags` have friendlier verbs (see [Manage macros, eventtypes, tags](knowledge.md)); `conf` reaches every file the same way, so nothing detection-relevant is locked out of code review or CI.

## Workflow

### Find the right file and stanza

```bash
splunkctl conf files
splunkctl conf files --filter tag
splunkctl conf list macros
splunkctl conf list macros --app my_app
```

Expected result: the conf files the server knows, then the stanzas in one file. Pass `--app` on `list` and `files`: the unscoped default view can miss app-private stanzas, the same as `rules list` and `dashboards list`.

### Read a stanza

```bash
splunkctl conf get macros my_macro
splunkctl conf get macros my_macro --key definition
splunkctl conf get eventtypes authentication --json | jq .
```

Expected result: every key in the stanza, or one key's value with `--key`. `--app` disambiguates a stanza that exists in more than one app.

### Set keys on a stanza

> **Safety:** Target is the Splunk host in the active profile and the named file and stanza. Impact: the listed keys are written; the stanza is created if it does not exist. Preview with `splunkctl conf set macros my_macro definition='index=main sourcetype=syslog'`, apply by adding `--yes`, and verify with `splunkctl conf get macros my_macro`.

```bash
splunkctl conf set macros my_macro definition='index=main sourcetype=syslog'
splunkctl conf set macros my_macro definition='index=main sourcetype=syslog' --yes
splunkctl conf get macros my_macro
```

Expected result: the preview names the file and stanza and shows a field-level diff, old value on the left, new value on the right, `add` for a brand-new key:

```text
[DRY RUN] Set 1 key(s) on 'my_macro' in macros.conf (profile: uat @ uat.splunk.internal:8089)
  file: macros.conf
  stanza: my_macro
  definition: index=old -> index=main sourcetype=syslog
Pass --yes to apply.
```

`conf set` creates the stanza when it is missing; there is no separate create step.

### Clear a key

> **Safety:** Target is the Splunk host in the active profile and the named file and stanza. Impact: the key is set to the empty string; the REST API cannot delete a key. Preview with `splunkctl conf unset macros my_macro definition`, apply by adding `--yes`, and verify with `splunkctl conf get macros my_macro --key definition`.

```bash
splunkctl conf unset macros my_macro definition
splunkctl conf unset macros my_macro definition --yes
```

Expected result: the key reads back empty (`""` or JSON `null`, depending on Splunk). This is the same mechanism `parsers unset` uses. To remove a whole stanza, use the dedicated command group for that file when one exists (for example `parsers delete` for `props.conf`).

### Reload the file

> **Safety:** Target is the Splunk host in the active profile. Impact: splunkd re-reads the named conf file so the change takes effect without a restart. Preview with `splunkctl conf reload macros`, apply with `splunkctl conf reload macros --yes`, and verify with `splunkctl conf get macros my_macro`.

```bash
splunkctl conf reload macros --yes
```

Reload after a `set` or `unset` when the change must take effect immediately.

## Troubleshooting

- `not_found` from `get`: the stanza lives in another app; rerun with `--app APP`, or list with `splunkctl conf list FILE --app APP`.
- `not_found` from `set` on a file: the conf file name is wrong; check `splunkctl conf files --filter <text>` and drop the `.conf` suffix.
- `permission` from `set`, `unset`, or `reload`: the account cannot write that file; `authorize.conf` and `server.conf` need `admin_all_objects`.
- A key still shows the old value after `set --yes`: run `splunkctl conf reload FILE --yes`, or the value is overridden by a higher-precedence app or a `default` layer.
- `unset` leaves the key present: expected, REST sets it to an empty string; remove the stanza through its dedicated group instead.

## See also

- [Manage macros, eventtypes, tags](knowledge.md)
- [Manage source types and extractions](parsers.md)
- [Manage configuration as code](state.md)
- [Command reference: conf](../commands/conf.md)
