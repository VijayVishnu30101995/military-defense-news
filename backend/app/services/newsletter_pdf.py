from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

INK = colors.HexColor("#14170f")
BODY_INK = colors.HexColor("#23261e")
MUTED = colors.HexColor("#5b6153")
ACCENT = colors.HexColor("#c8410b")
RULE = colors.HexColor("#c9c4b3")
BAND = colors.HexColor("#14170f")
BAND_MUTED = colors.HexColor("#a9ae9f")
PAPER = colors.HexColor("#f4f0e6")

PAGE_WIDTH, PAGE_HEIGHT = A4
PAGE_MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * PAGE_MARGIN
HEADER_HEIGHT = 12 * mm
COVER_BAND_HEIGHT = 78 * mm
TOP_MARGIN = 24 * mm
BOTTOM_MARGIN = 20 * mm

IMAGE_TIMEOUT_SECONDS = 6
IMAGE_MAX_PIXELS = 1400
IMAGE_MIN_PIXELS = 480

BRAND = "DEFENSE BRIEF"
TAGLINE = "DAILY DEFENSE & SECURITY INTELLIGENCE REPORT"


@dataclass
class PdfArticle:
    position: int
    title: str
    summary: str | None = None
    body: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    source_name: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    image_url: str | None = None


@dataclass
class PdfRelated:
    title: str
    source_name: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    categories: list[str] = field(default_factory=list)


@dataclass
class PdfNewsletter:
    title: str
    newsletter_date: date
    intro: str | None
    generated_at: datetime | None
    articles: list[PdfArticle]
    related: list[PdfRelated] = field(default_factory=list)
    edition: int | None = None


# ---------------------------------------------------------------- text helpers


