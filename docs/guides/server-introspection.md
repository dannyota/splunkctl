<!-- summary: Inspect ingestion queues, indexing status and disk usage, and safely change runtime logging levels. -->

# Inspect ingestion and runtime logging

Read ingestion queue occupancy, indexer status and filesystem usage:

```bash
splunkctl --json server introspection queues
splunkctl --json server introspection indexer
splunkctl --json server introspection disk
```

Queue rows include current occupancy, maximum, unit, fill ratio and blocked status. A zero maximum produces a null ratio. Indexer rows include name, status, reason and average KB per second. Disk sizes are numbers in MB, with capacity, available, used and fill ratio. Missing fields, including filesystem type, become JSON nulls. Table and CSV cells for null values are blank.

These commands use the [Splunk introspection endpoints](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.0/introspection-endpoints/introspection-endpoint-descriptions) and `server/status/partitions-space`. Response mapping is covered by supplied Splunk 10.6.1.1 fixtures.

Inspect every logger, or fetch one component:

```bash
splunkctl server log-level get
splunkctl server log-level get TcpOutputProc
```

The unfiltered command requests `count=0` to avoid Splunk's default page limit. A component filter fetches that component directly.

Save the original level before changing it:

```bash
splunkctl server log-level get TcpOutputProc
splunkctl server log-level set TcpOutputProc DEBUG
splunkctl server log-level set TcpOutputProc DEBUG --yes
splunkctl server log-level get TcpOutputProc
splunkctl server log-level set TcpOutputProc INFO --yes
```

The final example assumes the original level was INFO. Restore the level you actually recorded. Accepted levels are DEBUG, INFO, WARN and ERROR, case-insensitive. Without `--yes`, the setter previews the before and after levels. An unchanged level skips the write.

Changes are runtime only. Restarting splunkd resets them, as verified by the fixture capture on Splunk 10.6.1.1. Persistent logging configuration requires `log-local.cfg`; see [Splunk's logging guide](https://help.splunk.com/en/splunk-enterprise/administer/troubleshoot/10.6/splunk-enterprise-log-files/enable-debug-logging).

See [Command reference: server](../commands/server.md).
