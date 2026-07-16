# Install

## From GitHub

```bash
pip install git+https://github.com/dannyota/splunkctl
```

This pulls the forked SDK (`splunkctl` branch) automatically as a
dependency.

## From source

```bash
git clone https://github.com/dannyota/splunkctl.git
cd splunkctl
pip install -e .
```

## Verify

```bash
splunkctl --version
splunkctl doctor           # check connection + auth + permissions
```

## Shell completion

Tab completion for commands, options, and arguments. Add the eval line to
your shell profile:

**Bash** (`~/.bashrc`):

```bash
eval "$(splunkctl completion bash)"
```

**Zsh** (`~/.zshrc`):

```bash
eval "$(splunkctl completion zsh)"
```

**Fish** (`~/.config/fish/config.fish`):

```fish
splunkctl completion fish | source
```

Restart your shell (or `source` the profile) to activate.

## Requirements

- Python 3.13+
- A running Splunk Enterprise instance with the REST API enabled (port 8089)
