# Live response shapes: Splunk 10.6.1.1

Captured 2026-11-09 from the `splunkctl-live` container (`splunk/splunk:10.6.1.1`
plus a `chmod 0400 /etc/shadow` fix for the host's AppArmor; splunkd is
unchanged), with `curl` against `https://127.0.0.1:18089/...?output_mode=json`.
Bodies are pretty-printed; key order and values are as returned except for
the trims and redactions below. Use them to model mocks for 0.19.0.

`NS` below is `servicesNS/admin/search`. The test objects were created as
admin in the search app (private, `sharing=user`) and deleted afterwards.

## Redaction and trims (all files)

- Container hostname replaced with `splunk-host`.
- GUIDs replaced with `00000000-0000-0000-0000-00000000000N`, one number per
  distinct GUID, so equal GUIDs stay equal.
- `server-info.json`: `licenseKeys[]`, `licenseSignature` and
  `staticAssetId` set to `REDACTED`.
- Trimmed `entry` lists keep the original `paging.total`.
- `action.email.auth_password` is already masked (`********`) by Splunk.

## Files

| File | Request | HTTP | Notes |
|---|---|---|---|
| `introspection-queues.json` | GET `services/server/introspection/queues` | 200 | 14 entries trimmed to indexQueue, parsingQueue, typingQueue |
| `introspection-indexer.json` | GET `services/server/introspection/indexer` | 200 | one entry: `average_KBps`, `status`, `reason` |
| `status-partitions-space.json` | GET `services/server/status/partitions-space` | 200 | sizes are strings in MB; `fs_type` only on some entries |
| `data-indexes.json` | GET `services/data/indexes` | 200 | 13 entries trimmed to `main`; `currentDBSizeMB` is a string, `totalEventCount` an int |
| `server-info.json` | GET `services/server/info` | 200 | redacted as above |
| `server-logger.json` | GET `services/server/logger` | 200 | first 3 of 30 returned (`paging.total` 1879) |
| `server-logger-TcpOutputProc.json` | GET `services/server/logger/TcpOutputProc` | 200 | `fields.required` = `["level"]` |
| `logger-set-debug-response.json` | POST `services/server/logger/TcpOutputProc` `level=DEBUG` | 200 | entry with the new level |
| `logger-error-invalid-level.json` | POST `services/server/logger/TcpOutputProc` `level=BOGUS` | 400 | |
| `acl-saved-searches.json` | GET `NS/saved/searches/sc_live_acl_search` | 200 | full entry (435 content keys) |
| `acl-data-macros.json` | GET `NS/data/macros/sc_live_acl_macro_data` | 200 | created with POST `NS/data/macros` |
| `acl-conf-macros.json` | GET `NS/configs/conf-macros/sc_live_acl_macro` | 200 | created with POST `NS/configs/conf-macros` |
| `acl-lookup-definition.json` | GET `NS/data/transforms/lookups/sc_live_acl_lookup` | 200 | |
| `acl-lookup-table-file.json` | GET `NS/data/lookup-table-files/sc_live_acl_lookup.csv` | 200 | |
| `acl-eventtypes.json` | GET `NS/saved/eventtypes/sc_live_acl_eventtype` | 200 | |
| `acl-views.json` | GET `NS/data/ui/views/sc_live_acl_view` | 200 | |
| `acl-datamodel.json` | GET `NS/datamodel/model/sc_live_acl_dm` | 200 | |
| `acl-props-extraction.json` | GET `NS/data/props/extractions/sc_live_acl_st%20%3A%20EXTRACT-sc_live_acl_ext` | 200 | entry name is `<stanza> : EXTRACT-<name>` |
| `acl-tags-fvtags.json` | GET `NS/saved/fvtags/sourcetype%3Dsc_live_acl_st` | 200 | ACL is per field=value pair, not per tag |
| `acl-tags-conf-tags.json` | GET `NS/configs/conf-tags/sourcetype%3Dsc_live_acl_st` | 200 | same stanza as fvtags |
| `search-tags-entry.json` | GET `NS/search/tags/sc_live_acl_tag` | 200 | no `acl`, `links` or `content` on the entry |
| `acl-get-subpath.json` | GET `NS/saved/searches/sc_live_acl_search/acl` | 200 | entry with `acl`; `content` is only `eai:acl` |
| `acl-set-saved-search-response.json` | POST `NS/saved/searches/sc_live_acl_search/acl` `sharing=app owner=admin perms.read=* perms.write=admin` | 200 | |
| `acl-set-saved-search-getback.json` | GET `NS/saved/searches/sc_live_acl_search` after the POST | 200 | |
| `acl-error-invalid-sharing.json` | POST `.../acl` `sharing=bogus owner=admin` | 500 | |
| `acl-error-unknown-role.json` | POST `.../acl` `sharing=app owner=admin perms.read=sc_live_acl_no_such_role perms.write=admin` | 200 | accepted and stored |
| `acl-error-missing-owner.json` | POST `.../acl` `sharing=app` (no `owner`) | 400 | |

