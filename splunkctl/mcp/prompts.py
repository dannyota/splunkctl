"""MCP prompts — canned multi-step workflows for agent entry points."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import AssistantMessage, Message, UserMessage


def register_prompts(mcp: FastMCP) -> None:
    """Register canned workflow prompts on the server."""

    @mcp.prompt(
        name="investigate-ioc",
        description=(
            "Multi-step plan to investigate an indicator of compromise "
            "across SIEM and SOAR."
        ),
    )
    def investigate_ioc(
        ioc_value: str,
        ioc_type: Literal["ip", "domain", "hash", "url"] = "ip",
    ) -> list[Message]:
        """Investigate an IOC across Splunk SIEM and SOAR."""
        return [
            AssistantMessage(
                "Follow this workflow to investigate the IOC. "
                "Use the splunkctl tools for each step — adapt the SPL "
                "and parameters to the target environment.",
            ),
            UserMessage(
                f"Investigate {ioc_type} IOC: {ioc_value}\n\n"
                "1. Search SIEM for the IOC:\n"
                f'   search run "index=* {ioc_value} | stats count by '
                f'index, sourcetype, src, dest"\n\n'
                "2. Check ES threat intelligence (if available):\n"
                f'   search run "| inputlookup threat_intel_by_{ioc_type}'
                f' | search {ioc_type}={ioc_value}"\n\n'
                "3. Pivot to SOAR — search for matching indicators:\n"
                f'   soar indicators list --filter "value={ioc_value}"\n\n'
                "4. List related SOAR containers:\n"
                f'   soar containers list --filter "has_artifact={ioc_value}"\n\n'
                "5. Summarize: affected hosts/users, timeline, severity, "
                "and recommended response.",
            ),
        ]

    @mcp.prompt(
        name="triage-notable",
        description=(
            "Triage a Splunk ES notable event: inspect it, assess severity, "
            "ingest into SOAR, promote to case, and assign an owner."
        ),
    )
    def triage_notable(
        notable_id: str = "",
        search_query: str = "",
    ) -> list[Message]:
        """Triage an ES notable event end-to-end."""
        if notable_id:
            search_step = (
                "1. Retrieve the notable event:\n"
                f'   search run "| search event_id={notable_id} '
                f'index=notable"\n'
            )
        elif search_query:
            search_step = (
                f"1. Search for the notable event:\n   search run {search_query!r}\n"
            )
        else:
            search_step = (
                "1. Search for recent notable events:\n"
                '   search run "index=notable | head 20 | table '
                'event_id, rule_name, severity, urgency, owner, status"\n'
            )
        return [
            AssistantMessage(
                "Follow this workflow to triage a notable event from "
                "SIEM through SOAR. Adapt parameters to the environment.",
            ),
            UserMessage(
                f"{search_step}\n"
                "2. Review severity and urgency. Check the detection rule:\n"
                "   rules get <rule_name>\n\n"
                "3. Ingest the notable into SOAR to create a container:\n"
                "   soar ingest --label notable_triage <event_json>\n\n"
                "4. Promote the container to a case:\n"
                "   soar containers update <container_id> "
                "--case-type case --yes\n\n"
                "5. Assign an owner:\n"
                "   soar containers update <container_id> "
                "--owner <analyst> --yes\n\n"
                "6. Summarize: container ID, case status, assigned owner, "
                "and recommended next actions.",
            ),
        ]

    @mcp.prompt(
        name="audit-detection",
        description=(
            "Audit a detection rule: inspect its definition, check recent "
            "firings, and verify it is working as expected."
        ),
    )
    def audit_detection(rule_name: str) -> list[Message]:
        """Audit a saved-search detection rule."""
        return [
            AssistantMessage(
                "Follow this workflow to audit the detection rule. "
                "Use the splunkctl tools for each step.",
            ),
            UserMessage(
                f"Audit detection rule: {rule_name}\n\n"
                "1. Get the rule definition:\n"
                f"   rules get {rule_name!r}\n\n"
                "2. Search for recent firings:\n"
                f'   search run "index=notable rule_name=\\"{rule_name}\\"'
                f' | head 20 | stats count by urgency, status"\n\n'
                "3. List triggered alerts:\n"
                f"   alerts list --name {rule_name!r}\n\n"
                "4. Test the rule by running its search:\n"
                "   Copy the SPL from step 1 and run:\n"
                "   search run <spl> --limit 10\n\n"
                "5. Summarize: rule health (firing? suppressed?), "
                "recent hit count, and any tuning recommendations.",
            ),
        ]

    @mcp.prompt(
        name="export-state",
        description=(
            "Guide for exporting Splunk configuration state as code "
            "using the state pull workflow."
        ),
    )
    def export_state(
        types: str = "savedsearches,macros,lookups",
        app: str = "search",
    ) -> list[Message]:
        """Guide for pulling Splunk state as code."""
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        steps: list[str] = []
        for i, t in enumerate(type_list, 1):
            steps.append(f"{i}. Pull {t}:\n   state pull --type {t} --app {app}\n")
        n = len(type_list) + 1
        steps.append(
            f"{n}. Review the exported files in the state/ directory "
            "and commit to version control."
        )
        return [
            AssistantMessage(
                "Follow this workflow to export Splunk configuration "
                "state as code. Each pull writes to the state/ directory.",
            ),
            UserMessage(
                f"Export state for app={app}, types: {', '.join(type_list)}\n\n"
                + "\n".join(steps),
            ),
        ]
