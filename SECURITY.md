# Security policy

## Reporting a vulnerability

Report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/dannyota/splunkctl/security/advisories/new)
for this repository. Do not open a public issue for a security problem.

Include the version (`splunkctl --version`), the command or MCP tool
involved, and steps to reproduce. You will get an acknowledgement within
seven days. Fixes ship as a patch release and are noted in
[CHANGELOG.md](CHANGELOG.md).

## Supported versions

Only the latest release on PyPI receives security fixes.

## What this tool handles

- Credentials live in `~/.splunkctl/` with mode `0600`, and cached browser
  sessions in a `0700` directory under it. `config show` redacts secrets.
- Every mutation is a dry run until `--yes` is passed. Under the MCP server,
  guarded tools require `yes=true`.
- TLS certificate verification is on unless a profile sets `verify: false`,
  which prints a warning.
- The MCP server defaults to stdio. The Streamable HTTP transport binds to
  loopback only and has no authentication of its own, so any local user who
  can reach the port can act with the server owner's Splunk access. Use it
  only on single-user hosts.
- SPL that contains write commands such as `outputlookup` or `collect` is
  refused by `search` and `soar ingest` unless `--yes` is passed.

## Scope

The lab provisioning scripts under `installers/` and `lab/` create
throwaway test environments with known defaults. They are not hardened and
must not be pointed at production systems.
