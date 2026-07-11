"""SOAR command group — ``splunkctl soar <subcommand>``."""

import click

from splunkctl.commands.soar import (
    containers_write as _cw,  # noqa: F401  # register writes
)
from splunkctl.commands.soar.admin_views import meta, settings, stats
from splunkctl.commands.soar.apps import apps_group
from splunkctl.commands.soar.artifacts import artifacts_group
from splunkctl.commands.soar.assets import assets_group, ingest_status_cmd
from splunkctl.commands.soar.containers import containers_group
from splunkctl.commands.soar.notes import notes_group
from splunkctl.commands.soar.playbooks import playbooks_group
from splunkctl.commands.soar.system import health, info, license_cmd, test
from splunkctl.commands.soar.vault import vault_group


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
soar_group.add_command(notes_group)
soar_group.add_command(vault_group)
soar_group.add_command(artifacts_group)
soar_group.add_command(apps_group)
soar_group.add_command(assets_group)
soar_group.add_command(ingest_status_cmd)
soar_group.add_command(playbooks_group)
