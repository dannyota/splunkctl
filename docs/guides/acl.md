<!-- summary: Inspect knowledge object permissions and preview or apply ownership, sharing and role changes. -->

# Inspect and change permissions

Use `acl get` to inspect an object's owner, app, sharing, role arrays and modification capabilities. Use `acl set` to preview a change; add `--yes` to apply it.

```bash
splunkctl acl get saved-search 'My search' --app search
splunkctl acl set saved-search 'My search' --app search --sharing app --read '*' --write admin
splunkctl acl set saved-search 'My search' --app search --sharing app --read '*' --write admin --yes
splunkctl acl get saved-search 'My search' --app search
```

`--app` selects the namespace. On `get`, `--owner` selects the current owner. On `set`, `--current-owner` selects it and `--owner` changes ownership. Omitted selectors use the current namespace. Without configured selectors, lookup uses all owners (`-`) in the `search` app. An ambiguous lookup fails with `conflict`; select an owner and app explicitly.

Supported types: `saved-search`, `macro`, `eventtype`, `tag`, `props`, `transform`, `lookup-definition`, `lookup-table`, `field-extraction`, `data-model`, `view` and `dashboard`.

Names are exact stanza names. Include a macro's argument suffix, such as `'my_macro(2)'`. For `tag`, NAME is the tags.conf stanza `field=value`, such as `'sourcetype=my_source'`; permissions belong to the field/value pair. A field extraction is named `'<stanza> : EXTRACT-<name>'`. The CLI encodes each name as one URL segment.

`--sharing` accepts `user`, `app` or `global`. `--read` and `--write` accept comma-separated roles. Quote `'*'` for everyone, pass `''` to clear a role list, and omit an option to preserve its value. Duplicate roles are removed. Unknown roles fail before any write.

Private objects (`sharing=user`) have null read and write permissions in JSON and blank cells in table or CSV output. Permission options are rejected when the effective sharing is `user`. To change permissions, also select `app` or `global` sharing.

Sharing can move an object to the `nobody` namespace. The CLI reads back from the response's current location. Existing `dashboards share` and `rules share` commands use the same ACL helper.

The [Splunk REST ACL rules](https://help.splunk.com/en/splunk-enterprise/leverage-rest-apis/rest-api-user-manual/10.0/rest-api-user-manual/basic-concepts-about-the-splunk-platform-rest-api) describe sharing and role permissions. The supplied Splunk 10.6.1.1 fixtures additionally show that ACL updates require both owner and sharing, and that Splunk silently stores unknown roles; splunkctl validates them first.

See [Command reference: acl](../commands/acl.md) and [Read-only access](read-only.md).
