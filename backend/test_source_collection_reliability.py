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
