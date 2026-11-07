"""Detect only executable pipeline write commands."""

import pytest


@pytest.mark.parametrize(
    ("spl", "expected"),
    [
        ("search index=main", []),
        ("outputlookup=x", []),
        ("index=main outputlookup=x", []),
        ("| search outputlookup=x", []),
        ("index=main | search outputlookup x", []),
        ('index=main | eval outputlookup="a"', []),
        ("`mymacro([collect])`", []),
        ("index=main | where collect=1", []),
        ("| collect = 1", []),
        ("| outputlookup x", ["outputlookup"]),
        ("index=main | collect index=y", ["collect"]),
        ("index=main [ search a | collect index=b ]", ["collect"]),
        (" \n``` comment ``` | outputlookup x", ["outputlookup"]),
        ("index=main\n| collect index=y", ["collect"]),
        ("index=main | outputlookup x", ["outputlookup"]),
        ("index=main |outputlookup x", ["outputlookup"]),
        ('index=main | eval x="| outputlookup x"', []),
        ("index=main | eval x='| collect x'", []),
        ("index=main [ search index=other | collect index=x ]", ["collect"]),
        ("| OUTPUTLOOKUP x", ["outputlookup"]),
        ("search outputlookup x", []),
        ("``` | collect x ``` index=main", []),
        ("index=main | ``` comment ``` outputlookup x", ["outputlookup"]),
        (
            "| outputlookup x | collect index=y | outputlookup z",
            ["outputlookup", "collect"],
        ),
        ("[collect index=x]", ["collect"]),
    ],
)
def test_find_write_commands(spl: str, expected: list[str]) -> None:
    from splunkctl.spl_safety import find_write_commands

    assert find_write_commands(spl) == expected


@pytest.mark.parametrize(
    "command",
    [
        "outputlookup",
        "collect",
        "mcollect",
        "meventcollect",
        "sendalert",
        "delete",
        "outputcsv",
        "outputtext",
        "sendemail",
        "runshellscript",
        "script",
    ],
)
def test_each_write_command(command: str) -> None:
    from splunkctl.spl_safety import find_write_commands

    assert find_write_commands(f"index=main | {command} target") == [command]


def test_escaped_quote_does_not_expose_literal_pipeline() -> None:
    from splunkctl.spl_safety import find_write_commands

    assert find_write_commands(r'| eval x="escaped \" | collect x" | stats count') == []
