from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.database import SessionLocal
from app.main import app
from app.models.article import Article
from app.models.source import Source
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistMatch
from app.repositories.article import ArticleRepository
from app.services import watchlists as service
from app.services.watchlists import TermMatcher


def test_terms_match_whole_words_plurals_and_model_variants() -> None:
    matcher = TermMatcher(["drone", "F-35", "air defence", "HIMARS"], ["stock"])

    assert matcher.match("Drones hit Kyiv overnight") == ["drone"]
    assert matcher.match("New anti-drone system") == ["drone"]
    assert matcher.match("Androne launches app") == []
    assert matcher.match("First F-35A deliveries", "and more F-35s") == ["F-35"]
    assert matcher.match("Ford F-350 truck recall") == []
    assert matcher.match("Air-defence systems arrive") == ["air defence"]
    assert matcher.match("Army buys HIMARS", "and drones") == ["drone", "HIMARS"]
    # An excluded term rules the story out even when it matches.
    assert matcher.match("HIMARS maker stock rises") == []


@pytest.fixture
def world():
    """A source, two readers and a story factory; everything is removed afterwards."""
    db = SessionLocal()
    tag = uuid4().hex[:8]
    source = Source(
        name=f"Watchlist Test Source {tag}", website_url="https://example.com",
        feed_url="https://example.com/rss.xml", source_type="rss", is_active=True,
    )
    readers = [
        User(email=f"reader-{i}-{tag}@example.com", password_hash="x", display_name=f"Reader {i}")
        for i in range(2)
    ]
    db.add_all([source, *readers])
    db.commit()
    # A made-up word, so no real story in the database matches the test watchlists. It ends in
    # a letter: a term ending in a digit would also match "<word>x" as a model variant.
    word = f"zq{tag}q"

    def story(title, relevance=80, published_at=None, summary=None):
        title = f"{title} {uuid4().hex[:6]}"
        row = Article(
            source_id=source.id, title=title, normalized_title=ArticleRepository.normalize_title(title),
            original_url=f"https://example.com/{uuid4().hex}", summary=summary,
            relevance_score=relevance, published_at=published_at or datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return row

    def client(reader=0):
        c = TestClient(app)
        c.headers["Authorization"] = f"Bearer {create_access_token(str(readers[reader].id))}"
        return c

    try:
        yield db, word, story, client, readers
    finally:
        db.rollback()
        db.query(Watchlist).filter(Watchlist.user_id.in_([r.id for r in readers])).delete(synchronize_session=False)
        db.delete(source)
        for reader in readers:
            db.delete(reader)
        db.commit()
        db.close()


def _create(client, word, **extra):
    response = client.post("/api/v1/watchlists", json={"name": "Rockets", "terms": [word], **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_new_watchlist_is_filled_with_recent_stories_that_are_not_new(world) -> None:
    db, word, story, client, _ = world
    recent = story(f"Army orders {word} rockets")
    story(f"Old {word} story", published_at=datetime.now(timezone.utc) - timedelta(days=30))
    story(f"Hidden {word} story", relevance=0)
    story("Unrelated story about ships")

    preview = client().post("/api/v1/watchlists/preview", json={"terms": [word]}).json()
    created = _create(client(), word)
    matches = client().get(f"/api/v1/watchlists/{created['id']}/matches").json()

    assert preview["total"] == 1 and preview["items"][0]["id"] == recent.id
    assert (created["match_count"], created["unread_count"]) == (1, 0)
    assert [(m["id"], m["matched_terms"], m["is_new"]) for m in matches["items"]] == [(recent.id, [word], False)]
    match = db.query(WatchlistMatch).filter_by(watchlist_id=created["id"]).one()
    assert match.emailed_at is not None


def test_new_stories_are_matched_once_and_counted_as_unread(world) -> None:
    db, word, story, client, _ = world
    watchlist = _create(client(), word, email_frequency="instant")

    fresh = story("Navy news", summary=f"The navy tested {word} launchers.")
    story(f"Hidden {word} story", relevance=0)
    assert service.match_new_stories(db) == 1
    assert service.match_new_stories(db) == 0

    listing = client().get("/api/v1/watchlists").json()
    assert listing["unread_total"] == 1
    item = listing["items"][0]
    assert (item["match_count"], item["unread_count"]) == (1, 1)
    match = db.query(WatchlistMatch).filter_by(watchlist_id=watchlist["id"], article_id=fresh.id).one()
    assert match.emailed_at is None

    assert client().post(f"/api/v1/watchlists/{watchlist['id']}/seen").json() == {"marked_seen": 1}
    assert client().get("/api/v1/watchlists").json()["unread_total"] == 0


def test_stories_matched_while_email_is_off_are_never_emailed(world, monkeypatch) -> None:
    db, word, story, client, _ = world
    _create(client(), word)
    sent = []
    monkeypatch.setattr(service, "send_email", lambda *args: sent.append(args) or True)

    story(f"{word} contract signed")
    service.match_new_stories(db)

    assert service.send_watchlist_emails(db, "instant") == 0
    assert sent == []


def test_instant_alert_groups_a_readers_matches_into_one_email(world, monkeypatch) -> None:
    db, word, story, client, readers = world
    _create(client(), word, email_frequency="instant")
    _create(client(), f"{word}x", email_frequency="instant")
    _create(client(), f"{word}y", email_frequency="daily")
    sent = []
    monkeypatch.setattr(service, "send_email", lambda to, subject, text, html: sent.append((to, subject, text, html)) or True)

    first = story(f"{word} rockets ordered")
    story(f"{word}x <b>launchers</b> tested")
    story(f"{word}y digest only")
    service.match_new_stories(db)

    assert service.send_watchlist_emails(db, "instant") == 1
    (to, subject, text, html), = sent
    assert to == [readers[0].email]
    assert "2 new stories" in subject
    assert first.title in text and first.original_url in text
    assert "digest only" not in text
    # Headlines are escaped in the HTML version.
    assert "&lt;b&gt;launchers&lt;/b&gt;" in html

    # Already emailed: nothing goes out again. The daily list waits for the digest.
    assert service.send_watchlist_emails(db, "instant") == 0
    assert service.send_watchlist_emails(db, "daily") == 1
    assert "digest only" in sent[-1][2]


def test_unsent_alerts_are_kept_for_later_and_old_ones_dropped(world, monkeypatch) -> None:
    db, word, story, client, _ = world
    watchlist = _create(client(), word, email_frequency="instant")
    story(f"{word} story one")
    service.match_new_stories(db)

    monkeypatch.setattr(service, "send_email", lambda *args: False)
    assert service.send_watchlist_emails(db, "instant") == 0
    match = db.query(WatchlistMatch).filter_by(watchlist_id=watchlist["id"]).one()
    assert match.emailed_at is None

    # Mail comes back two days later: the stale alert is dropped, not sent.
    match.matched_at = datetime.now(timezone.utc) - timedelta(hours=49)
    db.commit()
    sent = []
    monkeypatch.setattr(service, "send_email", lambda *args: sent.append(args) or True)
    assert service.send_watchlist_emails(db, "instant") == 0
    db.refresh(match)
    assert sent == [] and match.emailed_at is not None


def test_editing_terms_refills_and_changing_email_skips_pending_alerts(world) -> None:
    db, word, story, client, _ = world
    watchlist = _create(client(), word, email_frequency="instant")
    story(f"{word} first story")
    other = story(f"{word}z second story")
    service.match_new_stories(db)

    updated = client().patch(f"/api/v1/watchlists/{watchlist['id']}", json={"terms": [f"{word}z"]}).json()
    assert (updated["terms"], updated["match_count"], updated["unread_count"]) == ([f"{word}z"], 1, 0)
    assert db.query(WatchlistMatch.article_id).filter_by(watchlist_id=watchlist["id"]).all() == [(other.id,)]

    story(f"{word}z third story")
    service.match_new_stories(db)
    client().patch(f"/api/v1/watchlists/{watchlist['id']}", json={"email_frequency": "daily"})
    pending = db.query(WatchlistMatch).filter_by(watchlist_id=watchlist["id"], emailed_at=None).count()
    assert pending == 0


def test_readers_cannot_see_or_change_each_others_watchlists(world) -> None:
    _, word, _, client, _ = world
    watchlist = _create(client(0), word)

    assert client(1).get("/api/v1/watchlists").json()["items"] == []
    for method, path in [
        ("get", f"/api/v1/watchlists/{watchlist['id']}/matches"),
        ("patch", f"/api/v1/watchlists/{watchlist['id']}"),
        ("post", f"/api/v1/watchlists/{watchlist['id']}/seen"),
        ("delete", f"/api/v1/watchlists/{watchlist['id']}"),
    ]:
        kwargs = {"json": {"name": "Mine now"}} if method == "patch" else {}
        assert getattr(client(1), method)(path, **kwargs).status_code == 404

    assert client(0).delete(f"/api/v1/watchlists/{watchlist['id']}").status_code == 204
    assert client(0).get("/api/v1/watchlists").json()["items"] == []


@pytest.mark.parametrize("body", [
    {"name": "x", "terms": []},
    {"name": "x", "terms": ["  "]},
    {"name": "   ", "terms": ["HIMARS"]},
    {"name": "x", "terms": ["a"]},
    {"name": "x", "terms": [f"term {i}" for i in range(21)]},
    {"name": "x", "terms": ["HIMARS"], "email_frequency": "hourly"},
])
def test_invalid_watchlists_are_rejected(world, body) -> None:
    _, _, _, client, _ = world

    assert client().post("/api/v1/watchlists", json=body).status_code == 422


def test_a_reader_can_have_at_most_twenty_watchlists(world) -> None:
    _, word, _, client, _ = world
    for i in range(20):
        _create(client(), f"{word}{i}")

    response = client().post("/api/v1/watchlists", json={"name": "One more", "terms": [word]})

    assert response.status_code == 409


def test_scheduler_starts_with_the_watchlist_jobs() -> None:
    from app.services import scheduler

    scheduler.start_collection_scheduler()
    try:
        jobs = {job.id: job for job in scheduler.scheduler.get_jobs()}
    finally:
        scheduler.scheduler.shutdown(wait=False)

    assert {"watchlist-alerts", "watchlist-daily-digest", "source-collection-scheduler"} <= set(jobs)
    assert str(jobs["watchlist-daily-digest"].trigger.timezone) == "Asia/Kolkata"
