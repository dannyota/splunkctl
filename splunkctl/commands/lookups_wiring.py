"""Pure helpers for the transforms.conf/props.conf lookup-wiring grammar.

Kept separate from ``lookups.py`` so the ``LOOKUP-<class>`` value-string
grammar and the lookup-definition kv-building logic have a direct, fast
unit-test surface with no CLI/guard/SDK scaffolding in the way. Command
callbacks in ``lookups.py`` stay thin: parse options, call these, hand the
result to ``conf_ops``.

Grammar reference (verified against Splunk 10.4's props.conf.spec):

    LOOKUP-<class> = $TRANSFORM (<match_field> (AS <match_field_in_event>)?)+
                     (OUTPUT|OUTPUTNEW (<output_field> (AS <output_field_in_event>)?)+)?

``<match_field>``/``<output_field>`` are the lookup TABLE's column names;
the optional ``AS`` clause supplies the EVENT-side field name only when it
differs. Confirmed live: every existing transforms.conf lookup stanza on
the dev instance uses bare ``filename``/``external_type=kvstore`` +
``collection`` (no surprises there either).
"""

import click


def parse_field_spec(raw: str) -> tuple[str, str | None]:
    """Split one repeatable ``--input``/``--output`` token on its ``:`` rename.

    ``"host"`` -> ``("host", None)``; ``"host:src_host"`` -> ``("host",
    "src_host")``. What the two sides *mean* (event field vs. lookup-table
    field, and which order they end up in on the wire) is the caller's
    concern -- see :func:`build_lookup_value`.

    Raises:
        click.BadParameter: More than one ``:``, or either side is empty.
    """
    parts = raw.split(":")
    if len(parts) == 1:
        return parts[0], None
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    raise click.BadParameter(
        f"invalid field spec '{raw}' (expected FIELD or FIELD:RENAME)"
    )


def build_transforms_kv(
    *,
    file: str | None,
    collection: str | None,
    max_matches: int | None,
    min_matches: int | None,
    case_sensitive: bool | None,
    default_match: str | None,
) -> dict[str, str]:
    """Build the transforms.conf kv dict for a lookup-definition stanza.

    Exactly one of ``file``/``collection`` is expected -- callers enforce
    that (usage error, exit 2) before reaching here; this just shapes the
    dict for whichever one was given. ``file`` binds a CSV/mmdb table
    (``filename=...``); ``collection`` binds a KV store collection
    (``external_type=kvstore`` + ``collection=...``).
    """
    kv: dict[str, str] = {}
    if file is not None:
        kv["filename"] = file
    elif collection is not None:
        kv["external_type"] = "kvstore"
        kv["collection"] = collection

    if max_matches is not None:
        kv["max_matches"] = str(max_matches)
    if min_matches is not None:
        kv["min_matches"] = str(min_matches)
    if case_sensitive is not None:
        kv["case_sensitive_match"] = "true" if case_sensitive else "false"
    if default_match is not None:
        kv["default_match"] = default_match
    return kv


def _match_clause(raw: str) -> str:
    """One ``--input`` token -> its ``LOOKUP-`` match-field clause.

    ``--input`` takes the EVENT-side field first (the field the operator
    already has in hand) and the lookup table's column second, after a
    ``:``, only when the names differ (``event_field:lookup_field``).
    Splunk's grammar wants the lookup-table field first on the wire
    (``<match_field> [AS <match_field_in_event>]``), so a renamed pair is
    emitted swapped; an unrenamed one is emitted bare (both sides share
    one name, so order is moot).
    """
    field, lookup_field = parse_field_spec(raw)
    return f"{lookup_field} AS {field}" if lookup_field else field


def _output_clause(raw: str) -> str:
    """One ``--output`` token -> its ``LOOKUP-`` output-field clause.

    ``--output`` already takes the lookup table's column first and the
    event-side rename second (``lookup_field:event_field``) -- the same
    order Splunk's grammar wants (``<output_field> [AS
    <output_field_in_event>]``), so this is a direct mapping, no swap.
    """
    field, renamed = parse_field_spec(raw)
    return f"{field} AS {renamed}" if renamed else field


def build_lookup_value(
    defname: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    *,
    overwrite: bool,
) -> str:
    """Build the ``LOOKUP-<autoname>`` value string for props.conf.

    ``inputs``/``outputs`` are raw ``--input``/``--output`` tokens (each
    ``FIELD`` or ``FIELD:RENAME``); callers enforce at least one of each
    (usage error, exit 2) before reaching here. ``overwrite=False`` emits
    ``OUTPUTNEW`` (only fill fields that don't already exist on the
    event) instead of ``OUTPUT`` (always overwrite).
    """
    verb = "OUTPUT" if overwrite else "OUTPUTNEW"
    match_clause = " ".join(_match_clause(i) for i in inputs)
    output_clause = " ".join(_output_clause(o) for o in outputs)
    return f"{defname} {match_clause} {verb} {output_clause}"
