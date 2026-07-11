"""SOAR command group — ``splunkctl soar <subcommand>``."""

import click

from splunkctl.commands.soar import (
    containers_write as _cw,  # noqa: F401  # register writes
)
from splunkctl.commands.soar.admin_views import meta, settings, stats
from splunkctl.commands.soar.containers import containers_group
from splunkctl.commands.soar.notes import notes_group
from splunkctl.commands.soar.system import health, info, license_cmd, test


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
