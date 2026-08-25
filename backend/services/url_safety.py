"""Outbound-fetch safety guard, shared by every code path that has the
server make an HTTP request to a URL supplied (directly or indirectly) by a
user: manual job URL ingestion and the Job Verification liveness check.

Both are a textbook SSRF surface — an authenticated user can otherwise point
the server at an internal service or a cloud metadata endpoint
(169.254.169.254) and read the response back through the job's title/
description or the verification notes. This validates the URL itself before
the first request, and every redirect target before it's followed, since a
same-origin-looking URL can still 302 to an internal address.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5_000_000  # generous for an HTML job posting page


class UnsafeURLError(ValueError):
    """A URL failed the outbound-fetch safety check. Message is safe to show a user."""


def _is_unsafe_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparsable -> treat as unsafe, never fetch
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_safe_outbound_url(url: str) -> None:
    """Raise UnsafeURLError if `url` must not be fetched server-side."""
    if not url or not url.strip():
        raise UnsafeURLError("URL is empty.")

    parsed = urlparse(url.strip())

    if parsed.scheme != "https":
        raise UnsafeURLError("Only https:// URLs are allowed.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL must not contain credentials.")

    try:
        host = parsed.hostname
    except ValueError as exc:
        # urlparse raises ValueError for some malformed netlocs (e.g. an
        # unbracketed literal IPv6 host) rather than returning None.
        raise UnsafeURLError("URL host is malformed.") from exc

    if not host:
        raise UnsafeURLError("URL has no host.")
    if "*" in host:
        raise UnsafeURLError("URL host must not contain a wildcard.")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise UnsafeURLError("URL must not target localhost.")

    # Resolve and check every returned address, not just the first — a
    # hostname can round-robin between a public and a private address.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError("URL host could not be resolved.") from exc
    if not infos:
        raise UnsafeURLError("URL host could not be resolved.")

    for info in infos:
        ip_str = info[4][0]
        if _is_unsafe_ip(ip_str):
            raise UnsafeURLError("URL resolves to a private, loopback, or reserved address.")


def fetch_url_safely(
    url: str,
    *,
    user_agent: str,
    timeout_seconds: float,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> httpx.Response:
    """GET a URL server-side, safely: validates the URL and every redirect
    hop before following it, and caps how much of the body is read.

    Redirects are followed manually (client itself has follow_redirects
    disabled) specifically so each hop's target gets the same safety check
    as the original URL — httpx's built-in follow_redirects=True would
    happily chase a redirect straight into a private address.
    """
    assert_safe_outbound_url(url)
    current = url

    with httpx.Client(
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
        follow_redirects=False,
    ) as client:
        for _ in range(max_redirects + 1):
            with client.stream("GET", current) as response:
                location = response.headers.get("location") if response.is_redirect else None
                if location:
                    next_url = urljoin(current, location)
                    assert_safe_outbound_url(next_url)
                    current = next_url
                    continue

                # Not a redirect we're following (either a normal response, or
                # a redirect status with no Location header) — read it, capped,
                # while still inside the stream's context, then rebuild a
                # plain Response so the caller gets normal .text/.status_code
                # access after this function returns (the streaming response
                # itself is unusable once its `with` block exits).
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise UnsafeURLError("Response exceeded the maximum allowed size.")
                    chunks.append(chunk)
                body = b"".join(chunks)
                # iter_bytes() already transparently decompresses (gzip/br/
                # deflate) as it reads — `body` is plain bytes. Drop
                # content-encoding/content-length from the original headers
                # before reconstructing, or the new Response thinks `body`
                # is still compressed and .text double-decompresses it.
                headers = httpx.Headers(response.headers)
                headers.pop("content-encoding", None)
                headers.pop("content-length", None)
                return httpx.Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=body,
                    request=response.request,
                )

    raise UnsafeURLError("Too many redirects.")
