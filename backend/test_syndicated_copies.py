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


def _lookup(monkeypatch, feed: bytes, pages: dict[str, str], publisher_host="www.reuters.com", **wants):
    import app.services.syndicated_copies as module

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
    return module.find_syndicated_copy(service, TITLE, publisher_host, **wants), fetched, searched


STORY = [
    "Airbus has flown the Valkyrie drone in Europe for the first time, the company said on Tuesday.",
    "The aircraft maker plans to have the uncrewed jet ready for combat missions by 2029, executives said.",
    "European air forces are weighing how many of the drones to buy alongside their crewed fighter jets.",
    "The test flight took place at an airbase in southern Germany and lasted a little under an hour.",
]


def _page(image: str | None = None, story: bool = False) -> str:
    meta = f'<meta property="og:image" content="{image}">' if image else ""
    body = "<article>" + "".join(f"<p>{p}</p>" for p in STORY) + "</article>" if story else ""
    return f"<html><head>{meta}</head><body>{body}</body></html>"


def test_takes_the_photo_from_a_near_identical_copy_and_credits_the_outlet(monkeypatch) -> None:
    feed = _search_feed(
        ("Joe Manganiello responds after Sofia Vergara likes post", "Yahoo", "https://sg.news.yahoo.com"),
        (TITLE, "Yahoo Finance Canada", "https://ca.finance.yahoo.com"),
    )
    pages = {"https://ca.finance.yahoo.com": _page("https://s.yimg.com/photos/valkyrie.jpg")}

    found, fetched, searched = _lookup(monkeypatch, feed, pages)

    assert (found.image_url, found.image_credit) == ("https://s.yimg.com/photos/valkyrie.jpg", "Yahoo Finance Canada")
    assert found.text is None
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
    import app.services.syndicated_copies as module

    monkeypatch.setattr(module, "open_public_url", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched")))

    assert module.find_syndicated_copy(SourceCollectorService(SessionLocal()), "Kyiv attacked", "www.reuters.com") is None


def test_takes_text_and_photo_from_different_copies_when_needed(monkeypatch) -> None:
    feed = _search_feed(
        (TITLE, "Photo Only", "https://photo.example"),
        (TITLE, "The Straits Times", "https://www.straitstimes.com"),
        (TITLE, "Never Reached", "https://late.example"),
    )
    pages = {
        "https://photo.example": _page("https://photo.example/valkyrie.jpg"),
        "https://www.straitstimes.com": _page(story=True),
    }

    found, fetched, _ = _lookup(monkeypatch, feed, pages, want_image=True, want_text=True)

    assert (found.image_url, found.image_credit) == ("https://photo.example/valkyrie.jpg", "Photo Only")
    assert (found.text, found.text_credit) == ("\n\n".join(STORY), "The Straits Times")
    # Both found: the third copy is not fetched.
    assert fetched == ["https://photo.example", "https://www.straitstimes.com"]


def test_text_only_lookup_ignores_photos(monkeypatch) -> None:
    feed = _search_feed((TITLE, "Photo Only", "https://photo.example"))

    found, _, _ = _lookup(
        monkeypatch, feed, {"https://photo.example": _page("https://photo.example/valkyrie.jpg")},
        want_image=False, want_text=True,
    )

    assert found is None


def test_translated_copies_are_not_used_for_text(monkeypatch) -> None:
    italian = "<article>" + "".join(
        f"<p>Le forze russe hanno colpito la capitale ucraina con missili balistici, uccidendo due persone {i}.</p>"
        for i in range(6)
    ) + "</article>"
    feed = _search_feed((TITLE, "Internazionale", "https://www.internazionale.it"), (TITLE, "CNA", "https://www.cna.example"))
    pages = {"https://www.internazionale.it": italian, "https://www.cna.example": _page(story=True)}

    found, _, _ = _lookup(monkeypatch, feed, pages, want_image=False, want_text=True)

    assert found.text_credit == "CNA"
