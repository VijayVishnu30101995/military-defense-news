"""Outbound HTTP for URLs that come from feeds and admins rather than from this code.

Feed items name arbitrary URLs, so every fetch is limited to public http(s) hosts (no
loopback, private ranges or cloud metadata, including via redirects) and to a fixed
number of bytes, so a hostile or broken server can't exhaust memory.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib import request
from urllib.parse import urlparse

MAX_FEED_BYTES = 10 * 1024 * 1024
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class UnsafeURLError(ValueError):
    pass


class ResponseTooLargeError(ValueError):
    pass


def check_public_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is http(s) on a host that resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError(f"Only http and https URLs can be fetched, not {parsed.scheme or 'none'}")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve {parsed.hostname}: {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if not address.is_global:
            raise UnsafeURLError(f"{parsed.hostname} resolves to a non-public address")


class _CheckedRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = request.build_opener(_CheckedRedirectHandler)


def open_public_url(req: request.Request, *, timeout: float):
    """`urlopen` for public http(s) URLs only; redirects are checked the same way."""
    check_public_url(req.full_url)
    return _opener.open(req, timeout=timeout)


def read_limited(response, max_bytes: int) -> bytes:
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResponseTooLargeError(f"Response is larger than {max_bytes // (1024 * 1024)} MB")
    return data
