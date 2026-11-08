# Splunk SIEM and SOAR VMware lab

This lab runs Splunk Enterprise and Splunk SOAR on separate RHEL 9 virtual
machines. Every stage can be rerun. Existing VMs are reused and are never
deleted by the provisioning scripts.

## Topology

| Role | Default VM path | Address | Product |
|---|---|---|---|
| SIEM | `$VM_BASE_DIR/siem` | `100.65.1.10` | Splunk Enterprise 10.6.1.1 and Splunk Security Essentials 3.8.3 |
| SOAR | `$VM_BASE_DIR/soar` | `100.65.1.11` | Splunk SOAR 8.8.0.282 |

The VMs use VMware Workstation NAT through `vmnet8`. The default gateway is
`100.65.1.2`.

RHEL is required inside both VMs. It is not required as the host operating
system. The RHEL DVD also provides offline packages during SOAR installation.

## Prepare an Ubuntu 24.04 host

Use one Ubuntu 24.04 LTS Linux host for VMware Workstation Pro 26, the
optional [Keycloak lab](../../lab/keycloak/README.md), and splunkctl itself.
No bridged networking or port forwards are needed. All access is local to
this host and its NAT network.

| VM | vCPU | RAM | Thin disk |
|---|---|---|---|
| SIEM | 4 | 4 GB | 150 GB |
| SOAR | 4 | 8 GB | 150 GB |

Use a host with at least 16 GB RAM and room for both disks under
`$VM_BASE_DIR` (default `~/vmware`). Thin disks grow as data is written.
SOAR 8.x evaluation guidance specifies 4 cores, 8 GB RAM (16 GB recommended)
and 500 GB disk, varying with data volume. This small lab uses 150 GB thin
disks; increase disk capacity for workloads that need the published minimum.
SOAR runs in a VM and cannot run in Docker or Podman.

Install host packages:

```bash
sudo apt update
sudo apt install build-essential linux-headers-$(uname -r) \
  xorriso openssh-client netcat-openbsd curl openssl python3
# Optional Keycloak IdP:
sudo apt install podman podman-compose
```

