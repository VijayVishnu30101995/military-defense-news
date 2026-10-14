from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.articles import _serialize_articles
from app.database import get_db
from app.models.article import Article
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistMatch
from app.schemas.watchlist import MAX_WATCHLISTS_PER_USER, WatchlistCreate, WatchlistTerms, WatchlistUpdate
from app.services.alerts import email_configured
from app.services.watchlists import BACKFILL_DAYS, matching_stories, refill_watchlist

router = APIRouter(prefix="/watchlists", tags=["Watchlists"])

PREVIEW_STORIES = 5


def _own_watchlist(db: Session, user: User, watchlist_id: int) -> Watchlist:
    watchlist = db.get(Watchlist, watchlist_id)
    # Another reader's watchlist is reported as missing, not forbidden, so ids reveal nothing.
    if watchlist is None or watchlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return watchlist


def _serialize(watchlist: Watchlist, counts: dict[int, tuple[int, int, datetime | None]]) -> dict:
    total, unread, latest = counts.get(watchlist.id, (0, 0, None))
    return {
        "id": watchlist.id,
        "name": watchlist.name,
        "terms": watchlist.terms,
        "exclude_terms": watchlist.exclude_terms,
        "email_frequency": watchlist.email_frequency,
        "is_active": watchlist.is_active,
        "match_count": total,
        "unread_count": unread,
        "latest_match_at": latest.isoformat() if latest else None,
        "created_at": watchlist.created_at.isoformat() if watchlist.created_at else None,
    }


def _counts(db: Session, watchlist_ids: list[int]) -> dict[int, tuple[int, int, datetime | None]]:
    if not watchlist_ids:
        return {}
    rows = (
        db.query(
            WatchlistMatch.watchlist_id,
            func.count(WatchlistMatch.id),
            func.sum(case((WatchlistMatch.seen_at.is_(None), 1), else_=0)),
            func.max(WatchlistMatch.matched_at),
        )
        .filter(WatchlistMatch.watchlist_id.in_(watchlist_ids))
        .group_by(WatchlistMatch.watchlist_id)
        .all()
    )
    return {watchlist_id: (total, int(unread or 0), latest) for watchlist_id, total, unread, latest in rows}


@router.get("")
def list_watchlists(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    watchlists = db.query(Watchlist).filter(Watchlist.user_id == user.id).order_by(Watchlist.name.asc()).all()
    counts = _counts(db, [watchlist.id for watchlist in watchlists])
    items = [_serialize(watchlist, counts) for watchlist in watchlists]
    return {
        "items": items,
        "unread_total": sum(item["unread_count"] for item in items if item["is_active"]),
        "email_available": email_configured(),
        "backfill_days": BACKFILL_DAYS,
    }


@router.post("/preview")
def preview_watchlist(payload: WatchlistTerms, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    """How many recent stories the terms would match, so readers can tune them before saving."""
    found = matching_stories(db, payload.terms, payload.exclude_terms)
    return {
        "total": len(found),
        "days": BACKFILL_DAYS,
        "items": [
            {"id": story.id, "title": story.title, "matched_terms": matched}
            for story, matched in found[:PREVIEW_STORIES]
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    owned = db.query(func.count(Watchlist.id)).filter(Watchlist.user_id == user.id).scalar()
    if owned >= MAX_WATCHLISTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You can have up to {MAX_WATCHLISTS_PER_USER} watchlists. Delete one to add another.",
        )
    watchlist = Watchlist(
        user_id=user.id,
        name=payload.name,
        terms=payload.terms,
        exclude_terms=payload.exclude_terms,
        email_frequency=payload.email_frequency,
    )
    db.add(watchlist)
    db.flush()
    refill_watchlist(db, watchlist)
    return _serialize(watchlist, _counts(db, [watchlist.id]))


@router.patch("/{watchlist_id}")
def update_watchlist(
    watchlist_id: int, payload: WatchlistUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    watchlist = _own_watchlist(db, user, watchlist_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    terms_changed = any(
        key in changes and changes[key] != getattr(watchlist, key) for key in ("terms", "exclude_terms")
    )
    if changes.get("email_frequency", watchlist.email_frequency) != watchlist.email_frequency:
        # Only stories matched from now on are emailed under the new setting.
        db.query(WatchlistMatch).filter(
            WatchlistMatch.watchlist_id == watchlist.id, WatchlistMatch.emailed_at.is_(None)
        ).update({WatchlistMatch.emailed_at: datetime.now(timezone.utc)}, synchronize_session=False)
    for key, value in changes.items():
        setattr(watchlist, key, value)
    db.commit()
    if terms_changed:
        refill_watchlist(db, watchlist)
    return _serialize(watchlist, _counts(db, [watchlist.id]))


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(watchlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    watchlist = _own_watchlist(db, user, watchlist_id)
    db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == watchlist.id).delete(synchronize_session=False)
    db.delete(watchlist)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{watchlist_id}/matches")
def list_matches(
    watchlist_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Stories that matched, newest first, each with the terms it mentioned and whether it is new."""
    watchlist = _own_watchlist(db, user, watchlist_id)
    query = (
        db.query(WatchlistMatch, Article)
        .join(Article, Article.id == WatchlistMatch.article_id)
        .filter(WatchlistMatch.watchlist_id == watchlist.id)
    )
    total = query.count()
    rows = (
        query.order_by(func.coalesce(Article.published_at, Article.collected_at).desc(), Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = _serialize_articles(db, [article for _, article in rows])
    for item, (match, _) in zip(items, rows):
        item["matched_terms"] = match.matched_terms
        item["is_new"] = match.seen_at is None
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{watchlist_id}/seen")
def mark_seen(watchlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    watchlist = _own_watchlist(db, user, watchlist_id)
    updated = (
        db.query(WatchlistMatch)
        .filter(WatchlistMatch.watchlist_id == watchlist.id, WatchlistMatch.seen_at.is_(None))
        .update({WatchlistMatch.seen_at: datetime.now(timezone.utc)}, synchronize_session=False)
    )
    db.commit()
    return {"marked_seen": updated}