## Observed behavior

- Objects that were never shared return `acl.perms: null`. Restoring
  `sharing=user` after app sharing keeps read `["*"]` and write `["admin"]`.
- After `sharing=app`, the entry `id` and `links` move to
  `servicesNS/nobody/search/...`; the `origin` keeps the request's namespace.
- POST `<entry>/acl` returns the entry with `content` reduced to `eai:acl`.
- An invalid `sharing` returns HTTP 500 `unknown sharing=bogus`, not 400.
- An unknown role in `perms.read` is accepted (200) and stored as given.
- Omitting `owner` returns 400 `User with name=system does not exist`.
- Both `data/macros` and `configs/conf-macros` work for create, GET and
  POST `<entry>/acl` (checked, response not saved); `data/macros` adds
  `fields.required: ["definition"]`.
- Tags: `search/tags/<tag>` has no ACL. `saved/fvtags/<field>=<value>` and
  `configs/conf-tags/<field>=<value>` expose the ACL of the tags.conf stanza,
  and POST `saved/fvtags/<field>=<value>/acl` changes it (seen through
  both endpoints).
- `server/logger` changes are runtime only: no `etc/log-local.cfg` is
  written, and `TcpOutputProc` was back to `INFO` after
  `podman restart -t 120`.

- L1: Any `perms.*` key in POST `<entry>/acl` replaces the whole perms
  object. From read `["*"]`, write `["admin"]`, sending only
  `perms.read=power` stored `{"read": ["power"]}` and exited 0.
  Omitting both keys preserves permissions. Merge current and requested
  lists, send both nonempty lists, and verify both on read-back.
- L2: `perms.read=''` stores the literal role `''`. Clear one list by
  omitting its key and sending the other: `sharing=app owner=X
  perms.write=admin` stores `{"write": ["admin"]}`. Splunk cannot clear
  both lists. Reject that request as usage before requests; never send an
  empty-string role.
- L3: Data-model lookups with owner `-`, including `servicesNS/-/-/`,
  return HTTP 500 with `{"messages": [{"type": "ERROR", "text":
  "Cannot get username when all users are selected"}]}`. Without an owner,
  try the authenticated user then `nobody`; if neither resolves, report
  not_found with `pass --current-owner`.
- L4: Returning app sharing to user sharing keeps permissions. Smoke
  assertions for `acl-search-back` and `acl-macro-back` check only sharing.
- L5: Queue responses have no `blocked` field. Disk used MB is capacity
  minus free when free exists, matching df with reserved blocks; otherwise
  use capacity minus available. Keep available separate and round computed
  MB to three decimals.
- L6: Global `splunkctl --read-only mcp install` must register stdio
  `mcp serve --read-only` and refuse HTTP with the same message as the
  command-local flag.
- L7: Codex CLI 0.167.0 listed splunkctl only after the directory was
  trusted. Codex skips project `.codex/config.toml` for untrusted projects.

L1 through L7 record the Linux lab verification of commit `4de5eea` and
its required CLI behavior; L6 describes registration policy, not splunkd.
