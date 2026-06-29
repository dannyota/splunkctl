# Apps

Splunk's detection and enrichment capabilities live in apps --
Technology Add-ons (TAs) for data normalization, security content packs
like Splunk Enterprise Security, and custom apps with org-specific
detections. Managing these remotely lets you deploy, update, and audit
apps across instances without SSH or manual Web UI clicks.

## Commands

```bash
splunkctl apps list                           # list installed apps
splunkctl apps get SplunkForwarder            # get app details
splunkctl apps install --path ./app.spl --yes # install from local file
splunkctl apps install --path ./app.tar.gz \
    --force --yes                             # force overwrite
splunkctl apps uninstall my_app --yes         # uninstall
splunkctl apps update my_app --enabled \
    --visible --yes                           # enable + show
splunkctl apps update my_app --disabled \
    --hidden --yes                            # disable + hide
splunkctl apps reload --yes                   # reload all apps
```

## Remote install

`apps install --path` uploads a local `.spl` or `.tar.gz` package to
the remote Splunk instance via the Web UI handler. No SSH, no SCP, no
server filesystem access needed -- push from your laptop to any
reachable instance.

Use `--force` to overwrite an existing app of the same name.

## Practical examples

```bash
# Deploy a TA for Windows event log normalization
splunkctl apps install \
    --path ./Splunk_TA_windows-8.9.0.spl --yes

# Upgrade a security content pack (force overwrite)
splunkctl apps install \
    --path ./DA-ESS-ContentUpdate-4.29.0.spl --force --yes

# Disable an app during an incident (stop its scheduled searches)
splunkctl apps update SplunkEnterpriseSecuritySuite \
    --disabled --yes

# Re-enable after the incident
splunkctl apps update SplunkEnterpriseSecuritySuite \
    --enabled --yes

# Audit installed apps -- pipe JSON to jq for scripting
splunkctl apps list --json | jq '.[] | {name, version, disabled}'

# Reload all app configs after a bulk change
splunkctl apps reload --yes
```

## Notes

- App install may require a Splunk restart to activate new modular
  inputs or scripted lookups. The CLI does not restart automatically.
- `--force` is required when reinstalling or upgrading an app that
  already exists on the instance.
