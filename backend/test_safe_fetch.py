import io

import pytest

from app.services.safe_fetch import ResponseTooLargeError, UnsafeURLError, check_public_url, read_limited


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://8.8.8.8/feed.xml",
        "http://127.0.0.1:8001/api/v1/sources",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/rss",
        "http://192.168.1.1/",
        "http://[::1]/",
        "https:///no-host",
    ],
)
def test_rejects_non_public_urls(url) -> None:
    with pytest.raises(UnsafeURLError):
        check_public_url(url)


def test_allows_public_address() -> None:
    check_public_url("https://8.8.8.8/feed.xml")


def test_read_limited_rejects_oversized_body() -> None:
    assert read_limited(io.BytesIO(b"x" * 10), 10) == b"x" * 10
    with pytest.raises(ResponseTooLargeError):
        read_limited(io.BytesIO(b"x" * 11), 10)
