"""Local transport constraints for the MCP server."""

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def require_loopback_host(host: str) -> str:
    """Return a permitted loopback host or reject remote binding."""
    if host not in LOOPBACK_HOSTS:
        allowed = ", ".join(LOOPBACK_HOSTS)
        raise ValueError(f"MCP HTTP host must be loopback ({allowed}); got {host!r}")
    return host


def local_mcp_url(host: str, port: int) -> str:
    """Build an MCP URL for an allowed loopback host."""
    checked = require_loopback_host(host)
    authority = f"[{checked}]" if ":" in checked else checked
    return f"http://{authority}:{port}/mcp"
