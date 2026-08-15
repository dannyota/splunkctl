# Splunk SIEM and SOAR VMware lab

This lab runs Splunk Enterprise and Splunk SOAR on separate RHEL 9 virtual
machines. Every stage can be rerun. Existing VMs are reused and are never
deleted by the provisioning scripts.

## Topology

| Role | Default VM path | Address | Product |
|---|---|---|---|
| SIEM | `/home/danny/vmware/siem` | `100.65.1.10` | Splunk Enterprise 10.4.2 and Splunk Security Essentials 3.8.3 |
| SOAR | `/home/danny/vmware/soar` | `100.65.1.11` | Splunk SOAR 8.6.0.530 |

The VMs use VMware Workstation NAT through `vmnet8`. The default gateway is
`100.65.1.2`.

RHEL is required inside both VMs. It is not required as the host operating
system. The RHEL DVD also provides offline packages during SOAR installation.

## Pinned installers

Place these files in `installers/`. They are ignored by Git.

```text
rhel-9.8-x86_64-dvd.iso
splunk-10.4.2-33c3bf42cd73.x86_64.rpm
splunk-security-essentials_383.tgz
splunk_soar-unpriv-8.6.0.530-9513a88f-el9-x86_64.tgz
```

For the local SSE package:

```bash
cp -p /home/danny/Documents/ISOs/splunk-security-essentials_383.tgz \
  ../splunk-security-essentials_383.tgz
sha256sum /home/danny/Documents/ISOs/splunk-security-essentials_383.tgz \
  ../splunk-security-essentials_383.tgz
```

## Host requirements

- VMware Workstation Pro with `vmrun` and `vmware-vdiskmanager`
- `xorriso`, `ssh`, `scp`, `nc`, `curl`, `openssl`, and Python 3
- VMware NAT configured for gateway `100.65.1.2`
- Enough free space under `/home/danny/vmware/`

Routine use does not need host root access. The scripts use the `labadmin`
account and `sudo` inside each VM. Host administration may still be needed to
install VMware or change its NAT network.

Run the read-only preflight before changing the lab:

```bash
cd installers/vmlab
./check-lab.sh --only both
```

## Credentials

Put lab credentials in the ignored `config.local.env` file:

```bash
LAB_PASSWORD='Splunk@2026'
SPLUNK_ADMIN_PASSWORD="$LAB_PASSWORD"
```

This is a lab-only password. Do not reuse it in production.

The accounts are:

- RHEL: `labadmin`
- Splunk Enterprise: `admin`
- Splunk SOAR: `soar_local_admin`

All other defaults are in `config.env`. Export a setting before a command to
override it without editing the file.

## Full provisioning

```bash
./provision-lab.sh
./provision-lab.sh --only siem
./provision-lab.sh --only soar
./provision-lab.sh --only both --skip-data
```

For each selected role, the orchestrator:

1. Runs preflight checks.
2. Creates the VM only when its VMX file is missing.
3. Starts and reuses an existing stopped VM.
4. Installs or verifies each product stage.
5. Prepares and imports SSE data unless `--skip-data` is set.
6. Runs end-to-end verification.

If a VM directory exists without its expected VMX file, provisioning stops for
inspection. It does not overwrite the directory.

## Standalone stages

Run only the failed or changed stage. Product installation does not require a
VM rebuild.

### Build a missing base VM

```bash
./build-rhel-vm.sh --name siem --ip 100.65.1.10 \
  --ram 4096 --cpu 4 --vnc-port 5901
./build-rhel-vm.sh --name soar --ip 100.65.1.11 \
  --ram 6144 --cpu 4 --vnc-port 5902
```

`build-rhel-vm.sh` refuses an existing VM directory and does not stop or remove
that VM.

### Install or verify Splunk Enterprise

```bash
./install-splunk.sh --ip 100.65.1.10
```

The command checks the pinned RPM version, host settings, systemd service,
firewall, and web endpoint. It copies the RPM only when the installed version
does not match.

### Install or verify Splunk Security Essentials

```bash
./install-sse.sh --ip 100.65.1.10
```

The command verifies app ID `Splunk_Security_Essentials` and version `3.8.3`.
It skips a matching active installation.

### Prepare recent SSE sample data

```bash
./import-sse-data.sh prepare --dry-run
./import-sse-data.sh prepare
./import-sse-data.sh prepare --anchor 2026-08-15T12:00:00Z
```

