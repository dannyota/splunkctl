# Live smoke coverage gaps

Every non-SOAR leaf in `docs/commands.json` must have a script invocation or
an entry below. The pytest coverage guard also rejects stale entries.

CIM install, update, acceleration enable/rebuild and uninstall require `CIM_TGZ`.
KV document operations require a ready KV store; built-in model reads require a model.

- `alerts get`: No fired-alert fixture; the test rule is unscheduled.
- `auth login`: Authentication/session changes are outside this live smoke test.
- `auth logout`: Authentication/session changes are outside this live smoke test.
- `auth status`: Authentication/session changes are outside this live smoke test.
- `completion`: Local shell setup; no live Splunk behavior.
- `config init`: Would replace the throwaway connection profile.
- `config use`: Would change the active profile during the run.
- `es correlations disable`: ES is absent; no owned correlation rule.
- `es correlations enable`: ES is absent; no owned correlation rule.
- `es correlations get`: ES is absent; only the group list refusal is checked.
- `es notables get`: ES is absent; no notable fixture.
- `es notables update`: ES is absent; no notable fixture.
- `es threat-intel delete`: ES is absent; no threat-intelligence fixture.
- `es threat-intel upload`: ES is absent; no threat-intelligence collection.
- `mcp install`: Writes local .mcp.json configuration; not a SIEM command workflow.
- `mcp serve`: Starts a protocol server; not a SIEM command workflow.
- `server serverclasses get`: No serverclass fixture exists on standalone Splunk.
- `server serverclasses reload`: No create verb for an owned serverclass; cannot safely reload others.
- `server tokens create`: Requires enabled token authentication; does not change authentication settings.
- `server tokens revoke`: No token fixture is issued.
- `soar *`: requires a SOAR instance; see [docs/design/soar-api.md](../../docs/design/soar-api.md).

Monitor child-path acceptance and CIM acceleration enablement through `conf set`
have not been verified against a server. CIM retains upstream app/model names;
other named fixtures use `sc_live_`.
