"""Prepare Splunk Security Essentials sample lookups as recent HEC events."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class PreparationError(ValueError):
    """Raised when the SSE package or a temporal value is unsafe to transform."""


class TimestampStyle(StrEnum):
    """Timestamp representations used by SSE 3.8.3 sample lookups."""

    EPOCH = "epoch"
    ISO = "iso"
    SPACE = "space"
    US = "us"
    GENERALIZED = "generalized"


@dataclass(frozen=True)
class ParsedTimestamp:
    """A parsed instant plus enough source details to preserve its style."""

    instant: datetime
    style: TimestampStyle
    fraction_digits: int
    timezone_text: str | None
    hour_padded: bool = False


@dataclass(frozen=True)
class DatasetReport:
    """Row and timestamp summary for one manifest dataset."""

    name: str
    label: str
    rows: int
    minimum: datetime | None
    maximum: datetime | None


@dataclass(frozen=True)
class ScanReport:
    """Validated inventory produced by the first package pass."""

    package_sha256: str
    datasets: tuple[DatasetReport, ...]
    total_rows: int
    global_min: datetime
    global_max: datetime
    field_formats: dict[str, tuple[str, ...]]
    unsupported: tuple[str, ...]


@dataclass(frozen=True)
class PreparationOptions:
    """Inputs controlling a deterministic SSE preparation run."""

    package: Path
    output_dir: Path
    index: str
    anchor: datetime
    dry_run: bool
    batch_size: int = 5_000


@dataclass(frozen=True)
class PreparationReport:
    """Preparation result returned to the CLI and importer."""

    package_sha256: str
    import_id: str
    datasets: tuple[DatasetReport, ...]
    total_rows: int
    global_min: datetime
    global_max: datetime
    shifted_min: datetime
    shifted_max: datetime
    anchor: datetime
    delta: timedelta
    batches: tuple[dict[str, int | str], ...]
    field_formats: dict[str, tuple[str, ...]]
    dry_run: bool


_EPOCH_RE = re.compile(r"^-?\d{9,}(?:\.(?P<fraction>\d+))?$")
_ISO_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})(?P<separator>[T ])"
    r"(?P<clock>\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d+))?"
    r"(?P<zone>Z|[+-]\d{2}:?\d{2})?$"
)
_US_RE = re.compile(
    r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4}) "
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2}) "
    r"(?P<period>AM|PM)$",
    re.IGNORECASE,
)
_GENERALIZED_RE = re.compile(r"^(?P<base>\d{14})(?:\.(?P<fraction>\d+))?Z$")
_EMBEDDED_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} (?:AM|PM)"
    r"|\d{14}(?:\.\d+)?Z"
    r")(?!\d)",
    re.IGNORECASE,
)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_TEMPORAL_FIELDS = {
    "_time",
    "password_last_set",
    "creationutctime",
    "previouscreationutctime",
    "maxtime",
    "lastlogontimestamp",
    "pwdlastset",
    "whencreated",
    "hiredate",
    "accountexpires",
}
_EMPTY_TEMPORAL_VALUES = {"", "<never>", "(never)", "never", "null", "n/a"}
csv.field_size_limit(16 * 1024 * 1024)


def _fixed_timezone(zone_text: str | None) -> timezone:
    if zone_text in (None, "Z"):
        return UTC
    compact = zone_text.replace(":", "")
    sign = 1 if compact[0] == "+" else -1
    offset = timedelta(hours=int(compact[1:3]), minutes=int(compact[3:5]))
    return timezone(sign * offset)


def _fraction_microseconds(fraction: str | None) -> int:
    return int(((fraction or "") + "000000")[:6])


def parse_timestamp(value: str) -> ParsedTimestamp | None:
    """Parse a complete SSE timestamp value, returning ``None`` for other data."""
    value = value.strip()
    epoch_match = _EPOCH_RE.fullmatch(value)
    if epoch_match:
        try:
            instant = datetime.fromtimestamp(float(Decimal(value)), UTC)
        except (OverflowError, ValueError):
            return None
        fraction = epoch_match.group("fraction") or ""
        return ParsedTimestamp(
            instant=instant,
            style=TimestampStyle.EPOCH,
            fraction_digits=len(fraction),
            timezone_text="Z",
        )

    iso_match = _ISO_RE.fullmatch(value)
    if iso_match:
        zone_text = iso_match.group("zone")
        fraction = iso_match.group("fraction") or ""
        naive = datetime.strptime(
            f"{iso_match.group('date')} {iso_match.group('clock')}",
            "%Y-%m-%d %H:%M:%S",
        ).replace(microsecond=_fraction_microseconds(fraction))
        instant = naive.replace(tzinfo=_fixed_timezone(zone_text)).astimezone(UTC)
        style = (
            TimestampStyle.ISO
            if iso_match.group("separator") == "T"
            else TimestampStyle.SPACE
        )
        return ParsedTimestamp(
            instant=instant,
            style=style,
            fraction_digits=len(fraction),
            timezone_text=zone_text,
        )

    us_match = _US_RE.fullmatch(value)
    if us_match:
        naive = datetime.strptime(value.upper(), "%m/%d/%Y %I:%M:%S %p")
        return ParsedTimestamp(
            instant=naive.replace(tzinfo=UTC),
            style=TimestampStyle.US,
            fraction_digits=0,
            timezone_text=None,
            hour_padded=len(us_match.group("hour")) == 2,
        )

    generalized_match = _GENERALIZED_RE.fullmatch(value)
    if generalized_match:
        fraction = generalized_match.group("fraction") or ""
        naive = datetime.strptime(generalized_match.group("base"), "%Y%m%d%H%M%S")
        return ParsedTimestamp(
            instant=naive.replace(
                microsecond=_fraction_microseconds(fraction), tzinfo=UTC
            ),
            style=TimestampStyle.GENERALIZED,
            fraction_digits=len(fraction),
            timezone_text="Z",
        )

    return None


def _format_fraction(instant: datetime, digits: int) -> str:
    if digits == 0:
        return ""
    return f".{instant.microsecond:06d}"[: digits + 1]


def format_shifted(value: ParsedTimestamp, delta: timedelta) -> str:
    """Shift a parsed value while retaining its original representation."""
    shifted = value.instant + delta
    if value.style is TimestampStyle.EPOCH:
        elapsed = shifted - _UNIX_EPOCH
        seconds = Decimal(elapsed.days * 86_400 + elapsed.seconds)
        seconds += Decimal(elapsed.microseconds) / Decimal(1_000_000)
        if value.fraction_digits:
            return f"{seconds:.{value.fraction_digits}f}"
        return f"{seconds:.0f}"

    local = shifted.astimezone(_fixed_timezone(value.timezone_text))
    fraction = _format_fraction(local, value.fraction_digits)
    if value.style in (TimestampStyle.ISO, TimestampStyle.SPACE):
        separator = "T" if value.style is TimestampStyle.ISO else " "
        zone = value.timezone_text or ""
        return f"{local:%Y-%m-%d}{separator}{local:%H:%M:%S}{fraction}{zone}"
    if value.style is TimestampStyle.US:
        hour = local.strftime("%I")
        if not value.hour_padded:
            hour = str(int(hour))
        return f"{local:%m/%d/%Y} {hour}:{local:%M:%S %p}"
    if value.style is TimestampStyle.GENERALIZED:
        return f"{local:%Y%m%d%H%M%S}{fraction}Z"
    raise AssertionError(f"unhandled timestamp style: {value.style}")


def is_temporal_field(field_name: str) -> bool:
    """Return whether an SSE CSV field is an instant rather than a duration."""
    return field_name.casefold() in _TEMPORAL_FIELDS


def _package_sha256(package: Path) -> str:
    digest = hashlib.sha256()
    with package.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_layout(
    archive: tarfile.TarFile,
) -> tuple[str, list[tuple[str, str]]]:
    names = {member.name for member in archive.getmembers() if member.isfile()}
    app_candidates = [name for name in names if name.endswith("/default/app.conf")]
    manifest_candidates = [
        name for name in names if name.endswith("/lookups/SampleDataList.csv")
    ]
    if len(app_candidates) != 1 or len(manifest_candidates) != 1:
        raise PreparationError(
            "package must contain one SSE app and one sample manifest"
        )
    root = app_candidates[0].removesuffix("/default/app.conf")
    if root != "Splunk_Security_Essentials":
        raise PreparationError(f"unexpected SSE app root: {root}")
    expected_manifest = f"{root}/lookups/SampleDataList.csv"
    if manifest_candidates[0] != expected_manifest:
        raise PreparationError("sample manifest is outside the SSE app root")

    manifest_stream = archive.extractfile(expected_manifest)
    if manifest_stream is None:
        raise PreparationError("cannot read SampleDataList.csv")
    with io.TextIOWrapper(manifest_stream, encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text)
        if reader.fieldnames is None or "lookup" not in reader.fieldnames:
            raise PreparationError("SampleDataList.csv has no lookup column")
        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            name = (row.get("lookup") or "").strip()
            label = (row.get("label") or "").strip()
            if not name or Path(name).name != name:
                raise PreparationError(
                    f"invalid lookup name at SampleDataList.csv row {row_number}"
                )
            if name in seen:
                raise PreparationError(f"duplicate lookup in manifest: {name}")
            member_name = f"{root}/lookups/{name}"
            if member_name not in names:
                raise PreparationError(f"manifest lookup is missing: {name}")
            seen.add(name)
            entries.append((name, label))
    if not entries:
        raise PreparationError("SampleDataList.csv contains no datasets")
    return root, entries


def _embedded_timestamps(value: str) -> list[ParsedTimestamp]:
    parsed: list[ParsedTimestamp] = []
    for match in _EMBEDDED_RE.finditer(value):
        timestamp = parse_timestamp(match.group(0))
        if timestamp is not None:
            parsed.append(timestamp)
    return parsed


def _scan_archive(
    archive: tarfile.TarFile,
    package_sha256: str,
) -> ScanReport:
    root, entries = _package_layout(archive)
    datasets: list[DatasetReport] = []
    formats: dict[str, set[str]] = {}
    unsupported: list[str] = []
    global_min: datetime | None = None
    global_max: datetime | None = None
    total_rows = 0

    for name, label in entries:
        member = archive.extractfile(f"{root}/lookups/{name}")
        if member is None:
            raise PreparationError(f"cannot read manifest lookup: {name}")
        dataset_min: datetime | None = None
        dataset_max: datetime | None = None
        row_count = 0
        with io.TextIOWrapper(member, encoding="utf-8-sig", newline="") as text:
            reader = csv.DictReader(text)
            if not reader.fieldnames:
                raise PreparationError(f"dataset has no header: {name}")
            for row_number, row in enumerate(reader, start=2):
                row_count += 1
                if None in row:
                    raise PreparationError(
                        f"extra CSV columns in {name} row {row_number}"
                    )
                for field_name, field_value in row.items():
                    value = field_value or ""
                    timestamps: list[ParsedTimestamp]
                    format_key = f"{name}:{field_name}"
                    if is_temporal_field(field_name):
                        if value.strip().casefold() in _EMPTY_TEMPORAL_VALUES:
                            continue
                        parsed = parse_timestamp(value)
                        if parsed is None:
                            unsupported.append(
                                f"{name} row {row_number} field {field_name}: {value!r}"
                            )
                            continue
                        timestamps = [parsed]
                    else:
                        timestamps = _embedded_timestamps(value)
                        if timestamps:
                            format_key += ":embedded"
                    for parsed in timestamps:
                        formats.setdefault(format_key, set()).add(parsed.style.value)
                        instant = parsed.instant
                        dataset_min = (
                            instant
                            if dataset_min is None
                            else min(dataset_min, instant)
                        )
                        dataset_max = (
                            instant
                            if dataset_max is None
                            else max(dataset_max, instant)
                        )
                        global_min = (
                            instant if global_min is None else min(global_min, instant)
                        )
                        global_max = (
                            instant if global_max is None else max(global_max, instant)
                        )
        total_rows += row_count
        datasets.append(
            DatasetReport(
                name=name,
                label=label,
                rows=row_count,
                minimum=dataset_min,
                maximum=dataset_max,
            )
        )

    if global_min is None or global_max is None:
        raise PreparationError("SSE sample datasets contain no recognized timestamps")
    frozen_formats = {key: tuple(sorted(values)) for key, values in formats.items()}
    return ScanReport(
        package_sha256=package_sha256,
        datasets=tuple(datasets),
        total_rows=total_rows,
        global_min=global_min,
        global_max=global_max,
        field_formats=frozen_formats,
        unsupported=tuple(unsupported),
    )


def scan_package(package: Path) -> ScanReport:
    """Inventory all manifest datasets and temporal values in an SSE package."""
    if not package.is_file():
        raise PreparationError(f"SSE package not found: {package}")
    try:
        with tarfile.open(package, "r:gz") as archive:
            return _scan_archive(archive, _package_sha256(package))
    except (tarfile.TarError, UnicodeError, csv.Error, OSError) as error:
        raise PreparationError(f"cannot scan SSE package: {error}") from error


def _shift_embedded(value: str, delta: timedelta) -> str:
    def replace(match: re.Match[str]) -> str:
        parsed = parse_timestamp(match.group(0))
        if parsed is None:
            raise PreparationError(f"cannot parse embedded timestamp: {match.group(0)}")
        return format_shifted(parsed, delta)

    return _EMBEDDED_RE.sub(replace, value)


_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _recompute_date_fields(row: dict[str, str], instant: datetime) -> None:
    utc = instant.astimezone(UTC)
    replacements = {
        "date_hour": str(utc.hour),
        "date_mday": str(utc.day),
        "date_minute": str(utc.minute),
        "date_month": _MONTHS[utc.month - 1],
        "date_second": str(utc.second),
        "date_wday": _WEEKDAYS[utc.weekday()],
        "date_year": str(utc.year),
        "date_zone": "UTC",
    }
    for field_name, value in replacements.items():
        if field_name in row:
            row[field_name] = value


def _transform_row(
    source: dict[str, str | None], delta: timedelta
) -> tuple[dict[str, str], datetime | None]:
    transformed: dict[str, str] = {}
    primary_time: datetime | None = None
    for field_name, field_value in source.items():
        value = field_value or ""
        if is_temporal_field(field_name):
            if value.strip().casefold() in _EMPTY_TEMPORAL_VALUES:
                transformed[field_name] = value
                continue
            parsed = parse_timestamp(value)
            if parsed is None:
                raise PreparationError(
                    f"unsupported temporal value in field {field_name}: {value!r}"
                )
            transformed[field_name] = format_shifted(parsed, delta)
            if field_name == "_time":
                primary_time = parsed.instant + delta
        else:
            transformed[field_name] = _shift_embedded(value, delta)
    if primary_time is not None:
        _recompute_date_fields(transformed, primary_time)
    return transformed, primary_time


def _sourcetype(name: str) -> str:
    stem = Path(name).stem.casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return f"sse:sample:{slug}"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _import_id(scan: ScanReport, anchor: datetime, delta: timedelta, index: str) -> str:
    identity = {
        "schema_version": 1,
        "package_sha256": scan.package_sha256,
        "anchor": _iso(anchor),
        "delta_seconds": delta.total_seconds(),
        "index": index,
        "datasets": [dataset.name for dataset in scan.datasets],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _batch_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_manifest(dataset: DatasetReport, delta: timedelta) -> dict[str, object]:
    return {
        "name": dataset.name,
        "label": dataset.label,
        "rows": dataset.rows,
        "original_min": _iso(dataset.minimum) if dataset.minimum else None,
        "original_max": _iso(dataset.maximum) if dataset.maximum else None,
        "shifted_min": _iso(dataset.minimum + delta) if dataset.minimum else None,
        "shifted_max": _iso(dataset.maximum + delta) if dataset.maximum else None,
        "sourcetype": _sourcetype(dataset.name),
    }


def _replace_output(staged: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.rename(backup)
    try:
        staged.rename(output)
    except OSError:
        if backup.exists() and not output.exists():
            backup.rename(output)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _write_prepared_data(
    options: PreparationOptions,
    scan: ScanReport,
    anchor: datetime,
    delta: timedelta,
    import_id: str,
) -> tuple[dict[str, int | str], ...]:
    output = options.output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.preparing-", dir=output.parent)
    )
    batch_dir = staged / "batches"
    batch_dir.mkdir()
    batches: list[dict[str, int | str]] = []
    stream: io.TextIOWrapper | None = None
    current_path: Path | None = None
    current_count = 0
    emitted = 0

    def close_batch() -> None:
        nonlocal stream, current_path, current_count
        if stream is None or current_path is None:
            return
        stream.close()
        batches.append(
            {
                "id": current_path.stem,
                "file": f"batches/{current_path.name}",
                "events": current_count,
                "sha256": _batch_sha256(current_path),
            }
        )
        stream = None
        current_path = None
        current_count = 0

    try:
        with tarfile.open(options.package, "r:gz") as archive:
            root, entries = _package_layout(archive)
            for dataset_name, _label in entries:
                member = archive.extractfile(f"{root}/lookups/{dataset_name}")
                if member is None:
                    raise PreparationError(
                        f"cannot read manifest lookup: {dataset_name}"
                    )
                with io.TextIOWrapper(member, encoding="utf-8-sig", newline="") as text:
                    reader = csv.DictReader(text)
                    for row in reader:
                        if stream is None or current_count == options.batch_size:
                            close_batch()
                            batch_id = f"{len(batches) + 1:06d}"
                            current_path = batch_dir / f"{batch_id}.ndjson"
                            stream = current_path.open(
                                "w", encoding="utf-8", newline="\n"
                            )
                        if current_path is None:
                            raise PreparationError("batch path was not initialized")
                        transformed, primary_time = _transform_row(row, delta)
                        batch_id = current_path.stem
                        transformed["lab_dataset"] = dataset_name
                        transformed["lab_import_id"] = import_id
                        transformed["lab_batch_id"] = batch_id
                        event = {
                            "time": (primary_time or anchor).timestamp(),
                            "host": "sse-lab",
                            "source": f"sse:{dataset_name}",
                            "sourcetype": _sourcetype(dataset_name),
                            "index": options.index,
                            "event": transformed,
                            "fields": {
                                "lab_dataset": dataset_name,
                                "lab_import_id": import_id,
                                "lab_batch_id": batch_id,
                            },
                        }
                        stream.write(
                            json.dumps(event, sort_keys=True, separators=(",", ":"))
                        )
                        stream.write("\n")
                        current_count += 1
                        emitted += 1
        close_batch()
        if emitted != scan.total_rows:
            raise PreparationError(
                f"row count changed during preparation: {scan.total_rows} -> {emitted}"
            )

        manifest = {
            "schema_version": 1,
            "app_id": "Splunk_Security_Essentials",
            "app_version": "3.8.3",
            "package_sha256": scan.package_sha256,
            "import_id": import_id,
            "index": options.index,
            "anchor": _iso(anchor),
            "delta_seconds": delta.total_seconds(),
            "dataset_count": len(scan.datasets),
            "event_count": scan.total_rows,
            "original_min": _iso(scan.global_min),
            "original_max": _iso(scan.global_max),
            "shifted_min": _iso(scan.global_min + delta),
            "shifted_max": _iso(scan.global_max + delta),
            "datasets": [
                _dataset_manifest(dataset, delta) for dataset in scan.datasets
            ],
            "batches": batches,
            "field_formats": scan.field_formats,
            "unsupported_count": len(scan.unsupported),
        }
        (staged / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _replace_output(staged, output)
    except Exception:
        if stream is not None:
            stream.close()
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return tuple(batches)


def prepare_package(options: PreparationOptions) -> PreparationReport:
    """Transform SSE lookups and atomically write HEC batches and a manifest."""
    if options.index != "sse_lab":
        raise PreparationError(
            f"refusing to prepare SSE lab data for index {options.index!r}"
        )
    if options.batch_size <= 0:
        raise PreparationError("batch size must be positive")
    if options.anchor.tzinfo is None:
        raise PreparationError("anchor must include a timezone")
    anchor = options.anchor.astimezone(UTC)
    scan = scan_package(options.package)
    if scan.unsupported:
        details = "\n".join(scan.unsupported[:20])
        raise PreparationError(f"unsupported temporal values:\n{details}")
    delta = anchor - scan.global_max
    import_id = _import_id(scan, anchor, delta, options.index)
    batches: tuple[dict[str, int | str], ...] = ()
    if not options.dry_run:
        batches = _write_prepared_data(
            options=options,
            scan=scan,
            anchor=anchor,
            delta=delta,
            import_id=import_id,
        )
    return PreparationReport(
        package_sha256=scan.package_sha256,
        import_id=import_id,
        datasets=scan.datasets,
        total_rows=scan.total_rows,
        global_min=scan.global_min,
        global_max=scan.global_max,
        shifted_min=scan.global_min + delta,
        shifted_max=scan.global_max + delta,
        anchor=anchor,
        delta=delta,
        batches=batches,
        field_formats=scan.field_formats,
        dry_run=options.dry_run,
    )
