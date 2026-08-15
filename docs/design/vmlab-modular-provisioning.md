# Modular vmlab provisioning and SSE data design

## Purpose

Make the VMware lab installable and recoverable one stage at a time. A failed
product or data step must not require deleting either VM. The lab must also
provide recent, repeatable Splunk Security Essentials (SSE) sample events for
testing `splunkctl` before using it against production systems.

## Scope

The lab remains two RHEL 9 VMware Workstation VMs:

- SIEM at `100.65.1.10`, running Splunk Enterprise 10.4.2 and SSE 3.8.3.
- SOAR at `100.65.1.11`, running Splunk SOAR 8.6.0.

Installer packages remain local, pinned, and ignored by Git. Credentials remain
in the ignored `config.local.env` file.

## Modular commands

Each command has one responsibility and can be rerun safely:

- `check-lab.sh` validates host commands, VMware NAT, artifacts, VM state,
  addresses, ports, storage, memory, and configuration.
- `build-rhel-vm.sh` creates one base VM. It continues to refuse to overwrite an
  existing VM directory.
- `install-splunk.sh` installs or verifies Splunk Enterprise on an existing SIEM
  VM.
- `install-sse.sh` installs or upgrades the pinned SSE package on an existing
  Splunk instance.
- `prepare-sse-data.py` reads SSE's `SampleDataList.csv`, transforms every listed
  dataset, and writes validated import batches without modifying the vendor app.
- `import-sse-data.sh` creates the lab index and imports prepared batches. Its
  `--clear-existing` option clears only prior lab-owned SSE event data first.
- `install-soar.sh` installs or resumes SOAR on an existing VM.
- `verify-lab.sh` checks VM reachability, versions, authentication, services,
  endpoints, SSE installation, imported event counts, and timestamp ranges.
- `provision-lab.sh` orchestrates the commands and skips stages whose actual
  postconditions already hold.

The scripts determine completion from product state and API checks rather than
from marker files alone. A failed stage reports its rerun command.

## SSE installation

`config.env` defines the pinned `splunk-security-essentials_383.tgz` artifact.
`install-sse.sh` copies it to the SIEM VM, installs it through Splunk's supported
app command, restarts Splunk only when required, and verifies app ID
`Splunk_Security_Essentials` at version 3.8.3.

## Recent-data transformation

SSE 3.8.3 lists 43 sample CSV datasets in `lookups/SampleDataList.csv`. The
transformer uses that manifest as the authoritative scope.

The transformer performs two passes:

1. Parse every recognized timestamp across all listed datasets and find one
   global latest timestamp.
2. Compute `delta = requested anchor - global latest` and apply that same delta
   to every recognized timestamp in every dataset.

The default anchor is the current UTC time at the start of preparation. Users
can supply an explicit UTC anchor for reproducible tests. The common delta
preserves ordering, gaps, durations, and relationships across files. Each file
must not receive its own delta.

Supported fields include epoch seconds, ISO 8601 values, SSE's US-formatted
datetimes, secondary timestamp fields, and timestamp values embedded in
structured event content. The transformer preserves each value's precision,
timezone style, and representation where possible. It recomputes derived
`date_*` fields from the shifted primary event time. Non-time values are not
changed. Intentionally anomalous historical timestamps remain anomalous because
they receive the same delta as all other timestamps.

The transformer fails closed when a field classified as temporal contains an
unsupported non-empty format. Its dry-run report includes:

- dataset and row counts;
- recognized timestamp fields and formats;
- original and shifted global ranges;
- the chosen anchor and delta;
- unsupported values, without writing import data.

Validation requires unchanged dataset and row counts, unchanged duration
between the global minimum and maximum, monotonic per-field shifts, and a
shifted global latest timestamp equal to the requested anchor within the source
precision.

## SIEM import and reset

The importer writes all transformed events to the dedicated `sse_lab` index
through Splunk HTTP Event Collector (HEC). Each event receives:

- an exact HEC event time;
- `source=sse:<dataset filename>`;
- a stable dataset-specific sourcetype;
- the transformed CSV fields as structured event content;
- a lab import identifier for verification.

The importer creates and owns its HEC token and `sse_lab` index. It batches
requests, checks HEC acknowledgements or responses, and compares indexed counts
with prepared counts before reporting success.

`--clear-existing` is explicit and destructive only within the lab-owned scope.
It clears event data in `sse_lab` and replaces generated staging data. It never
clears `_internal`, `_audit`, other user indexes, SSE's vendor lookup files,
Splunk configuration, or app state. `reset` is a convenience operation equal to
prepare plus import with `--clear-existing`.

## SOAR compatibility fix

SOAR 8.6 sets `/home/soar` to mode `0700`. The current installer incorrectly
changes into `/home/soar/splunk-soar` as `labadmin` before switching users. The
fixed command changes directory only after `sudo -u soar`, so both initial and
resumed installs run with the correct ownership boundary.

The SOAR step also treats prepare, install, firewall, media cleanup, password
configuration, and web verification as separate postconditions. Rerunning the
script resumes at the first incomplete postcondition.

## Error handling and safety

- No script deletes a VM directory.
- Existing VMs are started when stopped and reused when reachable.
- Destructive data reset requires `--clear-existing` or the explicit `reset`
  command and prints the exact `sse_lab` target before action.
- Artifact versions and app IDs are verified before copying or installing.
- Temporary and generated data use a lab-owned directory and are replaced
  atomically.
- Passwords and HEC tokens are not printed.
- Partial imports are detected by import ID and count validation.

## Tests and verification

Automated tests cover:

- timestamp formats present in all 43 SSE datasets;
- one global delta across datasets;
- secondary and embedded timestamps;
- derived `date_*` fields;
- historical anomaly preservation;
- unchanged row counts and time spans;
- dry-run behavior and unsupported formats;
- reset target guards;
- idempotent stage detection and SOAR command ownership.

Live verification checks both products, SSE, authenticated logins, HEC import
counts, searchability of every dataset, the recent-time anchor, and safe repeat
execution without VM recreation.

## User documentation

`installers/vmlab/README.md` becomes the lab runbook. It documents prerequisites,
pinned artifacts, configuration, topology, standalone commands, full
provisioning, rerun behavior, SSE timestamp semantics, import/reset examples,
credentials, endpoints, verification, and failure recovery.