def _plain(value: str | None) -> str:
    """Strip markup and collapse whitespace; the PDF base fonts only cover cp1252."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    text = text.encode("cp1252", errors="ignore").decode("cp1252")
    # Dropping unsupported scripts (e.g. Japanese names) can leave empty brackets behind.
    text = re.sub(r"[(\[]\s*[)\]]", "", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r" ([,.;:])", r"\1", text).strip()


def _para(value: str | None) -> str:
    return escape(_plain(value))


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _host(url: str | None) -> str:
    return urlparse(url or "").netloc.removeprefix("www.")


def _format_date(value: datetime | date | None) -> str:
    if value is None:
        return ""
    return f"{value.day} {value:%B %Y}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return f"{_format_date(value)}, {value:%H:%M} UTC"


# ---------------------------------------------------------------------- images


def _fetch_image(url: str | None, aspect: float) -> bytes | None:
    """Download an image and centre-crop it to `aspect` (width / height) as a compact JPEG."""
    if not url:
        return None
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DefenseBriefPDF/1.0)"})
        with urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
            data = response.read()
    except (URLError, OSError, ValueError):
        return None

    try:
        image = PILImage.open(BytesIO(data))
        image.load()
    except Exception:
        return None

    width, height = image.size
    # Feed thumbnails (e.g. BBC's 240px images) look blurry when stretched to full page width.
    if width < IMAGE_MIN_PIXELS or height < IMAGE_MIN_PIXELS / aspect:
        return None

    if width / height > aspect:
        new_width = int(height * aspect)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / aspect)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))

    if image.width > IMAGE_MAX_PIXELS:
        image = image.resize((IMAGE_MAX_PIXELS, int(IMAGE_MAX_PIXELS / aspect)))
    if image.mode != "RGB":
        image = image.convert("RGB")

    output = BytesIO()
    image.save(output, format="JPEG", quality=82, optimize=True)
    return output.getvalue()


def _image_aspect(article: PdfArticle) -> float:
    return 16 / 9 if article.position == 1 else 2.1


def _prefetch_images(articles: list[PdfArticle]) -> dict[int, bytes | None]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            article.position: pool.submit(_fetch_image, article.image_url, _image_aspect(article))
            for article in articles
            if article.image_url
        }
        return {position: future.result() for position, future in futures.items()}


# ------------------------------------------------------------------- branding


def _draw_emblem(canvas, x: float, y: float, size: float, fill=ACCENT, mark=colors.white) -> None:
    """Shield with double chevron; (x, y) is the bottom-left corner of its bounding box."""
    width = size * 0.82
    canvas.saveState()
    canvas.setFillColor(fill)
    path = canvas.beginPath()
    path.moveTo(x, y + size)
    path.lineTo(x + width, y + size)
    path.lineTo(x + width, y + size * 0.48)
    path.curveTo(x + width, y + size * 0.2, x + width * 0.72, y + size * 0.08, x + width / 2, y)
    path.curveTo(x + width * 0.28, y + size * 0.08, x, y + size * 0.2, x, y + size * 0.48)
    path.close()
    canvas.drawPath(path, stroke=0, fill=1)

    canvas.setStrokeColor(mark)
    canvas.setLineWidth(size * 0.085)
    canvas.setLineJoin(0)
    canvas.setLineCap(0)
    for offset in (0.62, 0.38):
        chevron = canvas.beginPath()
        chevron.moveTo(x + width * 0.2, y + size * (offset + 0.12))
        chevron.lineTo(x + width / 2, y + size * (offset - 0.04))
        chevron.lineTo(x + width * 0.8, y + size * (offset + 0.12))
        canvas.drawPath(chevron, stroke=1, fill=0)
    canvas.restoreState()


def _draw_spaced(canvas, x: float, y: float, text: str, font: str, size: float, spacing: float, align: str = "left") -> None:
    width = canvas.stringWidth(text, font, size) + spacing * max(len(text) - 1, 0)
    if align == "right":
        x -= width
    text_object = canvas.beginText(x, y)
    text_object.setFont(font, size)
    text_object.setCharSpace(spacing)
    text_object.textLine(text)
    # Character spacing persists in the PDF graphics state, so reset it for later text.
    text_object.setCharSpace(0)
    canvas.drawText(text_object)


# ------------------------------------------------------------- page furniture


class _NumberedCanvas(pdf_canvas.Canvas):
    """Defers page numbering until the total page count is known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_states: list[dict] = []

    def showPage(self):
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self.setFont("Helvetica", 8)
                self.setFillColor(MUTED)
                self.drawRightString(PAGE_WIDTH - PAGE_MARGIN, 8.5 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _draw_footer(canvas, newsletter: PdfNewsletter) -> None:
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(PAGE_MARGIN, 13 * mm, PAGE_WIDTH - PAGE_MARGIN, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(PAGE_MARGIN, 8.5 * mm, BRAND)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(
        PAGE_MARGIN + canvas.stringWidth(BRAND, "Helvetica-Bold", 7.5) + 6,
        8.5 * mm,
        f"Open-source briefing  |  {_format_date(newsletter.newsletter_date)}",
    )


def _draw_cover(canvas, doc, newsletter: PdfNewsletter) -> None:
    canvas.saveState()
    top = PAGE_HEIGHT
    canvas.setFillColor(BAND)
    canvas.rect(0, top - COVER_BAND_HEIGHT, PAGE_WIDTH, COVER_BAND_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, top - COVER_BAND_HEIGHT, PAGE_WIDTH, 2.2 * mm, stroke=0, fill=1)

    emblem_size = 24 * mm
    _draw_emblem(canvas, PAGE_MARGIN, top - 18 * mm - emblem_size, emblem_size)

    text_x = PAGE_MARGIN + emblem_size * 0.82 + 7 * mm
    canvas.setFillColor(colors.white)
    _draw_spaced(canvas, text_x, top - 31 * mm, BRAND, "Helvetica-Bold", 34, 1.5)
    canvas.setFillColor(ACCENT)
    _draw_spaced(canvas, text_x, top - 39.5 * mm, TAGLINE, "Helvetica-Bold", 8.5, 1.6)

    canvas.setStrokeColor(colors.HexColor("#3a3f33"))
    canvas.setLineWidth(0.6)
    canvas.line(PAGE_MARGIN, top - 54 * mm, PAGE_WIDTH - PAGE_MARGIN, top - 54 * mm)

    canvas.setFillColor(BAND_MUTED)
    edition_bits = []
    if newsletter.edition:
        edition_bits.append(f"EDITION NO. {newsletter.edition}")
    edition_bits.append(f"{newsletter.newsletter_date:%A}, {_format_date(newsletter.newsletter_date)}".upper())
    _draw_spaced(canvas, PAGE_MARGIN, top - 63 * mm, "   |   ".join(edition_bits), "Helvetica-Bold", 8, 1.2)
    if newsletter.generated_at:
        _draw_spaced(
            canvas,
            PAGE_WIDTH - PAGE_MARGIN,
            top - 63 * mm,
            f"COMPILED {_format_datetime(newsletter.generated_at).upper()}",
            "Helvetica",
            8,
            1.2,
            align="right",
        )
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(PAGE_MARGIN, top - 70.5 * mm, _plain(newsletter.title)[:110])

    _draw_footer(canvas, newsletter)
    canvas.restoreState()


def _draw_page(canvas, doc, newsletter: PdfNewsletter) -> None:
    canvas.saveState()
    top = PAGE_HEIGHT
    canvas.setFillColor(BAND)
    canvas.rect(0, top - HEADER_HEIGHT, PAGE_WIDTH, HEADER_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, top - HEADER_HEIGHT, PAGE_WIDTH, 0.8 * mm, stroke=0, fill=1)

    _draw_emblem(canvas, PAGE_MARGIN, top - 9.6 * mm, 7 * mm)
    canvas.setFillColor(colors.white)
    _draw_spaced(canvas, PAGE_MARGIN + 8.5 * mm, top - 7.6 * mm, BRAND, "Helvetica-Bold", 9, 1.2)
    canvas.setFillColor(BAND_MUTED)
    _draw_spaced(
        canvas,
        PAGE_WIDTH - PAGE_MARGIN,
        top - 7.6 * mm,
        f"DAILY SITUATION REPORT  |  {_format_date(newsletter.newsletter_date).upper()}",
        "Helvetica",
        7.5,
        1,
        align="right",
    )

    _draw_footer(canvas, newsletter)
    canvas.restoreState()


class _BriefDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "headline":
            key = getattr(flowable, "_bookmark", None)
            number = getattr(flowable, "_position", 0)
            text = flowable.getPlainText()
            self.notify("TOCEntry", (0, f"<b>{number:02d}</b>&nbsp;&nbsp;&nbsp;{escape(text)}", self.page, key))
            if key:
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0)


# --------------------------------------------------------------------- styles


def _styles() -> dict[str, ParagraphStyle]:
    sans = ParagraphStyle("sans", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, alignment=TA_LEFT)
    serif = ParagraphStyle("serif", fontName="Times-Roman", fontSize=10.8, leading=15.6, textColor=BODY_INK)
    return {
        "section": ParagraphStyle(
            "section", parent=sans, fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=ACCENT, spaceAfter=5,
        ),
        "overview": ParagraphStyle(
            "overview", parent=serif, fontName="Times-Roman", fontSize=13, leading=19, textColor=INK,
            spaceAfter=10,
        ),
        "kicker": ParagraphStyle(
            "kicker", parent=sans, fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=ACCENT, spaceAfter=4,
        ),
        "headline": ParagraphStyle(
            "headline", parent=sans, fontName="Helvetica-Bold", fontSize=20, leading=24,
            textColor=INK, spaceAfter=6,
        ),
        "lead_headline": ParagraphStyle(
            "headline", parent=sans, fontName="Helvetica-Bold", fontSize=25, leading=29,
            textColor=INK, spaceAfter=7,
        ),
        "byline": ParagraphStyle("byline", parent=sans, fontSize=8.5, leading=12, textColor=MUTED),
        "teaser_headline": ParagraphStyle(
            "teaser_headline", parent=sans, fontName="Helvetica-Bold", fontSize=15, leading=18.5,
            textColor=INK, spaceAfter=5,
        ),
        "teaser_text": ParagraphStyle(
            "teaser_text", parent=serif, fontSize=10, leading=14, spaceAfter=6,
        ),
        "credit": ParagraphStyle(
            "credit", parent=sans, fontSize=7, leading=9, textColor=MUTED, spaceBefore=2, spaceAfter=8,
        ),
        "standfirst": ParagraphStyle(
            "standfirst", parent=serif, fontName="Times-Bold", fontSize=12.5, leading=17.5,
            textColor=INK, spaceAfter=9,
        ),
        "body": ParagraphStyle("body", parent=serif, spaceAfter=7),
        "box_title": ParagraphStyle(
            "box_title", parent=sans, fontName="Helvetica-Bold", fontSize=7.5, leading=10,
            textColor=ACCENT, spaceAfter=4,
        ),
        "box_text": ParagraphStyle("box_text", parent=sans, fontSize=9, leading=13, textColor=BODY_INK),
        "point": ParagraphStyle(
            "point", parent=sans, fontSize=9, leading=13, leftIndent=10, firstLineIndent=-10,
            textColor=BODY_INK, spaceAfter=2,
        ),
        "source": ParagraphStyle("source", parent=sans, fontSize=8.5, leading=12, textColor=MUTED, spaceBefore=4),
        "stat_value": ParagraphStyle(
            "stat_value", parent=sans, fontName="Helvetica-Bold", fontSize=20, leading=22, textColor=INK,
        ),
        "stat_label": ParagraphStyle(
            "stat_label", parent=sans, fontName="Helvetica-Bold", fontSize=6.8, leading=9, textColor=MUTED,
        ),
        "toc": ParagraphStyle(
            "toc", parent=sans, fontName="Helvetica", fontSize=10, leading=14, textColor=INK,
            leftIndent=0, spaceBefore=3, spaceAfter=3,
        ),
        "related_title": ParagraphStyle(
            "related_title", parent=sans, fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK,
        ),
        "related_meta": ParagraphStyle(
            "related_meta", parent=sans, fontSize=8, leading=11, textColor=MUTED, spaceAfter=8,
        ),
        "reference": ParagraphStyle(
            "reference", parent=sans, fontSize=8.5, leading=12, textColor=BODY_INK, leftIndent=16,
            firstLineIndent=-16, spaceAfter=4,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=sans, fontSize=7.5, leading=10.5, textColor=MUTED, spaceBefore=14,
        ),
        "empty": ParagraphStyle("empty", parent=sans, textColor=MUTED, spaceBefore=20),
    }


def _boxed(flowables: list, background=PAPER, accent=ACCENT) -> Table:
    table = Table([[flowables]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), background),
            ("LINEBEFORE", (0, 0), (0, -1), 2.2, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 11),
            ("RIGHTPADDING", (0, 0), (-1, -1), 11),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ])
    )
    return table


