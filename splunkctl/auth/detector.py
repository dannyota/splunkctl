"""Public login-route classification for SAML vs password authentication.

The detector only reads public login pages; it never uses stored credentials
and never treats an ordinary HTTP 401 or a local login form as MFA. A 3xx to a
different host is the reliable SAML signal (the identity provider is external);
SAML/SSO text markers are a fallback for providers that serve a local
interstitial before redirecting.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

import requests

type AuthMode = Literal["password", "browser", "unknown"]

_REDIRECT = (301, 302, 303, 307, 308)


def _different_host(location: str, login_url: str) -> bool:
    """True when a redirect Location targets a different host than login_url.

    A relative or protocol-relative Location stays on the login host and is
    not an external-IdP signal; a scheme/port change on the same host is
    likewise not a different host.
    """
    host = urlsplit(location).hostname
    if host is None:
        return False
    return host != urlsplit(login_url).hostname


def classify(
    *,
    login_url: str,
    status: int,
    headers: Mapping[str, str],
    body: str,
) -> AuthMode:
    """Classify a login-route response without credentials."""
    if status in _REDIRECT:
        location = headers.get("Location", headers.get("location", ""))
        return (
            "browser"
            if location and _different_host(location, login_url)
            else "password"
        )
    if status == 401:
        return "password"
    lowered = body.lower()
    if any(
        marker in lowered for marker in ("saml", "single sign-on", "sign in with sso")
    ):
        return "browser"
    if (
        'type="password"' in lowered
        or 'name="password"' in lowered
        or "name='password'" in lowered
    ):
        return "password"
    return "unknown"


def probe(login_url: str, *, verify: bool, timeout: int) -> AuthMode:
    """GET the login route without following redirects and classify it."""
    try:
        resp = requests.get(
            login_url, allow_redirects=False, verify=verify, timeout=timeout
        )
    except requests.RequestException:
        return "unknown"
    return classify(
        login_url=login_url,
        status=resp.status_code,
        headers=dict(resp.headers),
        body=resp.text,
    )


def siem_login_url(web_url: str) -> str:
    """Splunk Web login route (SAML auto-redirects when configured)."""
    return f"{web_url.rstrip('/')}/en-US/account/login"


def soar_login_url(web_url: str) -> str:
    """SOAR Django login route (SAML auto-redirects when configured)."""
    return f"{web_url.rstrip('/')}/login"


_SAML_SSO_SUFFIX = "/protocol/saml"


def siem_idp_issuer(web_url: str, *, verify: bool, timeout: int) -> str | None:
    """Return the SAML IdP issuer the SIEM is configured against, or ``None``.

    Splunk's SAML login route renders a form that auto-submits to the IdP (its
    ``action`` is the IdP SSO URL); strip the ``/protocol/saml`` suffix to get
    the issuer. Used to derive another product's SSO URL from the same IdP.
    Returns ``None`` when the login route is unreachable, not SAML, or does not
    reveal an issuer.
    """
    login_url = siem_login_url(web_url)
    try:
        resp = requests.get(
            login_url, allow_redirects=False, verify=verify, timeout=timeout
        )
    except requests.RequestException:
        return None
    if resp.status_code in _REDIRECT:
        target = resp.headers.get("Location", "")
    else:
        match = re.search(r'action="([^"]*)"', resp.text)
        target = match.group(1) if match else ""
    if _SAML_SSO_SUFFIX not in target:
        return None
    return target.split(_SAML_SSO_SUFFIX, 1)[0]
