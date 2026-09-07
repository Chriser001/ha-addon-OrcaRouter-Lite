"""SSRF guard for the aggregated fetch surface.

`/v1/network/fetch` takes a caller-supplied URL and asks an upstream vendor
to retrieve it. Even though the request is issued by the vendor (so the
socket never originates here), the target is still chosen by an untrusted
caller, and several of these vendors resolve and follow redirects from their
own network — which for a self-hosted install is frequently the operator's
LAN. Blocking private/link-local targets here is cheap and stops the
obvious "fetch http://169.254.169.254/latest/meta-data/" probe.

Deliberately conservative: only http/https, no userinfo, and a DNS
resolution check before the request leaves. Resolution happens at check time
rather than connect time, so a DNS-rebinding target can still slip through —
accepted, because the actual socket is opened by the upstream vendor on a
network we don't control, and there is no local connect to re-check.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("http", "https")


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 4:
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True
        return ip.is_private
    # IPv6: loopback (::1), link-local (fe80::/10), unique-local (fc00::/7),
    # and the IPv4-mapped forms of the v4 ranges above.
    if ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ipaddress.ip_address(ip).is_private:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(mapped) and _is_blocked_ip(mapped)


def is_safe_url(url: str) -> tuple[bool, str]:
    """Return `(ok, reason)` for a caller-supplied fetch target.

    `reason` is a short, operator-readable code (also what the API returns),
    so the message never has to echo the rejected host back verbatim.
    """
    if not url or not isinstance(url, str):
        return False, "empty_url"
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False, "unparseable_url"

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, "unsupported_scheme"
    if parts.username or parts.password:
        # `https://expected.example.com@evil.example/` — the authority is the
        # part after the last `@`, so userinfo is a straight-up spoofing tool.
        return False, "userinfo_not_allowed"
    host = parts.hostname
    if not host:
        return False, "missing_host"

    try:
        # Numeric literals short-circuit: "http://2130706433" is 127.0.0.1.
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _is_blocked_ip(literal):
        return False, "private_address"

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable is the upstream's problem, not a safety violation —
        # let it through so the vendor returns its own clear DNS error.
        return True, "ok"

    for _family, _type, _proto, _canon, sockaddr in resolved:
        raw = sockaddr[0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if _is_blocked_ip(addr):
            return False, "private_address"
    return True, "ok"