SSE 3.8.3 lists 43 sample CSV datasets. Preparation reads that vendor manifest
as the exact scope and performs two passes:

1. Scan every recognized timestamp in all 43 datasets and find one global
   latest timestamp.
2. Calculate `delta = anchor - global latest` and apply that same delta to every
   recognized timestamp in every dataset.

The default anchor is current UTC at the start of preparation. One shared delta
preserves ordering, gaps, durations, cross-dataset relationships, and deliberate
historical anomalies. Each file does not receive its own delta.

The transformer handles SSE epoch, ISO 8601, US datetime, space-separated
datetime, and Active Directory generalized-time values. It also shifts
secondary and embedded timestamps, then recomputes derived `date_*` fields.
Non-time values are unchanged. A classified temporal field with an unsupported
non-empty value stops preparation.

Generated batches and `manifest.json` are written atomically under
`/home/danny/vmware/sse-data/`. The SSE app and its vendor lookup files are not
modified.

### Import, inspect, or reset SSE data

```bash
./import-sse-data.sh import
./import-sse-data.sh status
./import-sse-data.sh import --clear-existing
./import-sse-data.sh reset
./import-sse-data.sh reset --anchor 2026-08-15T12:00:00Z
```

The importer owns:

- the `sse_lab` index;
- the `sse-lab` HTTP Event Collector token;
- the `sse_lab_loader` Splunk app containing index, HEC, field, and sourcetype
  settings;
- generated files under `/home/danny/vmware/sse-data/`;
- the mode-`0600` token file `/home/danny/vmware/.sse_hec_token`.

Every event has an exact HEC time, `source=sse:<dataset filename>`, a stable
dataset sourcetype, `lab_dataset`, `lab_batch_id`, and `lab_import_id`.

Normal import does not clear data. It queries indexed batch counts, skips a
complete batch, and refuses a partial batch to prevent duplicates.

`--clear-existing` is explicit. It stops Splunk, clears event data only from
the literal `sse_lab` index, restarts Splunk, imports the prepared batches, and
verifies counts. `reset` prepares a new current anchor and then performs that
same scoped clear and import.

The reset never clears:

- `_internal`, `_audit`, `main`, or another user index;
- SSE vendor lookups or app state;
- Splunk configuration outside the lab loader app;
- either VM.

### Install or verify SOAR

```bash
./install-soar.sh --name soar --ip 100.65.1.11
```

The command checks version, service files, web, firewall, and authenticated REST
access before deciding whether installation work is needed. A partial install
resumes from extraction, offline dependency preparation, or product install.
SOAR commands change into `/home/soar/splunk-soar` only after switching to the
`soar` account, which is required because `/home/soar` has mode `0700`.

### Verify the lab

```bash
./verify-lab.sh --only both
./verify-lab.sh --only siem
./verify-lab.sh --only soar
./verify-lab.sh --only both --skip-data
```

SIEM verification checks the VM, SSH, Splunk version and service, authenticated
management API, web, SSE version, HEC health, import count, all 43 datasets, and
the latest-event anchor. SOAR verification checks the VM, SSH, product version,
authenticated REST API, and web endpoint.

## Endpoints

| Service | URL |
|---|---|
| Splunk Web | `http://100.65.1.10:8000` |
| Splunk management API | `https://100.65.1.10:8089` |
| Splunk HEC | `https://100.65.1.10:8088` |
| Splunk SOAR | `https://100.65.1.11:8443` |

## Recovery

Use the smallest command that owns the failed stage:

| Failure | Rerun |
|---|---|
| Host, NAT, artifact, or reachability check | `./check-lab.sh --only both` |
| Missing RHEL VM | `./build-rhel-vm.sh ...` for that role |
| Splunk install or service | `./install-splunk.sh --ip 100.65.1.10` |
| SSE app install | `./install-sse.sh --ip 100.65.1.10` |
| Timestamp classification | `./import-sse-data.sh prepare --dry-run` |
| Partial or unwanted lab data | `./import-sse-data.sh import --clear-existing` |
| New current data cycle | `./import-sse-data.sh reset` |
| SOAR preparation or install | `./install-soar.sh --name soar --ip 100.65.1.11` |
| Final state check | `./verify-lab.sh --only both` |

Do not delete a VM to retry a product or data stage. Remove generated
`/home/danny/vmware/sse-data/` only when intentionally discarding prepared
batches; running `prepare` normally replaces that directory atomically.
