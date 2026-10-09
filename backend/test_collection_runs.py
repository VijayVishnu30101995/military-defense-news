import threading
import time
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.models.source import Source
from app.schemas.collection import CollectionRunResponse
from app.services import collection_run
from app.services.collector import SourceCollectorService


def _make_sources(count: int) -> list[int]:
    db = SessionLocal()
    ids = []
    for index in range(count):
        source = Source(
            name=f"Run Example {index} {uuid4().hex[:8]}",
            website_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            source_type="rss",
            is_active=True,
        )
        db.add(source)
        db.commit()
        ids.append(source.id)
    db.close()
    return ids


def _delete_sources(ids: list[int]) -> None:
    db = SessionLocal()
    for source in db.query(Source).filter(Source.id.in_(ids)).all():
        db.delete(source)
    db.commit()
    db.close()


def _wait_until_finished(timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = collection_run.latest_run_snapshot()
        if run["status"] != "in_progress":
            return run
        time.sleep(0.02)
    raise AssertionError("collection run did not finish")


def test_collection_run_reports_progress_and_retries_only_failed_sources(monkeypatch) -> None:
    ids = _make_sources(2)
    good, bad = ids
    attempts: list[int] = []

    def fake_collect(_self, source_id: int):
        attempts.append(source_id)
        if source_id == bad:
            raise RuntimeError("Failed to fetch source feed: HTTP Error 503")
        return CollectionRunResponse(
            source_id=source_id, articles_found=10, articles_created=4, status="SUCCESS", message="ok",
        )

    monkeypatch.setattr(SourceCollectorService, "collect_source", fake_collect)
    try:
        collection_run.start_collection_run(ids)
        run = _wait_until_finished()
        assert run["status"] == "completed_with_errors"
        assert run["total_sources"] == 2
        assert run["completed_sources"] == 2
        assert run["failed_sources"] == 1
        assert run["articles_created"] == 4
        failed = [s for s in run["sources"] if s["status"] == "failed"]
        assert [s["source_id"] for s in failed] == [bad]
        assert "503" in failed[0]["error"]

        attempts.clear()
        collection_run.start_collection_run([bad])
        retry = _wait_until_finished()
        assert attempts == [bad]
        assert retry["status"] == "failed"
    finally:
        _delete_sources(ids)


def test_collection_run_refuses_a_second_run_and_blocks_the_scheduler(monkeypatch) -> None:
    ids = _make_sources(1)
    release = threading.Event()
    started = threading.Event()

    def slow_collect(_self, source_id: int):
        started.set()
        release.wait(5)
        return CollectionRunResponse(
            source_id=source_id, articles_found=0, articles_created=0, status="SUCCESS", message="ok",
        )

    monkeypatch.setattr(SourceCollectorService, "collect_source", slow_collect)
    import app.services.scheduler as scheduler_module

    scheduler_calls: list[str] = []
    monkeypatch.setattr(scheduler_module, "_run_due_collection_jobs", lambda: scheduler_calls.append("ran"))
    try:
        collection_run.start_collection_run(ids)
        assert started.wait(5)
        assert collection_run.latest_run_snapshot()["current_source"] is not None

        with pytest.raises(collection_run.CollectionAlreadyRunning):
            collection_run.start_collection_run(ids)
        scheduler_module.run_due_collection_jobs()
        assert scheduler_calls == []

        release.set()
        assert _wait_until_finished()["status"] == "completed"
        scheduler_module.run_due_collection_jobs()
        assert scheduler_calls == ["ran"]
    finally:
        release.set()
        _delete_sources(ids)
