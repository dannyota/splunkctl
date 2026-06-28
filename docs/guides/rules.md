# Detection rules

> Stub — will be filled when the `rules` command group is implemented.

## Commands

```bash
splunkctl rules list                      # list all saved searches
splunkctl rules get <name>                # get rule details + SPL
splunkctl rules create -f rule.yaml       # create from YAML (--dry-run)
splunkctl rules update <name> -f rule.yaml  # update rule (--dry-run)
splunkctl rules delete <name>             # delete rule (--dry-run)
splunkctl rules enable <name>             # enable scheduling (--dry-run)
splunkctl rules disable <name>            # disable scheduling (--dry-run)
splunkctl rules history <name>            # run history
```
