"""Collect many sources in one background run and report live progress.

Every collection path (this runner, the scheduler and the single-source endpoint) holds
collection_lock while it collects, so two runs never fetch the same feed at once. That is
what keeps repeated "Collect latest news" clicks from inserting the same story twice; the
URL/title dedupe in ArticleRepository.find_duplicate handles everything already stored.

Progress lives in memory: the API runs as a single process, and a restart mid-run loses
only the progress display. Each source's outcome is also recorded on its job run as before.
"""
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.source import Source
from app.services.collector import SourceCollectorService


logger = logging.getLogger(__name__)

collection_lock = threading.Lock()


@dataclass
class SourceProgress:
    source_id: int
    name: str
    status: str = "pending"  # pending | running | succeeded | failed
    articles_found: int = 0
    articles_created: int = 0
    warning: str | None = None
    error: str | None = None


@dataclass
class CollectionRun:
    id: int
    status: str = "in_progress"  # in_progress | completed | completed_with_errors | failed
    waiting: bool = True
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error: str | None = None
    sources: list[SourceProgress] = field(default_factory=list)

    def snapshot(self) -> dict:
        done = [s for s in self.sources if s.status in ("succeeded", "failed")]
        running = next((s for s in self.sources if s.status == "running"), None)
        return {
            **asdict(self),
            "total_sources": len(self.sources),
            "completed_sources": len(done),
            "failed_sources": sum(1 for s in self.sources if s.status == "failed"),
            "articles_found": sum(s.articles_found for s in self.sources),
            "articles_created": sum(s.articles_created for s in self.sources),
            "current_source": running.name if running else None,
        }


_state_lock = threading.Lock()
_latest: CollectionRun | None = None
_next_id = 1


class CollectionAlreadyRunning(Exception):
    pass


def latest_run_snapshot() -> dict:
    with _state_lock:
        if _latest is None:
            return {"status": "idle"}
        return _latest.snapshot()


def start_collection_run(source_ids: list[int] | None = None) -> dict:
    """Start collecting the given sources (default: every active source with a feed)."""
    global _latest, _next_id
    with _state_lock:
        if _latest is not None and _latest.status == "in_progress":
            raise CollectionAlreadyRunning("A collection is already in progress.")

        with SessionLocal() as db:
            query = db.query(Source).filter(Source.is_active.is_(True)).filter(Source.feed_url.isnot(None))
            if source_ids is not None:
                query = query.filter(Source.id.in_(source_ids))
            sources = query.order_by(Source.name).all()
            run = CollectionRun(
                id=_next_id,
                sources=[SourceProgress(source_id=s.id, name=s.name) for s in sources if s.feed_url],
            )
        _next_id += 1
        _latest = run

    threading.Thread(target=_run, args=(run,), name=f"collection-run-{run.id}", daemon=True).start()
    return latest_run_snapshot()


def _run(run: CollectionRun) -> None:
    try:
        # Waits for a scheduled collection that is already underway; the UI shows "waiting".
        with collection_lock:
            with _state_lock:
                run.waiting = False
            for progress in run.sources:
                _collect_one(progress)
        with _state_lock:
            failed = sum(1 for s in run.sources if s.status == "failed")
            if run.sources and failed == len(run.sources):
                run.status = "failed"
                run.error = "Every source failed to collect."
            elif failed:
                run.status = "completed_with_errors"
            else:
                run.status = "completed"
    except Exception as exc:
        logger.exception("Collection run %s crashed", run.id)
        with _state_lock:
            run.status = "failed"
            run.error = f"Collection stopped unexpectedly: {exc}"
            for progress in run.sources:
                if progress.status in ("pending", "running"):
                    progress.status = "failed"
                    progress.error = progress.error or "Not collected: the run stopped early."
    finally:
        with _state_lock:
            run.finished_at = datetime.now(timezone.utc)


def _collect_one(progress: SourceProgress) -> None:
    with _state_lock:
        progress.status = "running"
    with SessionLocal() as db:
        collector = SourceCollectorService(db)
        try:
            result = collector.collect_source(progress.source_id)
        except (ValueError, RuntimeError) as exc:
            # Expected failures (feed unreachable, invalid XML, source paused) are already
            # recorded on the source's job run by collect_source.
            outcome = {"status": "failed", "error": str(exc)}
        except Exception as exc:
            logger.exception("Collecting source %s crashed", progress.source_id)
            db.rollback()
            error = f"Unexpected error: {exc}"
            try:
                collector._upsert_job_run(progress.source_id, "FAILED", error=error)
            except Exception:
                db.rollback()
            outcome = {"status": "failed", "error": error}
        else:
            outcome = {
                "status": "succeeded",
                "articles_found": result.articles_found,
                "articles_created": result.articles_created,
                "warning": result.warning,
            }
    with _state_lock:
        for key, value in outcome.items():
            setattr(progress, key, value)
