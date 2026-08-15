"""Parse and shift timestamps in Splunk Security Essentials sample rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum


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
EMPTY_TEMPORAL_VALUES = {"", "<never>", "(never)", "never", "null", "n/a"}


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


def embedded_timestamps(value: str) -> list[ParsedTimestamp]:
    """Return every supported timestamp embedded in a larger value."""
    parsed: list[ParsedTimestamp] = []
    for match in _EMBEDDED_RE.finditer(value):
        timestamp = parse_timestamp(match.group(0))
        if timestamp is not None:
            parsed.append(timestamp)
    return parsed


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


def transform_row(
    source: dict[str, str | None], delta: timedelta
) -> tuple[dict[str, str], datetime | None]:
    """Shift temporal values and return the transformed row and event time."""
    transformed: dict[str, str] = {}
    primary_time: datetime | None = None
    for field_name, field_value in source.items():
        value = field_value or ""
        if is_temporal_field(field_name):
            if value.strip().casefold() in EMPTY_TEMPORAL_VALUES:
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
