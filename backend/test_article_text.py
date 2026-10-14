from datetime import datetime, timedelta, timezone
from uuid import uuid4
from xml.etree import ElementTree

from app.database import SessionLocal
from app.models.article import Article
from app.models.source import Source
from app.repositories.article import ArticleRepository
from app.services.collector import SourceCollectorService
from app.services.feed_text import MAX_PAGE_EXCERPT_CHARS, article_text_from_page

STORY = [
    "Turkish police have raided the headquarters of a pro-opposition TV channel, halting its live broadcasts on Wednesday.",
    "The channel said its employees were unable to enter the building in Istanbul, and that a new manager had been appointed.",
    "Reports in Turkish media said financial crimes police were searching the building and eleven people had been detained.",
    "The station's news channel and its live broadcasts on YouTube were both offline early on Wednesday morning, staff said.",
]
PAGE = f"""
<html><body>
  <nav><p>World Africa Asia Australia Europe Latin America Middle East US and Canada</p></nav>
  <header><p>Sign in to your account to save this story and read it later on any device you own</p></header>
  <div class="byline"><p>Share</p><p>By a staff reporter</p></div>
  <article><div class="story">{"".join(f"<p>{p}</p>" for p in STORY)}</div>
    <figure><p>A staff member shared images of police stood beside a TV studio in its office early on Wednesday</p></figure>
  </article>
  <aside><p>Related: The rise of the opposition and why the government fears it, explained in five charts</p></aside>
  <footer><p>Copyright 2026. The BBC is not responsible for the content of external sites. Read more about it.</p></footer>
</body></html>"""


def test_page_text_is_the_story_without_menus_captions_or_asides() -> None:
    assert article_text_from_page(PAGE) == "\n\n".join(STORY)


def test_page_text_drops_invisible_characters_hidden_in_words() -> None:
    marked = STORY[0].replace("police", "pol\u200bice").replace("raided", "\u2060raided")

    assert article_text_from_page(PAGE.replace(STORY[0], marked)).split("\n\n")[0] == STORY[0]


def test_page_text_keeps_only_the_opening_of_a_long_story() -> None:
    long_page = "<article>" + "".join(f"<p>{p} Paragraph {i}.</p>" for i in range(60) for p in STORY[:1]) + "</article>"

    text = article_text_from_page(long_page)

    assert len(text) <= MAX_PAGE_EXCERPT_CHARS
    assert text.startswith(STORY[0])


def test_fill_missing_article_text_stops_after_repeated_network_failures(monkeypatch) -> None:
    import app.services.collector as collector_module

    db = SessionLocal()
    source = Source(
        name=f"Unreachable Site {uuid4().hex[:8]}", website_url="https://example.com",
        feed_url="https://example.com/rss.xml", source_type="rss", is_active=True,
    )
    db.add(source)
    db.commit()
    fetched = []
    monkeypatch.setattr(SourceCollectorService, "_fetch_article_html", lambda self, url, publisher_url=None: fetched.append(url))
    try:
        for _ in range(collector_module.ARTICLE_TEXT_MAX_FAILURES + 3):
            title = f"Unreachable story {uuid4().hex}"
            db.add(Article(
                source_id=source.id, title=title, normalized_title=ArticleRepository.normalize_title(title),
                original_url=f"https://example.com/{uuid4().hex}", relevance_score=80,
                published_at=datetime.now(timezone.utc),
            ))
        db.commit()

        assert SourceCollectorService(db).fill_missing_article_text(source) == 0
        assert len(fetched) == collector_module.ARTICLE_TEXT_MAX_FAILURES
    finally:
        db.rollback()
        db.delete(source)
        db.commit()
        db.close()


def test_page_text_is_none_for_pages_without_a_story() -> None:
    assert article_text_from_page(None) is None
    assert article_text_from_page("<p>Too short to be a story.</p>") is None
    assert article_text_from_page("<html><body><nav><p>" + " ".join(STORY) + "</p></nav></body></html>") is None


def test_feed_description_holding_the_whole_story_becomes_body_and_short_summary() -> None:
    description = (
        "<p><img src='https://www.armyrecognition.com/' alt='photo'></p><div>{loadposition bannertop}</div>"
        + f"<p>{STORY[0]} {STORY[0]}</p><p>Police outside the channel's studio ( Picture Source: Halk TV)</p>"
        + "".join(f"<p>{p} {p}</p>" for p in STORY[1:])
        + "<p>Explore More Defense News</p><ul><li>Land Defense News</li></ul><p>Written by a defense analyst</p>"
    )
    xml = f"""<rss><channel><item><title>Raid on TV channel</title><link>https://example.com/raid</link>
      <description><![CDATA[{description}]]></description></item>
      <item><title>Short one</title><link>https://example.com/short</link>
      <description>Just a one-line summary.</description></item></channel></rss>"""

    long_item, short_item = SourceCollectorService(SessionLocal())._find_feed_items(ElementTree.fromstring(xml))

    assert long_item["summary"] == f"{STORY[0]} {STORY[0]}"
    assert long_item["body"].split("\n\n") == [f"{p} {p}" for p in STORY]
    assert "loadposition" not in long_item["body"]
    assert (short_item["summary"], short_item["body"]) == ("Just a one-line summary.", None)


