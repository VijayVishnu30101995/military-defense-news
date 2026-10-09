from datetime import datetime, timezone
from uuid import uuid4
from xml.etree import ElementTree

import pytest

from app.database import SessionLocal
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.repositories.article import ArticleRepository
from app.services.collector import SourceCollectorService
from app.services.scheduler import run_due_collection_jobs


def test_collect_source_rejects_inactive_source() -> None:
    db = SessionLocal()
    source = Source(
        name="Inactive Feed Example",
        website_url="https://example.com",
        feed_url="https://example.com/rss.xml",
        source_type="rss",
        is_active=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    try:
        with pytest.raises(ValueError, match="inactive"):
            SourceCollectorService(db).collect_source(source.id)
    finally:
        db.delete(source)
        db.commit()
        db.close()


def test_run_due_collection_jobs_skips_inactive_sources(monkeypatch) -> None:
    db = SessionLocal()
    source = Source(
        name="Inactive Scheduler Example",
        website_url="https://example.com",
        feed_url="https://example.com/rss.xml",
        source_type="rss",
        is_active=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    job = SourceCollectionJob(
        source_id=source.id,
        is_enabled=True,
        interval_minutes=60,
        next_run_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    called = {"value": False}

    def fake_collect(_source_id: int):
        called["value"] = True

    import app.services.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.SourceCollectorService, "collect_source", fake_collect)

    try:
        run_due_collection_jobs()
        assert called["value"] is False
    finally:
        db.delete(source)
        db.commit()
        db.close()


def test_feed_parser_skips_invalid_links_and_normalizes_urls() -> None:
    xml = """
    <rss><channel>
      <item>
        <title>Example Title</title>
        <link>https://example.com/article?utm_source=tracker#section</link>
        <description>Summary</description>
      </item>
      <item>
        <title>Bad Link</title>
        <link>mailto:test@example.com</link>
      </item>
      <item>
        <title>Relative Link</title>
        <link>/story/123?utm_medium=email#top</link>
      </item>
    </channel></rss>
    """

    root = ElementTree.fromstring(xml)
    items = SourceCollectorService(SessionLocal())._find_feed_items(root, fallback_base_url="https://example.com")

    assert len(items) == 2
    assert items[0]["link"] == "https://example.com/article"
    assert items[1]["link"] == "https://example.com/story/123"
    assert ArticleRepository.normalize_url("https://example.com/story/123?utm_medium=email#top") == "https://example.com/story/123"


class _FakeFeedResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _collect_with_feed(monkeypatch, feed_xml: str):
    import app.services.collector as collector_module
    from app.models.job_run import JobRun

    db = SessionLocal()
    source = Source(
        name=f"Feed Warning Example {uuid4().hex[:8]}",
        website_url="https://example.com",
        feed_url="https://example.com/rss.xml",
        source_type="rss",
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    monkeypatch.setattr(
        collector_module.request,
        "urlopen",
        lambda *args, **kwargs: _FakeFeedResponse(feed_xml.encode("utf-8")),
    )

    try:
        result = SourceCollectorService(db).collect_source(source.id)
        job = SourceCollectorService(db).job_service.get_by_source_id(source.id)
        last_run = db.query(JobRun).filter(JobRun.source_collection_job_id == job.id).order_by(JobRun.id.desc()).first()
        return result, last_run.status, last_run.error_message
    finally:
        db.rollback()
        db.delete(source)
        db.commit()
        db.close()


def test_collect_source_warns_when_feed_has_no_entries(monkeypatch) -> None:
    result, status, error_message = _collect_with_feed(monkeypatch, "<rss><channel></channel></rss>")

    assert result.articles_found == 0
    assert status == "SUCCESS"
    assert error_message == "Feed parsed but contained no entries."


def test_collect_source_warns_when_entries_have_no_usable_link(monkeypatch) -> None:
    feed = """
    <rss><channel>
      <item><title>Mail link</title><link>mailto:test@example.com</link></item>
      <item><title>FTP link</title><link>ftp://example.com/story</link></item>
    </channel></rss>
    """
    result, status, error_message = _collect_with_feed(monkeypatch, feed)

    assert result.articles_found == 0
    assert status == "SUCCESS"
    assert error_message == "Feed contained 2 entries but none had a usable title and link."


def test_run_due_collection_jobs_schedules_sources_without_a_job(monkeypatch) -> None:
    db = SessionLocal()
    source = Source(
        name=f"Unscheduled Feed Example {uuid4().hex[:8]}",
        website_url="https://example.com",
        feed_url="https://example.com/rss.xml",
        source_type="rss",
        is_active=True,
        collection_frequency=180,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    collected: list[int] = []

    def fake_collect(_self, source_id: int):
        collected.append(source_id)

    import app.services.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.SourceCollectorService, "collect_source", fake_collect)

    try:
        run_due_collection_jobs()
        job = db.query(SourceCollectionJob).filter(SourceCollectionJob.source_id == source.id).first()
        assert job is not None
        assert job.interval_minutes == 180
        assert source.id in collected
    finally:
        db.delete(source)
        db.commit()
        db.close()


def test_normalize_title_keeps_non_latin_letters() -> None:
    assert ArticleRepository.normalize_title("Мир и война: обзор") == "мир и война обзор"
    assert ArticleRepository.normalize_title("भारत ने नया मिसाइल परीक्षण किया") != ""
    assert ArticleRepository.normalize_title("Морской флот") != ArticleRepository.normalize_title("Сухопутные войска")


def _make_source(db, label: str) -> Source:
    source = Source(
        name=f"{label} {uuid4().hex[:8]}",
        website_url="https://example.com",
        feed_url="https://example.com/rss.xml",
        source_type="rss",
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def test_find_duplicate_ignores_short_recurring_titles() -> None:
    from app.schemas.article import ArticleCreate

    db = SessionLocal()
    source = _make_source(db, "Short Title Example")
    repository = ArticleRepository(db)
    try:
        repository.create(ArticleCreate(
            source_id=source.id,
            title="Morning Brief",
            original_url=f"https://example.com/{uuid4().hex}",
        ))
        assert repository.find_duplicate(
            source_id=source.id,
            title="Morning Brief",
            original_url=f"https://example.com/{uuid4().hex}",
            canonical_url=None,
        ) is None
    finally:
        db.delete(source)
        db.commit()
        db.close()


def test_find_duplicate_matches_same_url_or_specific_title() -> None:
    from app.schemas.article import ArticleCreate

    db = SessionLocal()
    first = _make_source(db, "Wire Example")
    second = _make_source(db, "Syndication Example")
    repository = ArticleRepository(db)
    title = f"Pentagon awards {uuid4().hex[:8]} contract for next generation interceptors"
    url = f"https://example.com/{uuid4().hex}"
    try:
        stored = repository.create(ArticleCreate(source_id=first.id, title=title, original_url=url))
        # Same URL with tracking parameters is the same story.
        assert repository.find_duplicate(
            source_id=first.id,
            title="Different headline entirely",
            original_url=f"{url}?utm_source=feed",
            canonical_url=None,
        ).id == stored.id
        # A long, specific headline from another outlet is the same wire story.
        assert repository.find_duplicate(
            source_id=second.id,
            title=title,
            original_url=f"https://other.example.com/{uuid4().hex}",
            canonical_url=None,
        ).id == stored.id
    finally:
        db.delete(first)
        db.delete(second)
        db.commit()
        db.close()


def test_feed_parser_strips_aggregator_publisher_suffix() -> None:
    xml = """
    <rss><channel>
      <item>
        <title>Lithuania says it would pay the cost if US establishes military base - Reuters</title>
        <link>https://news.google.com/rss/articles/abc</link>
        <source url="https://www.reuters.com">Reuters</source>
      </item>
      <item>
        <title>Ukraine strikes refinery - Reuters reports</title>
        <link>https://example.com/story</link>
      </item>
    </channel></rss>
    """
    items = SourceCollectorService(SessionLocal())._find_feed_items(ElementTree.fromstring(xml))

    assert items[0]["title"] == "Lithuania says it would pay the cost if US establishes military base"
    assert items[1]["title"] == "Ukraine strikes refinery - Reuters reports"


def test_borrow_missing_images_uses_only_strong_matches_from_other_sources() -> None:
    from app.models.article import Article

    db = SessionLocal()
    wire = _make_source(db, "Wire Without Photos")
    outlet = _make_source(db, "Outlet With Photos")
    now = datetime.now(timezone.utc)
    tag = uuid4().hex[:8]

    def article(source, title, image_url=None):
        row = Article(
            source_id=source.id,
            title=title,
            normalized_title=ArticleRepository.normalize_title(title),
            original_url=f"https://example.com/{uuid4().hex}",
            image_url=image_url,
            published_at=now,
        )
        db.add(row)
        return row

    try:
        article(outlet, f"Yemeni government launches offensive against Houthis {tag}", "https://img.example.com/yemen.jpg")
        article(outlet, f"Israeli attacks across Gaza kill at least four Palestinians {tag}", "https://img.example.com/gaza.jpg")
        same_story = article(wire, f"Yemeni government launches offensive against Houthis {tag}")
        different_event = article(wire, f"Israeli strikes kill two people in Gaza, medics say {tag}")
        same_source = article(outlet, f"Yemeni government launches offensive against Houthis {tag} again")
        db.commit()

        SourceCollectorService(db).borrow_missing_images()
        for row in (same_story, different_event, same_source):
            db.refresh(row)

        assert same_story.image_url == "https://img.example.com/yemen.jpg"
        assert same_story.image_credit == outlet.name
        assert different_event.image_url is None
        assert same_source.image_url is None
    finally:
        db.rollback()
        db.delete(wire)
        db.delete(outlet)
        db.commit()
        db.close()
