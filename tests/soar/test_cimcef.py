"""Tests for CIM-to-CEF mapping and row-to-artifact transforms."""

from __future__ import annotations

from typing import Any

from splunkctl.soar.cimcef import (
    CEF_CONTAINS_MAP,
    CIM_CEF_MAP,
    artifact_name_for_row,
    auto_cef_types,
    container_name_for_row,
    map_severity,
    row_sdi,
    row_to_cef,
)

# ---------------------------------------------------------------------------
# CIM_CEF_MAP data checks
# ---------------------------------------------------------------------------


class TestCimCefMap:
    def test_bytesIn_fixed(self) -> None:
        """Upstream typo ``butesIn`` is corrected to ``bytesIn``."""
        assert CIM_CEF_MAP["bytes_in"] == "bytesIn"

    def test_src_maps_to_sourceAddress(self) -> None:
        assert CIM_CEF_MAP["src"] == "sourceAddress"

    def test_dest_maps_to_destinationAddress(self) -> None:
        assert CIM_CEF_MAP["dest"] == "destinationAddress"

    def test_url_maps_to_requestURL(self) -> None:
        assert CIM_CEF_MAP["url"] == "requestURL"

    def test_user_maps_to_destinationUserName(self) -> None:
        assert CIM_CEF_MAP["user"] == "destinationUserName"


# ---------------------------------------------------------------------------
# CEF_CONTAINS_MAP data checks
# ---------------------------------------------------------------------------


class TestCefContainsMap:
    def test_sourceAddress_has_ip(self) -> None:
        assert "ip" in CEF_CONTAINS_MAP["sourceAddress"]

    def test_requestURL_has_url(self) -> None:
        assert "url" in CEF_CONTAINS_MAP["requestURL"]

    def test_fileHash_has_hash(self) -> None:
        assert "hash" in CEF_CONTAINS_MAP["fileHash"]


# ---------------------------------------------------------------------------
# map_severity
# ---------------------------------------------------------------------------


class TestMapSeverity:
    def test_severity_high(self) -> None:
        assert map_severity({"severity": "high"}) == "high"

    def test_severity_critical_maps_to_high(self) -> None:
        assert map_severity({"severity": "critical"}) == "high"

    def test_severity_low(self) -> None:
        assert map_severity({"severity": "low"}) == "low"

    def test_severity_informational(self) -> None:
        assert map_severity({"severity": "informational"}) == "low"

    def test_severity_medium(self) -> None:
        assert map_severity({"severity": "medium"}) == "medium"

    def test_urgency_fallback(self) -> None:
        assert map_severity({"urgency": "high"}) == "high"

    def test_severity_takes_precedence(self) -> None:
        assert map_severity({"severity": "low", "urgency": "high"}) == "low"

    def test_default_medium(self) -> None:
        assert map_severity({}) == "medium"

    def test_multivalue_highest_wins(self) -> None:
        assert map_severity({"severity": "low,high"}) == "high"

    def test_multivalue_list(self) -> None:
        assert map_severity({"severity": ["informational", "critical"]}) == "high"

    def test_empty_string(self) -> None:
        assert map_severity({"severity": ""}) == "medium"


# ---------------------------------------------------------------------------
# row_sdi
# ---------------------------------------------------------------------------


class TestRowSdi:
    def test_uses_event_id(self) -> None:
        row: dict[str, Any] = {"event_id": "EVT-123", "src": "1.2.3.4"}
        assert row_sdi(row, "event_id") == "EVT-123"

    def test_falls_back_to_hash(self) -> None:
        row: dict[str, Any] = {"src": "1.2.3.4", "dest": "5.6.7.8"}
        sdi = row_sdi(row, "event_id")
        assert len(sdi) == 64  # SHA-256 hex digest

    def test_hash_deterministic(self) -> None:
        row: dict[str, Any] = {"a": "1", "b": "2"}
        assert row_sdi(row, "event_id") == row_sdi(row, "event_id")

    def test_custom_sdi_field(self) -> None:
        row: dict[str, Any] = {"my_id": "X99", "src": "10.0.0.1"}
        assert row_sdi(row, "my_id") == "X99"

    def test_whitespace_only_falls_to_hash(self) -> None:
        row: dict[str, Any] = {"event_id": "  ", "src": "1.2.3.4"}
        sdi = row_sdi(row, "event_id")
        assert len(sdi) == 64


# ---------------------------------------------------------------------------
# row_to_cef
# ---------------------------------------------------------------------------


