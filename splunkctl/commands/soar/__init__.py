"""SOAR command group — ``splunkctl soar <subcommand>``."""

import click

from splunkctl.commands.soar import (
    containers_write as _cw,  # noqa: F401  # register writes
)
from splunkctl.commands.soar import (
    playbook_runs as _pr,  # noqa: F401  # register run/runs
)
from splunkctl.commands.soar import (
    playbooks_delete as _pd,  # noqa: F401  # register delete
)
from splunkctl.commands.soar.actions import actions_group
from splunkctl.commands.soar.admin import users_group
from splunkctl.commands.soar.admin_roles_audit import audit_cmd, roles_group
from splunkctl.commands.soar.admin_views import meta, settings, stats
from splunkctl.commands.soar.approvals import approvals_group
from splunkctl.commands.soar.apps import apps_group
from splunkctl.commands.soar.artifacts import artifacts_group
from splunkctl.commands.soar.assets import assets_group, ingest_status_cmd
from splunkctl.commands.soar.cases import cases_group
from splunkctl.commands.soar.containers import containers_group
from splunkctl.commands.soar.functions import functions_group
from splunkctl.commands.soar.indicators import evidence_group, indicators_group
from splunkctl.commands.soar.ingest import ingest_cmd
from splunkctl.commands.soar.lists import lists_group
from splunkctl.commands.soar.notes import notes_group
from splunkctl.commands.soar.playbooks import playbooks_group
from splunkctl.commands.soar.search import search
from splunkctl.commands.soar.system import health, info, license_cmd, test
from splunkctl.commands.soar.vault import vault_group
from splunkctl.commands.soar.workbook_templates import workbook_templates_group


@click.group("soar")
def soar_group() -> None:
    """Splunk SOAR operations — platform reads, containers, playbooks."""


soar_group.add_command(test)
soar_group.add_command(info)
soar_group.add_command(health)
soar_group.add_command(license_cmd)
soar_group.add_command(settings)
soar_group.add_command(stats)
soar_group.add_command(meta)
soar_group.add_command(containers_group)
soar_group.add_command(cases_group)
soar_group.add_command(notes_group)
soar_group.add_command(vault_group)
soar_group.add_command(artifacts_group)
soar_group.add_command(apps_group)
soar_group.add_command(assets_group)
soar_group.add_command(ingest_status_cmd)
soar_group.add_command(playbooks_group)
soar_group.add_command(actions_group)
soar_group.add_command(functions_group)
soar_group.add_command(approvals_group)
soar_group.add_command(lists_group)
soar_group.add_command(indicators_group)
soar_group.add_command(evidence_group)
soar_group.add_command(users_group)
soar_group.add_command(roles_group)
soar_group.add_command(audit_cmd)
soar_group.add_command(workbook_templates_group)
soar_group.add_command(search)
soar_group.add_command(ingest_cmd)