def _link(url: str, label: str) -> str:
    return f'<a href="{_attr(url)}" color="#c8410b">{label}</a>'


# ------------------------------------------------------------------- sections


def _lead_teaser(article: PdfArticle, image_data: bytes | None, styles: dict[str, ParagraphStyle]) -> Table:
    text: list = []
    if article.categories:
        text.append(Paragraph(_para(" / ".join(article.categories[:2])).upper(), styles["kicker"]))
    text.append(Paragraph(_para(article.title), styles["teaser_headline"]))
    if article.summary:
        summary = _plain(article.summary)
        if len(summary) > 260:
            summary = summary[:257].rsplit(" ", 1)[0] + "..."
        text.append(Paragraph(escape(summary), styles["teaser_text"]))
    source = " &middot; ".join(_para(bit) for bit in (article.source_name, _format_date(article.published_at)) if bit)
    text.append(Paragraph(f"{source}{' &middot; ' if source else ''}<b>Full report on page 2</b>", styles["byline"]))

    image_width = CONTENT_WIDTH * 0.44
    if image_data:
        image = Image(BytesIO(image_data), width=image_width, height=image_width / _image_aspect(article))
        table = Table([[image, text]], colWidths=[image_width, CONTENT_WIDTH - image_width])
        padding = [("LEFTPADDING", (1, 0), (1, 0), 12), ("LEFTPADDING", (0, 0), (0, 0), 0)]
    else:
        table = Table([[text]], colWidths=[CONTENT_WIDTH])
        padding = [("LEFTPADDING", (0, 0), (-1, -1), 0)]
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        *padding,
    ]))
    return table


