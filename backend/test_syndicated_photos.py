from app.database import SessionLocal
from app.services.collector import SourceCollectorService

TITLE = "Airbus tests Valkyrie drone in Europe, plans 2029 combat readiness"


def _search_feed(*copies: tuple[str, str, str]) -> bytes:
    items = "".join(
        f'<item><title>{title} - {name}</title><link>https://news.google.com/rss/articles/{i}</link>'
        f'<source url="{url}">{name}</source></item>'
        for i, (title, name, url) in enumerate(copies)
    )
    return f"<rss><channel>{items}</channel></rss>".encode()


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self, size: int = -1) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _lookup(monkeypatch, feed: bytes, pages: dict[str, str], publisher_host="www.reuters.com"):
    import app.services.syndicated_photos as module

    searched = {}

    def fake_open(req, timeout=None):
        searched["url"] = req.full_url
        return _Response(feed)

    monkeypatch.setattr(module, "open_public_url", fake_open)
    service = SourceCollectorService(SessionLocal())
    fetched = []

    def fake_fetch(link, publisher_url=None):
        fetched.append(publisher_url)
        return pages.get(publisher_url)

    monkeypatch.setattr(service, "_fetch_article_html", fake_fetch)
    return module.find_syndicated_photo(service, TITLE, publisher_host), fetched, searched


def _page(image: str) -> str:
    return f'<html><head><meta property="og:image" content="{image}"></head></html>'


def test_takes_the_photo_from_a_near_identical_copy_and_credits_the_outlet(monkeypatch) -> None:
    feed = _search_feed(
        ("Joe Manganiello responds after Sofia Vergara likes post", "Yahoo", "https://sg.news.yahoo.com"),
        (TITLE, "Yahoo Finance Canada", "https://ca.finance.yahoo.com"),
    )
    pages = {"https://ca.finance.yahoo.com": _page("https://s.yimg.com/photos/valkyrie.jpg")}

    found, fetched, searched = _lookup(monkeypatch, feed, pages)

    assert found == ("https://s.yimg.com/photos/valkyrie.jpg", "Yahoo Finance Canada")
    # The unrelated story is never fetched.
    assert fetched == ["https://ca.finance.yahoo.com"]
    assert "-site%3Areuters.com" in searched["url"]


def test_skips_social_posts_market_sites_and_the_publisher_itself(monkeypatch) -> None:
    feed = _search_feed(
        (TITLE, "X", "https://x.com"),
        (TITLE, "Threads", "https://www.threads.com"),
        (TITLE, "TradingView", "https://www.tradingview.com"),
        (TITLE, "Reuters", "https://www.reuters.com"),
        (TITLE, "Reuters Connect", "https://www.reutersconnect.com"),
    )

    found, fetched, _ = _lookup(monkeypatch, feed, {})

    assert found is None
    assert fetched == []


def test_rejects_placeholder_images_and_stops_after_three_copies(monkeypatch) -> None:
    outlets = [f"https://outlet{i}.example" for i in range(5)]
    feed = _search_feed(*[(TITLE, f"Outlet {i}", url) for i, url in enumerate(outlets)])
    pages = {url: _page(f"{url}/assets/img/home-summary-img-substitute.png") for url in outlets}

    found, fetched, _ = _lookup(monkeypatch, feed, pages)

    assert found is None
    assert fetched == outlets[:3]


def test_short_headlines_are_not_searched(monkeypatch) -> None:
    import app.services.syndicated_photos as module

    monkeypatch.setattr(module, "open_public_url", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched")))

    assert module.find_syndicated_photo(SourceCollectorService(SessionLocal()), "Kyiv attacked", "www.reuters.com") is None
