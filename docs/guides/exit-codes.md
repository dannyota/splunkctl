# Exit codes

splunkctl uses three exit codes. Scripts and CI pipelines can branch on
`$?` to distinguish success, operational errors, and bad invocations.

| Code | Meaning | Examples |
|------|---------|---------|
| 0 | Success | Command completed normally. |
| 1 | Command error | Auth failure, resource not found, API/network error, validation rejected by the server, runtime fault. |
| 2 | Usage error | Invalid argument, unknown option, missing required option, unrecognized subcommand. |

## Details

**Code 0** -- the command ran and produced its result. For mutation
commands with `--yes`, the change was applied. For dry-run previews
(the default), the preview was printed successfully.

**Code 1** -- the command understood what you asked for but could not
complete it. Common causes:

- Authentication or authorization failure (wrong credentials, expired
  token, insufficient role).
- Resource not found (no such index, saved search, dashboard, lookup,
  container, playbook).
- Server-side validation error (invalid cron, duplicate name, field
  constraint).
- Network or connectivity error (host unreachable, timeout, TLS
  handshake failure).

**Code 2** -- Click rejected the invocation before the command ran.
The arguments or options did not match the command's schema. Fix the
invocation and retry. This code is never produced by splunkctl's own
logic; it comes from the argument parser.

## Scripting example

```bash
splunkctl rules list --format json > rules.json
case $? in
  0) echo "OK";;
  1) echo "command failed" >&2; exit 1;;
  2) echo "bad usage" >&2; exit 2;;
esac
```
