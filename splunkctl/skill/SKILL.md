# splunkctl — Agent Skill Guide

You are operating a Splunk Enterprise instance via `splunkctl`. This guide
tells you how to authenticate, run commands, and handle common workflows.

## Scope

`splunkctl` targets Splunk Enterprise core over the REST API. Enterprise
Security's notable-event triage loop (assign, status/urgency/disposition,
comment) has a dedicated, feature-detected `es notables` group — see
**ES notables** under Commands. Other ES capabilities — risk,
correlation-search actions, asset/identity lookups — are reachable
through the generic search, rules, and lookups commands; see
**ES recipes** under Workflow patterns.

## Auth

Set up credentials once — all commands inherit them automatically.

```bash
# Interactive (human use):
splunkctl config init

# Non-interactive (agent use):
splunkctl config init --host localhost --port 8089 \
    --username admin --password changeme --scheme https --no-verify

# Verify:
splunkctl config test
splunkctl config show                  # secrets redacted
```

Credentials resolve in order: CLI flags > env vars > config file
(`~/.splunkctl/config.yaml`). Env vars: `SPLUNK_HOST`, `SPLUNK_PORT`,
`SPLUNK_USER`, `SPLUNK_PASS`, `SPLUNK_TOKEN`, `SPLUNK_SCHEME`.

Token auth: set `SPLUNK_TOKEN` for service-account access without a password.

### Profiles (multi-instance: dev/UAT/prod)

The config file supports named profiles — one `~/.splunkctl/config.yaml`
covering several Splunk instances instead of juggling `-c` paths:

```yaml
profiles:
  dev:
    host: dev.splunk.internal
    username: admin
    password: devpass
  uat:
    host: uat.splunk.internal
    token: "..."
current: uat            # active profile when nothing else is specified
```

```bash
splunkctl config use uat                # switch the active profile
splunkctl config show                   # active profile (redacted) + other names
splunkctl config show --profile prod    # show a specific profile without switching
splunkctl --profile prod rules list     # override for one invocation only
```

Selection precedence: `--profile <name>` global flag > `current:` pointer >
`default`. `config use` only rewrites `current` — it never tests
connectivity (lazy auth is preserved). A plain single-instance config file
(flat `host`/`port`/... at the root, no `profiles:` key) keeps working
unchanged forever — it's treated as an implicit profile named `default`.
`config init` (bare) writes that flat shape — unless the destination
already has a `profiles:` key, in which case it folds the new values into
`profiles.default` instead, leaving sibling profiles and `current`
untouched (bare `config init` never clobbers an existing multi-profile
file). `config init --profile <name>` creates/updates a named profile
instead (upgrading a legacy file in place, folding its old values into
`profiles.default`, then run `config use <name>` to make the new profile
active).

**Bank-safety guard banner.** Every dry-run preview and every `--yes`
confirmation prints where the mutation is headed —
`(profile: <name> @ <host>:<port>)` when a config-file profile supplies
credentials, `(env @ <host>:<port>)` / `(flags @ <host>:<port>)` when env
vars or CLI flags override them — so an agent driving multiple instances
can never mistake UAT for prod:

```
[DRY RUN] Disable saved search 'X' (profile: uat @ uat.splunk.internal:8089)
```

Building this banner only reads local config/env — it never opens a
connection, preserving lazy auth even for a blocked dry-run.

## Global flags

