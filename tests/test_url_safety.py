"""url_safety.py — the SSRF guard shared by manual job URL ingestion and the
Job Verification liveness check. Regression suite for a real, previously
unguarded gap: ingest_job_url()/check_still_open() fetched any user-supplied
URL server-side with no validation and follow_redirects=True, so an
authenticated user could point the server at an internal service or a cloud
metadata endpoint (169.254.169.254) and read the response back.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from backend.services.url_safety import (
    MAX_REDIRECTS,
    UnsafeURLError,
    assert_safe_outbound_url,
    fetch_url_safely,
)


def _fake_resolve(ip: str):
    """Monkeypatch target: makes socket.getaddrinfo return a single fixed IP
    for any hostname, so tests control resolution without real DNS."""

    def _getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


# ---------------------------------------------------------------------------
# assert_safe_outbound_url — pure validation, no network
# ---------------------------------------------------------------------------


def test_rejects_empty_url() -> None:
    with pytest.raises(UnsafeURLError, match="empty"):
        assert_safe_outbound_url("")


def test_rejects_http_scheme_requires_https(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(UnsafeURLError, match="https"):
        assert_safe_outbound_url("http://example.com/jobs/1")


def test_rejects_url_with_embedded_credentials(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(UnsafeURLError, match="credentials"):
        assert_safe_outbound_url("https://user:pass@example.com/jobs/1")


def test_rejects_localhost_by_name() -> None:
    with pytest.raises(UnsafeURLError, match="localhost"):
        assert_safe_outbound_url("https://localhost/jobs/1")
    with pytest.raises(UnsafeURLError, match="localhost"):
        assert_safe_outbound_url("https://foo.localhost/jobs/1")


def test_rejects_loopback_ipv4_literal() -> None:
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved"):
        assert_safe_outbound_url("https://127.0.0.1/jobs/1")


def test_rejects_loopback_ipv6_literal() -> None:
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved"):
        assert_safe_outbound_url("https://[::1]/jobs/1")


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.5",
        "172.16.0.5",
        "192.168.1.5",
    ],
)
def test_rejects_private_range_hostname_resolution(monkeypatch, ip) -> None:
    """A hostname (not an IP literal) that resolves to a private range must
    be rejected too — the check is on the resolved address, not the literal
    text of the URL."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve(ip))
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved"):
        assert_safe_outbound_url("https://internal.example.com/jobs/1")


def test_rejects_link_local_cloud_metadata_address(monkeypatch) -> None:
    """169.254.169.254 specifically: the AWS/GCP/Azure instance metadata
    endpoint — the single most consequential SSRF target in practice."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("169.254.169.254"))
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved"):
        assert_safe_outbound_url("https://metadata.example.com/jobs/1")


def test_rejects_wildcard_host() -> None:
    with pytest.raises(UnsafeURLError, match="wildcard"):
        assert_safe_outbound_url("https://*.example.com/jobs/1")


def test_rejects_host_that_fails_dns_resolution(monkeypatch) -> None:
    def _fail(*_a, **_k):
        raise socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(UnsafeURLError, match="resolved"):
        assert_safe_outbound_url("https://does-not-resolve.example.invalid/jobs/1")


def test_accepts_a_normal_public_https_url(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    assert_safe_outbound_url("https://example.com/jobs/1")  # must not raise


def test_accepts_explicit_port_443_with_allowed_hosts(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    assert_safe_outbound_url(
        "https://job-boards.greenhouse.io:443/instead/jobs/1",
        allowed_hosts=frozenset({"job-boards.greenhouse.io"}),
    )


def test_out_of_range_port_raises_unsafe_url_error_not_valueerror(monkeypatch) -> None:
    """https://...:65536 makes urllib.parse.ParseResult.port raise ValueError.
    The SSRF guard must convert that into UnsafeURLError so callers never see
    a raw traceback or HTTP 500."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(UnsafeURLError) as exc_info:
        assert_safe_outbound_url("https://example.com:65536/jobs/1")
    assert exc_info.type is UnsafeURLError
    assert "65536" not in str(exc_info.value)


