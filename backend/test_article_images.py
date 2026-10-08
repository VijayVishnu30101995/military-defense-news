import os
from urllib.parse import urlparse

import pytest
from app.database import SessionLocal
from app.services.collector import SourceCollectorService

ARTICLE_HTML = """
<html><head>
<meta property="og:image" content="https://cdn.example.com/photos/frigate-launch.jpg">
</head><body>
<img src="https://cdn.example.com/ads/banner.jpg">
</body></html>
"""


def test_og_image_is_preferred_over_inline_images() -> None:
    url = SourceCollectorService._extract_image_from_html(ARTICLE_HTML, include_inline=True)

    assert url == "https://cdn.example.com/photos/frigate-launch.jpg"


def test_json_ld_article_image_is_used_when_meta_is_missing() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "NewsArticle",
     "headline": "Carrier group deploys",
     "image": {"@type": "ImageObject", "url": "https://cdn.example.com/photos/carrier.jpg"}}
    </script>
    </head><body><img src="https://cdn.example.com/ads/banner.jpg"></body></html>
    """

    url = SourceCollectorService._extract_image_from_html(html, include_inline=False)

    assert url == "https://cdn.example.com/photos/carrier.jpg"


def test_json_ld_ignores_non_article_nodes_such_as_organisations() -> None:
    html = """
    <script type="application/ld+json">
    {"@graph": [
        {"@type": "Organization", "logo": "https://cdn.example.com/brand/logo-big.png",
         "image": "https://cdn.example.com/brand/hq.jpg"},
        {"@type": "NewsArticle", "image": ["https://cdn.example.com/photos/tank-column.jpg"]}
    ]}
    </script>
    """

    url = SourceCollectorService._extract_image_from_html(html, include_inline=False)

    assert url == "https://cdn.example.com/photos/tank-column.jpg"


def test_inline_image_is_skipped_when_include_inline_is_false() -> None:
    html = '<html><body><img src="https://cdn.example.com/photos/inline.jpg"></body></html>'

    assert SourceCollectorService._extract_image_from_html(html, include_inline=False) is None
    assert SourceCollectorService._extract_image_from_html(html, include_inline=True) == (
        "https://cdn.example.com/photos/inline.jpg"
    )


def test_malformed_json_ld_is_ignored() -> None:
    html = '<script type="application/ld+json">{not valid json</script>'

    assert SourceCollectorService._extract_image_from_html(html, include_inline=False) is None


def test_best_article_image_prefers_article_page_over_feed_thumbnail(monkeypatch) -> None:
    service = SourceCollectorService(SessionLocal())
    monkeypatch.setattr(service, "_fetch_article_html", lambda _url: ARTICLE_HTML)

    class Source:
        website_url = "https://example.com"

    feed_item = {"image_url": "https://cdn.example.com/stock/generic-navy.jpg"}

    url = service._best_article_image("https://example.com/story", feed_item, Source())

    assert url == "https://cdn.example.com/photos/frigate-launch.jpg"


def test_best_article_image_falls_back_to_feed_then_inline(monkeypatch) -> None:
    service = SourceCollectorService(SessionLocal())

    class Source:
        website_url = "https://example.com"

    feed_item = {"image_url": "https://cdn.example.com/feed/thumb.jpg"}

    monkeypatch.setattr(service, "_fetch_article_html", lambda _url: "<html></html>")
    assert service._best_article_image("https://example.com/s", feed_item, Source()) == (
        "https://cdn.example.com/feed/thumb.jpg"
    )

    no_feed_image = '<html><body><img src="https://cdn.example.com/photos/only-inline.jpg"></body></html>'
    monkeypatch.setattr(service, "_fetch_article_html", lambda _url: no_feed_image)
    assert service._best_article_image("https://example.com/s", {}, Source()) == (
        "https://cdn.example.com/photos/only-inline.jpg"
    )


def test_fetch_article_html_skips_google_news_redirects() -> None:
    service = SourceCollectorService(SessionLocal())

    assert service._fetch_article_html("https://news.google.com/articles/abc") is None


GOOGLE_NEWS_LINK = "https://news.google.com/rss/articles/CBMiExample?oc=5"


def test_google_news_link_is_decoded_to_publisher_article(monkeypatch) -> None:
    import app.services.collector as collector_module

    seen = {}

    def fake_decoder(url, interval=None, proxy=None):
        seen["url"] = url
        return {"status": True, "decoded_url": "https://www.navalnews.com/story/destroyer"}

    monkeypatch.setattr(collector_module, "gnewsdecoder", fake_decoder)
    fetched = {}

    class FakeResponse:
        class headers:
            @staticmethod
            def get_content_type():
                return "text/html"

        def read(self):
            return ARTICLE_HTML.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        fetched["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(collector_module.request, "urlopen", fake_urlopen)

    html = SourceCollectorService(SessionLocal())._fetch_article_html(GOOGLE_NEWS_LINK)

    assert seen["url"] == GOOGLE_NEWS_LINK
    assert fetched["url"] == "https://www.navalnews.com/story/destroyer"
    assert html == ARTICLE_HTML


def test_failed_google_news_decode_returns_none_without_fetching(monkeypatch) -> None:
    import app.services.collector as collector_module

    monkeypatch.setattr(
        collector_module, "gnewsdecoder", lambda url, interval=None, proxy=None: {"status": False, "message": "nope"}
    )
    monkeypatch.setattr(
        collector_module.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch Google's page")),
    )

    assert SourceCollectorService(SessionLocal())._fetch_article_html(GOOGLE_NEWS_LINK) is None


def test_hung_google_news_decode_times_out(monkeypatch) -> None:
    import time
    import app.services.collector as collector_module

    monkeypatch.setattr(collector_module, "GOOGLE_NEWS_DECODE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(collector_module, "gnewsdecoder", lambda url, interval=None, proxy=None: time.sleep(1))

    assert collector_module._decode_google_news_url(GOOGLE_NEWS_LINK) is None


def test_decoded_google_news_url_must_not_point_back_to_google(monkeypatch) -> None:
    import app.services.collector as collector_module

    monkeypatch.setattr(
        collector_module, "gnewsdecoder",
        lambda url, interval=None, proxy=None: {"status": True, "decoded_url": "https://news.google.com/x"},
    )

    assert collector_module._decode_google_news_url(GOOGLE_NEWS_LINK) is None


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_GNEWS"), reason="set RUN_LIVE_GNEWS=1 to hit news.google.com")
def test_live_google_news_links_decode_to_publishers() -> None:
    from app.services.collector import _decode_google_news_url

    url = _decode_google_news_url(
        "https://news.google.com/rss/articles/CBMivgFBVV95cUxNN2lVS3E0aTFaaE5tdWZVT2tobVN0VS1ZeFlFNVlTUmxkdkdqLTFPcnM0LUo2X0w3TUZuWll0bHlNWHJuS0x1Tnk4bWw3Ukp6Nzhjc1RSLXByWXRVUFc0eklnb3c4eEJZYml4ZTFyUmVtWkdoblNndW1qZnBMQXY1czNjNG9heENtd2ZNQ2xYOGx5QTJZVWV1LVVBQ3NqWmFVVTVqQnc2NUI0Q2xzbGxLaFMyRnY4anl6TlhYbERB?oc=5"
    )

    assert url is not None and urlparse(url).netloc != "news.google.com"
