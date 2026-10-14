from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.jwt import create_access_token
from app.database import SessionLocal
from app.main import app
from app.models.article import Article
from app.models.source import Source
from app.repositories.article import ArticleRepository


@pytest.fixture
def stories():
    """Stories either side of midnight in Asia/Kolkata (UTC+5:30), plus undated and hidden ones."""
    db = SessionLocal()
    tag = uuid4().hex[:10]
    source = Source(
        name=f"Report Test Source {tag}", website_url="https://example.com",
        feed_url="https://example.com/rss.xml", source_type="rss", is_active=True,
    )
    db.add(source)
    db.commit()

    def article(label, published_at, relevance=80):
        title = f"{label} navy frigate story {tag}"
        row = Article(
            source_id=source.id, title=title, normalized_title=ArticleRepository.normalize_title(title),
            original_url=f"https://example.com/{uuid4().hex}", summary=f"Summary of the {label} story.",
            relevance_score=relevance, published_at=published_at,
        )
        db.add(row)
        return row

    rows = {
        # 23:59 IST on 13 October and 00:01 IST on 14 October.
        "late": article("Late", datetime(2026, 10, 13, 18, 29, tzinfo=timezone.utc)),
        "early": article("Early", datetime(2026, 10, 13, 18, 31, tzinfo=timezone.utc)),
        "undated": article("Undated", None),
        "hidden": article("Hidden", datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc), relevance=0),
    }
    db.commit()
    try:
        yield tag, {key: row.id for key, row in rows.items()}
    finally:
        db.rollback()
        db.delete(source)
        db.commit()
        db.close()


def _client():
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token('1')}"
    return client


def _ids(response):
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_date_filter_uses_publication_day_in_the_news_timezone(stories) -> None:
    tag, ids = stories
    client = _client()

    on_14th = client.get("/api/v1/articles", params={"q": tag, "published_from": "2026-10-14", "published_to": "2026-10-14"})
    on_13th = client.get("/api/v1/articles", params={"q": tag, "published_from": "2026-10-13", "published_to": "2026-10-13"})
    undated = client.get("/api/v1/articles", params={"q": tag})

    assert _ids(on_14th) == [ids["early"]]
    assert _ids(on_13th) == [ids["late"]]
    # Without a date filter the undated story is listed; the hidden one never is.
    assert set(_ids(undated)) == {ids["early"], ids["late"], ids["undated"]}


def test_date_filter_rejects_a_reversed_range() -> None:
    response = _client().get("/api/v1/articles", params={"published_from": "2026-10-14", "published_to": "2026-10-13"})

    assert response.status_code == 422


def test_selection_returns_every_match_across_pages(stories) -> None:
    tag, ids = stories

    response = _client().get("/api/v1/articles/selection", params={"q": tag})

    assert response.json()["total"] == 3
    assert set(_ids(response)) == {ids["early"], ids["late"], ids["undated"]}
    assert response.json()["items"][0]["title"].endswith(tag)


@pytest.fixture
def captured_report(monkeypatch):
    import app.api.v1.reports as reports_module

    captured = {}

    def fake_build(report):
        captured["report"] = report
        return b"%PDF-fake"

    monkeypatch.setattr(reports_module, "build_report_pdf", fake_build)
    return captured


def test_report_orders_and_skips_unavailable_stories(stories, captured_report) -> None:
    _, ids = stories
    client = _client()
    requested = [ids["late"], 999999999, ids["hidden"], ids["early"]]

    def titles(order):
        response = client.post("/api/v1/reports/pdf", json={"article_ids": requested, "order": order})
        assert response.status_code == 200, response.text
        return [article.title.split()[0] for article in captured_report["report"].articles]

    assert titles("newest") == ["Early", "Late"]
    assert titles("oldest") == ["Late", "Early"]
    assert titles("custom") == ["Late", "Early"]


def test_report_passes_title_dates_and_options(stories, captured_report) -> None:
    _, ids = stories

    response = _client().post("/api/v1/reports/pdf", json={
        "title": "Weekly Naval Digest",
        "date_from": "2026-10-13",
        "date_to": "2026-10-14",
        "article_ids": [ids["late"]],
        "include_images": False,
        "include_links": False,
    })

    report = captured_report["report"]
    assert response.headers["content-disposition"] == 'attachment; filename="weekly-naval-digest.pdf"'
    assert (report.title, str(report.date_from), str(report.date_to)) == ("Weekly Naval Digest", "2026-10-13", "2026-10-14")
    assert report.options.include_images is False and report.options.include_links is False
    assert report.options.include_summary is True
    assert report.timezone_name == "Asia/Kolkata"


def test_report_with_no_available_stories_is_404(stories) -> None:
    _, ids = stories

    response = _client().post("/api/v1/reports/pdf", json={"article_ids": [ids["hidden"], 999999999]})

    assert response.status_code == 404


@pytest.mark.parametrize("body", [
    {"article_ids": []},
    {"article_ids": list(range(1, 52))},
    {"article_ids": [1], "date_from": "2026-10-14", "date_to": "2026-10-13"},
    {"article_ids": [1], "title": "   "},
])
def test_report_rejects_invalid_requests(body) -> None:
    assert _client().post("/api/v1/reports/pdf", json=body).status_code == 422


def test_report_builds_a_real_pdf_without_network(stories) -> None:
    _, ids = stories

    response = _client().post(
        "/api/v1/reports/pdf", json={"article_ids": [ids["late"], ids["early"]], "include_images": False}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_report_drops_a_summary_that_only_repeats_the_headline() -> None:
    from datetime import date

    from reportlab.platypus import Paragraph

    from app.services.newsletter_pdf import PdfArticle, PdfReport, _report_article, _report_styles

    def summaries(summary):
        article = PdfArticle(position=1, title="Russian strikes kill one in Kyiv", summary=summary, url="https://example.com/a")
        report = PdfReport("Report", date(2026, 10, 14), None, datetime.now(timezone.utc), [article])
        flowables = _report_article(article, None, report, _report_styles())[1]._content
        return [f.getPlainText() for f in flowables if isinstance(f, Paragraph) and f.style.name == "report_summary"]

    assert summaries("Russian strikes kill one in Kyiv Reuters") == []
    assert summaries("A Russian drone hit an apartment block overnight, officials said.") == [
        "A Russian drone hit an apartment block overnight, officials said."
    ]
