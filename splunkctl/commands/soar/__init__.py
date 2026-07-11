"""SOAR command group — ``splunkctl soar <subcommand>``."""

import click

from splunkctl.commands.soar.system import health, info, license_cmd, test


@click.group("soar")
def soar_group() -> None:
    """Splunk SOAR operations — platform reads, containers, playbooks."""


soar_group.add_command(test)
soar_group.add_command(info)
soar_group.add_command(health)
soar_group.add_command(license_cmd)
