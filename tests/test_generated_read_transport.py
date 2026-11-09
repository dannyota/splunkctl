"""Audit production read generators at the real SDK dispatch boundary."""

import io
import re
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner
from splunklib.client import Service

from splunkctl.commands import alerts, audit, datamodels, doctor, es, lookups, search
from splunkctl.commands.state_io_blobs import _download_csv
from splunkctl.request_context import invocation
from splunkctl.transport import sdk_handler


@pytest.fixture
def sdk_read():
    seen = []

    def low_level(url, message, **kwargs):
        path = urlsplit(str(url)).path
        seen.append((path, message))
        if message["method"] == "POST":
            query = parse_qs(message["body"].decode())["search"][0]
            body = (
                b'{"results":[{"event_id":"example"}]}'
                if query.endswith("| head 1")
                else b'{"results":[]}'
            )
        elif path.endswith("/search/parser"):
            # A macro expanding to a writer must never reach dispatch.
            body = b'{"commands":[{"command":"outputlookup"}]}'
        elif path.endswith("/apps/local/SplunkEnterpriseSecuritySuite"):
            body = (
                b'<feed xmlns="http://www.w3.org/2005/Atom" '
                b'xmlns:s="http://dev.splunk.com/ns/rest">'
                b"<entry><title>SplunkEnterpriseSecuritySuite</title>"
                b'<link rel="alternate" '
                b'href="/services/apps/local/SplunkEnterpriseSecuritySuite"/>'
                b'<content type="text/xml"><s:dict/></content></entry></feed>'
            )
        elif path.endswith("/server/info"):
            body = (
                b'<feed xmlns="http://www.w3.org/2005/Atom" '
                b'xmlns:s="http://dev.splunk.com/ns/rest">'
                b"<entry><title>info</title>"
                b'<link rel="alternate" href="/services/server/info"/>'
                b'<content type="text/xml"><s:dict>'
                b'<s:key name="version">10.0.0</s:key>'
                b"</s:dict></content></entry></feed>"
            )
        elif path.endswith(("/server/health/splunkd", "/kvstore/status")):
            body = b'{"entry":[{"content":{}}]}'
        else:
            body = (
                b"<feed><title>empty</title></feed>"
                if "output_mode=json" not in str(url)
                else b'{"entry":[]}'
            )
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(body)}

    service = Service(
        host="example.test",
        username="reader",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    service._splunk_version = (10, 0, 0)
    service._instance_type = "enterprise"
    client = SimpleNamespace(
        service=service,
        lookup_table_files=SimpleNamespace(list=lambda **kwargs: [object()]),
    )
    return client, seen


def dispatched(seen):
    return [
        parse_qs(message["body"].decode())["search"][0]
        for _, message in seen
        if message["method"] == "POST"
    ]


@pytest.mark.parametrize(
    "module,command,args,expected",
    [
        (
            lookups,
            lookups.lookups_group,
            ["download", "example.csv"],
            '| inputlookup "example.csv"',
        ),
        (
            es,
            es.es_group,
            ["notables", "list"],
            "search index=notable | sort - _time"
            " | rename _time as time, rule_name as rule"
            " | table time, rule, security_domain, urgency, status, owner, event_id",
        ),
        (
            es,
            es.es_group,
            ["notables", "get", "example"],
            'search index=notable event_id="example" | sort - _time | head 1',
        ),
        (audit, audit.audit_group, ["changes"], "search index=_audit"),
        (
            search,
            search.search_group,
            ["metrics", "--index", "metrics"],
            '| mcatalog values(metric_name) WHERE index="metrics"',
        ),
        (
            search,
            search.search_group,
            ["metrics", "--index", "metrics", "--metric", "cpu"],
            '| mcatalog values(_dims) WHERE metric_name="cpu" AND index="metrics"',
        ),
    ],
)
def test_generated_read_commands_real_sdk(sdk_read, module, command, args, expected):
    client, seen = sdk_read
    with (
        patch.object(module, "get_client", return_value=client),
        invocation("read", True),
    ):
        result = CliRunner().invoke(command, args, obj={})
    assert result.exit_code == 0, (result.output, result.exception)
    assert dispatched(seen) == [expected]


def test_state_lookup_generator_real_sdk(sdk_read):
    client, seen = sdk_read
    with invocation("state pull", True):
        _download_csv(client.service, "example.csv", "search")
    assert dispatched(seen) == ['| inputlookup "example.csv"']


@pytest.mark.parametrize(
    "hostile",
    [
        "x | outputlookup x",
        'x" | outputlookup x',
        "`write_macro`",
        'x\\" | outputlookup x',
    ],
)
@pytest.mark.parametrize(
    "generator",
    ["lookup", "state", "index", "metric", "notable-list", "notable-get", "audit"],
)
def test_generated_hostile_inputs_real_sdk(sdk_read, hostile, generator):
    client, seen = sdk_read
    if generator == "state":
        with invocation("state pull", True):
            _download_csv(client.service, hostile, "search")
    else:
        module, command, args = {
            "lookup": (lookups, lookups.lookups_group, ["download", hostile]),
            "index": (search, search.search_group, ["metrics", "--index", hostile]),
            "metric": (
                search,
                search.search_group,
                ["metrics", "--index", "metrics", "--metric", hostile],
            ),
            "notable-list": (
                es,
                es.es_group,
                ["notables", "list", "--owner", hostile, "--rule", hostile],
            ),
            "notable-get": (es, es.es_group, ["notables", "get", hostile]),
            "audit": (
                audit,
                audit.audit_group,
                [
                    "changes",
                    "--user",
                    hostile,
                    "--action",
                    hostile,
                    "--object-type",
                    hostile,
                ],
            ),
        }[generator]
        with (
            patch.object(module, "get_client", return_value=client),
            invocation("read", True),
        ):
            result = CliRunner().invoke(command, args, obj={})
        assert result.exit_code == 0, (result.output, result.exception)
    queries = dispatched(seen)
    assert len(queries) == 1
    if generator == "audit":
        assert queries == ["search index=_audit"]
    else:
        # Every hostile value is confined to a quoted literal. Independently
        # remove escaped characters/literals and check no writer or macro remains.
        outside = re.sub(r'"(?:\\.|[^"\\])*"', '"literal"', queries[0])
        assert "outputlookup" not in outside
        assert "`" not in outside
    assert not any(path.endswith("/parser") for path, _ in seen)


@pytest.mark.parametrize(
    "module,command,args,route",
    [
        (datamodels, datamodels.datamodels_group, ["list"], "/datamodel/model"),
        (datamodels, datamodels.datamodels_group, ["acceleration"], "/datamodel/model"),
        (alerts, alerts.alerts_group, ["list"], "/alerts/fired_alerts"),
        (doctor, doctor.doctor_cmd, [], "/server/info"),
    ],
)
def test_rest_read_commands_real_sdk(sdk_read, tmp_path, module, command, args, route):
    """These commands read REST resources; they do not currently generate SPL."""
    client, seen = sdk_read
    with (
        patch.object(module, "get_client", return_value=client),
        patch.object(doctor, "_check_soar"),
        patch.object(doctor, "_check_mcp_registered"),
        invocation("read", True),
    ):
        result = CliRunner().invoke(
            command, args, obj={"config": str(tmp_path / "missing.yaml")}
        )
    assert result.exit_code == (1 if module is doctor else 0), (
        result.output,
        result.exception,
    )
    assert any(path.rstrip("/").endswith(route) for path, _ in seen)
    assert all(message["method"] == "GET" for _, message in seen)
    assert "read-only:" not in result.output
    if module is doctor:
        assert "[Permissions]" in result.output
        assert "[MCP]" in result.output


@pytest.mark.parametrize("name", ["x\n| outputlookup x", "x\r", "x\x00"])
def test_state_lookup_unsafe_names_refused_before_sdk(sdk_read, name):
    from splunkctl.commands.common import UnsafeLookupNameError

    client, seen = sdk_read
    with invocation("state pull", True), pytest.raises(UnsafeLookupNameError):
        _download_csv(client.service, name, "search")
    assert seen == []
