# Modular vmlab Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the VMware SIEM and SOAR lab recoverable by stage, install SSE 3.8.3, and load all 43 SSE sample datasets into a lab-only Splunk index with one global shift to recent timestamps.

**Architecture:** Keep VM creation separate from product installation. Add an import pipeline with a standard-library Python transformer and small shell commands for app install, HEC configuration, scoped reset, import, and verification. Determine stage completion from VM and product state so reruns reuse `/home/danny/vmware/siem` and `/home/danny/vmware/soar`.

**Tech Stack:** Bash, Python 3 standard library, VMware Workstation `vmrun`, RHEL 9, Splunk Enterprise 10.4.2, Splunk Security Essentials 3.8.3, Splunk SOAR 8.6.0, Splunk HEC, pytest, Ruff, mypy, ShellCheck.

## Global Constraints

- Do not delete or recreate an existing VM.
- Keep installer packages, generated data, passwords, SSH keys, and HEC tokens out of Git.
- Use `sse_lab` as the only event-data reset target.
- Shift every supported timestamp in every SSE dataset by the same delta.
- Stop on unsupported values in fields classified as temporal.
- Use tests before implementation changes for each behavior.
- Run the live lab checks only after the local tests pass.

---

## Task 1: Pin the SSE artifact and centralize lab state

**Files:**

- Modify: `installers/vmlab/config.env:4-29`
- Modify: `installers/vmlab/lib.sh:1-91`
- Create: `installers/vmlab/check-lab.sh`
- Create: `tests/vmlab/__init__.py`
- Create: `tests/vmlab/test_scripts.py`

- [x] **Step 1: Write failing configuration and shell-contract tests**

Add tests that read the shell files and assert these contracts:

```python
from pathlib import Path

VMLAB = Path(__file__).parents[2] / "installers" / "vmlab"


def test_config_pins_sse_and_lab_paths() -> None:
    text = (VMLAB / "config.env").read_text()
    assert "splunk-security-essentials_383.tgz" in text
    assert "SSE_INDEX:=sse_lab" in text
    assert "SIEM_IP:=100.65.1.10" in text
    assert "SOAR_IP:=100.65.1.11" in text


def test_reset_guard_accepts_only_the_configured_lab_index() -> None:
    text = (VMLAB / "lib.sh").read_text()
    assert "require_sse_lab_index" in text
    assert '[[ "$SSE_INDEX" == "sse_lab" ]]' in text
```

Also assert that `check-lab.sh` checks required host commands, all four pinned artifacts, NAT configuration, both VMX paths, and free disk space without changing VM state.