def _cover_section(
    newsletter: PdfNewsletter,
    images: dict[int, bytes | None],
    styles: dict[str, ParagraphStyle],
) -> list:
    sources = {article.source_name for article in newsletter.articles if article.source_name}
    categories = {category for article in newsletter.articles for category in article.categories}
    full_reports = sum(1 for article in newsletter.articles if article.body)

    def stat(value: int, label: str) -> list:
        return [Paragraph(str(value), styles["stat_value"]), Paragraph(label, styles["stat_label"])]

    stats = Table(
        [[
            stat(len(newsletter.articles), "STORIES IN THIS EDITION"),
            stat(len(sources), "SOURCES CITED"),
            stat(len(categories), "CATEGORIES COVERED"),
            stat(full_reports, "FULL-LENGTH REPORTS"),
        ]],
        colWidths=[CONTENT_WIDTH / 4] * 4,
    )
    stats.setStyle(
        TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1.2, INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
            ("LINEAFTER", (0, 0), (-2, 0), 0.5, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ])
    )

    toc = TableOfContents()
    toc.levelStyles = [styles["toc"]]
    toc.dotsMinLevel = 0

    story: list = [Spacer(1, COVER_BAND_HEIGHT - TOP_MARGIN + 8 * mm)]
    story.append(Paragraph("BRIEFING OVERVIEW", styles["section"]))
    story.append(
        Paragraph(
            _para(newsletter.intro or "Today's briefing summarises the most significant defense and security developments."),
            styles["overview"],
        )
    )
    story += [stats, Spacer(1, 9 * mm)]
    if newsletter.articles:
        lead = newsletter.articles[0]
        story += [
            Paragraph("LEAD STORY", styles["section"]),
            _lead_teaser(lead, images.get(lead.position), styles),
            Spacer(1, 9 * mm),
        ]
    story += [Paragraph("IN THIS EDITION", styles["section"]), toc, PageBreak()]
    return story


