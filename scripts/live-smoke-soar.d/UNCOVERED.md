# SOAR live smoke coverage gaps

Every SOAR leaf must be invoked or listed here, never both. Conditional
invocations print SKIPPED when the lab lacks a feature or an explicit opt-in.

- `soar apps install`: No owned test app package is supplied.
- `soar apps uninstall`: No owned test package; shipped apps must never be uninstalled.
- `soar playbooks sync`: Force-pulls an external SCM repository and changes unrelated content.
- `soar users create`: Deleted users remain inactive and accumulate.
- `soar users delete`: Deleted users remain inactive and accumulate; no disposable user is created.
- `soar users update`: No disposable user is created because deleted users remain inactive and accumulate.

The default runner spends no licensed actions. The no-op playbook calls no
`phantom.act()` or `phantom.prompt()`. `soar approvals get` and `respond` run
only with `LIVE_SOAR_APPROVALS=1`: the owned prompt playbook's prompt is an
action run and consumes one licensed action. Indicator records may remain after
fixture artifact deletion. Only the runner's dedicated case is closed.
