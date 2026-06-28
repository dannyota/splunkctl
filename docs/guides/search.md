# Search

> Stub — will be filled when the `search` command group is implemented.

## Commands

```bash
splunkctl search run '<SPL>'              # sync search, print results
splunkctl search export '<SPL>'           # streaming export (large results)
splunkctl search oneshot '<SPL>'          # quick one-off search
splunkctl search jobs                     # list running/recent jobs
splunkctl search job <sid>                # get job status + results
splunkctl search cancel <sid>             # cancel running job
```

## Options

- `--earliest` / `--latest` — time range
- `--limit` — max results
- `--app` — app context
- `--format` — output format (table, json, csv, jsonl)