| Flag | Purpose |
|---|---|
| `--json` | Force JSON output |
| `--format table\|json\|csv\|jsonl` | Output format |
| `--fields f1,f2` | Project specific fields |
| `-o, --out file` | Write output to file |
| `-y, --yes` | Apply mutations (skip dry-run) |
| `--timeout N` | Request timeout in seconds (default 30) |
| `-c, --config path` | Config file path override |
| `--profile name` | Named profile to use (overrides the file's `current:`) |
| `--debug` | HTTP request/response logging |

**Dry-run by default.** Every mutation previews what would change. Only
`--yes` applies it.

## Output behavior

- **stdout**: data payload only (table, JSON, CSV, JSONL)
- **stderr**: info messages, errors, dry-run previews
- **JSON format**: always a JSON array of objects, even for single items
- **Exit codes**: 0 = success, 1 = application error (not found, server
  rejected the request, etc.), 2 = usage error (missing/invalid flags or
  arguments — Click rejects before any request is made). Dry-run exits 0.

## List paging & filtering

Every list surface (`rules list`, `alerts list`, `dashboards list`,
`indexes list`, `inputs list`, `lookups list`, `hec list`, `apps list`,
`users list`, `users roles`, `parsers sourcetypes`, `parsers extractions`,
`search jobs`) accepts three uniform options:

| Option | Meaning |
|---|---|
| `--limit N` | Return at most N entries (N ≥ 1; default: all) |
| `--offset N` | Skip the first N entries (N ≥ 0) |
| `--filter STR` | Case-insensitive name substring, applied before paging |

- **Defaults are complete.** Without flags, every list fetches the entire
  collection — there is no hidden page size. An unflagged `rules list
  --app -` or `users list` is a full inventory. Exception: `inputs list` uses
  the SDK's union Inputs collection, which pages each kind with a 30-per-kind
  default limit — for environments with >30 inputs of a single kind, the list
  may be incomplete. To verify completeness for a specific kind, use
  `splunkctl search oneshot '| rest /services/data/inputs/<kind>' --limit 10000` (e.g.,
  `'| rest /services/data/inputs/monitor'`).
- **Order**: `--filter` narrows first; `--limit`/`--offset` then page the
  filtered set.
- `--filter` matches the name column (`search jobs` matches the sid;
  `alerts list` matches the rule name and pages firing rows).
- Existing flags compose: `rules list --app X --filter beacon --limit 10`.

## Commands

### Doctor

```bash
splunkctl doctor                         # check connection, auth, health, permissions
splunkctl doctor --json                  # machine-readable output
splunkctl doctor --strict                # treat warnings as failures (exit 1)
```

### Search

```bash
splunkctl search run 'index=main error | head 10'
splunkctl search run 'index=main' --earliest -24h --latest now --limit 50
splunkctl search run 'index=main' --detach           # start job, return SID, don't wait
splunkctl search export 'index=main | stats count by sourcetype'
splunkctl search oneshot '| makeresults count=5 | eval x=random()'
splunkctl search jobs                    # list recent jobs (with owner, SPL preview)
splunkctl search job <sid>               # get job results
splunkctl search job <sid> --offset 100 --count 50   # paged results
splunkctl search job <sid> --events      # raw events instead of results
splunkctl search job <sid> --status-only # job status without results
splunkctl search cancel <sid> --yes      # cancel a running job
splunkctl search upload --path threats.csv --index threat_intel --yes
```

SPL is auto-normalized: bare keywords get `search` prepended; pipe-leading
and generating commands (`makeresults`, `inputlookup`, `tstats`, etc.) are
passed through unchanged. Use `--app` to scope searches to a specific app.
The `owner` column in `search jobs` is the real submitting user (job ACL,
not the job's internal `author` field, which is always blank).

### Rules (saved searches)

```bash
splunkctl rules list
splunkctl rules list --app Splunk_Security_Essentials  # include app-private rules
splunkctl rules get 'My Rule'
splunkctl rules get 'My Rule' --app Splunk_Security_Essentials --owner nobody
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --cron '*/5 * * * *' --actions email --email-to soc@bank.example \
    --description 'Alert on errors' --yes
splunkctl rules update 'My Rule' --search 'index=main fail' --yes
splunkctl rules update 'My Rule' --enabled --yes
splunkctl rules delete 'My Rule' --yes
splunkctl rules enable 'My Rule' --yes
splunkctl rules disable 'My Rule' --yes
splunkctl rules share 'My Rule' --sharing app --yes
splunkctl rules history 'My Rule'
splunkctl rules list --filter mitre          # name substring (case-insensitive)
splunkctl rules export --path detections.yml
splunkctl rules export --path detections.yml --name 'My Rule'
splunkctl rules import --path detections.yml --yes
splunkctl rules import --path detections.yml --no-update --yes
```

`list`/`get` default to the current namespace, which misses saved
searches private to another app — e.g. detections shipped inside
Splunk_Security_Essentials are invisible to a plain `rules list`. Always
pass `--app` when auditing detection coverage: it automatically
wildcards the owner (`owner="-"`) so app-private rules owned by any user
are included, not just the caller's own. Add `--owner` only to narrow
the audit to a single user's rules — omitting `--app` entirely still
leaves a blind spot. `get` also surfaces every enabled action's
non-empty `action.<name>.*` params (e.g. `action.notable.param.severity`,
`action.risk.param._risk_score`) inline — no export needed just to see
what a correlation search's actions are configured to do.

`create`/`update --actions email` or `--actions webhook` warn on stderr
during dry-run if the action's required companion field is missing
(`action.email.to` for email, `action.webhook.param.url` for webhook) —
the server otherwise 400s on `--yes`. First-class flags supply the common
fields (`create`/`update` both):

| Flag | Field |
|---|---|
| `--email-to` | `action.email.to` |
| `--email-subject` | `action.email.subject` |
| `--webhook-url` | `action.webhook.param.url` |

```bash
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --actions email --email-to soc@bank.example --yes
```

A flag does not enable its action by itself — `--actions` still must name
it, or the CLI prints a non-blocking advisory (the command still applies).
A flag together with an equivalent `--set` for the *same* field is a usage
error (exit 2) — fix the collision, the CLI won't silently pick one:

```bash
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --email-to soc@bank.example --set action.email.to=other@bank.example
# Error: --email-to conflicts with --set action.email.to
```

`--set KEY=VALUE` (repeatable, `create`/`update` only) sets any raw
saved-search REST field — the generic escape hatch for anything without
a first-class flag, including ES action params:

```bash
splunkctl rules update 'ES Correlation Search' \
    --set action.notable.param.severity=high \
    --set action.notable.param.security_domain=access \
    --set action.risk.param._risk_score=80 \
    --set action.risk.param._risk_object_type=user \
    --yes
```

### Alerts

```bash
splunkctl alerts list
splunkctl alerts get 'Alert Name'
splunkctl alerts actions               # list alert action types
splunkctl alerts suppress 'Alert Name' --duration 7200 --yes
splunkctl alerts unsuppress 'Alert Name' --yes
```

### ES notables

Requires Enterprise Security (`SplunkEnterpriseSecuritySuite`) — every
subcommand feature-detects first and exits 1 with a `not_found` envelope
naming the app if it's missing. No dedicated SDK entity class; `list`/`get`
run over oneshot search against `index=notable`, `update` POSTs to
`/services/notable_update`. Live-verified against ES: pending (local dev
has Splunk Security Essentials, not ES) — only the feature-detection
negative path has been verified against a real instance.

```bash
splunkctl es notables list                                # last 24h, up to 100
splunkctl es notables list --since -7d --status new --owner unassigned
splunkctl es notables list --rule beacon --limit 20        # by correlation search
splunkctl es notables get <event_id>                       # full field set
splunkctl es notables update <event_id> --status closed \
    --comment 'false positive' --yes
splunkctl es notables update <id1> <id2> <id3> \
    --owner analyst1 --urgency high --yes                  # bulk triage
```

`--status` accepts a name (`unassigned`/`new`/`in progress`/`pending`/
`resolved`/`closed`) or the raw integer (0-5, or higher for custom
statuses). `--disposition` passes through as given (e.g. `disposition:1`)
— dispositions are instance-configurable, so the CLI doesn't invent a
name map. `update` requires at least one of `--status`/`--owner`/
`--urgency`/`--disposition`/`--comment`; none is a usage error (exit 2).

### Audit (compliance & RBAC attestation)

Read-only, no `guard`. `changes` wraps `index=_audit`, which mixes two
incompatible event shapes (legacy `Audit:[timestamp=...]` text and
structured JSON), and normalizes both into one six-key schema: `time`,
`user`, `action`, `object`, `object_type`, `app`. An event matching
neither shape is never dropped — it comes back as `action: "unparsed"`
with the raw line in `object`.

```bash
splunkctl audit changes                                # last 24h, up to 500
splunkctl audit changes --since -7d --user jdoe         # case-insensitive exact-match user
splunkctl audit changes --action edit --json            # case-insensitive substring-match action
splunkctl audit changes --object-type saved_search      # case-insensitive exact-match object type
splunkctl audit rbac                                    # users x roles x caps x indexes
splunkctl audit rbac --format csv --out recert.csv      # recertification export
splunkctl audit rbac --roles-only                       # one row per role instead
```

SECURITY: `changes`'s dispatched SPL is always the constant
`search index=_audit` — `--since`/`--until` go through the search job's
time-range kwargs, and `--user`/`--action`/`--object-type` filter the
normalized rows client-side (case-insensitive). No flag value ever reaches the SPL string,
even adversarial ones. `rbac`'s `capabilities`/`srch_indexes_allowed`
columns aggregate across each principal's direct roles AND the full
transitive closure of imported roles (dedup, sort, `;`-joined — never
`\n`, so CSV stays clean).

### Dashboards

```bash
splunkctl dashboards list                # includes type column (classic/studio)
splunkctl dashboards list --app search
splunkctl dashboards get my_dashboard
splunkctl dashboards get my_dashboard --definition  # Studio JSON only
splunkctl dashboards create --name new_dash --file dash.xml --yes
splunkctl dashboards create --name studio_dash --file viz.json --type studio --yes
splunkctl dashboards create --name dash --file d.xml --sharing app --yes
splunkctl dashboards update my_dash --file updated.xml --yes   # shows diff preview
splunkctl dashboards delete my_dash --yes
splunkctl dashboards export my_dash --out dash.xml
splunkctl dashboards export my_dash --definition     # Studio JSON definition
splunkctl dashboards export --all --dir ./dashboards # bulk export all
splunkctl dashboards share my_dash --sharing app --yes
```

### Indexes

```bash
splunkctl indexes list
splunkctl indexes get main
splunkctl indexes create --name my_index --yes
splunkctl indexes create --name metrics_idx --datatype metric \
    --max-size 500 --frozen-period 604800 --yes
splunkctl indexes update my_index --max-size 1000 --yes
splunkctl indexes update my_index --frozen-period 2592000 --yes
splunkctl indexes delete my_index --yes
splunkctl indexes clean my_index --yes   # remove all events
splunkctl indexes reload --yes
```

### Inputs

```bash
splunkctl inputs list
splunkctl inputs list --kind monitor
splunkctl inputs get /var/log/syslog
splunkctl inputs create --name /var/log/app.log --kind monitor \
    --index main --sourcetype syslog --yes
splunkctl inputs update /var/log/app.log --sourcetype json --yes
splunkctl inputs update /var/log/app.log --disabled --yes
splunkctl inputs delete /var/log/app.log --yes
splunkctl inputs enable /var/log/app.log --yes
splunkctl inputs disable /var/log/app.log --yes
```

### Lookups

```bash
splunkctl lookups list
splunkctl lookups list --app Splunk_Security_Essentials
splunkctl lookups get my_lookup.csv
splunkctl lookups upload my_lookup.csv --file data.csv --app search --yes
splunkctl lookups update my_lookup.csv --file updated.csv --app search --yes
splunkctl lookups download my_lookup.csv --app search
splunkctl lookups download my_lookup.csv --app search --out local.csv
splunkctl lookups delete my_lookup.csv --app search --yes

splunkctl lookups define my_def --file my_lookup.csv --yes       # transforms.conf
splunkctl lookups define my_def --collection my_coll --yes       # kvstore-backed
splunkctl lookups auto my_def --sourcetype my_st \
    --input host --output owner --yes                            # props.conf LOOKUP-*
splunkctl lookups definitions                                    # list transforms.conf lookup stanzas
```

Uploading a table file makes it exist server-side; it isn't a usable
*lookup* until `define` binds a name to it (transforms.conf) and,
usually, `auto` wires that name onto a sourcetype (props.conf
`LOOKUP-<name> = ...`) so matching events enrich automatically with no
`| lookup` in the SPL. Both are guarded, both delegate to `conf_ops`
(no hand-rolled SDK conf access). `define` requires exactly one of
`--file`/`--collection` (else exit 2) and warns, without blocking, if
`--file` names a table that doesn't exist yet in that app. `auto`
requires at least one `--input` and one `--output` (else exit 2, both
repeatable); `--input FIELD[:LOOKUP_FIELD]` gives the event field first
and the lookup table's column second only if it differs;
`--output LOOKUP_FIELD[:EVENT_FIELD]` gives the lookup column first and
the event-side rename second. `--overwrite` (default) emits `OUTPUT`;
`--no-overwrite` emits `OUTPUTNEW`. Full define -> auto -> enrich
worked example: `docs/guides/lookups.md`.

### KV store (collections + data CRUD)

Allowlists, threat intel, ES asset/identity — schema-less JSON document
storage scoped per app. No SDK entity class; every command is a thin,
typed wrapper around raw `storage/collections/{config|data}` REST calls,
always addressing `servicesNS/nobody/<app>/...` (`--app`, default
`search`). Live round-trip pending a healthy KV store — the local dev
instance's is down (`server kvstore` -> `status: failed`); only the
negative path (clean classified failure, never blank/traceback) is
live-verified. Full guide: `docs/guides/kvstore.md`.

```bash
splunkctl kvstore collections                       # list collection names (app: search)
splunkctl kvstore create my_allowlist --yes          # empty collection
splunkctl kvstore delete my_allowlist --yes          # collection + ALL its data

splunkctl kvstore query my_allowlist                              # all documents
splunkctl kvstore query my_allowlist --query '{"host": "evil.example"}'
splunkctl kvstore query my_allowlist --limit 50 --skip 100 --sort '-_key'

splunkctl kvstore insert my_allowlist --data '{"host": "evil.example"}' --yes
splunkctl kvstore insert my_allowlist --file doc.json --yes
splunkctl kvstore update my_allowlist <key> --data '{"host": "new.example"}' --yes
splunkctl kvstore remove my_allowlist <key> --yes                       # by _key
splunkctl kvstore remove my_allowlist --query '{"host": "evil.example"}' --yes  # by query

splunkctl kvstore export my_allowlist --out backup.jsonl   # JSONL, one doc per line
splunkctl kvstore import my_allowlist --file backup.jsonl --yes   # upserts by _key, chunked at 500
```

`query`'s `--limit`/`--skip`/`--sort` are KV store API params passed
straight through server-side — this is **not** the uniform
`--limit`/`--offset`/`--filter` list-paging convention above (no
client-side filtering, no `--offset`/`--filter`). `insert`/`update`
require exactly one of `--data`/`--file`; `remove` requires exactly one
of `KEY`/`--query`; invalid JSON anywhere is a usage error (exit 2), not
a silent failure. `export`/`import` round-trip JSONL with `_key`
preserved, so re-importing an export upserts onto the same documents
(`batch_save` semantics). A raw collection name isn't automatically
usable via `| inputlookup` — that needs a lookup *definition*
(`transforms.conf`) binding the collection to a lookup name:
`splunkctl lookups define <name> --collection <collection> --yes` (see
**Lookups** above).

### HEC (HTTP Event Collector)

```bash
splunkctl hec list                      # list all HEC tokens
splunkctl hec get my_token              # get token details
splunkctl hec create --name my_token --index main --yes
splunkctl hec create --name my_token --index main --set useACK=1 --yes
splunkctl hec delete my_token --yes
splunkctl hec enable my_token --yes
splunkctl hec disable my_token --yes
splunkctl hec settings                  # show global HEC state (port, SSL)
splunkctl hec settings --enable --yes   # enable global HEC
splunkctl hec settings --disable --yes  # disable global HEC
splunkctl hec send my_token 'test event data' --yes  # send event via HEC
```

### Parsers (sourcetypes & extractions)

```bash
splunkctl parsers sourcetypes           # list all sourcetypes
splunkctl parsers get syslog            # get sourcetype config
splunkctl parsers get syslog --key TIME_FORMAT  # get one key
splunkctl parsers extractions           # list field extractions
splunkctl parsers set syslog TIME_FORMAT '%Y-%m-%d' --yes  # set config key
splunkctl parsers unset syslog TIME_FORMAT --yes           # remove key
splunkctl parsers create --sourcetype mysource --category Custom --yes
splunkctl parsers update mysource --category Operating_System --yes
splunkctl parsers delete mysource --yes
splunkctl parsers reload --yes
splunkctl parsers export --path parsers.yml          # export props/transforms
splunkctl parsers import --path parsers.yml --yes    # import from YAML
```

### Conf (generic escape hatch — any conf file/stanza)

`parsers` only reaches `props.conf`/`transforms.conf`. `conf` reaches
every other conf file (`macros`, `eventtypes`, `tags`, `limits`,
`authorize`, `server`, `web`, ...) the same way — there is no
blocklist, so double-check the preview before `--yes` on a sensitive
file. `macros`/`eventtypes`/`tags` below wrap `macros.conf`/
`eventtypes.conf`/`tags.conf` with a friendlier shape (arg-form macro
resolution, tags' enabled-only summary); `conf` is still the tool for
anything they don't cover, including creating/editing an eventtype or
tag assignment.

```bash
splunkctl conf files                        # list conf files
splunkctl conf list macros                  # list stanzas in a conf file
splunkctl conf list macros --app my_app     # scope to one app's stanzas
splunkctl conf get macros my_macro          # full stanza config
splunkctl conf get macros my_macro --key definition  # one key only
splunkctl conf set macros my_macro definition='index=main' --yes  # create/update
splunkctl conf unset macros my_macro definition --yes  # clear a key (sets empty)
splunkctl conf reload macros --yes          # reload the conf file
```

`conf set` previews a field-level diff (`key: old -> new`, `add` for a
brand-new key) before applying; `conf unset` previews the same shape
for the values being cleared. The REST API has no true per-key delete,
so `unset` sets keys to the empty string — it does not remove the
stanza itself.

### Macros, eventtypes, tags (friendly wrappers over `conf`)

Only `macros set` mutates; `eventtypes` and `tags` are read-only — use
`conf set`/`conf unset` on `eventtypes`/`tags` for anything beyond
reading.

```bash
splunkctl macros list --app Splunk_Security_Essentials  # macros with definitions
splunkctl macros get Sort_MITRE_Rows          # resolves to Sort_MITRE_Rows(1)
splunkctl macros set my_macro --definition 'index=main' --yes
splunkctl macros set my_macro --definition 'eval x=$a$+$b$' \
    --args a,b --yes                          # writes stanza my_macro(2)

splunkctl eventtypes list                     # name, search, app, disabled
splunkctl eventtypes get cim:authentication   # full stanza

splunkctl tags list                           # field=value -> enabled tag names (;-joined)
splunkctl tags get "eventtype=cim%3Aauthentication"  # full enabled/disabled breakdown
```

A macro with arguments is stored under stanza `name(argcount)`, e.g.
`Sort_MITRE_Rows(1)` — `macros get` accepts the name with or without
that suffix and resolves a bare name to its arg-form stanza when one
exists. `macros set` does not do that resolution: it always writes
`name(len(--args))` when `--args` is given, else the bare `name` — to
update an existing arg-form macro, pass `--args` with the same count.

A `tags.conf` stanza is named `<field>=<value>` (e.g.
`eventtype=cim:authentication`, shown percent-encoded by Splunk as
`eventtype=cim%3Aauthentication`); each key inside it is a tag name
with value `enabled`/`disabled`. `tags list` shows only the enabled
tag names per stanza; `tags get` shows every tag's actual state.

### Data models (CIM/tstats acceleration)

No SDK entity — raw REST over `datamodel/model` (definitions) and
`admin/summarization` (acceleration build status; percent complete and
the summarized range do NOT live on the model resource itself). Full
guide: `docs/guides/datamodels.md`.

```bash
splunkctl datamodels list                             # name, app, accelerated, disabled
splunkctl datamodels list --app Splunk_SA_CIM --filter auth

splunkctl datamodels get Authentication                # detection-engineering summary
splunkctl datamodels get Authentication --definition   # raw objects/fields/calculations JSON

splunkctl datamodels acceleration                      # every accelerated model's build status
splunkctl datamodels acceleration Authentication        # one model, accelerated or not

splunkctl datamodels rebuild Authentication --yes       # re-summarize from scratch (guarded)
```

`acceleration` (no name) lists only models whose acceleration config is
enabled — `enabled`, `has_summary` (built at least once), `is_complete`/
`percent_complete`, `size`, `earliest_summarized`/`latest_summarized`,
`last_error`; cleanly renders empty when nothing is accelerated. Named
with a model that isn't accelerated, it still shows the row
(`enabled: false`) rather than erroring — only a nonexistent model is an
error. `rebuild` has no dedicated REST verb: it disables then
re-enables acceleration with the same `earliest_time` window (exactly
what Splunk Web's own "Rebuild" button does), dropping and rebuilding
the summary from scratch; a non-accelerated model exits 1 before the
dry-run/`--yes` guard even runs.

> **Verification status:** `list`/`get`/non-accelerated `acceleration` are
> live-verified; the populated `acceleration` status row and the
> `rebuild --yes` apply path are unit-tested against the documented REST
> shape but not yet exercised against a live accelerated model (no CIM
> add-on on the test instance). See `docs/guides/datamodels.md`.

### Apps

```bash
splunkctl apps list
splunkctl apps get SplunkForwarder
splunkctl apps install --path ./my_app.spl --yes
splunkctl apps install --path ./my_app.tar.gz --force --yes
splunkctl apps uninstall my_app --yes
splunkctl apps update my_app --enabled --visible --yes
splunkctl apps update my_app --disabled --hidden --yes
splunkctl apps reload --yes
```

`apps install --path` uploads a local .spl/.tar.gz to the remote Splunk
instance via the Web UI (no server filesystem access needed).

### Users

```bash
splunkctl users list
splunkctl users get admin
splunkctl users create --name newuser --password 'pass' \
    --roles user --email user@example.com --yes
splunkctl users update newuser --roles 'user,power' --yes
splunkctl users update newuser --password 'newpass' --yes
splunkctl users delete newuser --yes
splunkctl users roles                   # list all roles
splunkctl users roles get admin         # role details
splunkctl users roles create --name myrole --imported-roles user \
    --capabilities 'search,list_inputs' --yes
splunkctl users roles update myrole --search-filter 'index=main' --yes
splunkctl users roles delete myrole --yes
```

### Server

```bash
splunkctl server messages               # list system messages
splunkctl server messages --dismiss warn_disk --yes  # dismiss a message
splunkctl server license                # license pool usage
splunkctl server kvstore                # KV store status
```

`kvstore` always reports an explicit status word (`ready`, `failed`,
`starting`, `unknown`, ...) — never a blank field, so a down KV store
can't be mistaken for a healthy empty result.

### Config

```bash
splunkctl config init                   # interactive setup (writes the flat/default file)
splunkctl config init --host h --port 8089 --username u --password p
splunkctl config init --profile uat --host h --username u --password p  # named profile
splunkctl config use uat                # switch the active profile (no connectivity test)
splunkctl config show                   # active profile, redacted, + other profile names
splunkctl config show --profile prod    # show one profile without switching
splunkctl config test                   # verify connectivity
```

See **Profiles** under Auth for the multi-instance (dev/UAT/prod) model and
the guard-banner safety contract.

### Info & version

```bash
splunkctl info                          # server info
splunkctl --version                     # CLI version
```

### Agent discovery

```bash
splunkctl commands                      # JSON command tree
splunkctl skill                         # print this guide
splunkctl skill install                 # install to ~/.claude/skills/
```

## Workflow patterns

### Investigate an alert

Pivot on the firing's `sid` to pull the exact triggering events — don't
re-run the detection's SPL broadly, that returns whatever matches now,
not what actually fired.

```bash
splunkctl alerts list                    # each firing has a sid
splunkctl alerts get 'Alert Rule Name'    # all firings for one rule, with sid
splunkctl search job <sid>                # the exact triggering results
splunkctl search job <sid> --events       # raw events instead of stats/table rows
```

Fallback only: if the job's TTL has expired (`search job <sid>` errors
not-found), recover the SPL from the rule and re-run it over the firing's
time window instead:

```bash
splunkctl rules get 'Alert Rule Name'                # recover the SPL
splunkctl search run '<SPL from rules get>' \
    --earliest -7d --latest now --limit 1000
```

### Audit detection coverage

```bash
splunkctl rules list --json | jq '[.[] | select(.is_scheduled == "1")]'
splunkctl rules list --json | jq '[.[] | select(.disabled == "1")]'
# Repeat with --app for every app that ships detections, or app-private
# rules (e.g. Splunk_Security_Essentials) are silently excluded:
splunkctl rules list --app Splunk_Security_Essentials --json | jq '[.[] | select(.disabled == "1")]'
```

### Check CIM acceleration health before trusting a tstats detection

A `| tstats` detection only sees what its data model has actually
summarized — before trusting (or debugging) one, confirm the model
behind it is not just accelerated, but complete and current:

```bash
splunkctl rules get 'My tstats Detection' --json | jq -r .search
# note the datamodel=<Name> the search reads from, then:
splunkctl datamodels acceleration <Name>
```

Read the row: `enabled: false` means the detection is running `tstats`
against a model that was never accelerated at all (it'll silently return
nothing, or fall back to a slow raw search depending on the SPL) —
accelerate it or fix the detection. `has_summary: false` means
accelerated but never built yet (cron hasn't fired). `is_complete:
false`/`percent_complete` under 100 means still backfilling — expect
gaps in the earliest part of the window. `last_error` non-empty means
the build itself is failing — that's the root cause of "this detection
never fires," not the SPL. If `latest_summarized` is far behind now,
the schedule is falling behind volume; consider `datamodels rebuild
<Name> --yes` only if the summary looks corrupted/stuck, since a
rebuild re-summarizes from scratch rather than catching up
incrementally.

### ES recipes

Notable-event triage (list/get/update) has a dedicated group — see
**ES notables** under Commands. These recipes cover the rest of
Enterprise Security, still reachable only through the generic search,
rules, and lookups commands.

```bash
# Read notables with ad-hoc SPL the es notables group doesn't cover
splunkctl search run 'index=notable' --earliest -24h --latest now --limit 100
splunkctl search run 'index=notable status_label!=Closed' --earliest -7d --limit 200

# Read risk — aggregate risk score per object
splunkctl search run 'index=risk | stats sum(risk_score) by risk_object' \
    --earliest -24h --latest now

# Author/tune a correlation search's notable + risk actions via --set
splunkctl rules update 'ES Correlation Search Name' \
    --set action.notable.param.severity=high \
    --set action.notable.param.security_domain=access \
    --set action.risk.param._risk_score=80 \
    --set action.risk.param._risk_object=user \
    --set action.risk.param._risk_object_type=user \
    --yes
# Audit what a correlation search's actions are already set to:
splunkctl rules get 'ES Correlation Search Name'   # inlines action.notable.*/action.risk.* params

# Asset/identity CSVs — managed like any other lookup table (exact
# filename/app vary by ES version, e.g. assets_by_str.csv /
# identities_lookup_by_str.csv under SplunkEnterpriseSecuritySuite):
splunkctl lookups list --app SplunkEnterpriseSecuritySuite
splunkctl lookups download assets_by_str.csv --app SplunkEnterpriseSecuritySuite
splunkctl lookups update assets_by_str.csv --file assets.csv \
    --app SplunkEnterpriseSecuritySuite --yes
```

### Detection rule lifecycle

```bash
# Create, test, enable:
splunkctl rules create --name 'Failed Logins' \
    --search 'index=main sourcetype=auth action=failure | stats count by user' \
    --cron '*/15 * * * *' --actions email --yes
splunkctl search run 'index=main sourcetype=auth action=failure | stats count by user'
splunkctl rules enable 'Failed Logins' --yes
splunkctl rules history 'Failed Logins'
```

### Export a dashboard for version control

```bash
splunkctl dashboards export my_dashboard --out dashboards/my_dashboard.xml
```

### Detection-as-code

```bash
# Export all rules to YAML, version control them
splunkctl rules export --path detections.yml
# Export specific rules
splunkctl rules export --path detections.yml --name 'Brute Force' --name 'C2 Beacon'
# Import into another instance (dry-run first)
splunkctl rules import --path detections.yml
splunkctl rules import --path detections.yml --yes
# Import without updating existing rules
splunkctl rules import --path detections.yml --no-update --yes
# Machine-readable dry-run diff, to verify programmatically before --yes
splunkctl rules import --path detections.yml --json
```

`import --json` (dry-run only, apply path is unaffected) emits a full,
untruncated diff array on stdout instead of applying anything: one
object per rule, `{"name", "action", "changes": [{"field", "old",
"new"}], "reason"}`. `action` is `create` | `update` | `unchanged` |
`skip`; `reason` is present only when `action` is `skip`; `old` is
`null` for `create`; `changes` is `[]` for `unchanged` and `skip`.

### Parsers-as-code

```bash
# Export props/transforms for version control
splunkctl parsers export --path parsers.yml
# Import into another instance (dry-run shows diff)
splunkctl parsers import --path parsers.yml
splunkctl parsers import --path parsers.yml --yes
```

### Upload data from laptop

```bash
# Ingest threat intel, logs, or sample data remotely
splunkctl search upload --path threats.csv --index threat_intel \
    --sourcetype csv --yes
splunkctl search upload --path firewall.log --yes
```

### Bulk lookup update

```bash
splunkctl lookups download hosts.csv --app search --out hosts.csv
# Edit hosts.csv locally...
splunkctl lookups update hosts.csv --file hosts.csv --app search --yes
```

### Wire an automatic lookup (upload -> define -> auto -> enrich)

```bash
# 1. Upload the table file
splunkctl lookups upload threat_indicators.csv --file threat_indicators.csv --yes

# 2. Define: bind a name to it (or --collection for a KV store-backed one)
splunkctl lookups define threat_intel --file threat_indicators.csv --yes

# 3. Auto: wire the definition onto every event of a sourcetype
splunkctl lookups auto threat_intel --sourcetype firewall_logs \
    --input dest_ip:ip --output threat_level --yes

# 4. Verify: events of that sourcetype now carry threat_level, no
# `| lookup` needed in the search
splunkctl search oneshot 'sourcetype=firewall_logs | table dest_ip threat_level' --limit 10

# Confirm the written stanzas directly if there's no live traffic yet:
splunkctl conf get transforms threat_intel
splunkctl conf get props firewall_logs
```

### Check index health

```bash
splunkctl indexes list --json \
    | jq '.[] | {name, totalEventCount, currentDBSizeMB}'
```

### User and role audit

```bash
splunkctl users list --json | jq '.[] | {name, roles, email}'
splunkctl users roles --json | jq '.[] | {name, capabilities}'
```

### Periodic access recertification (RBAC attestation)

```bash
# Export the full users x roles x capabilities x index-restrictions view
# for a compliance sign-off, one row per user, transitively aggregated:
splunkctl audit rbac --format csv --out recert-$(date +%Y%m).csv

# Same, role-centric — one row per role, for reviewing a role definition
# rather than who holds it:
splunkctl audit rbac --roles-only --json | jq '.[] | select(.capabilities | contains("admin_all_objects"))'

# Pair with a change-audit slice over the same window, for "did anyone
# touch a role/user between recertifications":
splunkctl audit changes --since -30d --action edit_roles --json
splunkctl audit changes --since -30d --object-type account --json
```

### Discover data sources

```bash
splunkctl search oneshot '| metadata type=sourcetypes index=*' --limit 500
splunkctl search oneshot '| metadata type=sources index=main' --limit 100
```

## SPL tips

| Pattern | Example |
|---|---|
| Time range | `--earliest -24h --latest now` |
| Stats | `index=main \| stats count by sourcetype` |
| Table | `index=main \| table _time host source message` |
| Dedup | `index=main \| dedup host` |
| Where | `index=main \| where count > 10` |
| Eval | `index=main \| eval dur=end-start` |
| Timechart | `index=main \| timechart span=1h count by source` |
| Lookup | `\| inputlookup my_lookup.csv` |
| Generate | `\| makeresults count=10 \| eval x=random()` |
| REST | `\| rest /services/server/info` |
| Metadata | `\| metadata type=sources index=main` |
| Tstats | `\| tstats count where index=main by sourcetype` |
| Rex | `\| rex field=_raw "code=(?<code>\d+)"` |

## Error handling

- **Diagnostics**: run `splunkctl doctor` to check everything at once
- **Connection errors**: run `splunkctl config test` to verify auth
- **Timeout**: increase with `--timeout 120`
- **SSL errors**: SSL verification is off by default. Use `--verify` during
  `config init` to enable certificate validation for production.
- **Not found**: commands print `Error: ...` to stderr and exit 1
- **Dry-run block**: add `--yes` to apply mutations
- **Permission denied**: check user roles with `splunkctl users get <name>`
- **Debug**: add `--debug` to see full HTTP request/response logs

### JSON error envelope

Errors follow the same dual-output rule as data: piped stdout or `--json`/
`--format json` prints one JSON line to stderr instead of `Error: ...`
text — `jq`-able, no text-scraping needed — while a TTY (or an explicit
`--format table`/`csv`/`jsonl`) keeps human text:

```json
{"error": {"kind": "auth", "http_status": 401, "message": "Authentication failed: Login failed."}}
```

- `kind` — a typed failure category (see table below). `message` is the
  same text that would appear after `Error: ` in non-JSON mode.
- `http_status` — the HTTP status code when the failure came straight from
  a REST call; `null` for non-HTTP failures (connection, timeout) and for
  app-level lookups that resolve a name locally without surfacing a raw
  status code (e.g. `rules get <missing-name>` reports `kind: not_found`
  with `http_status: null`).
- Exit code is unchanged (`1`); stdout stays empty/`[]` per the usual
  empty-result contract. Non-JSON formats are unaffected — same `Error:
  ...` text as always.

| kind | meaning |
|---|---|
| `auth` | 401 — authentication failed (bad credentials/token) |
| `permission` | 403 — authenticated but not authorized |
| `not_found` | 404, or an app-level lookup miss (e.g. unknown rule name) |
| `conflict` | 409 — e.g. name already exists |
| `http` | any other HTTP error status |
| `connection` | socket/SSL/DNS failure — Splunk unreachable |
| `timeout` | request timed out |
| `usage` | reserved for app-level argument validation — not yet emitted |
| `error` | fallback for unclassified app errors |

Recipe: `splunkctl rules get my-rule --json 2>&1 1>/dev/null | jq -R 'fromjson? // empty | .error.kind'`
to branch on failure type without parsing text. Use the `-R`/`fromjson?`
form, not `jq -r .error.kind` — stderr can carry advisory lines (a `--yes`
path's `Applying: ...` banner, `output.info` lines, dry-run warnings)
alongside the single-line JSON envelope, and those lines aren't JSON
themselves.

## Output piping

```bash
# JSON to jq
splunkctl rules list --json | jq '.[] | .name'

# CSV to file
splunkctl indexes list --format csv --out indexes.csv

# JSONL for streaming
splunkctl search export 'index=main' --format jsonl > events.jsonl

# Field projection
splunkctl users list --fields name,roles

# Alternate config
splunkctl -c /path/to/other.yaml config test
```
