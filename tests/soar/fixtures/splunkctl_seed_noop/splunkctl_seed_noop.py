"""
Minimal no-op playbook for splunkctl seed and round-trip testing.

Playbook: splunkctl_seed_noop
Type: automation
Labels: events
"""

import phantom.rules as phantom


def on_start(container):
    phantom.debug("splunkctl_seed_noop: start")

    ## Custom Code Start
    ## Custom Code End

    return


def on_finish(container, summary):
    phantom.debug("splunkctl_seed_noop: finish")

    ## Custom Code Start
    ## Custom Code End

    return
