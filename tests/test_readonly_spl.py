from unittest.mock import Mock

import pytest

from splunkctl.request_policy import ReadOnlyError
from splunkctl.spl_safety import WRITE_COMMANDS, check_readonly_spl


@pytest.mark.parametrize(
    "command",
    sorted(
        WRITE_COMMANDS
        | {
            "map",
            "savedsearch",
            "dbxquery",
            "dbxoutput",
            "run",
            "customcommand",
            "tscollect",
            "rest",
            "from",
        }
    ),
)
def test_unsafe_commands(command):
    with pytest.raises(ReadOnlyError, match=command):
        check_readonly_spl(f"| makeresults | {command} x")


def test_safe_literals():
    check_readonly_spl('search index=main | eval x="| delete" | stats count')


def test_macro_expansion():
    parser = Mock(
        return_value={"commands": [{"command": "makeresults"}, {"command": "stats"}]}
    )
    check_readonly_spl("| `safe` | stats count", parser=parser)
    parser.assert_called_once()
    parser.return_value = {"commands": [{"command": "outputlookup"}]}
    with pytest.raises(ReadOnlyError, match="outputlookup"):
        check_readonly_spl("| `unsafe`", parser=parser)


@pytest.mark.parametrize(
    "response", [{}, {"commands": []}, {"commands": [{"command": "custom"}]}]
)
def test_unknown_expansion(response):
    with pytest.raises(ReadOnlyError):
        check_readonly_spl("| `macro`", parser=lambda _: response)


def test_parser_failure():
    with pytest.raises(ReadOnlyError, match="parser"):
        check_readonly_spl(
            "search [search index=main]", parser=Mock(side_effect=OSError())
        )


@pytest.mark.parametrize(
    "spl",
    [
        "| stats count |",
        '| eval x="broken',
        "search [search index=main",
        "| stats count || delete",
    ],
)
def test_malformed(spl):
    with pytest.raises(ReadOnlyError):
        check_readonly_spl(spl)
