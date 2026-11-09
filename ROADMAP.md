# splunkctl — Roadmap

What is planned, what is out of scope, and the decisions behind both. The
shipped command surface is the generated
[command reference](docs/commands/README.md); release history is in
[CHANGELOG.md](CHANGELOG.md).

## Now

Nothing in progress.

## Out of scope

Not planned, as of the 2026-11-09 backlog review. Each item notes why;
reopen it only if that reason changes.

Auth-token minting, once listed here, shipped in v0.11.0 as
`server tokens create`.

- **ES governance surfaces** (incident-review settings, threat-intel
  framework): the lab has no Enterprise Security license to verify against.
- **Forwarder fleet / deployment-server writes**: reads and reload exist
  (`server serverclasses`, `server deployment`); serverclass and client
  writes were not chosen in the backlog review.
- **Workflow actions CRUD**: not chosen in the backlog review.
- **JSON `schemaVersion`**: would change the `--json` output contract.
- **SOAR app development**: owned by the official `soarapps` SDK.
  `soar apps install` and `uninstall` exist.
- **SOAR clustering, automation broker and multi-tenant**: not available
  on the single-node Community edition lab.
- **SOAR webhooks**: not chosen in the backlog review; not verified on
  the lab.
- **SOAR token minting**: REST cannot return a usable token plaintext.
- **SOAR label creation, backup and restore**: UI-only, or `phenv` only.
- **SOAR severity, status and CEF vocabulary writes**: platform admin
  settings; reads are enough for the CLI.

## Naming and coexistence with Splunk's splunkctl

Decision (2026-11-08): keep the `splunkctl` name and PyPI package. This
project predates Splunk's Go CLI of the same name
([`splunk/splunkctl`](https://github.com/splunk/splunkctl), first release
2026-09-09; this project's first release was 2026-06-29). The README states
that the two are unrelated, both tools can share `~/.splunkctl`, and this
package also installs a `splunkctl-py` executable for hosts that have both.

Revisit the rename plan if any of these happen:

- Splunk publishes a `splunkctl` package to PyPI or asks for the name.
- Splunk raises a trademark concern about the name.
- User reports show the name collision causing real confusion or breakage
  that the coexistence measures do not cover.

The rename plan, if triggered: rename package, executable, skill, MCP
registration, and config directory together; keep `splunkctl` on PyPI as a
migration shim that does not install a competing executable; ship an
explicit config import.

## History

Waves 1–34 (v0.1.0 to v0.9.0) built the SIEM command tree, the MCP server
and the SOAR arc; later releases hardened them against live Splunk 10.6 and
SOAR 8.8; browser SAML login, status and logout now pass on the current Keycloak lab with scripted SIEM setup. Per-release detail is in [CHANGELOG.md](CHANGELOG.md) and
[docs/changelog-archive.md](docs/changelog-archive.md).
