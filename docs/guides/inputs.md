# Data inputs

Manage monitor, TCP, UDP, script, and HTTP data inputs.

## Why it matters

Inputs control what data enters Splunk -- which log sources, at what
volume, into which index, with which sourcetype. Misconfigured inputs
cause parsing failures, license overages, and detection blind spots.

## Commands

```bash
splunkctl inputs list                         # list all inputs
splunkctl inputs list --kind monitor          # filter by type
splunkctl inputs get /var/log/syslog          # get input details
splunkctl inputs create --name /var/log/app.log \
    --kind monitor --index main \
    --sourcetype syslog --yes                 # create monitor input
splunkctl inputs update /var/log/app.log \
    --sourcetype json --yes                   # change sourcetype
splunkctl inputs delete /var/log/app.log --yes
splunkctl inputs enable /var/log/app.log --yes
splunkctl inputs disable /var/log/app.log --yes
```

## Input kinds

`monitor`, `tcp`, `udp`, `script`, `http` (HEC). Use `--kind` to filter
the list or specify the type when creating.

## Practical examples

### Onboard a new log source

```bash
# Monitor a new application log, route to a dedicated index
splunkctl inputs create --name /var/log/webapp/access.log \
    --kind monitor --index security_logs \
    --sourcetype access_combined --yes

# Accept syslog over TCP on port 5514
splunkctl inputs create --name 5514 \
    --kind tcp --index security_logs \
    --sourcetype syslog --yes
```

### Audit and lifecycle

```bash
# List all monitor inputs and their target indexes
splunkctl inputs list --kind monitor --json \
    | jq '.[] | {name, index, sourcetype, disabled}'

# Disable an input during maintenance (no data loss, just paused)
splunkctl inputs disable /var/log/old_app.log --yes

# Re-enable after maintenance
splunkctl inputs enable /var/log/old_app.log --yes

# Remove a decommissioned source
splunkctl inputs delete /var/log/retired_app.log --yes
```

### Verify data flow

```bash
# After creating an input, confirm events are arriving
splunkctl search run 'index=security_logs sourcetype=access_combined
    | head 5' --earliest -15m
```

## Notes

- Inputs are managed on the Splunk server via REST API; `splunkctl`
  does not need filesystem access to the server.
- Disabling an input stops ingestion but preserves the configuration.
  Use this for maintenance windows instead of deleting.
- TCP/UDP inputs bind to a port on the Splunk server. Confirm the port
  is not already in use before creating.
