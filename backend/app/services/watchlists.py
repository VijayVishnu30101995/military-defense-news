"""Watchlists: readers' saved topics, the stories that match them, and the email alerts.

A story matches a watchlist when its headline, summary or text mentions any of the
watchlist's terms as a whole word or phrase (case and a plural ending ignored: "drone"
matches "Drones" and "anti-drone" but not "Androne"), and none of its excluded terms. Each watchlist remembers the newest story it has checked,
so every pass only reads stories collected since the last one.
"""
from __future__ import annotations

import html
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.core.content_filters import is_off_topic_story
from app.models.article import Article
from app.models.source import Source
from app.models.user import User
from app.models.watchlist import EMAIL_DAILY, EMAIL_INSTANT, EMAIL_OFF, Watchlist, WatchlistMatch
from app.services.alerts import send_email

logger = logging.getLogger(__name__)

# A new or edited watchlist is filled with this many days of earlier stories, so it is not
# empty until the next collection. Those matches are not emailed or counted as new.
BACKFILL_DAYS = 7
# Stories read per matching pass; a backlog larger than this is finished on later passes.
MATCH_BATCH_SIZE = 2000
# Matches older than this are not emailed (e.g. email was set up long after they matched).
EMAIL_WINDOW = timedelta(hours=48)
MAX_STORIES_PER_EMAIL = 30
DAILY_DIGEST_HOUR = 8


def _term_pattern(term: str) -> re.Pattern:
    words = [re.escape(word) for word in term.split()]
    # Whole words only, so "Navy" does not match "Navya"; a plural ending is allowed, and a
    # model code ending in a number also matches its variants ("F-35" matches "F-35A").
    ending = r"(?:[a-z]|e?s)?" if term[-1].isdigit() else r"(?:e?s)?"
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(words) + ending + r"(?!\w)", re.IGNORECASE)


class TermMatcher:
    def __init__(self, terms: list[str], exclude_terms: list[str] | None = None) -> None:
        self._terms = [(term, _term_pattern(term)) for term in terms]
        self._excludes = [_term_pattern(term) for term in exclude_terms or []]

    def match(self, *texts: str | None) -> list[str]:
        """The terms the text mentions, or [] if it mentions none or an excluded term."""
        text = "\n".join(t for t in texts if t)
        if any(pattern.search(text) for pattern in self._excludes):
            return []
        return [term for term, pattern in self._terms if pattern.search(text)]


def _story_texts(article: Article) -> tuple[str | None, ...]:
    return article.title, article.summary or article.description, article.content_excerpt


def _shown(article: Article) -> bool:
    if article.relevance_score is not None:
        return article.relevance_score >= settings.relevance_threshold
    return not is_off_topic_story(article.title, article.summary or article.description)


def _candidate_stories(db: Session):
    return db.query(Article).filter(
        or_(Article.relevance_score.is_(None), Article.relevance_score >= settings.relevance_threshold)
    )


def matching_stories(db: Session, terms: list[str], exclude_terms: list[str], days: int = BACKFILL_DAYS):
    """Stories from the last `days` days that the terms match, newest first, with the matched terms."""
    matcher = TermMatcher(terms, exclude_terms)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stories = (
        _candidate_stories(db)
        .filter(func.coalesce(Article.published_at, Article.collected_at) >= since)
        .order_by(func.coalesce(Article.published_at, Article.collected_at).desc())
        .all()
    )
    return [(story, matched) for story in stories if _shown(story) and (matched := matcher.match(*_story_texts(story)))]


def refill_watchlist(db: Session, watchlist: Watchlist) -> int:
    """Replace a watchlist's matches with the recent stories its current terms match.

    Used when a watchlist is created or its terms change. These matches are already
    "seen" and never emailed: only stories collected from now on are news to the reader.
    """
    now = datetime.now(timezone.utc)
    db.query(WatchlistMatch).filter(WatchlistMatch.watchlist_id == watchlist.id).delete(synchronize_session=False)
    found = matching_stories(db, watchlist.terms, watchlist.exclude_terms)
    for story, matched in found:
        db.add(WatchlistMatch(
            watchlist_id=watchlist.id, article_id=story.id, matched_terms=matched, seen_at=now, emailed_at=now,
        ))
    watchlist.last_article_id = db.query(func.coalesce(func.max(Article.id), 0)).scalar()
    db.commit()
    return len(found)


def match_new_stories(db: Session) -> int:
    """Check stories collected since each active watchlist's last pass. Returns new matches."""
    watchlists = db.query(Watchlist).filter(Watchlist.is_active.is_(True)).all()
    if not watchlists:
        return 0
    start = min(watchlist.last_article_id for watchlist in watchlists)
    stories = (
        _candidate_stories(db)
        .filter(Article.id > start)
        .order_by(Article.id.asc())
        .limit(MATCH_BATCH_SIZE)
        .all()
    )
    # Hidden stories are not read at all, so the cursor moves past them by the highest id.
    newest = db.query(func.coalesce(func.max(Article.id), 0)).scalar()
    if len(stories) == MATCH_BATCH_SIZE:
        newest = stories[-1].id
    now = datetime.now(timezone.utc)
    created = 0
    for watchlist in watchlists:
        matcher = TermMatcher(watchlist.terms, watchlist.exclude_terms)
        for story in stories:
            if story.id <= watchlist.last_article_id or not _shown(story):
                continue
            matched = matcher.match(*_story_texts(story))
            if not matched:
                continue
            db.add(WatchlistMatch(
                watchlist_id=watchlist.id,
                article_id=story.id,
                matched_terms=matched,
                emailed_at=now if watchlist.email_frequency == EMAIL_OFF else None,
            ))
            created += 1
        watchlist.last_article_id = max(watchlist.last_article_id, newest)
    db.commit()
    return created