def test_rejects_nonstandard_valid_port_8443(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(UnsafeURLError, match="non-default port"):
        assert_safe_outbound_url("https://example.com:8443/jobs/1")


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1:jobs",
        "https://[::1/jobs",
        "https://[::ffff:127.0.0.1:443/jobs",
        "https://[https://example.com/jobs",
        "https://[::1]:65536/jobs",
        "https://[::1]:abc/jobs",
    ],
)
def test_malformed_bracketed_ipv6_or_netloc_raises_unsafe_url_error(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        assert_safe_outbound_url(url)


def test_fetch_rejects_out_of_range_port_before_any_request(monkeypatch) -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text="should never run")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError):
        fetch_url_safely(
            "https://job-boards.greenhouse.io:65536/instead/jobs/1",
            user_agent="test",
            timeout_seconds=5,
            allowed_hosts=frozenset({"job-boards.greenhouse.io"}),
        )
    assert called["n"] == 0


def test_allowed_hosts_rejects_suffix_trick_without_dns(monkeypatch) -> None:
    with pytest.raises(UnsafeURLError, match="not supported"):
        assert_safe_outbound_url(
            "https://job-boards.greenhouse.io.evil.example/instead/jobs/1",
            allowed_hosts=frozenset({"job-boards.greenhouse.io"}),
        )


def test_fetch_with_allowed_hosts_rejects_redirect_to_different_host(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example.com/next"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError):
        fetch_url_safely(
            "https://jobs.lever.co/acme/abc-123",
            user_agent="test",
            timeout_seconds=5,
            allowed_hosts=frozenset({"jobs.lever.co"}),
        )


def test_fetch_client_disables_trust_env(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    captured: dict = {}

    class RecordingClient(_RealClient):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))

    monkeypatch.setattr(httpx, "Client", RecordingClient)
    fetch_url_safely("https://example.com/ok", user_agent="test", timeout_seconds=5)
    assert captured.get("trust_env") is False


def test_rejects_a_hostname_where_any_resolved_address_is_private(monkeypatch) -> None:
    """A hostname can round-robin between multiple addresses — one public,
    one private. Every returned address must be checked, not just the
    first, since the OS/network stack picks which one is actually used."""

    def _multi(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", _multi)
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved"):
        assert_safe_outbound_url("https://mixed.example.com/jobs/1")


# ---------------------------------------------------------------------------
# fetch_url_safely — mocked network, no real requests
# ---------------------------------------------------------------------------


_RealClient = httpx.Client  # captured before any test monkeypatches httpx.Client itself


def _client_with_transport(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def test_fetch_rejects_unsafe_url_before_any_request(monkeypatch) -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text="should never run")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError):
        fetch_url_safely("https://127.0.0.1/jobs/1", user_agent="test", timeout_seconds=5)
    assert called["n"] == 0


def test_fetch_follows_a_redirect_to_a_safe_destination(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/first":
            return httpx.Response(302, headers={"location": "https://example.com/second"})
        return httpx.Response(200, text="<title>Real Job</title>")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    response = fetch_url_safely("https://example.com/first", user_agent="test", timeout_seconds=5)
    assert response.status_code == 200
    assert "Real Job" in response.text


def test_fetch_rejects_a_redirect_to_a_private_destination(monkeypatch) -> None:
    """The core regression: the *initial* URL is safe and would have passed
    the old code's (nonexistent) checks, but the site 302s to a private
    address. Proves redirects are validated per-hop, not just the start."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError, match="private, loopback, or reserved|https"):
        fetch_url_safely("https://example.com/first", user_agent="test", timeout_seconds=5)


def test_fetch_rejects_excessive_redirects(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    hop_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hop_count["n"] += 1
        return httpx.Response(302, headers={"location": f"https://example.com/hop{hop_count['n']}"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError, match="redirects"):
        fetch_url_safely("https://example.com/start", user_agent="test", timeout_seconds=5)
    assert hop_count["n"] == MAX_REDIRECTS + 1


def test_fetch_rejects_oversized_response(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1000)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    with pytest.raises(UnsafeURLError, match="size"):
        fetch_url_safely("https://example.com/big", user_agent="test", timeout_seconds=5, max_bytes=100)


def test_fetch_returns_readable_text_for_a_gzip_encoded_response(monkeypatch) -> None:
    """Regression: iter_bytes() already transparently decompresses as it
    reads, so the reconstructed Response must not keep the original
    content-encoding/content-length headers — otherwise .text tries to
    decompress the already-plain bytes a second time and raises. Caught live
    against a real server during this same audit (example.com is served
    gzip-encoded), not just in this mocked test."""
    import gzip

    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    plain = "<title>Backend Intern</title>"
    compressed = gzip.compress(plain.encode())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=compressed,
            headers={"content-encoding": "gzip", "content-length": str(len(compressed))},
        )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _client_with_transport(handler))
    response = fetch_url_safely("https://example.com/gzipped", user_agent="test", timeout_seconds=5)
    assert response.text == plain
