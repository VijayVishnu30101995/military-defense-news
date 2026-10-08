from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

INK = colors.HexColor("#14170f")
MUTED = colors.HexColor("#5b6153")
ACCENT = colors.HexColor("#c8410b")
RULE = colors.HexColor("#c9c4b3")
BAND = colors.HexColor("#14170f")

PAGE_MARGIN = 18 * mm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN
MAX_IMAGE_HEIGHT = 65 * mm


@dataclass
class PdfArticle:
    position: int
    title: str
    summary: str | None = None
    key_points: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    source_name: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    image_url: str | None = None


@dataclass
class PdfNewsletter:
    title: str
    newsletter_date: date
    intro: str | None
    generated_at: datetime | None
    articles: list[PdfArticle]


def _plain(value: str | None) -> str:
    """Strip markup and collapse whitespace; reportlab's base fonts are cp1252."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _para(value: str | None) -> str:
    return escape(_plain(value))


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base",
        fontName="Helvetica",
        fontSize=10,
        leading=14.5,
        textColor=INK,
        alignment=TA_LEFT,
    )
    return {
        "kicker": ParagraphStyle(
            "kicker", parent=base, fontName="Helvetica-Bold", fontSize=8,
            leading=10, textColor=ACCENT, spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontName="Helvetica-Bold", fontSize=24,
            leading=27, spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base, fontSize=8.5, leading=11, textColor=MUTED,
        ),
        "intro": ParagraphStyle(
            "intro", parent=base, fontSize=11, leading=16, textColor=MUTED,
            spaceBefore=6, spaceAfter=4,
        ),
        "heading": ParagraphStyle(
            "heading", parent=base, fontName="Helvetica-Bold", fontSize=13.5,
            leading=17, spaceBefore=2, spaceAfter=3,
        ),
        "tags": ParagraphStyle(
            "tags", parent=base, fontName="Helvetica-Bold", fontSize=7.5,
            leading=10, textColor=ACCENT,
        ),
        "body": ParagraphStyle("body", parent=base, spaceAfter=4),
        "point": ParagraphStyle(
            "point", parent=base, fontSize=9.5, leading=13.5,
            leftIndent=12, firstLineIndent=-12, spaceAfter=1,
        ),
        "link": ParagraphStyle(
            "link", parent=base, fontSize=8.5, leading=11, textColor=ACCENT,
            spaceBefore=3,
        ),
        "empty": ParagraphStyle(
            "empty", parent=base, textColor=MUTED, spaceBefore=20,
        ),
    }


def _format_date(value: datetime | date | None) -> str:
    if value is None:
        return ""
    return f"{value.day} {value:%B %Y}"


def _fetch_image(url: str | None) -> Image | None:
    """Download and size an article image for the PDF; returns None on any failure."""
    if not url:
        return None
    try:
        request = Request(url, headers={"User-Agent": "DefenseBriefPDF/1.0"})
        with urlopen(request, timeout=6) as response:
            data = response.read()
    except (URLError, OSError, ValueError):
        return None

    try:
        pil_image = PILImage.open(BytesIO(data))
        pil_image.load()
        width_px, height_px = pil_image.size
    except Exception:
        return None

    if not width_px or not height_px:
        return None

    width = CONTENT_WIDTH
    height = width * (height_px / width_px)
    if height > MAX_IMAGE_HEIGHT:
        height = MAX_IMAGE_HEIGHT
        width = height * (width_px / height_px)

    return Image(BytesIO(data), width=width, height=height)


def _article_block(article: PdfArticle, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    meta_bits = [
        bit for bit in (article.source_name, _format_date(article.published_at)) if bit
    ]

    parts = []
    if article.categories:
        parts.append(Paragraph(_para(" / ".join(article.categories)).upper(), styles["tags"]))
    parts.append(Paragraph(f"{article.position:02d} &nbsp; {_para(article.title)}", styles["heading"]))
    image = _fetch_image(article.image_url)
    if image is not None:
        parts.append(Spacer(1, 2))
        parts.append(image)
        parts.append(Spacer(1, 4))
    if meta_bits:
        parts.append(Paragraph(_para("  |  ".join(meta_bits)), styles["meta"]))
        parts.append(Spacer(1, 4))
    if article.summary:
        parts.append(Paragraph(_para(article.summary), styles["body"]))
    for point in article.key_points[:3]:
        parts.append(Paragraph(f"&bull; &nbsp;{_para(point)}", styles["point"]))
    if article.url:
        safe_url = escape(article.url, {'"': "&quot;"})
        host = urlparse(article.url).netloc.removeprefix("www.")
        label = _para(host or article.url)
        parts.append(Paragraph(f'<a href="{safe_url}" color="#c8410b">Read the full story on {label}</a>', styles["link"]))
    parts.append(Spacer(1, 8))
    parts.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=10))
    return KeepTogether(parts)


def _draw_page(canvas, doc, newsletter_title: str) -> None:
    width, height = A4
    canvas.saveState()

    canvas.setFillColor(BAND)
    canvas.rect(0, height - 12 * mm, width, 12 * mm, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, height - 12 * mm, 4 * mm, 12 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(PAGE_MARGIN, height - 7.6 * mm, "DEFENSE BRIEF")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - PAGE_MARGIN, height - 7.6 * mm, "DAILY SITUATION REPORT")

    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(PAGE_MARGIN, 13 * mm, width - PAGE_MARGIN, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(PAGE_MARGIN, 8.5 * mm, _plain(newsletter_title)[:90])
    canvas.drawRightString(width - PAGE_MARGIN, 8.5 * mm, f"Page {doc.page}")

    canvas.restoreState()


def build_newsletter_pdf(newsletter: PdfNewsletter) -> bytes:
    styles = _styles()
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=24 * mm,
        bottomMargin=20 * mm,
        title=_plain(newsletter.title),
        author="Defense Brief",
        subject="Daily defense and security briefing",
    )

    generated = (
        f"Generated {newsletter.generated_at:%d %B %Y, %H:%M} UTC"
        if newsletter.generated_at
        else ""
    )
    story: list = [
        Paragraph("DAILY BRIEFING", styles["kicker"]),
        Paragraph(_para(newsletter.title), styles["title"]),
        Paragraph(
            _para(
                "  |  ".join(
                    bit for bit in (_format_date(newsletter.newsletter_date), generated) if bit
                )
            ),
            styles["meta"],
        ),
    ]
    if newsletter.intro:
        story.append(Paragraph(_para(newsletter.intro), styles["intro"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceBefore=6, spaceAfter=14))

    if newsletter.articles:
        story.extend(_article_block(article, styles) for article in newsletter.articles)
    else:
        story.append(Paragraph("No defense stories were selected for this edition.", styles["empty"]))

    def on_page(canvas, doc):
        _draw_page(canvas, doc, newsletter.title)

    document.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
