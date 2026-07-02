"""Tests for `lookups auto` (props.conf LOOKUP-* wiring).

Covers >=1-input/>=1-output validation (exit 2), dry-run diff previews,
delegation to `conf_ops.set_keys` (the actual LOOKUP- value-string
construction, including OUTPUT/OUTPUTNEW and AS-rename direction, is
unit tested directly against `lookups_wiring` in
test_lookups_wiring.py), and the guard. `lookups define`/`lookups
definitions` live in test_lookups_define.py.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.lookups.get_client"


def _conf(mock_gc: MagicMock) -> MagicMock:
    """Wire ``get_client(ctx).service.confs[...]`` to a fresh conf mock."""
    conf = MagicMock()
    mock_gc.return_value.service.confs.__getitem__.return_value = conf
    return conf


# --- lookups auto: validation ---


def test_auto_requires_at_least_one_input() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "auto",
            "agenttest_h4_def",
            "--sourcetype",
            "agenttest_h4_st",
            "--output",
            "col",
        ],
    )
    assert result.exit_code == 2


def test_auto_requires_at_least_one_output() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "auto",
            "agenttest_h4_def",
            "--sourcetype",
            "agenttest_h4_st",
            "--input",
            "host",
        ],
    )
    assert result.exit_code == 2


def test_auto_requires_sourcetype() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "auto",
            "agenttest_h4_def",
            "--input",
            "host",
            "--output",
            "col",
        ],
    )
    assert result.exit_code == 2


# --- lookups auto: dry run ---


@patch(_PATCH)
def test_auto_dry_run_names_props_stanza_and_lookup_key(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "auto",
            "agenttest_h4_def",
            "--sourcetype",
            "agenttest_h4_st",
            "--input",
            "host",
            "--output",
            "col",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output
    assert "props.conf" in result.output
    assert "agenttest_h4_st" in result.output
    assert "LOOKUP-agenttest_h4_def" in result.output
    assert "agenttest_h4_def host OUTPUT col" in result.output
    conf.create.assert_not_called()


# --- lookups auto: delegation to conf_ops.set_keys ---


@patch(_PATCH)
def test_auto_delegates_expected_value_string(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--output",
                "col",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "props",
        "agenttest_h4_st",
        {"LOOKUP-agenttest_h4_def": "agenttest_h4_def host OUTPUT col"},
        app=None,
    )


@patch(_PATCH)
def test_auto_no_overwrite_uses_outputnew(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--output",
                "col",
                "--no-overwrite",
            ],
        )
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "props",
        "agenttest_h4_st",
        {"LOOKUP-agenttest_h4_def": "agenttest_h4_def host OUTPUTNEW col"},
        app=None,
    )


@patch(_PATCH)
def test_auto_name_option_overrides_lookup_key_suffix(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--output",
                "col",
                "--name",
                "custom_auto",
            ],
        )
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "props",
        "agenttest_h4_st",
        {"LOOKUP-custom_auto": "agenttest_h4_def host OUTPUT col"},
        app=None,
    )


@patch(_PATCH)
def test_auto_multi_input_output(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--input",
                "user:username",
                "--output",
                "col1",
                "--output",
                "col2:renamed2",
            ],
        )
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "props",
        "agenttest_h4_st",
        {
            "LOOKUP-agenttest_h4_def": (
                "agenttest_h4_def host username AS user OUTPUT col1 col2 AS renamed2"
            )
        },
        app=None,
    )


@patch(_PATCH)
def test_auto_app_option_scopes_lookup_and_set_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--output",
                "col",
                "--app",
                "my_app",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "props",
        "agenttest_h4_st",
        {"LOOKUP-agenttest_h4_def": "agenttest_h4_def host OUTPUT col"},
        app="my_app",
    )


@patch(_PATCH)
def test_auto_requires_yes_to_apply(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_st")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        result = CliRunner().invoke(
            cli,
            [
                "lookups",
                "auto",
                "agenttest_h4_def",
                "--sourcetype",
                "agenttest_h4_st",
                "--input",
                "host",
                "--output",
                "col",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_not_called()
