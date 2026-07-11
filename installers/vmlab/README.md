# vmlab — reproducible Splunk SIEM + SOAR lab VMs

Scripted, unattended build of RHEL 9 VMs in **VMware Workstation** running
**Splunk Enterprise** (SIEM) and **Splunk SOAR** (on-prem), on the host's NAT
network. Fully headless — no clicking through the RHEL installer.

## Layout

| File | Role |
|---|---|
| `config.env` | Paths, network, credentials (override via env) |
| `rhel-ks.tmpl` | Parameterized RHEL 9 kickstart |
| `lib.sh` | Shared helpers (ssh/scp, OEMDRV build, waits) |
| `build-rhel-vm.sh` | Create a VM + unattended RHEL install |
| `install-splunk.sh` | Install Splunk Enterprise on a VM |
| `install-soar.sh` | Install Splunk SOAR on a VM |
| `provision-lab.sh` | Orchestrate the full two-VM lab |

## Prerequisites

- VMware Workstation Pro (`vmrun`, `vmware-vdiskmanager`), `xorriso`, `nc`, `openssl`
- Installer artifacts in `installers/` (gitignored): the RHEL 9 DVD ISO,
  the Splunk Enterprise RPM, and the SOAR unprivileged `.tgz`
  (filenames set in `config.env`)
- The VMware NAT subnet in `config.env` matches `/etc/vmware/vmnet8/nat/nat.conf`

## Usage

```bash
cd installers/vmlab
./provision-lab.sh                 # builds SIEM (100.65.1.10) + SOAR (100.65.1.11)
./provision-lab.sh --only siem     # one role only
```

Then, from the host (which routes directly to the NAT subnet):

- SIEM: `http://100.65.1.10:8000` — user `admin`, password from `config.local.env`
- SOAR: `https://100.65.1.11:8443` — user `soar_local_admin`, same password

## Design notes (hard-won)

- **Two VMs on purpose.** Splunk 10 ships an embedded PostgreSQL (5432/6432,
  backs SPL2 / Data Orchestration); SOAR's bundled PostgreSQL wants the same
  ports. Separating them keeps both fully featured with no port hacks.
- **Kickstart `network` must be one line** — pykickstart does not join
  backslash-continued lines (a stray `\` aborts the installer).
- **`zerombr`** avoids an interactive "initialize disk?" prompt on a blank disk.
- **OEMDRV auto-kickstart** — a small ISO labelled `OEMDRV` holding `ks.cfg`;
  Anaconda auto-detects it, so no boot-menu interaction is needed.
- **Offline SOAR deps** — the RHEL DVD is hot-attached (`vmrun
  connectNamedDevice`) and enabled as a local dnf repo; SOAR only needs a couple
  of packages (`compat-openssl11`, `initscripts`) beyond the base install.
- **VNC console** — each VM enables VMware's built-in VNC (`localhost:5901+`)
  for headless troubleshooting (`vncdo -s localhost::5901 capture out.png`).
- SELinux is **permissive** by default (lab simplification); set
  `SELINUX_MODE=enforcing` in `config.env` to harden.
