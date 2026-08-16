"""Product session adapters — convert browser cookies into API sessions.

SIEM extracts the Splunk Web ``splunkd_<port>`` session value and validates it
against the management API. SOAR keeps the Django ``sessionid`` and
``csrftoken`` cookies and validates against ``/rest/version``. Logout is
best-effort: the local session is always removed even if the remote endpoint
rejects the request.
"""

from __future__ import annotations

from typing import Literal, Protocol

import requests

from splunkctl.auth.session import Target

type ValidationStatus = Literal["valid", "expired", "unreachable"]


class ExtractError(RuntimeError):
    """Browser cookies did not contain the expected product session values."""


class SessionAdapter(Protocol):
    """A product's cookie->session mapping plus validation and logout."""

    target: Target

    def extract(self, cookies: dict[str, str]) -> dict[str, str]:
        """Map browser cookies to the product's API session values."""
        ...

    def validate(
        self, values: dict[str, str], *, api_base: str, verify: bool, timeout: int
    ) -> ValidationStatus:
        """Check ``values`` and return their current validation status."""
        ...

    def logout(
        self, values: dict[str, str], *, web_url: str, verify: bool, timeout: int
    ) -> None:
        """Best-effort remote logout for the given session values."""
        ...


class SIEMAdapter:
    """Splunk Enterprise SIEM adapter."""

    target: Target = "siem"

    def extract(self, cookies: dict[str, str]) -> dict[str, str]:
        """Extract the Splunk session key from the ``splunkd_*`` cookie."""
        for name, value in cookies.items():
            if name.startswith("splunkd_"):
                return {"session_key": value, "cookie": name}
        raise ExtractError(
            "SIEM browser login did not produce a Splunk session cookie "
            "(splunkd_<port>). The identity-provider flow may not have "
            "completed."
        )

    def validate(
        self, values: dict[str, str], *, api_base: str, verify: bool, timeout: int
    ) -> ValidationStatus:
        """Validate the session key against the management API."""
        try:
            resp = requests.get(
                f"{api_base.rstrip('/')}/services/server/info",
                params={"output_mode": "json"},
                headers={"Authorization": f"Splunk {values['session_key']}"},
                verify=verify,
                timeout=timeout,
            )
        except (requests.RequestException, OSError):
            return "unreachable"
        if resp.status_code == 200:
            return "valid"
        if resp.status_code in (401, 403):
            return "expired"
        return "unreachable"

    def logout(
        self, values: dict[str, str], *, web_url: str, verify: bool, timeout: int
    ) -> None:
        """GET the Splunk Web logout route to end the session."""
        requests.get(
            f"{web_url.rstrip('/')}/en-US/account/logout",
            cookies={values["cookie"]: values["session_key"]},
            verify=verify,
            timeout=timeout,
        )


class SOARAdapter:
    """Splunk SOAR adapter."""

    target: Target = "soar"

    def extract(self, cookies: dict[str, str]) -> dict[str, str]:
        """Extract the Django ``sessionid`` and ``csrftoken`` cookies."""
        session_id = cookies.get("sessionid")
        csrf = cookies.get("csrftoken")
        if not session_id or not csrf:
            raise ExtractError(
                "SOAR browser login did not produce sessionid and csrftoken "
                "cookies. The identity-provider flow may not have completed."
            )
        return {"sessionid": session_id, "csrftoken": csrf}

    def validate(
        self, values: dict[str, str], *, api_base: str, verify: bool, timeout: int
    ) -> ValidationStatus:
        """Validate the cookies against ``/rest/version``."""
        try:
            resp = requests.get(
                f"{api_base.rstrip('/')}/rest/version",
                cookies=values,
                verify=verify,
                timeout=timeout,
            )
        except (requests.RequestException, OSError):
            return "unreachable"
        if resp.status_code == 200:
            return "valid"
        if resp.status_code in (401, 403):
            return "expired"
        return "unreachable"

    def logout(
        self, values: dict[str, str], *, web_url: str, verify: bool, timeout: int
    ) -> None:
        """POST the SOAR logout route to end the session."""
        requests.post(
            f"{web_url.rstrip('/')}/logout",
            cookies=values,
            headers={"X-CSRFToken": values["csrftoken"]},
            verify=verify,
            timeout=timeout,
        )


_ADAPTERS: dict[Target, SessionAdapter] = {
    "siem": SIEMAdapter(),
    "soar": SOARAdapter(),
}


def get_adapter(target: Target) -> SessionAdapter:
    """Return the session adapter for a product target."""
    return _ADAPTERS[target]
