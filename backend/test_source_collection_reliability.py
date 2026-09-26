from datetime import datetime, timezone
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
