<!-- summary: This project and Splunk's own splunkctl share an executable name and a config path but nothing else; here is how they differ and how to run both. -->

# Relationship to Splunk's splunkctl

This project started in June 2026. In August 2026 Splunk Inc. published an unrelated, experimental Go CLI with the same name at [`splunk/splunkctl`](https://github.com/splunk/splunkctl). The two tools share a name and nothing else. This project is not a fork, wrapper, or replacement for Splunk's tool, and it focuses on SOC workflows across Splunk Enterprise, Enterprise Security, and Splunk SOAR rather than on general Splunk administration.

## Comparison

| | This project (`pip install splunkctl`) | `splunk/splunkctl` |
|---|---|---|
| Language and install | Python package from PyPI | Go binary from GitHub Releases |
| Products | Splunk Enterprise, Enterprise Security, Splunk SOAR | Splunk Enterprise, Splunk Cloud Platform |
| Authentication | Username and password by default, bearer token, optional browser SAML SSO | Bearer token only |
| Profiles | Named profiles for dev, UAT, and production | One host and token |
| Mutations | Dry run by default, `--yes` to apply | Prompt, or `CONFIRMATION_REQUIRED` for non-interactive callers; `--read-only` |
| AI agents | Built-in MCP server plus `commands --json` | `schema` JSON and agent skill files; pairs with Splunk's MCP server |
| Configuration as code | `state pull`, `diff`, and `push` with change reports | Not provided |
| Command surface | SOC-focused groups (see the [command reference](../commands/README.md)) | Generated from Splunk's REST definitions, including cluster and licenser internals |
| Config file | `~/.splunkctl/config.yaml` with profiles | `~/.splunkctl/config.yaml` with flat `host` and `token` keys |
| Support | Community project, Apache-2.0 | Experimental, Apache-2.0, pull requests not accepted |

Both tools install an executable named `splunkctl` and read the same configuration path.

## Coexistence

- **Executable name.** This package installs both `splunkctl` and `splunkctl-py`. If Splunk's binary shadows `splunkctl` on your `PATH`, call `splunkctl-py` instead.
- **Config file.** If `~/.splunkctl/config.yaml` holds Splunk's flat `host`/`token` format, this tool leaves it untouched and keeps its own profiles in `~/.splunkctl/profiles.yaml`. It prints one notice on standard error when that happens, and `splunkctl doctor` reports which file is in use. Pass `--config FILE` to choose a file explicitly; an explicit file in Splunk's format is refused rather than redirected.
- **Credentials are not shared.** The two tools do not read each other's settings. Run `splunkctl config init` once to set up this tool.

## Check which tool you are running

```bash
splunkctl --version
```

This project prints `splunkctl, version X.Y.Z`. If the output looks different, `splunkctl` on your `PATH` is Splunk's binary; use `splunkctl-py`.

## See also

- [Install](install.md)
- [Configure](configure.md)
- [Diagnose a connection](doctor.md)
