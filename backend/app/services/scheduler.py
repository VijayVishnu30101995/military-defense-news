import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func

from app.database import SessionLocal
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.services.collector import SourceCollectorService


logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def run_due_collection_jobs() -> None:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        due_jobs = (
            db.query(SourceCollectionJob)
            .join(Source, Source.id == SourceCollectionJob.source_id)
            .filter(SourceCollectionJob.is_enabled.is_(True))
            .filter(Source.is_active.is_(True))
            .filter(
                (SourceCollectionJob.next_run_at.is_(None))
                | (SourceCollectionJob.next_run_at <= now)
            )
            .all()
        )

        for job in due_jobs:
            source = db.query(Source).filter(Source.id == job.source_id).first()
            if source is None or not source.feed_url or not source.is_active:
                continue
            try:
                SourceCollectorService(db).collect_source(job.source_id)
            except Exception:
                # Feed fetch/parse failures are already recorded on the job run; this catches
                # anything unexpected so it is at least visible in the logs.
                logger.exception("Scheduled collection crashed for source %s (%s)", source.id, source.name)
                db.rollback()


def start_collection_scheduler() -> None:
    if scheduler.running:
        return

    # Collection runner: every 5 minutes
    scheduler.add_job(
        run_due_collection_jobs,
        trigger="interval",
        minutes=5,
        id="source-collection-scheduler",
        replace_existing=True,
    )

    # Health alert job: runs at configurable interval and sends aggregated alerts when threshold exceeded
    try:
        from app.config import settings
        from app.services.alerts import notify_health_summary
        from datetime import datetime, timezone

        def _compute_health_summary() -> list[dict]:
            with SessionLocal() as db:
                now = datetime.now(timezone.utc)
                sources = db.query(Source).all()
                results = []
                for s in sources:
                    if not s.is_active:
                        status = "paused"
                    elif s.last_success_at is None:
                        status = "critical"
                    else:
                        delta_minutes = (now - s.last_success_at).total_seconds() / 60.0
                        if delta_minutes > (s.collection_frequency * 6):
                            status = "critical"
                        elif delta_minutes > (s.collection_frequency * 2):
                            status = "warning"
                        else:
                            status = "ok"
                    results.append(
                        {
                            "source_id": s.id,
                            "name": s.name,
                            "status": status,
                            "last_success_at": s.last_success_at,
                            "last_failure_at": s.last_failure_at,
                            "collection_frequency": s.collection_frequency,
                        }
                    )
                return results

        def run_health_alert_check() -> dict:
            """Compute health summary and send aggregated alert if threshold exceeded.

            Returns a dict with counts and whether an email was sent.
            """
            results = _compute_health_summary()
            critical = [r for r in results if r["status"] == "critical"]
            threshold = int(getattr(settings, "alert_critical_threshold", 3) or 3)
            sent = False
            if len(critical) >= threshold:
                sent = notify_health_summary(results)
            return {"critical_count": len(critical), "threshold": threshold, "sent": bool(sent), "total_sources": len(results)}

        # schedule background job calling run_health_alert_check
        scheduler.add_job(
            run_health_alert_check,
            trigger="interval",
            minutes=getattr(settings, "alert_check_interval_minutes", 60),
            id="source-health-alerts",
            replace_existing=True,
        )
    except Exception:
        # If config is unavailable for any reason, skip scheduling health alerts
        pass

    scheduler.start()

# expose helper for manual triggering
def run_health_alert_check() -> dict:
    """Run a single health check & alert evaluation (used by manual API)."""
    try:
        from app.config import settings
        from app.services.alerts import notify_health_summary
        from datetime import datetime, timezone

        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            sources = db.query(Source).all()
            results = []
            for s in sources:
                if not s.is_active:
                    status = "paused"
                elif s.last_success_at is None:
                    status = "critical"
                else:
                    delta_minutes = (now - s.last_success_at).total_seconds() / 60.0
                    if delta_minutes > (s.collection_frequency * 6):
                        status = "critical"
                    elif delta_minutes > (s.collection_frequency * 2):
                        status = "warning"
                    else:
                        status = "ok"
                results.append(
                    {
                        "source_id": s.id,
                        "name": s.name,
                        "status": status,
                        "last_success_at": s.last_success_at,
                        "last_failure_at": s.last_failure_at,
                        "collection_frequency": s.collection_frequency,
                    }
                )

            critical = [r for r in results if r["status"] == "critical"]
            threshold = int(getattr(settings, "alert_critical_threshold", 3) or 3)
            sent = False
            if len(critical) >= threshold:
                sent = notify_health_summary(results)

            return {"critical_count": len(critical), "threshold": threshold, "sent": bool(sent), "total_sources": len(results)}
    except Exception as exc:
        return {"error": str(exc)}


def stop_collection_scheduler() -> None:
    if not scheduler.running:
        return

    scheduler.shutdown(wait=False)
