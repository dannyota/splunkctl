"""Tests for parsers commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

PATCH_GC = "splunkctl.commands.parsers.get_client"


def _mock_service(
    mock_gc: MagicMock,
    stanzas: list[MagicMock] | None = None,
) -> MagicMock:
    mock_conf = MagicMock()
    if stanzas is not None:
        mock_conf.list.return_value = stanzas
    mock_svc = MagicMock()
    mock_svc.confs.__getitem__.return_value = mock_conf
    mock_gc.return_value.service = mock_svc
    return mock_conf


def _stanza(name: str, content: dict[str, str]) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.content = content
    return s


# --- sourcetypes ---


@patch(PATCH_GC)
def test_sourcetypes_lists_stanzas(mock_gc: MagicMock) -> None:
    st = _stanza(
        "syslog", {"category": "OS", "description": "Syslog", "TRANSFORMS": ""}
    )
    _mock_service(mock_gc, [st])

    result = CliRunner().invoke(cli, ["--json", "parsers", "sourcetypes"])
    assert result.exit_code == 0
    assert "syslog" in result.output
    assert "OS" in result.output


@patch(PATCH_GC)
def test_sourcetypes_empty(mock_gc: MagicMock) -> None:
    _mock_service(mock_gc, [])

    result = CliRunner().invoke(cli, ["--json", "parsers", "sourcetypes"])
    assert result.exit_code == 0


# --- get ---


@patch(PATCH_GC)
def test_get_sourcetype(mock_gc: MagicMock) -> None:
    st = _stanza("syslog", {"category": "OS", "TIME_FORMAT": "%b %d"})
    conf = _mock_service(mock_gc)
    conf.__getitem__.return_value = st

    result = CliRunner().invoke(cli, ["--json", "parsers", "get", "syslog"])
    assert result.exit_code == 0
    assert "syslog" in result.output
    assert "OS" in result.output


@patch(PATCH_GC)
def test_get_sourcetype_not_found(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(cli, ["parsers", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


# --- extractions ---


@patch(PATCH_GC)
def test_extractions_lists_transforms(mock_gc: MagicMock) -> None:
    t = _stanza("syslog-extract", {"REGEX": "(.+)", "FORMAT": "$1", "DEST_KEY": ""})
    _mock_service(mock_gc, [t])

    result = CliRunner().invoke(cli, ["--json", "parsers", "extractions"])
    assert result.exit_code == 0
    assert "syslog-extract" in result.output
    assert "(.+)" in result.output


@patch(PATCH_GC)
def test_extractions_filters_by_sourcetype(mock_gc: MagicMock) -> None:
    t1 = _stanza("syslog-host", {"REGEX": "(.+)", "FORMAT": "", "DEST_KEY": ""})
    t2 = _stanza("apache-uri", {"REGEX": "\\S+", "FORMAT": "", "DEST_KEY": ""})
    _mock_service(mock_gc, [t1, t2])

    result = CliRunner().invoke(
        cli, ["--json", "parsers", "extractions", "--sourcetype", "syslog"]
    )
    assert result.exit_code == 0
    assert "syslog-host" in result.output
    assert "apache-uri" not in result.output


# --- create ---


@patch(PATCH_GC)
def test_create_dry_run(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)

    result = CliRunner().invoke(cli, ["parsers", "create", "--sourcetype", "my-st"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    conf.create.assert_not_called()


@patch(PATCH_GC)
def test_create_applies_with_yes(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "parsers",
            "create",
            "--sourcetype",
            "my-st",
            "--category",
            "Custom",
        ],
    )
    assert result.exit_code == 0
    conf.create.assert_called_once_with("my-st", category="Custom")


# --- update ---


@patch(PATCH_GC)
def test_update_dry_run(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)

    result = CliRunner().invoke(
        cli, ["parsers", "update", "my-st", "--category", "Custom"]
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    conf.__getitem__.return_value.update.assert_not_called()


@patch(PATCH_GC)
def test_update_applies_with_yes(mock_gc: MagicMock) -> None:
    st = _stanza("my-st", {})
    conf = _mock_service(mock_gc)
    conf.__getitem__.return_value = st

    result = CliRunner().invoke(
        cli,
        ["--yes", "parsers", "update", "my-st", "--category", "NewCat"],
    )
    assert result.exit_code == 0
    st.update.assert_called_once_with(category="NewCat")


@patch(PATCH_GC)
def test_update_no_options_errors(mock_gc: MagicMock) -> None:
    _mock_service(mock_gc)

    result = CliRunner().invoke(cli, ["parsers", "update", "my-st"])
    assert result.exit_code != 0
    assert "Nothing to update" in result.output


@patch(PATCH_GC)
def test_update_not_found(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(
        cli, ["--yes", "parsers", "update", "nope", "--category", "X"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output


# --- delete ---


@patch(PATCH_GC)
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)

    result = CliRunner().invoke(cli, ["parsers", "delete", "my-st"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    conf.__getitem__.return_value.delete.assert_not_called()


@patch(PATCH_GC)
def test_delete_applies_with_yes(mock_gc: MagicMock) -> None:
    st = _stanza("my-st", {})
    conf = _mock_service(mock_gc)
    conf.__getitem__.return_value = st

    result = CliRunner().invoke(cli, ["--yes", "parsers", "delete", "my-st"])
    assert result.exit_code == 0
    st.delete.assert_called_once()


@patch(PATCH_GC)
def test_delete_not_found(mock_gc: MagicMock) -> None:
    conf = _mock_service(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(cli, ["--yes", "parsers", "delete", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output
