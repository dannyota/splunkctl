"""Shared conf-stanza core — fetch, diff, set, unset, reload.

Both ``conf`` (the generic conf editor) and ``parsers`` (the
props/transforms convenience layer) mutate conf stanzas through this
module, so there is exactly one implementation of the underlying SDK
calls. Functions here are pure SDK plumbing — no ``click``/``output``
dependency — so callers stay free to shape guard previews and error
messages for their own command surface.
"""

from types import SimpleNamespace
from typing import Any


def get_stanza(
    client: Any, conf_name: str, stanza: str, *, app: str | None = None
) -> Any:
    """Fetch one conf stanza entity.

    ``app``, when given, qualifies the lookup with a wildcard-owner
    namespace tuple (the same ``owner="-"`` convention every ``--app``
    list option in this CLI already uses) so a stanza name that exists
    in more than one app resolves instead of raising
    ``AmbiguousReferenceException``.

    Raises:
        KeyError: The conf file or the stanza does not exist.
    """
    conf = client.service.confs[conf_name]
    if app is None:
        return conf[stanza]
    return conf[stanza, SimpleNamespace(owner="-", app=app)]


def diff_lines(current: dict[str, Any], kv: dict[str, str]) -> list[str]:
    """Per-key ``key: old -> new`` preview lines for a set operation.

    A key absent from ``current`` shows ``add`` in place of the old
    value, e.g. ``definition: add -> index=main`` for a brand-new key.
    """
    lines: list[str] = []
    for k, v in kv.items():
        old = current.get(k)
        old_label = "add" if old is None else str(old)
        lines.append(f"  {k}: {old_label} -> {v}")
    return lines


def set_keys(
    client: Any,
    conf_name: str,
    stanza: str,
    kv: dict[str, str],
    *,
    app: str | None = None,
    sharing: str | None = None,
    create_missing: bool = True,
) -> tuple[Any, bool]:
    """Create-or-update a stanza's keys.

    New stanzas (and any stanza when ``sharing`` is given) are promoted
    via :meth:`SplunkClient.set_acl` — new stanzas default to ``app``
    sharing, since user-private stanzas do not apply at index time for
    props/transforms and are surprising defaults elsewhere too.

    ``app``, when given, scopes both the existing-stanza lookup (the same
    wildcard-owner namespace tuple :func:`get_stanza` uses) and a newly
    created stanza's namespace (passed straight through to
    ``Collection.create`` as a namespace kwarg, the same way
    ``dashboards create`` picks its target app). This is the one path
    through ``conf_ops`` that lets a mutation choose *which app* a
    stanza lands in — every other caller (``parsers set``, ``conf set``,
    ``macros set``) writes to the connection's current default
    namespace. Omitted (the default), behavior is unchanged from before
    ``app`` existed.

    Returns:
        The stanza entity and whether it was created.

    Raises:
        KeyError: The stanza is missing and ``create_missing`` is False.
    """
    conf = client.service.confs[conf_name]
    try:
        target = (
            conf[stanza]
            if app is None
            else conf[stanza, SimpleNamespace(owner="-", app=app)]
        )
        target.update(**kv)
        created = False
    except KeyError:
        if not create_missing:
            raise
        if app is not None:
            target = conf.create(stanza, app=app, **kv)
        else:
            target = conf.create(stanza, **kv)
        created = True

    if sharing or created:
        client.set_acl(target, sharing=sharing or "app")
    return target, created


def unset_keys(client: Any, conf_name: str, stanza: str, keys: tuple[str, ...]) -> Any:
    """Clear keys on a stanza.

    The REST API has no true per-key delete; keys are set to the empty
    string, which disables most parsing/config keys.

    Raises:
        KeyError: The stanza does not exist.
    """
    target = client.service.confs[conf_name][stanza]
    target.update(**dict.fromkeys(keys, ""))
    return target


def reload_conf(client: Any, conf_name: str) -> None:
    """POST the conf reload endpoint for one conf file."""
    client.service.post(f"/services/configs/conf-{conf_name}/_reload")
