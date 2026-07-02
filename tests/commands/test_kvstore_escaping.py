"""Tests for kvstore path escaping (CIDR keys, slashes in names).

These assert the REAL wire form, not the argument the mocked ``svc``
method received. ``svc.get/post/delete`` route the path through the
forked SDK's ``Context._abspath``, which wraps a plain ``str`` in
``UrlEncoded(...)`` -- re-quoting it. A path built with a plain-``str``
``_seg`` (``urllib.parse.quote``) therefore gets quoted TWICE on the wire
(``%2F`` becomes ``%252F``), even though a test that only inspects the
mock's received argument (before ``_abspath`` runs) would never see it.
Every test here proves the composed path is already a ``UrlEncoded`` and
is IDEMPOTENT under a second ``UrlEncoded(...)`` pass -- exactly what
``_abspath`` does to it -- so double-encoding is structurally impossible.
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from splunklib.binding import UrlEncoded

from splunkctl.commands.kvstore import _seg
from splunkctl.main import cli

_PATCH = "splunkctl.commands.kvstore.get_client"


def _resp(body: object) -> MagicMock:
    r = MagicMock()
    if isinstance(body, (bytes, bytearray)):
        r.body.read.return_value = body
    else:
        r.body.read.return_value = json.dumps(body).encode()
    return r


def _assert_wire_safe(path: object) -> None:
    """A path is safe from the SDK's ``_abspath`` re-quote iff it's a
    ``UrlEncoded`` AND passing it through ``UrlEncoded(...)`` again --
    exactly what ``_abspath`` does to whatever it's handed -- is a no-op.
    """
    assert isinstance(path, UrlEncoded), f"{path!r} is not a UrlEncoded"
    assert UrlEncoded(path) == path, f"{path!r} is not idempotent under UrlEncoded()"


# --- _seg + composition: the real wire form, proven idempotent ---


def test_seg_returns_urlencoded() -> None:
    seg = _seg("10.0.0.0/24")
    assert isinstance(seg, UrlEncoded)


def test_seg_composed_path_no_double_encode_on_cidr_key() -> None:
    """RED against a plain-``str`` ``_seg`` (``urllib.parse.quote``): a
    second ``UrlEncoded(...)`` pass -- what ``_abspath`` does to any bare
    ``str`` it's handed -- turns '%2F' into '%252F'. Composing with a
    ``UrlEncoded`` ``_seg`` via ``+`` must stay a ``UrlEncoded`` end to
    end, so the second pass is a no-op.
    """
    path = "storage/collections/data/agenttest_g3/" + _seg("10.0.0.0/24")
    assert "10.0.0.0%2F24" in path
    assert "%252F" not in path
    _assert_wire_safe(path)


def test_seg_composed_path_two_segments_no_double_encode() -> None:
    """The update/remove-by-key shape: two ``_seg`` calls in one path."""
    path = (
        "storage/collections/data/"
        + _seg("coll/with/slashes")
        + "/"
        + _seg("10.0.0.0/24")
    )
    assert "%252F" not in path
    _assert_wire_safe(path)


def test_seg_composed_path_survives_space_in_key() -> None:
    """A key containing a space must not come out mangled or re-encoded
    on a second UrlEncoded pass (the regression the prior fix introduced
    on top of the double-encoding bug)."""
    path = "storage/collections/data/agenttest_g3/" + _seg("my key")
    assert "%25" not in path  # no encoded '%' anywhere -- not re-quoted
    _assert_wire_safe(path)


# --- command-level: mocked svc call captures a UrlEncoded, idempotent path ---


@patch(_PATCH)
def test_update_key_with_slash_escapes_path(mock_gc: MagicMock) -> None:
    """Ensure CIDR keys like '10.0.0.0/24' are escaped as path segments,
    and that the captured path is the real wire-safe form (not just the
    string the mock happened to receive)."""
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp({"_key": "10.0.0.0/24"})

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "kvstore",
            "update",
            "agenttest_g3",
            "10.0.0.0/24",
            "--data",
            '{"allowed": true}',
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    call_path = svc.post.call_args[0][0]
    assert "10.0.0.0%2F24" in call_path
    assert "storage/collections/data/agenttest_g3/10.0.0.0%2F24" == call_path
    _assert_wire_safe(call_path)


@patch(_PATCH)
def test_query_collection_with_slash_escapes_path(mock_gc: MagicMock) -> None:
    """Ensure collection names with slashes are escaped in the path, and
    the captured path is the real wire-safe form."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp([])

    result = CliRunner().invoke(
        cli, ["--json", "kvstore", "query", "collection/with/slashes"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once()
    call_path = svc.get.call_args[0][0]
    assert "collection%2Fwith%2Fslashes" in call_path
    assert "storage/collections/data/collection%2Fwith%2Fslashes" == call_path
    _assert_wire_safe(call_path)


@patch(_PATCH)
def test_remove_by_key_with_slash_escapes_path(mock_gc: MagicMock) -> None:
    """remove-by-key builds a two-segment path (collection + key); prove
    it's wire-safe too, not just the single-segment shapes above."""
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(
        cli, ["--yes", "kvstore", "remove", "agenttest_g3", "10.0.0.0/24"]
    )
    assert result.exit_code == 0
    svc.delete.assert_called_once()
    call_path = svc.delete.call_args[0][0]
    assert "storage/collections/data/agenttest_g3/10.0.0.0%2F24" == call_path
    _assert_wire_safe(call_path)


@patch(_PATCH)
def test_remove_by_query_dry_run_no_call(mock_gc: MagicMock) -> None:
    """Ensure dry-run of remove --query does not call delete."""
    result = CliRunner().invoke(
        cli,
        [
            "kvstore",
            "remove",
            "agenttest_g3",
            "--query",
            '{"host": "evil.example"}',
        ],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    # ensure no actual delete happened
    mock_gc.return_value.service.delete.assert_not_called()