class TestRowToCef:
    def test_basic_mapping(self) -> None:
        row: dict[str, Any] = {"src": "1.2.3.4", "dest_port": "443"}
        cef = row_to_cef(row)
        assert cef["sourceAddress"] == "1.2.3.4"
        assert cef["destinationPort"] == "443"

    def test_unmapped_fields_dropped(self) -> None:
        row: dict[str, Any] = {"src": "1.2.3.4", "custom_field": "val"}
        cef = row_to_cef(row)
        assert "custom_field" not in cef

    def test_include_unmapped(self) -> None:
        row: dict[str, Any] = {"src": "1.2.3.4", "custom_field": "val"}
        cef = row_to_cef(row, include_unmapped=True)
        assert cef["custom_field"] == "val"

    def test_internal_fields_excluded(self) -> None:
        row: dict[str, Any] = {
            "src": "1.2.3.4",
            "_raw": "raw data",
            "_time": "2026-01-01",
        }
        cef = row_to_cef(row, include_unmapped=True)
        assert "_raw" not in cef
        assert "_time" not in cef

    def test_empty_values_skipped(self) -> None:
        row: dict[str, Any] = {"src": "", "dest": "5.6.7.8"}
        cef = row_to_cef(row)
        assert "sourceAddress" not in cef
        assert cef["destinationAddress"] == "5.6.7.8"

    def test_custom_map(self) -> None:
        custom_map = {"my_src": "sourceAddress"}
        row: dict[str, Any] = {"my_src": "10.0.0.1", "src": "1.2.3.4"}
        cef = row_to_cef(row, cim_map=custom_map)
        assert cef["sourceAddress"] == "10.0.0.1"
        # Standard src not in custom map -> not mapped
        assert len(cef) == 1

    def test_none_values_skipped(self) -> None:
        row: dict[str, Any] = {"src": None, "dest": "5.6.7.8"}
        cef = row_to_cef(row)
        assert "sourceAddress" not in cef

    def test_notable_fields_preserved(self) -> None:
        """ES notable fields map through CIM->CEF."""
        row: dict[str, Any] = {
            "src": "10.0.0.1",
            "dest": "10.0.0.2",
            "user": "admin",
            "event_id": "EVT-001",
            "rule_name": "Brute Force",
            "security_domain": "access",
            "risk_score": "85",
        }
        cef = row_to_cef(row, include_unmapped=True)
        assert cef["sourceAddress"] == "10.0.0.1"
        assert cef["destinationAddress"] == "10.0.0.2"
        assert cef["destinationUserName"] == "admin"
        # Unmapped notable fields pass through
        assert cef["event_id"] == "EVT-001"
        assert cef["risk_score"] == "85"


# ---------------------------------------------------------------------------
# auto_cef_types
# ---------------------------------------------------------------------------


class TestAutoCefTypes:
    def test_known_keys(self) -> None:
        cef = {"sourceAddress": "1.2.3.4", "destinationPort": "443"}
        types = auto_cef_types(cef)
        assert "ip" in types["sourceAddress"]
        assert "port" in types["destinationPort"]

    def test_unknown_keys_omitted(self) -> None:
        cef = {"custom_field": "val"}
        types = auto_cef_types(cef)
        assert "custom_field" not in types

    def test_custom_map(self) -> None:
        custom: dict[str, list[str]] = {"myField": ["custom type"]}
        cef = {"myField": "val"}
        types = auto_cef_types(cef, contains_map=custom)
        assert types["myField"] == ["custom type"]


# ---------------------------------------------------------------------------
# container_name_for_row
# ---------------------------------------------------------------------------


class TestContainerName:
    def test_name_field(self) -> None:
        row: dict[str, Any] = {"custom": "My Event", "rule_name": "Rule"}
        assert container_name_for_row(row, name_field="custom") == "My Event"

    def test_template(self) -> None:
        row: dict[str, Any] = {"rule_name": "Rule"}
        assert container_name_for_row(row, template="Custom Name") == "Custom Name"

    def test_rule_name(self) -> None:
        row: dict[str, Any] = {"rule_name": "Brute Force"}
        assert container_name_for_row(row) == "Brute Force"

    def test_search_name_fallback(self) -> None:
        row: dict[str, Any] = {"search_name": "My Search"}
        assert container_name_for_row(row) == "My Search"

    def test_default_fallback(self) -> None:
        row: dict[str, Any] = {"_time": "2026-01-01", "source": "syslog"}
        name = container_name_for_row(row)
        assert "Splunk Log Entry" in name
        assert "2026-01-01" in name
        assert "syslog" in name

    def test_name_field_takes_precedence(self) -> None:
        row: dict[str, Any] = {"custom": "Override", "rule_name": "Rule"}
        assert (
            container_name_for_row(row, template="Template", name_field="custom")
            == "Override"
        )


# ---------------------------------------------------------------------------
# artifact_name_for_row
# ---------------------------------------------------------------------------


class TestArtifactName:
    def test_search_name(self) -> None:
        assert artifact_name_for_row({"search_name": "DNS Lookup"}) == "DNS Lookup"

    def test_default(self) -> None:
        assert artifact_name_for_row({}) == "Field Values"

    def test_empty_search_name(self) -> None:
        assert artifact_name_for_row({"search_name": ""}) == "Field Values"
