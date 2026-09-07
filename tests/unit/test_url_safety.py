"""SSRF guard for the aggregated fetch surface."""

from app.url_safety import is_safe_url


def test_public_host_allowed():
    ok, reason = is_safe_url("https://example.com/article")
    assert (ok, reason) == (True, "ok")


def test_plain_http_allowed():
    # Not our call to force TLS — plenty of internal/legacy targets are http,
    # and the upstream vendor handles the connection.
    assert is_safe_url("http://example.com")[0] is True


def test_non_http_scheme_blocked():
    for url in ("file:///etc/passwd", "gopher://example.com", "ftp://example.com"):
        ok, reason = is_safe_url(url)
        assert ok is False
        assert reason == "unsupported_scheme"


def test_userinfo_blocked():
    # https://expected.example.com@evil.example/ — the authority is what
    # follows the last '@', so userinfo is a spoofing primitive.
    ok, reason = is_safe_url("https://expected.example.com@evil.example/")
    assert (ok, reason) == (False, "userinfo_not_allowed")


def test_loopback_blocked():
    assert is_safe_url("http://127.0.0.1:8080/admin")[1] == "private_address"
    assert is_safe_url("http://localhost/admin")[1] == "private_address"
    assert is_safe_url("http://[::1]/admin")[1] == "private_address"


def test_cloud_metadata_blocked():
    assert is_safe_url("http://169.254.169.254/latest/meta-data/")[1] == "private_address"


def test_private_ranges_blocked():
    for url in ("http://10.0.0.5/", "http://172.16.3.4/", "http://192.168.1.1/"):
        assert is_safe_url(url)[1] == "private_address"


def test_numeric_literal_loopback_blocked():
    # 2130706433 == 127.0.0.1; written in decimal it dodges a naive
    # string-prefix check on "127.".
    assert is_safe_url("http://2130706433/")[1] == "private_address"


def test_unresolvable_host_is_not_a_safety_failure():
    # The vendor will return its own DNS error; blocking it here would mask a
    # typo as a security rejection.
    assert is_safe_url("https://definitely-not-a-real-host.invalid")[0] is True


def test_empty_and_garbage():
    assert is_safe_url("")[1] == "empty_url"
    # No scheme at all — urlsplit leaves it empty, which is not http(s).
    assert is_safe_url("not a url")[1] == "unsupported_scheme"
    assert is_safe_url("https://")[1] == "missing_host"