Download `VMware-Workstation-Full-<version>.x86_64.bundle` for Workstation Pro
26 from the [Broadcom support portal](https://support.broadcom.com/) using a
free account. Install the downloaded bundle:

```bash
sudo sh VMware-Workstation-Full-<version>.x86_64.bundle
sudo vmware-modconfig --console --install-all
sudo systemctl restart vmware
```

Replace `<version>` with the downloaded version. The reference lab used
26.0.0 build 25388281. Rerun `vmware-modconfig` after kernel updates.

### Secure Boot

With Secure Boot enabled, sign both `vmmon` and `vmnet`, as described in
[Broadcom KB 315309](https://knowledge.broadcom.com/external/article/315309).
Create a signing key once in a private directory outside this repository:

```bash
mkdir -p ~/.local/share/vmware-signing
cd ~/.local/share/vmware-signing
umask 077
openssl req -new -x509 -newkey rsa:2048 -keyout MOK.priv \
  -outform DER -out MOK.der -nodes -days 36500 \
  -subj "/CN=VMware Module Signing/"
sudo /usr/src/linux-headers-$(uname -r)/scripts/sign-file \
  sha256 MOK.priv MOK.der "$(modinfo -n vmmon)"
sudo /usr/src/linux-headers-$(uname -r)/scripts/sign-file \
  sha256 MOK.priv MOK.der "$(modinfo -n vmnet)"
sudo mokutil --import MOK.der
```

Install `mokutil` if needed (`sudo apt install mokutil`). Reboot and enroll
the key in the MOK manager. Keep the key and re-sign both modules after every
module rebuild, then restart VMware.

### Configure vmnet8

In a desktop session, run `sudo vmware-netcfg`. Select VMnet8 with NAT and
DHCP enabled, subnet `100.65.1.0`, mask `255.255.255.0`, and NAT Settings
gateway `100.65.1.2`. Set the DHCP range to `100.65.1.128` through
`100.65.1.254`; the static VM addresses sit below it. The host vmnet8 address
is `100.65.1.1/24`.

Use the Virtual Network Editor; editing `/etc/vmware/networking` alone is
not sufficient. `/etc/vmware/vmnet8/nat/nat.conf` must have `[host]` values
`ip = 100.65.1.2` and `netmask = 255.255.255.0`. `check-lab.sh` verifies the
gateway there. For another subnet, override `NAT_GATEWAY`, `SIEM_IP`, and
`SOAR_IP` and update the addresses in Keycloak's `.env`.

Routine use needs no host root access. Scripts use `labadmin` and `sudo`
inside each VM. From the repository root:

```bash
cd installers/vmlab
./check-lab.sh --only both
```

Preflight reports missing installers until the next step is complete.

## Get the installers

From `installers/vmlab`, run:

```bash
./fetch-installers.sh                 # both roles
./fetch-installers.sh --only siem     # RHEL, Splunk and SSE
./fetch-installers.sh --only soar     # RHEL and SOAR
./fetch-installers.sh --check         # verify only, never download
```

The script downloads public Splunk Enterprise and SOAR installers with no
login, verifies pinned checksums, and leaves existing files untouched.
Missing or mismatched artifacts produce a nonzero exit and a summary.
Downloads use `.part` files, which are removed on checksum failure.

Download these two files manually into `installers/` (Git ignores them):

- `rhel-9.8-x86_64-dvd.iso`: [Red Hat downloads](https://developers.redhat.com/products/rhel/download),
  using a Red Hat account and the free Red Hat Developer Subscription.
- `splunk-security-essentials_383.tgz`: [Splunkbase app 3435](https://splunkbase.splunk.com/app/3435),
  release 3.8.3, using a Splunkbase login. It lists Splunk 10.6 as compatible.

Public pins are `splunk-10.6.1.1-b2ae2962645c.x86_64.rpm` and
`splunk_soar-unpriv-8.8.0.282-81cb9deb-el9-x86_64.tgz` (2.2 GB).
SOAR Community is free with 100 actions/day, one tenant and five open cases.
SOAR 8.8.0 supports RHEL 9.7 or higher; both VMs here use RHEL 9.8.
The RHEL DVD supplies offline packages during SOAR installation.

Names, URLs and checksums are in `config.env`, checked on 2026-11-08.
Override them together through exported variables or `config.local.env`
when using other artifacts. `INSTALLERS_DIR` can point to another directory.
Rerun `./fetch-installers.sh --check` and `./check-lab.sh` after downloads.

## Credentials

Put lab credentials in the ignored `config.local.env` file:

```bash
LAB_PASSWORD='<set-a-private-lab-password>'
SPLUNK_ADMIN_PASSWORD="$LAB_PASSWORD"
```

This is a lab-only password. Do not reuse it in production.

The accounts are:

- RHEL: `labadmin`
- Splunk Enterprise: `admin`
- Splunk SOAR: `soar_local_admin`

The timezone defaults to `UTC`. The reusable SSH key is
`$VM_BASE_DIR/.vmlab_key`. All other defaults are in `config.env`. Export a
setting before a command to override it without editing the file.

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
  --ram 8192 --cpu 4 --vnc-port 5902
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
`$VM_BASE_DIR/sse-data/`. The SSE app and its vendor lookup files are not
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
- generated files under `$VM_BASE_DIR/sse-data/`;
- the mode-`0600` token file `$VM_BASE_DIR/.sse_hec_token`.

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
SOAR commands change into `/home/soar/splunk-soar` only after switching to
the `soar` account, which is required because `/home/soar` has mode `0700`.

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

## Point splunkctl at the lab

Install splunkctl on this same host using the [install guide](../../docs/guides/install.md).
Configure the Splunk REST endpoint as `https://100.65.1.10:8089` and the SOAR
endpoint as `https://100.65.1.11:8443`. Set `verify: false` for these lab
profiles because the certificates are self-signed. For browser SAML login,
follow the optional [Keycloak guide](../../docs/guides/keycloak-lab.md).

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
`$VM_BASE_DIR/sse-data/` only when intentionally discarding prepared
batches; running `prepare` normally replaces that directory atomically.