def _article_section(
    article: PdfArticle,
    image_data: bytes | None,
    styles: dict[str, ParagraphStyle],
) -> list:
    is_lead = article.position == 1
    kicker_bits = [f"{article.position:02d}"]
    if is_lead:
        kicker_bits.append("LEAD STORY")
    if article.categories:
        kicker_bits.append(" / ".join(article.categories[:3]).upper())

    headline = Paragraph(_para(article.title), styles["lead_headline" if is_lead else "headline"])
    headline._bookmark = f"article-{article.position}"
    headline._position = article.position

    byline_bits = []
    if article.author:
        byline_bits.append(f"By <b>{_para(article.author)}</b>")
    if article.source_name:
        byline_bits.append(_para(article.source_name))
    if article.published_at:
        byline_bits.append(_para(_format_datetime(article.published_at)))

    header: list = [Paragraph("  |  ".join(kicker_bits), styles["kicker"]), headline]
    if byline_bits:
        header.append(Paragraph("  &middot;  ".join(byline_bits), styles["byline"]))
    header.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=7, spaceAfter=9))
    if image_data:
        aspect = _image_aspect(article)
        header.append(Image(BytesIO(image_data), width=CONTENT_WIDTH, height=CONTENT_WIDTH / aspect))
        credit = f"Image: {article.source_name}" if article.source_name else "Image courtesy of the publisher"
        header.append(Paragraph(_para(credit), styles["credit"]))

    story: list = [CondPageBreak(95 * mm), KeepTogether(header)]

    summary = _plain(article.summary)
    body = [_plain(paragraph) for paragraph in article.body]
    body = [paragraph for paragraph in body if paragraph]
    # Feed descriptions are often the body's opening cut off with "...": promote the full first paragraph instead.
    teaser = re.sub(r"\s*\[?(\.\.\.|…)\]?\s*$", "", summary)[:100]
    if body and (not summary or " ".join(body).startswith(teaser)):
        summary, body = body[0], body[1:]

    if summary:
        story.append(Paragraph(escape(summary), styles["standfirst"]))
    for paragraph in body:
        story.append(Paragraph(escape(paragraph), styles["body"]))

    if article.key_points:
        box = [Paragraph("KEY POINTS", styles["box_title"])]
        box += [Paragraph(f"&bull;&nbsp; {_para(point)}", styles["point"]) for point in article.key_points[:4]]
        story += [Spacer(1, 4), _boxed(box)]

    if article.url:
        host = _host(article.url) or article.url
        if body:
            text = f"Original reporting: {_link(article.url, _para(article.source_name or host))} &middot; {_para(host)}"
            story.append(Paragraph(text, styles["source"]))
        else:
            note = [
                Paragraph("FULL REPORT", styles["box_title"]),
                Paragraph(
                    f"{_para(article.source_name or host)} publishes only a summary of this story in its feed. "
                    f"The complete report is available at {_link(article.url, _para(host))}.",
                    styles["box_text"],
                ),
            ]
            story += [Spacer(1, 4), _boxed(note)]

    story.append(Spacer(1, 10 * mm))
    return story