def _story_time(article: Article) -> str:
    when = article.published_at or article.collected_at
    if when is None:
        return ""
    return when.astimezone(ZoneInfo(settings.news_timezone)).strftime("%d %b, %H:%M %Z")


def _build_email(user: User, groups: list[tuple[Watchlist, list[tuple[Article, WatchlistMatch]]]], sources: dict[int, str], daily: bool):
    total = sum(len(items) for _, items in groups)
    names = ", ".join(watchlist.name for watchlist, _ in groups)
    subject = (
        f"Defense Brief daily watchlist digest: {total} {'story' if total == 1 else 'stories'}"
        if daily else f"Defense Brief alert: {total} new {'story' if total == 1 else 'stories'} for {names}"
    )[:200]
    app_link = (settings.frontend_url or "").rstrip("/")

    text_lines = [f"Hello {user.display_name},", ""]
    html_parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#1d232a;max-width:640px">',
        f"<p>Hello {html.escape(user.display_name)},</p>",
    ]
    shown = 0
    for watchlist, items in groups:
        text_lines += [f"{watchlist.name} ({len(items)})", "-" * min(60, len(watchlist.name) + 6)]
        html_parts.append(
            f'<h3 style="margin:22px 0 6px;border-bottom:2px solid #c9a227;padding-bottom:4px">'
            f"{html.escape(watchlist.name)} <span style=\"color:#6b7280;font-weight:normal\">({len(items)})</span></h3>"
        )
        for article, match in items:
            if shown == MAX_STORIES_PER_EMAIL:
                break
            shown += 1
            meta = " · ".join(filter(None, [sources.get(article.source_id), _story_time(article)]))
            terms = ", ".join(match.matched_terms)
            text_lines += [f"* {article.title}", f"  {meta} · mentions {terms}", f"  {article.original_url}", ""]
            html_parts.append(
                '<p style="margin:10px 0">'
                f'<a href="{html.escape(article.original_url, quote=True)}" style="color:#0b5cad;font-weight:bold;text-decoration:none">'
                f"{html.escape(article.title)}</a><br>"
                f'<span style="color:#6b7280;font-size:13px">{html.escape(meta)} · mentions {html.escape(terms)}</span></p>'
            )
    if total > shown:
        more = f"...and {total - shown} more in the app."
        text_lines += [more, ""]
        html_parts.append(f"<p>{html.escape(more)}</p>")
    if app_link:
        text_lines.append(f"Open your watchlists: {app_link}/#watchlists")
        html_parts.append(f'<p><a href="{html.escape(app_link)}/#watchlists">Open your watchlists in Defense Brief</a></p>')
    footer = "You receive this because of your watchlist email settings in Defense Brief. Change them on the Watchlists page."
    text_lines += ["", footer]
    html_parts.append(f'<p style="color:#6b7280;font-size:12px">{html.escape(footer)}</p></div>')
    return subject, "\n".join(text_lines), "".join(html_parts)


def send_watchlist_emails(db: Session, frequency: str) -> int:
    """Email each reader their not-yet-emailed matches for watchlists set to `frequency`.

    One email per reader, grouped by watchlist. Matches are marked emailed only when the
    email was sent, so an unreachable mail server means they go out on a later pass.
    Returns how many emails were sent.
    """
    now = datetime.now(timezone.utc)
    pending = (
        db.query(WatchlistMatch, Watchlist, Article)
        .join(Watchlist, Watchlist.id == WatchlistMatch.watchlist_id)
        .join(Article, Article.id == WatchlistMatch.article_id)
        .filter(WatchlistMatch.emailed_at.is_(None))
        .filter(Watchlist.email_frequency == frequency)
        .filter(Watchlist.is_active.is_(True))
        .order_by(Watchlist.name.asc(), func.coalesce(Article.published_at, Article.collected_at).desc())
        .all()
    )
    by_user: dict[int, dict[int, tuple[Watchlist, list]]] = defaultdict(dict)
    for match, watchlist, article in pending:
        # Too old to be news by email; the reader still sees it in the app.
        if match.matched_at < now - EMAIL_WINDOW:
            match.emailed_at = now
            continue
        by_user[watchlist.user_id].setdefault(watchlist.id, (watchlist, []))[1].append((article, match))

    sources = dict(db.query(Source.id, Source.name).all()) if by_user else {}
    sent = 0
    for user_id, groups in by_user.items():
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            continue
        subject, text, html_body = _build_email(user, list(groups.values()), sources, daily=frequency == EMAIL_DAILY)
        if not send_email([user.email], subject, text, html_body):
            logger.info("Watchlist email for user %s not sent (email not configured or failed); kept for a later pass", user_id)
            continue
        for _, items in groups.values():
            for _, match in items:
                match.emailed_at = now
        sent += 1
    db.commit()
    return sent


def run_watchlist_pass(db: Session) -> dict:
    """Match new stories, then send the instant alerts they produced."""
    matched = match_new_stories(db)
    emailed = send_watchlist_emails(db, EMAIL_INSTANT)
    if matched or emailed:
        logger.info("Watchlists: %d new matches, %d alert emails sent", matched, emailed)
    return {"matched": matched, "emailed": emailed}


def run_daily_digest(db: Session) -> dict:
    matched = match_new_stories(db)
    emailed = send_watchlist_emails(db, EMAIL_DAILY)
    logger.info("Watchlist daily digest: %d new matches, %d digest emails sent", matched, emailed)
    return {"matched": matched, "emailed": emailed}
