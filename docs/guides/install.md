<!-- summary: Install splunkctl from PyPI on Python 3.12 or newer, add the browser extra when you need it, and verify the install with doctor. -->

# Install

When to use: you are putting splunkctl on a workstation, a jump host, or a CI runner for the first time, or adding an optional component to an existing install.

## Prerequisites

- Python 3.12 or newer with `pip`.
- Network access from this machine to the Splunk REST API (port 8089 by default) and, for SOAR, to the SOAR REST port (8443 by default).
- A Splunk account. `splunkctl doctor` reports which permissions it has; each command needs the capabilities its action requires.

## Synopsis

```text
python -m pip install splunkctl
python -m pip install 'splunkctl[browser]'
python -m pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
splunkctl --version
splunkctl config init [--profile NAME] [--soar]
splunkctl doctor [--strict]
splunkctl completion <bash|zsh|fish>
```

## Workflow

### Install from PyPI

```bash
python -m pip install splunkctl
splunkctl --version
```

Expected result: `splunkctl, version X.Y.Z`. If the output looks different, Splunk's own `splunkctl` binary is ahead of this package on your `PATH`; run `splunkctl-py` instead (see [Relationship to Splunk's splunkctl](splunk-cli.md)).

Core commands work with the upstream Splunk SDK that `pip` installs as a dependency.

### Add optional components

Browser SAML login (`splunkctl auth login`) needs Playwright:

```bash
python -m pip install 'splunkctl[browser]'
```

See [Log in through browser SAML](auth.md) for the browser setup that follows.

### Install from source

```bash
git clone https://github.com/dannyota/splunkctl.git
cd splunkctl
python -m pip install -e .
```

For a development install with test tooling, see [CONTRIBUTING.md](https://github.com/dannyota/splunkctl/blob/master/CONTRIBUTING.md).

### Configure and verify

```bash
splunkctl config init
splunkctl doctor
```

`config init` prompts for host, port, username, and password and writes `~/.splunkctl/config.yaml` on this machine (not guarded). `doctor` checks the connection, authentication, server health, and your permissions. Expected result: every check passes; `--strict` turns warnings into exit 1 for CI. Add SOAR afterwards with `splunkctl config init --soar` and `splunkctl soar test`. Profiles and environment variables are covered in [Configure](configure.md).

### Enable shell completion

Add the matching line to your shell profile, then restart the shell or source the file.

Bash (`~/.bashrc`):

```bash
eval "$(splunkctl completion bash)"
```

Zsh (`~/.zshrc`):

```bash
eval "$(splunkctl completion zsh)"
```

Fish (`~/.config/fish/config.fish`):

```bash
splunkctl completion fish | source
```

## Troubleshooting

- `pip` reports no matching distribution: your Python is older than 3.12. Check with `python --version` and install a newer interpreter.
- `splunkctl --version` prints something other than `splunkctl, version X.Y.Z`: another `splunkctl` is first on `PATH`; use `splunkctl-py`.
- `doctor` fails on connection: confirm host and port, and that the REST port is reachable from this machine (`curl -k https://HOST:8089/services/server/info`).
- `doctor` reports a Splunk-format config file: `~/.splunkctl/config.yaml` belongs to Splunk's CLI; run `splunkctl config init --path ~/.splunkctl/profiles.yaml` or see [Relationship to Splunk's splunkctl](splunk-cli.md).

## See also

- [Configure](configure.md)
- [Diagnose a connection](doctor.md)
- [Set up the MCP server](mcp.md)
- [Relationship to Splunk's splunkctl](splunk-cli.md)
