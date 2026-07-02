"""Tests for the shared conf-stanza core (conf_ops)."""

from unittest.mock import MagicMock

import pytest

from splunkctl.commands.conf_ops import (
    diff_lines,
    get_stanza,
    reload_conf,
    set_keys,
    unset_keys,
)

# --- get_stanza ---


def test_get_stanza_returns_entity() -> None:
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    result = get_stanza(client, "macros", "my_macro")
    assert result is stanza
    client.service.confs.__getitem__.assert_called_with("macros")
    conf.__getitem__.assert_called_with("my_macro")


def test_get_stanza_missing_raises_keyerror() -> None:
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("nope")
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    with pytest.raises(KeyError):
        get_stanza(client, "macros", "nope")


def test_get_stanza_with_app_scopes_the_lookup() -> None:
    """``app`` qualifies the lookup with a wildcard-owner namespace tuple.

    Disambiguates a stanza name that exists in more than one app —
    without it, ``Collection.__getitem__`` raises ``AmbiguousReferenceException``
    instead of resolving.
    """
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    result = get_stanza(client, "macros", "my_macro", app="my_app")
    assert result is stanza
    (key,), _kwargs = conf.__getitem__.call_args
    name, ns = key
    assert name == "my_macro"
    assert ns.app == "my_app"
    assert ns.owner == "-"


def test_get_stanza_without_app_uses_plain_lookup() -> None:
    """No ``app`` keeps the original single-arg lookup (no namespace tuple)."""
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    get_stanza(client, "macros", "my_macro")
    conf.__getitem__.assert_called_once_with("my_macro")


# --- diff_lines ---


def test_diff_lines_new_key_shows_add() -> None:
    lines = diff_lines({}, {"definition": "index=main"})
    assert lines == ["  definition: add -> index=main"]


def test_diff_lines_changed_key_shows_old_new() -> None:
    lines = diff_lines({"definition": "index=old"}, {"definition": "index=new"})
    assert lines == ["  definition: index=old -> index=new"]


def test_diff_lines_unchanged_key_still_shown() -> None:
    lines = diff_lines({"definition": "same"}, {"definition": "same"})
    assert lines == ["  definition: same -> same"]


def test_diff_lines_preserves_kv_order() -> None:
    lines = diff_lines({}, {"b": "2", "a": "1"})
    assert lines == ["  b: add -> 2", "  a: add -> 1"]


# --- set_keys ---


def test_set_keys_updates_existing_stanza() -> None:
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    target, created = set_keys(client, "macros", "my_macro", {"definition": "x"})
    assert created is False
    assert target is stanza
    stanza.update.assert_called_once_with(definition="x")
    client.set_acl.assert_not_called()


def test_set_keys_creates_missing_stanza_default_app_sharing() -> None:
    created_entity = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    conf.create.return_value = created_entity
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    target, created = set_keys(client, "macros", "my_macro", {"definition": "x"})
    assert created is True
    assert target is created_entity
    conf.create.assert_called_once_with("my_macro", definition="x")
    client.set_acl.assert_called_once_with(created_entity, sharing="app")


def test_set_keys_creates_missing_stanza_explicit_sharing() -> None:
    created_entity = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    conf.create.return_value = created_entity
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    set_keys(client, "macros", "my_macro", {"definition": "x"}, sharing="global")
    client.set_acl.assert_called_once_with(created_entity, sharing="global")


def test_set_keys_existing_stanza_explicit_sharing_still_applied() -> None:
    """Sharing is promoted on an update too, not only on create."""
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    set_keys(client, "macros", "my_macro", {"definition": "x"}, sharing="global")
    client.set_acl.assert_called_once_with(stanza, sharing="global")


def test_set_keys_with_app_scopes_existing_stanza_lookup() -> None:
    """``app`` qualifies the update lookup the same way ``get_stanza`` does."""
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    target, created = set_keys(
        client, "transforms", "my_def", {"filename": "x.csv"}, app="my_app"
    )
    assert created is False
    assert target is stanza
    (key,), _kwargs = conf.__getitem__.call_args
    name, ns = key
    assert name == "my_def"
    assert ns.app == "my_app"
    assert ns.owner == "-"
    stanza.update.assert_called_once_with(filename="x.csv")


def test_set_keys_without_app_keeps_plain_lookup() -> None:
    """No ``app`` preserves the original single-arg lookup (regression)."""
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    set_keys(client, "macros", "my_macro", {"definition": "x"})
    conf.__getitem__.assert_called_once_with("my_macro")


def test_set_keys_with_app_creates_scoped_stanza() -> None:
    """``app`` on a create passes through to ``Collection.create`` as a
    namespace kwarg, landing the new stanza in that app rather than the
    connection's default namespace."""
    created_entity = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_def")
    conf.create.return_value = created_entity
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    target, created = set_keys(
        client, "transforms", "my_def", {"filename": "x.csv"}, app="my_app"
    )
    assert created is True
    assert target is created_entity
    conf.create.assert_called_once_with("my_def", app="my_app", filename="x.csv")
    client.set_acl.assert_called_once_with(created_entity, sharing="app")


def test_set_keys_without_app_create_omits_app_kwarg() -> None:
    """Regression: default (no ``app``) still calls ``create`` with no
    ``app=`` kwarg at all, not ``app=None`` — keeps every existing caller's
    call-shape (and any SDK version sensitive to an explicit ``None``)
    unchanged."""
    created_entity = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    conf.create.return_value = created_entity
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    set_keys(client, "macros", "my_macro", {"definition": "x"})
    conf.create.assert_called_once_with("my_macro", definition="x")


def test_set_keys_no_create_missing_raises() -> None:
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    with pytest.raises(KeyError):
        set_keys(
            client, "macros", "my_macro", {"definition": "x"}, create_missing=False
        )
    conf.create.assert_not_called()


# --- unset_keys ---


def test_unset_keys_sets_empty_string() -> None:
    stanza = MagicMock()
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    target = unset_keys(client, "macros", "my_macro", ("definition", "args"))
    assert target is stanza
    stanza.update.assert_called_once_with(definition="", args="")


def test_unset_keys_missing_stanza_raises() -> None:
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("nope")
    client = MagicMock()
    client.service.confs.__getitem__.return_value = conf

    with pytest.raises(KeyError):
        unset_keys(client, "macros", "nope", ("definition",))


# --- reload_conf ---


def test_reload_conf_posts_expected_path() -> None:
    client = MagicMock()
    reload_conf(client, "macros")
    client.service.post.assert_called_once_with("/services/configs/conf-macros/_reload")