def test_fill_missing_article_text_reads_each_shown_story_once(monkeypatch) -> None:
    db = SessionLocal()
    source = Source(
        name=f"Summary Only Feed {uuid4().hex[:8]}", website_url="https://example.com",
        feed_url="https://example.com/rss.xml", source_type="rss", is_active=True,
    )
    db.add(source)
    db.commit()
    now = datetime.now(timezone.utc)
    fetched = []

    def fake_fetch(self, url, publisher_url=None):
        fetched.append(url)
        if "refused" in url:
            self._blocked_hosts.add("refused.example.com")
        return PAGE if "has-page" in url else None

    monkeypatch.setattr(SourceCollectorService, "_fetch_article_html", fake_fetch)

    def article(slug, relevance=80, body=None, summary="One-line summary.", published_at=now):
        title = f"{slug} story {uuid4().hex}"
        row = Article(
            source_id=source.id, title=title, normalized_title=ArticleRepository.normalize_title(title),
            original_url=f"https://{'refused.' if slug == 'refused' else ''}example.com/{slug}/{uuid4().hex}", summary=summary, description=summary,
            content_excerpt=body, relevance_score=relevance, published_at=published_at,
        )
        db.add(row)
        return row

    try:
        thin = article("has-page")
        whole_story_summary = article("has-page", summary=" ".join(STORY) * 3)
        refused = article("refused")
        unreachable = article("network-error")
        has_body = article("has-page", body="Already has its text.")
        hidden = article("has-page", relevance=0)
        old = article("has-page", published_at=now - timedelta(days=30))
        db.commit()

        service = SourceCollectorService(db)
        assert service.fill_missing_article_text(source) == 2
        for row in (thin, whole_story_summary, refused, unreachable, has_body, hidden, old):
            db.refresh(row)

        assert sorted(fetched) == sorted(
            [thin.original_url, whole_story_summary.original_url, refused.original_url, unreachable.original_url]
        )
        assert thin.content_excerpt == "\n\n".join(STORY) and thin.summary == "One-line summary."
        assert whole_story_summary.summary == STORY[0]
        assert refused.content_excerpt is None and refused.text_lookup_at is not None
        assert has_body.content_excerpt == "Already has its text."
        assert hidden.text_lookup_at is None and old.text_lookup_at is None

        # A page that could not be fetched is retried next run; the others are not.
        assert unreachable.text_lookup_at is None
        fetched.clear()
        assert service.fill_missing_article_text(source) == 0
        assert fetched == [unreachable.original_url]
    finally:
        db.rollback()
        db.delete(source)
        db.commit()
        db.close()


def test_stories_from_a_site_that_refuses_us_take_text_from_another_outlets_copy(monkeypatch) -> None:
    import app.services.collector as collector_module
    from app.services.syndicated_copies import SyndicatedCopy

    db = SessionLocal()
    source = Source(
        name=f"Wire Refusing Pages {uuid4().hex[:8]}", website_url="https://www.wire.example/world/",
        feed_url="https://news.google.com/rss/search?q=wire", source_type="rss", is_active=True,
    )
    db.add(source)
    db.commit()
    now = datetime.now(timezone.utc)
    searched = []

    def refusing_fetch(self, url, publisher_url=None):
        self._blocked_hosts.add("www.wire.example")
        return None

    def fake_find(collector, title, publisher_host, want_image, want_text):
        searched.append((title.split()[0], want_image, want_text))
        return SyndicatedCopy(text="\n\n".join(STORY), text_credit="Yahoo News") if "Copied" in title else None

    monkeypatch.setattr(SourceCollectorService, "_fetch_article_html", refusing_fetch)
    monkeypatch.setattr(collector_module, "find_syndicated_copy", fake_find)

    def article(label, image_url="https://img.example.com/own.jpg"):
        title = f"{label} wire story {uuid4().hex}"
        row = Article(
            source_id=source.id, title=title, normalized_title=ArticleRepository.normalize_title(title),
            original_url=f"https://news.google.com/rss/articles/{uuid4().hex}", summary="One line.",
            image_url=image_url, relevance_score=80, published_at=now,
        )
        db.add(row)
        return row

    try:
        copied = article("Copied")
        uncopied = article("Uncopied", image_url=None)
        db.commit()

        service = SourceCollectorService(db)
        # Its own pages are refused: nothing is marked, the copies are searched instead.
        assert service.fill_missing_article_text(source) == 0
        assert service.borrow_from_syndicated_copies(source) == 1
        db.refresh(copied)
        db.refresh(uncopied)

        assert sorted(searched) == [("Copied", False, True), ("Uncopied", True, True)]
        assert (copied.content_excerpt, copied.text_credit) == ("\n\n".join(STORY), "Yahoo News")
        assert copied.text_lookup_at is not None and copied.image_lookup_at is None
        assert uncopied.content_excerpt is None
        assert uncopied.text_lookup_at is not None and uncopied.image_lookup_at is not None
    finally:
        db.rollback()
        db.delete(source)
        db.commit()
        db.close()
