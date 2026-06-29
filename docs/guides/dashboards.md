# Dashboards

## Commands

```bash
splunkctl dashboards list                 # list dashboards
splunkctl dashboards list --app search    # filter by app
splunkctl dashboards get <name>           # get definition (XML)
splunkctl dashboards create --name new_dash --file dash.xml \
    --app search --yes
splunkctl dashboards update <name> --file updated.xml \
    --app search --yes
splunkctl dashboards delete <name> --app search --yes
splunkctl dashboards export <name> --out dash.xml
```

Uses the `Dashboard`/`Dashboards` entity classes from the SDK fork.
