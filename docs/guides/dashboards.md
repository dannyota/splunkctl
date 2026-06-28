# Dashboards

> Stub — will be filled when the `dashboards` command group is implemented.

## Commands

```bash
splunkctl dashboards list                 # list dashboards
splunkctl dashboards get <name>           # get definition (XML/JSON)
splunkctl dashboards create -f dash.xml   # create from file (--dry-run)
splunkctl dashboards update <name> -f dash.xml  # update (--dry-run)
splunkctl dashboards delete <name>        # delete (--dry-run)
splunkctl dashboards export <name> -o file  # export to file
```

Uses raw REST (`/services/data/ui/views/`) — SDK gap.
