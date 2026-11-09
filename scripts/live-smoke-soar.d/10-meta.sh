#!/usr/bin/env bash
# Read-only platform and vocabulary checks.
if soar_selected 10-meta; then
    step "10-meta"
    check_json 'd[0]["status"] == "ok" and bool(d[0]["version"])' soar test
    check_json 'bool(d[0]["version"])' soar info
    check_json 'any(r.get("type") == "daemon" for r in d) and all({"name", "status", "time"} <= r.keys() for r in d if r.get("type") == "daemon")' soar health
    check_json '{"license_type", "max_allowed_actions_per_day", "recent_app_run_count", "recent_playbook_run_count", "recent_debug_run_count"} <= d[0].keys()' soar license
    for vocabulary in severities statuses labels tags cef features; do
        expect_ok "$S" soar meta "$vocabulary" --json
    done
    expect_ok "$S" soar approvals list --json
    expect_ok "$S" soar settings --json
    expect_ok "$S" soar stats --json
    expect_ok "$S" soar ingest-status --json
    check_json 'isinstance(d, list) and len(d) <= 5' soar audit --limit 5
    if capture "$T/audit.csv" "$S" soar audit --format csv --limit 5; then
        "$PY" - "$T/audit.csv" <<'PY' || bad 'audit must return raw CSV'
import csv
import json
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
if not text.strip():
    sys.exit(0)
try:
    json.loads(text)
except ValueError:
    pass
else:
    raise AssertionError('audit CSV was JSON')
rows = list(csv.reader(text.splitlines()))
assert rows and len(rows) <= 6, rows
assert len(rows[0]) > 1, rows
PY
    fi
fi