- [x] **Step 2: Run the tests and confirm they fail**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
```

Expected: failures for the missing SSE settings, guard, and check command.

- [x] **Step 3: Add shared configuration**

Add environment-overridable values to `config.env`:

```bash
: "${SSE_TGZ:=splunk-security-essentials_383.tgz}"
: "${SIEM_IP:=100.65.1.10}"
: "${SOAR_IP:=100.65.1.11}"
: "${SSE_INDEX:=sse_lab}"
: "${SSE_DATA_DIR:=$VM_BASE_DIR/sse-data}"
: "${SSE_HEC_TOKEN_FILE:=$VM_BASE_DIR/.sse_hec_token}"
: "${SIEM_RAM:=4096}"
: "${SOAR_RAM:=6144}"
: "${SIEM_CPU:=4}"
: "${SOAR_CPU:=4}"
```

Keep `LAB_PASSWORD` and `SPLUNK_ADMIN_PASSWORD` as defaults that can be set by the ignored `config.local.env`.

- [x] **Step 4: Add reusable state and safety helpers**

Extend `lib.sh` with functions having these exact interfaces:

```bash
require_command COMMAND
vmx_path NAME
ensure_vm_running NAME
wait_http URL EXPECTED_STATUS TIMEOUT_SECONDS
require_sse_lab_index
splunk_is_ready IP
soar_is_ready IP
```

`ensure_vm_running` must start an existing VM with `vmrun -T ws start "$vmx" nogui`; it must fail if the VMX does not exist. `require_sse_lab_index` must require the literal configured value `sse_lab` before any event-data cleanup.

- [x] **Step 5: Implement the read-only preflight command**

`check-lab.sh` accepts `--only siem|soar|both` and reports:

- host commands: `vmrun`, `vmware-vdiskmanager`, `xorriso`, `ssh`, `scp`, `nc`, `curl`, `openssl`, `python3`;
- required artifacts for the selected roles;
- VMware NAT gateway/subnet compatibility;
- VMX existence and running/stopped/missing state;
- available space under `VM_BASE_DIR` and generated-data path;
- port reachability for SSH, Splunk web/management/HEC, and SOAR web.

Missing prerequisites return nonzero. Missing VMs are reported but are not a preflight failure when installation artifacts are present and a build can proceed.

- [x] **Step 6: Verify syntax and tests**

Run:

```bash
bash -n installers/vmlab/*.sh
shellcheck installers/vmlab/*.sh
python3 -m pytest tests/vmlab/test_scripts.py -q
```

Expected: all checks pass.

- [x] **Step 7: Commit the shared lab state work**

```bash
git add installers/vmlab/config.env installers/vmlab/lib.sh \
  installers/vmlab/check-lab.sh tests/vmlab
git commit -m "Add vmlab preflight and shared state checks"
```

---

## Task 2: Build the two-pass SSE timestamp transformer

**Files:**

- Create: `installers/vmlab/sse_data.py`
- Create: `installers/vmlab/prepare-sse-data.py`
- Create: `tests/vmlab/test_sse_data.py`
- Create: `tests/vmlab/fixtures/sse-mini/Splunk_Security_Essentials/lookups/SampleDataList.csv`
- Create: `tests/vmlab/fixtures/sse-mini/Splunk_Security_Essentials/lookups/sample_epoch.csv`
- Create: `tests/vmlab/fixtures/sse-mini/Splunk_Security_Essentials/lookups/sample_text.csv`

- [x] **Step 1: Write failing timestamp parsing tests**

Cover the formats found in SSE 3.8.3:

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1483375327.000", "2017-01-02T18:02:07+00:00"),
        ("2016-08-24T12:27:26.000-0600", "2016-08-24T18:27:26+00:00"),
        ("2018-03-07T16:37:04.992946Z", "2018-03-07T16:37:04.992946+00:00"),
        ("11/28/2016 2:31:25 PM", "2016-11-28T14:31:25+00:00"),
        ("2016-08-16 20:58:37.142", "2016-08-16T20:58:37.142000+00:00"),
    ],
)
def test_parse_supported_timestamp(value: str, expected: str) -> None:
    parsed = parse_timestamp(value)
    assert parsed is not None
    assert parsed.instant.isoformat() == expected
```

Test formatting after a fixed shift. Require retention of epoch decimal precision, `Z`, numeric timezone suffix, AM/PM style, and fractional-second width.

- [x] **Step 2: Run parsing tests and confirm they fail**

Run:

```bash
python3 -m pytest tests/vmlab/test_sse_data.py -q
```

Expected: import failure because `sse_data.py` does not exist.

- [x] **Step 3: Implement the timestamp value model**

Implement typed standard-library structures:

```python
@dataclass(frozen=True)
class ParsedTimestamp:
    instant: datetime
    style: TimestampStyle
    fraction_digits: int
    timezone_text: str | None


def parse_timestamp(value: str) -> ParsedTimestamp | None: ...
def format_shifted(value: ParsedTimestamp, delta: timedelta) -> str: ...
def is_temporal_field(field_name: str) -> bool: ...
```

Normalize parsed instants to UTC for comparison. Treat timezone-free SSE timestamps as UTC. Limit numeric epoch detection to temporal fields or the primary `_time` field so ordinary numeric values are never shifted.

- [x] **Step 4: Write failing global-shift and validation tests**

The fixture manifest contains two datasets with different ranges and secondary fields such as `Password_Last_Set`, `CreationUtcTime`, `PreviousCreationUtcTime`, `lastLogonTimestamp`, `pwdLastSet`, and `maxtime`. Tests must prove:

- `SampleDataList.csv` determines the exact dataset scope;
- the global latest value, not each file's latest, determines one delta;
- every timestamp receives the same delta;
- row and dataset counts remain unchanged;
- global and per-field spans remain unchanged;
- old anomaly values preserve their distance from surrounding events;
- `date_hour`, `date_mday`, `date_minute`, `date_month`, `date_second`, `date_wday`, `date_year`, and `date_zone` are recomputed from shifted primary event time;
- unsupported non-empty values in classified temporal fields fail preparation;
- dry run writes a report but no batches.

- [x] **Step 5: Implement package scanning and two-pass transformation**

Use these public interfaces:

```python
@dataclass(frozen=True)
class PreparationOptions:
    package: Path
    output_dir: Path
    anchor: datetime
    dry_run: bool
    batch_size: int = 5_000


def scan_package(package: Path) -> ScanReport: ...
def prepare_package(options: PreparationOptions) -> PreparationReport: ...
```

Read the tar archive without extracting it into the repository. Locate the app root by `Splunk_Security_Essentials/default/app.conf`, read `lookups/SampleDataList.csv`, resolve exactly the 43 listed files, and reject missing or duplicate entries.

Pass one scans recognized fields and embedded structured values, records source formats, and calculates global minimum and maximum. Pass two applies `anchor - global_max` everywhere, validates counts and ranges, and writes to a temporary sibling directory before an atomic rename.

Write:

```text
SSE_DATA_DIR/
  manifest.json
  batches/000001.ndjson
  batches/000002.ndjson
```

Each NDJSON line is a complete HEC event envelope:

```json
{
  "time": 1786793704.992946,
  "host": "sse-lab",
  "source": "sse:sample_epoch.csv",
  "sourcetype": "sse:sample:sample_epoch",
  "index": "sse_lab",
  "event": {"_time": "1786793704.992946", "user": "alice"},
  "fields": {
    "lab_dataset": "sample_epoch.csv",
    "lab_import_id": "<stable id>",
    "lab_batch_id": "000001"
  }
}
```

The import ID is a SHA-256 digest of package SHA-256, anchor, delta, transformer schema version, index, and sorted dataset list. `manifest.json` includes the import ID, hashes, anchor, delta, source/shifted ranges, all dataset counts, batch counts, field formats, and unsupported-value count.

- [x] **Step 6: Add the CLI**

`prepare-sse-data.py` accepts:

```text
--package PATH
--output-dir PATH
--index NAME
--anchor ISO_8601_UTC
--dry-run
--batch-size EVENTS
```

Defaults come from `config.env` only through the calling shell script; the Python command itself requires explicit paths and index, which keeps it testable. Print a concise JSON summary to stdout and detailed errors to stderr.

- [x] **Step 7: Run focused and static checks**

Run:

```bash
python3 -m pytest tests/vmlab/test_sse_data.py -q
ruff check installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py tests/vmlab
ruff format --check installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py tests/vmlab
mypy installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py
```

Expected: all checks pass.

- [x] **Step 8: Validate against the real package without writing batches**

Run:

```bash
python3 installers/vmlab/prepare-sse-data.py \
  --package installers/splunk-security-essentials_383.tgz \
  --output-dir /home/danny/vmware/sse-data \
  --index sse_lab --dry-run
```

Expected: 43 datasets, zero unsupported temporal values, unchanged global span, and no `batches` directory replacement.

- [x] **Step 9: Commit the transformer**

```bash
git add installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py \
  tests/vmlab/test_sse_data.py tests/vmlab/fixtures
git commit -m "Add SSE recent-data transformer"
```

---

## Task 3: Add SSE app installation, HEC import, and scoped reset

**Files:**

- Create: `installers/vmlab/install-sse.sh`
- Create: `installers/vmlab/import-sse-data.sh`
- Modify: `tests/vmlab/test_scripts.py`

- [x] **Step 1: Write failing shell safety and interface tests**

Assert:

- `install-sse.sh` accepts `--ip`, verifies app ID `Splunk_Security_Essentials` and version `3.8.3`, and skips installation when that version is already active;
- `import-sse-data.sh` exposes `prepare`, `import`, `reset`, and `status` subcommands;
- only `reset` and `import --clear-existing` invoke event cleanup;
- cleanup calls `require_sse_lab_index` immediately before `splunk clean eventdata -index "$SSE_INDEX" -f`;
- no cleanup command names `_internal`, `_audit`, `main`, or a wildcard;
- token permissions are `0600` and no log statement prints the token or password.

- [x] **Step 2: Run the tests and confirm they fail**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
```

Expected: failures for the missing commands.

- [x] **Step 3: Implement idempotent SSE app installation**

`install-sse.sh --ip "$SIEM_IP"` must:

1. require the pinned package and reachable Splunk;
2. read the package app ID and version before copying;
3. query installed app state through the local Splunk CLI on the SIEM VM;
4. skip when active version 3.8.3 is already installed;
5. copy to `/var/tmp`, install with `splunk install app ... -update 1`, and restart only when needed;
6. remove the remote package and verify app ID/version after restart.

Pass credentials through a mode-`0600` temporary file or protected stdin. Do not include the password in log output.

- [x] **Step 4: Implement lab-owned HEC configuration**

The import command creates `/opt/splunk/etc/apps/sse_lab_loader/local` on the SIEM VM with:

- an `indexes.conf` stanza named exactly `$SSE_INDEX`;
- an `inputs.conf` global HEC stanza and a token named `sse-lab` restricted to `$SSE_INDEX`;
- a generated token copied to `$SSE_HEC_TOKEN_FILE` with mode `0600`.

Restart Splunk only if the configuration changes. Verify HEC with an authenticated health request before importing.

- [x] **Step 5: Implement prepare, import, status, and reset**

Use this command contract:

```bash
./import-sse-data.sh prepare [--anchor ISO_8601_UTC] [--dry-run]
./import-sse-data.sh import [--clear-existing]
./import-sse-data.sh status
./import-sse-data.sh reset [--anchor ISO_8601_UTC]
```

`prepare` calls the Python CLI with `SSE_TGZ`, `SSE_DATA_DIR`, and `SSE_INDEX`. `import` sends each batch to `https://$SIEM_IP:8088/services/collector/event` using `curl --data-binary`. It checks every HEC response and polls Splunk search until the indexed count for `lab_import_id` equals the manifest count.

Before sending a stable manifest again, query counts grouped by `lab_batch_id`. Skip complete batches. Refuse a partial batch unless `--clear-existing` is supplied, because resending it would duplicate events.

`status` reports the prepared import ID, expected count, indexed count, dataset coverage, earliest shifted event, and latest shifted event.

`reset` is exactly:

1. prepare using the supplied anchor or current UTC;
2. require the literal `sse_lab` guard;
3. stop Splunk, run `/opt/splunk/bin/splunk clean eventdata -index "$SSE_INDEX" -f`, start Splunk, and wait for readiness;
4. import all prepared batches and verify counts.

It must not remove SSE lookups, app files, other indexes, or either VM.

- [x] **Step 6: Run tests and shell analysis**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
bash -n installers/vmlab/*.sh
shellcheck installers/vmlab/*.sh
```

Expected: all checks pass.

- [x] **Step 7: Commit SSE installation and import commands**

```bash
git add installers/vmlab/install-sse.sh installers/vmlab/import-sse-data.sh \
  tests/vmlab/test_scripts.py
git commit -m "Add SSE app and scoped lab data import"
```

---

## Task 4: Make Splunk and SOAR installation resumable

**Files:**

- Modify: `installers/vmlab/install-splunk.sh:1-55`
- Modify: `installers/vmlab/install-soar.sh:1-44`
- Modify: `tests/vmlab/test_scripts.py`

- [x] **Step 1: Add failing idempotency and ownership tests**

Assert that `install-splunk.sh` checks installed RPM version, service state, boot-start, firewall, and authenticated readiness before deciding what to change.

Assert that `install-soar.sh`:

- never runs `cd /home/soar/splunk-soar` before `sudo -u soar`;
- recognizes a completed install from `/opt/phantom/bin/phsvc`, service state, and web response;
- skips extraction, prepare, and install postconditions that are already complete;
- configures `soar_local_admin` from `LAB_PASSWORD` without printing it;
- detaches the DVD and disables its repository on success or error.

- [x] **Step 2: Run the tests and confirm the SOAR ownership test fails**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
```

Expected: failure showing the current outer `cd` runs as `labadmin`.

- [x] **Step 3: Refactor Splunk into postcondition steps**

Make each of these safe to rerun:

1. OS user, Transparent Huge Pages unit, and limits;
2. exact pinned RPM installed;
3. first-start credentials only when Splunk is uninitialized;
4. systemd boot-start configured;
5. Splunk running and authenticated;
6. firewall ports present.

Do not overwrite an existing admin password seed after Splunk has initialized.

- [x] **Step 4: Fix SOAR ownership and resume state**

The install command must have no outer directory change:

```bash
ssh_vm "$IP" "sudo -u soar bash -c \
  'cd /home/soar/splunk-soar && ./soar-install ...'"
```

Check separate postconditions for user/directory setup, archive extraction, OS preparation, product installation, firewall, password configuration, and web readiness. Use an EXIT trap for the DVD/repository cleanup. A current successful SOAR 8.6 VM should take only the verify path on rerun.

- [x] **Step 5: Run local checks**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
bash -n installers/vmlab/*.sh
shellcheck installers/vmlab/*.sh
```

Expected: all checks pass.

- [x] **Step 6: Run both commands against the existing VMs**

Run:

```bash
installers/vmlab/install-splunk.sh --ip 100.65.1.10
installers/vmlab/install-soar.sh --name soar --ip 100.65.1.11
```

Expected: both commands preserve the VMs and report existing installed product state. SOAR must not repeat `soar-prepare-system` or `soar-install`.

- [x] **Step 7: Commit resumable product installation**

```bash
git add installers/vmlab/install-splunk.sh installers/vmlab/install-soar.sh \
  tests/vmlab/test_scripts.py
git commit -m "Make vmlab product installs resumable"
```

---

## Task 5: Add orchestration and end-to-end verification

**Files:**

- Modify: `installers/vmlab/provision-lab.sh:1-31`
- Create: `installers/vmlab/verify-lab.sh`
- Modify: `tests/vmlab/test_scripts.py`

- [x] **Step 1: Add failing orchestration tests**

Assert that the orchestrator:

- accepts `--only siem|soar|both`;
- runs `check-lab.sh` first;
- calls `build-rhel-vm.sh` only when the target VMX is missing;
- starts but does not rebuild an existing stopped VM;
- installs Splunk, SSE, and prepared data for the SIEM role;
- installs SOAR for the SOAR role;
- runs `verify-lab.sh` last;
- accepts `--skip-data` so product provisioning can run without a data reset or import.

Assert that no path invokes VM directory deletion.

- [x] **Step 2: Run tests and confirm they fail**

Run:

```bash
python3 -m pytest tests/vmlab/test_scripts.py -q
```

Expected: failures because the current orchestrator always builds and no verifier exists.

- [x] **Step 3: Implement VM reuse in the orchestrator**

For each selected role:

```bash
if [[ -f "$(vmx_path "$name")" ]]; then
  ensure_vm_running "$name"
  wait_ssh "$ip"
else
  "$HERE/build-rhel-vm.sh" --name "$name" --ip "$ip" ...
fi
```

SIEM order is Splunk, SSE, data preparation if absent, data import, verification. SOAR order is product install then verification. Existing import data is reused when its manifest matches the package and index; the normal provision path must not clear data.

- [x] **Step 4: Implement verification**

`verify-lab.sh --only siem|soar|both` checks:

- VMX exists and VM is running;
- SSH works;
- SIEM RPM is 10.4.2, Splunk authenticates, web and management endpoints answer;
- SSE app ID/version is `Splunk_Security_Essentials`/3.8.3;
- HEC answers, manifest count equals indexed import-ID count, all 43 datasets are present, and latest event matches the manifest anchor within source precision;
- SOAR reports 8.6.0.530, `soar_local_admin` can authenticate, and HTTPS returns the expected redirect or success status.

Return nonzero for any failed postcondition. Print no secrets.

- [x] **Step 5: Run tests and syntax checks**

Run:

```bash
python3 -m pytest tests/vmlab -q
bash -n installers/vmlab/*.sh
shellcheck installers/vmlab/*.sh
```

Expected: all checks pass.

- [x] **Step 6: Commit orchestration and verification**

```bash
git add installers/vmlab/provision-lab.sh installers/vmlab/verify-lab.sh \
  tests/vmlab/test_scripts.py
git commit -m "Reuse vmlab VMs and verify each stage"
```

---

## Task 6: Copy the pinned SSE package and verify the live pipeline

**Files:**

- Copy, ignored by Git: `/home/danny/Documents/ISOs/splunk-security-essentials_383.tgz` to `installers/splunk-security-essentials_383.tgz`
- Generate, outside Git: `/home/danny/vmware/sse-data/`
- Generate, outside Git: `/home/danny/vmware/.sse_hec_token`

- [x] **Step 1: Copy and verify the installer package**

Run:

```bash
cp -p /home/danny/Documents/ISOs/splunk-security-essentials_383.tgz \
  installers/splunk-security-essentials_383.tgz
sha256sum /home/danny/Documents/ISOs/splunk-security-essentials_383.tgz \
  installers/splunk-security-essentials_383.tgz
```

Expected: both hashes match. Confirm `git status --ignored` shows the copied package as ignored.

- [x] **Step 2: Run read-only preflight**

Run:

```bash
installers/vmlab/check-lab.sh --only both
```

Expected: pinned artifacts and existing VM state are reported; required endpoints are reachable.

- [x] **Step 3: Install and verify SSE**

Run:

```bash
installers/vmlab/install-sse.sh --ip 100.65.1.10
installers/vmlab/install-sse.sh --ip 100.65.1.10
```

Expected: first run installs SSE 3.8.3; second run verifies and skips installation.

- [x] **Step 4: Prepare all recent data**

Run:

```bash
installers/vmlab/import-sse-data.sh prepare
```

Expected: manifest covers 43 datasets; its latest shifted timestamp equals the recorded current UTC anchor; source and shifted spans match.

- [x] **Step 5: Import without clearing unrelated data**

Run:

```bash
installers/vmlab/import-sse-data.sh import
installers/vmlab/import-sse-data.sh status
```

Expected: all batches return successful HEC responses, indexed count equals the manifest, and all 43 dataset sources are searchable in `sse_lab`.

- [x] **Step 6: Prove idempotency and scoped reset**

Run a second import and confirm it skips complete batches. Record counts from `main`, `_internal`, and `_audit`, then run:

```bash
installers/vmlab/import-sse-data.sh reset
```

Expected: a new current anchor and import ID are created; `sse_lab` contains exactly the new import; the comparison indexes retain their prior data; both VMs still exist and run.

- [x] **Step 7: Run end-to-end verification**

Run:

```bash
installers/vmlab/verify-lab.sh --only both
installers/vmlab/provision-lab.sh --only both
```

Expected: verification passes; provisioning reuses both VMX files and completes without reinstalling completed stages.

---

## Task 7: Replace the vmlab README with the lab runbook

**Files:**

- Modify: `installers/vmlab/README.md:1-65`

- [x] **Step 1: Write the runbook**

Document:

- the two-VM topology and `/home/danny/vmware/` location;
- exact pinned RHEL, Splunk Enterprise, SSE, and SOAR artifact names;
- VMware NAT addresses and ports;
- `config.local.env` with `LAB_PASSWORD='Splunk@2026'` as a lab-only example and a warning not to reuse it;
- preflight and full provisioning;
- every standalone build/install/prepare/import/status/reset/verify command;
- rerun behavior and the rule that existing VMs are reused;
- the two-pass global timestamp shift and why it preserves relationships;
- the exact `sse_lab` reset scope and what is never cleared;
- endpoints and account names;
- recovery commands for failed SIEM, SSE, data, and SOAR stages;
- generated paths and how to replace only generated preparation output.

- [x] **Step 2: Check command names against scripts**

Run:

```bash
rg -o '`[^`]+\.sh[^`]*`' installers/vmlab/README.md
rg --files installers/vmlab | sort
```

Expected: every documented script and option exists.

- [x] **Step 3: Run the full local verification suite**

Run:

```bash
python3 -m pytest tests/vmlab -q
bash -n installers/vmlab/*.sh
shellcheck installers/vmlab/*.sh
ruff check installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py tests/vmlab
ruff format --check installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py tests/vmlab
mypy installers/vmlab/sse_data.py installers/vmlab/prepare-sse-data.py
git diff --check
```

Expected: all checks pass.

- [x] **Step 4: Commit the runbook**

```bash
git add installers/vmlab/README.md
git commit -m "Document the modular Splunk lab workflow"
```

- [x] **Step 5: Inspect final scope**

Run:

```bash
git status --short
git log --oneline --max-count=8
git diff HEAD~5 --stat
```

Expected: source, tests, design, plan, and README are tracked; packages, credentials, tokens, and generated batches remain ignored or outside the repository.
