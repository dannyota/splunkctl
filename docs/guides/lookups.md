# Lookups

> Stub — will be filled when the `lookups` command group is implemented.

## Commands

```bash
splunkctl lookups list                    # list lookup files + definitions
splunkctl lookups get <name>              # get lookup contents
splunkctl lookups upload <file>           # upload CSV (--dry-run)
splunkctl lookups download <name> -o file # download lookup
splunkctl lookups delete <name>           # delete lookup (--dry-run)
```

Uses raw REST (`/services/data/lookup-table-files/`) — SDK gap.
