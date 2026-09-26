from datetime import date, datetime
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.newsletter import Newsletter
from app.repositories.newsletter import NewsletterRepository
from app.schemas.newsletter import NewsletterArticleSummary, NewsletterResponse


class NewsletterService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = NewsletterRepository(db)

    def _serialize_article(self, article: Article, position: int) -> NewsletterArticleSummary:
        return NewsletterArticleSummary(
            article_id=article.id,
            position=position,
            title=article.title,
            summary=article.summary or article.description,
            source_id=article.source_id,
            original_url=article.original_url,
        )

    def _serialize_newsletter(self, newsletter: Newsletter) -> NewsletterResponse:
        rows = self.repository.get_articles(newsletter.id)
        articles = [
            self._serialize_article(article, entry.position)
            for article, entry in rows
        ]
        return NewsletterResponse(
            id=newsletter.id,
            newsletter_date=newsletter.newsletter_date,
            title=newsletter.title,
            intro=newsletter.intro,
            status=newsletter.status,
            generated_at=newsletter.generated_at,
            published_at=newsletter.published_at,
            articles=articles,
        )

    def list_newsletters(self) -> list[NewsletterResponse]:
        return [self._serialize_newsletter(newsletter) for newsletter in self.repository.list_all()]

    def get_by_id(self, newsletter_id: int) -> NewsletterResponse | None:
        newsletter = self.repository.get_by_id(newsletter_id)
        if newsletter is None:
            return None
        return self._serialize_newsletter(newsletter)

    def generate_daily_newsletter(self, *, newsletter_date: date | None = None, article_limit: int = 5) -> NewsletterResponse:
        target_date = newsletter_date or date.today()
        selected_articles = (
            self.db.query(Article)
            .filter(Article.processing_status != "draft")
            .order_by(Article.importance_score.desc().nullslast(), Article.published_at.desc().nullslast(), Article.id.desc())
            .limit(article_limit)
            .all()
        )

        newsletter = self.repository.generate_for_date(target_date, selected_articles)
        return self._serialize_newsletter(newsletter)

    def generate_pdf(self, newsletter_id: int) -> bytes:
        """Generate a PDF for the given newsletter.

        Prefer HTML -> PDF using WeasyPrint when available (better CSS/layout support).
        Fall back to the existing ReportLab implementation if WeasyPrint is not installed
        or fails at runtime.
        """
        newsletter = self.repository.get_by_id(newsletter_id)
        if newsletter is None:
            raise ValueError("Newsletter not found")

        rows = self.repository.get_articles(newsletter_id)

        # Try WeasyPrint first (HTML -> PDF). This requires system libraries (cairo, pango).
        try:
            from weasyprint import HTML, CSS  # type: ignore

            def _escape(s: str) -> str:
                if s is None:
                    return ''
                return (
                    str(s)
                    .replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                )

            css = """
            @page { size: A4; margin: 20mm; }
            body { font-family: Arial, Helvetica, sans-serif; color: #111; font-size: 11pt; }
            .masthead { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
            .brand { font-weight:700; font-size:18pt; }
            .tagline { color:#666; font-size:10pt; }
            .title { font-size:16pt; font-weight:700; margin:6px 0 4px 0; }
            .meta { color: #666; margin-bottom: 10px; font-size:9pt; }
            .intro { margin-bottom:8px; }
            .article { margin-bottom: 12px; }
            .article h2 { font-size: 13pt; margin: 0 0 6px 0; }
            .article .summary { margin: 0 0 6px 0; font-size: 10pt; color:#222; }
            .article .meta { font-size:9pt; color:#555; }
            .source a { color:#0b5; text-decoration:none; }
            hr { border:none; border-top:1px solid #eee; margin:12px 0; }
            """

            def _short(s: str, limit: int = 220) -> str:
                if not s:
                    return ''
                s2 = s.strip()
                if len(s2) <= limit:
                    return s2
                return s2[:limit].rsplit(' ', 1)[0] + '…'

            import requests
            import base64

            def _inline_image(url: str) -> str:
                try:
                    if not url:
                        return ''
                    resp = requests.get(url, timeout=6)
                    if resp.status_code != 200:
                        return ''
                    content_type = resp.headers.get('Content-Type', '')
                    if not content_type:
                        content_type = 'image/jpeg'
                    data = base64.b64encode(resp.content).decode('ascii')
                    return f"data:{content_type};base64,{data}"
                except Exception:
                    return ''

            articles_html = ''
            # hero article for first item
            for idx, (article, relation) in enumerate(rows):
                title = _escape(article.title or '')
                summary = _escape(_short(article.summary or article.description or ''))
                source = _escape(article.original_url or '')
                pub = article.published_at.isoformat() if getattr(article, 'published_at', None) else ''
                image_url = getattr(article, 'image_url', None) or getattr(article, 'thumbnail_url', None) or ''
                data_uri = _inline_image(image_url) if image_url else ''

                if idx == 0:
                    # Hero layout
                    img_html = f"<img class=\"hero-img\" src=\"{data_uri}\" />" if data_uri else ''
                    articles_html += f"""
                    <div class=\"article hero\">
                      {img_html}
                      <h2>{relation.position}. {title}</h2>
                      <div class=\"summary\">{summary}</div>
                      <div class=\"meta\">Source: <span class=\"source\"><a href=\"{source}\">{_escape(article.original_url or '')}</a></span> • { _escape(pub) }</div>
                    </div>
                    """
                else:
                    thumb = f"<img class=\"thumb\" src=\"{data_uri}\" />" if data_uri else ''
                    articles_html += f"""
                    <div class=\"article row\">
                      {thumb}
                      <div class=\"col\">
                        <h3>{relation.position}. {title}</h3>
                        <div class=\"summary\">{summary}</div>
                        <div class=\"meta\">Source: <span class=\"source\"><a href=\"{source}\">{_escape(article.original_url or '')}</a></span> • { _escape(pub) }</div>
                      </div>
                    </div>
                    """

            # Add CSS adjustments for hero and thumbnails
            css = css + """
            .hero-img { width: 100%; height: 160px; object-fit: cover; margin-bottom:8px; }
            .article.row { display:flex; gap:10px; align-items:flex-start; }
            .article.row .thumb { width: 120px; height: 80px; object-fit: cover; }
            .article.row .col { flex:1; }
            .article.hero h2 { font-size: 16pt; }
            """

            html = f"""
            <!doctype html>
            <html>
            <head>
              <meta charset=\"utf-8\" />
              <title>{_escape(newsletter.title or 'Newsletter')}</title>
              <style>{css}</style>
            </head>
            <body>
              <div class=\"masthead\">\n                <div class=\"brand\">Defense Brief</div>\n                <div class=\"tagline\">Daily intelligence summary</div>\n              </div>
              <div class=\"title\">{_escape(newsletter.title or 'Daily Defense Brief')}</div>
              <div class=\"meta\">{_escape(str(newsletter.newsletter_date))} • Generated { _escape(str(newsletter.generated_at)) if newsletter.generated_at else '' }</div>
              <div class=\"intro\">{_escape(newsletter.intro or 'Daily defense brief.')}</div>
              <hr />
              {articles_html or '<p>No articles selected for this edition.</p>'}
            </body>
            </html>
            """

            pdf_bytes = HTML(string=html).write_pdf(stylesheets=[CSS(string=css)])
            return pdf_bytes
        except Exception:
            # Fall back to ReportLab implementation if WeasyPrint is unavailable or fails
            buffer = BytesIO()
            document = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                title=newsletter.title,
            )
            styles = getSampleStyleSheet()
            story = [
                Paragraph(newsletter.title, styles["Title"]),
                Spacer(1, 12),
                Paragraph(newsletter.intro or "Daily defense brief.", styles["BodyText"]),
                Spacer(1, 12),
            ]

            for article, relation in rows:
                story.append(Paragraph(f"{relation.position}. {article.title}", styles["Heading2"]))
                if article.summary or article.description:
                    story.append(Paragraph(article.summary or article.description, styles["BodyText"]))
                story.append(Paragraph(f"Source: {article.original_url}", styles["BodyText"]))
                story.append(Spacer(1, 8))

            if not rows:
                story.append(Paragraph("No articles selected for this edition.", styles["BodyText"]))

            document.build(story)
            return buffer.getvalue()
