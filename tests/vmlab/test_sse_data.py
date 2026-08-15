import csv
import io
import json
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
VMLAB = ROOT / "installers" / "vmlab"
FIXTURE = Path(__file__).parent / "fixtures" / "sse-mini"
sys.path.insert(0, str(VMLAB))

from sse_data import (  # noqa: E402
    PreparationError,
    PreparationOptions,
    format_shifted,
    parse_timestamp,
    prepare_package,
    scan_package,
)


def build_package(tmp_path: Path, *, bad_password_time: bool = False) -> Path:
    package = tmp_path / "sse.tgz"
    with tarfile.open(package, "w:gz") as archive:
        for source in sorted(FIXTURE.rglob("*")):
            if not source.is_file():
                continue
            arcname = source.relative_to(FIXTURE)
            if bad_password_time and source.name == "sample_epoch.csv":
                content = source.read_text().replace(
                    "01/01/2010 2:03:04 PM", "not-a-timestamp", 1
                )
                data = content.encode()
                info = tarfile.TarInfo(str(arcname))
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            else:
                archive.add(source, arcname=arcname)
    return package


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1483375327.000", "2017-01-02T16:42:07+00:00"),
        ("2016-08-24T12:27:26.000-0600", "2016-08-24T18:27:26+00:00"),
        ("2018-03-07T16:37:04.992946Z", "2018-03-07T16:37:04.992946+00:00"),
        ("11/28/2016 2:31:25 PM", "2016-11-28T14:31:25+00:00"),
        ("2016-08-16 20:58:37.142", "2016-08-16T20:58:37.142000+00:00"),
        ("20161117075431.0Z", "2016-11-17T07:54:31+00:00"),
    ],
)
def test_parse_supported_timestamp(value: str, expected: str) -> None:
    parsed = parse_timestamp(value)

    assert parsed is not None
    assert parsed.instant.isoformat() == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1483375327.000", "1483461727.000"),
        ("2016-08-24T12:27:26.000-0600", "2016-08-25T12:27:26.000-0600"),
        ("2018-03-07T16:37:04.992946Z", "2018-03-08T16:37:04.992946Z"),
        ("11/28/2016 2:31:25 PM", "11/29/2016 2:31:25 PM"),
        ("2016-08-16 20:58:37.142", "2016-08-17 20:58:37.142"),
        ("20161117075431.0Z", "20161118075431.0Z"),
    ],
)
def test_format_shifted_preserves_source_style(value: str, expected: str) -> None:
    parsed = parse_timestamp(value)
    one_day = datetime(2016, 1, 2, tzinfo=UTC) - datetime(2016, 1, 1, tzinfo=UTC)

    assert parsed is not None
    assert format_shifted(parsed, one_day) == expected


def test_scan_uses_the_manifest_as_dataset_scope(tmp_path: Path) -> None:
    package = build_package(tmp_path)

    report = scan_package(package)

    assert [item.name for item in report.datasets] == [
        "sample_epoch.csv",
        "sample_text.csv",
    ]
    assert [item.rows for item in report.datasets] == [2, 1]
    assert report.total_rows == 3
    assert report.global_max == datetime(2020, 1, 2, tzinfo=UTC)
    assert report.unsupported == ()


def test_prepare_applies_one_delta_and_writes_hec_batches(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    output = tmp_path / "prepared"
    anchor = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

    report = prepare_package(
        PreparationOptions(
            package=package,
            output_dir=output,
            index="sse_lab",
            anchor=anchor,
            dry_run=False,
            batch_size=2,
        )
    )

    manifest = json.loads((output / "manifest.json").read_text())
    events = [
        json.loads(line)
        for batch in sorted((output / "batches").glob("*.ndjson"))
        for line in batch.read_text().splitlines()
    ]
    by_user = {event["event"].get("user", "text"): event for event in events}
    alice = by_user["alice"]
    text_event = by_user["text"]

    assert report.total_rows == 3
    assert manifest["dataset_count"] == 2
    assert manifest["event_count"] == 3
    assert len(manifest["batches"]) == 2
    assert text_event["time"] == anchor.timestamp()
    assert text_event["event"]["_time"] == "2026-08-15T12:00:00.000+0000"
    assert alice["event"]["user"] == "alice"
    assert alice["index"] == "sse_lab"
    assert alice["fields"]["lab_import_id"] == manifest["import_id"]
    assert alice["event"]["_raw"].startswith("08/14/2026 12:00:00 PM")
    assert alice["event"]["date_year"] == "2026"
    assert alice["event"]["date_month"] == "august"

    source_creation = parse_timestamp("1602-05-15 14:07:01.334")
    shifted_creation = parse_timestamp(text_event["event"]["CreationUtcTime"])
    assert source_creation is not None and shifted_creation is not None
    assert shifted_creation.instant - source_creation.instant == report.delta
    assert text_event["event"]["note"] == "unchanged"


def test_dry_run_validates_without_replacing_output(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    output = tmp_path / "prepared"

    report = prepare_package(
        PreparationOptions(
            package=package,
            output_dir=output,
            index="sse_lab",
            anchor=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
            dry_run=True,
        )
    )

    assert report.total_rows == 3
    assert not output.exists()


def test_prepare_fails_closed_for_bad_temporal_value(tmp_path: Path) -> None:
    package = build_package(tmp_path, bad_password_time=True)

    with pytest.raises(PreparationError, match="Password_Last_Set"):
        prepare_package(
            PreparationOptions(
                package=package,
                output_dir=tmp_path / "prepared",
                index="sse_lab",
                anchor=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
                dry_run=False,
            )
        )


def test_prepared_csv_fields_remain_structured_json(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    output = tmp_path / "prepared"
    prepare_package(
        PreparationOptions(
            package=package,
            output_dir=output,
            index="sse_lab",
            anchor=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
            dry_run=False,
        )
    )
    first = json.loads(
        next((output / "batches").glob("*.ndjson")).read_text().splitlines()[0]
    )

    serialized = io.StringIO()
    writer = csv.DictWriter(serialized, fieldnames=first["event"])
    writer.writeheader()
    writer.writerow(first["event"])
    assert "alice" in serialized.getvalue()


def test_prepare_cli_prints_a_dry_run_summary(tmp_path: Path) -> None:
    package = build_package(tmp_path)
    output = tmp_path / "prepared"

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(VMLAB / "prepare-sse-data.py"),
            "--package",
            str(package),
            "--output-dir",
            str(output),
            "--index",
            "sse_lab",
            "--anchor",
            "2026-08-15T12:00:00Z",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["dataset_count"] == 2
    assert summary["event_count"] == 3
    assert summary["shifted_max"] == "2026-08-15T12:00:00Z"
    assert summary["dry_run"] is True
    assert not output.exists()
