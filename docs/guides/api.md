<!-- summary: Read Splunk REST endpoints, discover fields, and preview or execute raw POST and DELETE requests. -->

# Call Splunk REST endpoints

Use `api` when a Splunk REST endpoint has no dedicated command. It uses the active Splunk profile and supports the normal output, projection and file options. `soar api` is deferred.

```bash
splunkctl api get server/info
splunkctl api get saved/searches --describe
splunkctl api get saved/searches --param count=10 --param search='name=sc_live_*'
splunkctl api post saved/searches --param name=sc_live_example --param 'search=| makeresults'
splunkctl api delete saved/searches/sc_live_example
```

POST and DELETE preview by default. Add `--yes` to execute. With [`--read-only`](read-only.md), previews still work, and `--yes` writes are refused.

## Paths and parameters

Paths can be service-relative (`server/info`), start with `/services/`, or include an explicit namespace (`/servicesNS/nobody/search/saved/searches`). Schemes, authorities, backslashes, control characters, query strings, fragments, dot segments and encoded path attacks are rejected before client creation.

Repeat `--param KEY=VALUE` to add request parameters. Duplicate values are preserved. `output_mode` is reserved for JSON output and cannot be overridden.

For POST without a body, parameters are form-encoded. With `--body` or `--body-file`, parameters go in the query string. The two body options are mutually exclusive; `--content-type` sets the body media type.

```bash
splunkctl api post some/endpoint --body-file payload.json --content-type application/json
```

Check the endpoint's documented body contract before applying a request. The CLI does not invent endpoint-specific fields or validate arbitrary request bodies for the server.

## Field discovery and output

`get PATH --describe` reads `PATH/_new` and extracts required and optional fields from `eai:attributes`. Splunk documents this metadata in [Using the REST API reference](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/9.1/introduction/using-the-rest-api-reference). Endpoints without supported discovery return a classified error.

Output defaults to JSON. Response dictionaries retain their envelope as one row in the output list; empty responses render as `[]`. The normal `--fields`, `--format` and `--out` options apply.

All requests carry `splunkctl/<version> (cmd=<command path>; requestID=<uuid4>)`. The command path excludes arguments, and each CLI invocation gets a fresh UUID. Browser headers are unchanged.