def _related_section(related: list[PdfRelated], styles: dict[str, ParagraphStyle]) -> list:
    if not related:
        return []
    story: list = [
        CondPageBreak(70 * mm),
        Paragraph("RELATED COVERAGE", styles["section"]),
        HRFlowable(width="100%", thickness=1.2, color=INK, spaceAfter=9),
    ]
    for item in related:
        title = _para(item.title)
        if item.url:
            title = _link(item.url, title).replace('color="#c8410b"', 'color="#14170f"')
        meta = [bit for bit in (
            " / ".join(item.categories[:2]).upper() if item.categories else "",
            _plain(item.source_name),
            _format_date(item.published_at),
        ) if bit]
        story.append(Paragraph(title, styles["related_title"]))
        story.append(Paragraph(escape("  |  ".join(meta)), styles["related_meta"]))
    return story


def _references_section(newsletter: PdfNewsletter, styles: dict[str, ParagraphStyle]) -> list:
    articles = [article for article in newsletter.articles if article.url]
    story: list = [Spacer(1, 6 * mm)]
    if articles:
        story += [
            CondPageBreak(60 * mm),
            Paragraph("SOURCES &amp; REFERENCES", styles["section"]),
            HRFlowable(width="100%", thickness=1.2, color=INK, spaceAfter=9),
        ]
        for article in articles:
            bits = [_para(article.source_name or _host(article.url)), f"&ldquo;{_para(article.title)}&rdquo;"]
            if article.published_at:
                bits.append(_para(_format_date(article.published_at)))
            text = f"[{article.position}]&nbsp;&nbsp;{', '.join(bits)}. {_link(article.url, _para(article.url))}"
            story.append(Paragraph(text, styles["reference"]))

    story.append(
        Paragraph(
            "This briefing is compiled from open-source reporting by the publications credited above. "
            "Article text and images remain the copyright of their respective publishers; follow the "
            "reference links for the original reports.",
            styles["disclaimer"],
        )
    )
    return story


# ------------------------------------------------------------------------ build


def build_newsletter_pdf(newsletter: PdfNewsletter) -> bytes:
    styles = _styles()
    images = _prefetch_images(newsletter.articles)

    story: list = _cover_section(newsletter, images, styles)
    if newsletter.articles:
        for article in newsletter.articles:
            story += _article_section(article, images.get(article.position), styles)
    else:
        story.append(Paragraph("No defense stories were selected for this edition.", styles["empty"]))
    story += _related_section(newsletter.related, styles)
    story += _references_section(newsletter, styles)

    buffer = BytesIO()
    document = _BriefDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=_plain(newsletter.title),
        author="Defense Brief",
        subject="Daily defense and security briefing",
        creator="Defense Brief",
    )
    document.multiBuild(
        story,
        onFirstPage=lambda canvas, doc: _draw_cover(canvas, doc, newsletter),
        onLaterPages=lambda canvas, doc: _draw_page(canvas, doc, newsletter),
        canvasmaker=_NumberedCanvas,
    )
    return buffer.getvalue()
