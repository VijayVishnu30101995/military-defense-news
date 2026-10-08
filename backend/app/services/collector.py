from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import re
from urllib import request
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from googlenewsdecoder import gnewsdecoder
from sqlalchemy.orm import Session

from app.core.content_filters import score_defense_relevance
from app.models.article import Article
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.repositories.article import ArticleRepository
from app.schemas.article import ArticleCreate
from app.schemas.collection import CollectionRunResponse
from app.schemas.source_collection_job import SourceCollectionJobCreate
from app.services.alerts import alert_source_failure
from app.services.feed_text import body_text_from_html, clean_author, clean_summary, score_importance, split_paragraphs
from app.services.source_collection_job import SourceCollectionJobService

logger = logging.getLogger(__name__)

# Feeds routinely offer tracking pixels, site furniture and author avatars as the
# first image. Storing one of those is worse than storing nothing.
JUNK_IMAGE_PATTERN = re.compile(
    r"(?:1x1|\bpixel\b|spacer|blank\.|transparent\.|\bdot\.|beacon|track(?:ing)?[-_./]|"
    r"\blogo\b|wordmark|favicon|avatar|gravatar|profile[-_]pic|\bbadge\b|\bicon\b|"
    r"placeholder|default[-_](?:image|thumb)|feedburner|doubleclick|googlesyndication)",
    re.IGNORECASE,
)
# Dimensions advertised in the URL itself, e.g. .../photo-320x180.jpg or ?w=120&h=90
_URL_DIMENSIONS = re.compile(r"(?:[-_/](\d{2,4})x(\d{2,4})[._-])|(?:[?&](?:w|width)=(\d{2,4}))", re.IGNORECASE)
IMAGE_MIN_EDGE = 320
# news.google.com item links are redirects; the decoder makes network calls with no timeout
# of its own, so each decode runs in a worker thread that the collector can give up on.
GOOGLE_NEWS_DECODE_TIMEOUT_SECONDS = 20
_google_news_decoder_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gnews-decode")
JSON_LD_PATTERN = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
# Only nodes describing the story itself; breadcrumbs, organisations and "related" widgets
# carry images that belong to other pages.
ARTICLE_TYPE_PATTERN = re.compile(r"Article|Posting", re.IGNORECASE)

ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
DC_NS = "http://purl.org/dc/elements/1.1/"

# Whole-word patterns: plain substring checks tagged "affairs" as Air and "Poland" as Land.
CATEGORY_PATTERNS = {
    category: re.compile(r"\b(?:" + "|".join(terms) + r")\b")
    for category, terms in {
        "Air": [r"air ?forces?", r"aircraft", r"airmen", r"fighters?", r"jets?", r"bombers?", r"aerospace",
                r"f-\d+\w?", r"helicopters?", r"air defen[cs]e", r"airstrikes?", r"aviation"],
        "Naval": [r"nav(?:y|ies|al)", r"warships?", r"ships?", r"submarines?", r"maritime", r"fleets?",
                  r"frigates?", r"destroyers?", r"carriers?", r"coast guard", r"marines?"],
        "Land": [r"arm(?:y|ies)", r"soldiers?", r"troops", r"infantry", r"(?<!think )tanks?", r"artillery",
                 r"armou?red", r"howitzers?", r"rifles?", r"ground forces?", r"brigades?"],
        "Defense Technology": [r"missiles?", r"hypersonic", r"lasers?", r"directed[- ]energy", r"radars?",
                               r"artificial intelligence", r"a\.?i\.?", r"autonomous", r"weapons? systems?",
                               r"interceptors?", r"munitions?", r"prototypes?", r"sixth[- ]generation"],
        "Drones": [r"drones?", r"uavs?", r"uas", r"unmanned", r"uncrewed", r"loitering"],
        "Space": [r"space ?force", r"space command", r"satellites?", r"orbit(?:al)?", r"spacecraft",
                  r"space-based", r"anti-satellite"],
        "Cyber": [r"cyber\w*", r"hack(?:ers?|ing|ed)", r"ransomware", r"malware", r"data breach"],
        "Procurement": [r"procurement", r"contracts?", r"acquisitions?", r"budget", r"defen[cs]e industry",
                        r"shipyards?", r"manufactur\w+", r"orders? for", r"ordered", r"arms deals?"],
        "Military Exercises": [r"exercises?", r"drills?", r"war ?games?", r"joint training", r"maneuvers?"],
        "Geopolitics": [r"geopolitic\w*", r"diplomac\w*", r"diplomats?", r"summit", r"sanctions?", r"nato",
                        r"ceasefire", r"treaty", r"alliances?", r"tensions?", r"minister", r"talks"],
    }.items()
}


def _decode_google_news_url(article_url: str) -> str | None:
    """Return the publisher's own article URL behind a Google News link, or None."""
    future = _google_news_decoder_pool.submit(gnewsdecoder, article_url, interval=1)
    try:
        result = future.result(timeout=GOOGLE_NEWS_DECODE_TIMEOUT_SECONDS)
    except Exception:
        return None
    if not result.get("status"):
        return None
    decoded = result.get("decoded_url")
    if not decoded or urlparse(decoded).scheme not in ("http", "https"):
        return None
    if urlparse(decoded).netloc.endswith("news.google.com"):
        return None
    return decoded


def _decode_google_news_url_logged(article_url: str) -> str | None:
    decoded = _decode_google_news_url(article_url)
    if decoded is None:
        logger.warning("Could not decode Google News link %s; article page and image skipped", article_url)
    return decoded


def _json_ld_nodes(data):
    """Yield every object in a JSON-LD document, including nested @graph entries."""
    if isinstance(data, list):
        for item in data:
            yield from _json_ld_nodes(item)
    elif isinstance(data, dict):
        yield data
        yield from _json_ld_nodes(data.get("@graph"))


def _json_ld_image_urls(value) -> list[str]:
    """JSON-LD `image` may be a URL, an ImageObject, or a list of either."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return _json_ld_image_urls(value.get("url") or value.get("contentUrl"))
    if isinstance(value, list):
        return [url for entry in value for url in _json_ld_image_urls(entry)]
    return []


def _json_ld_article_images(html: str) -> list[str]:
    images: list[str] = []
    for block in JSON_LD_PATTERN.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for node in _json_ld_nodes(data):
            node_types = node.get("@type")
            node_types = [node_types] if isinstance(node_types, str) else node_types or []
            if not any(isinstance(t, str) and ARTICLE_TYPE_PATTERN.search(t) for t in node_types):
                continue
            images.extend(_json_ld_image_urls(node.get("image")))
    return images


class SourceCollectorService:
    def __init__(self, db: Session):
        self.db = db
        self.article_repository = ArticleRepository(db)
        self.job_service = SourceCollectionJobService(db)

    @staticmethod
    def _safe_text(element) -> str | None:
        if element is None:
            return None
        text = "".join(element.itertext())
        # Some feeds (e.g. Google News) put HTML inside the description.
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ").replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _infer_categories(title: str, description: str | None) -> list[str]:
        headline = title.lower()
        text = f"{headline} {(description or '').lower()}"
        scores = {}
        for category, pattern in CATEGORY_PATTERNS.items():
            hits = len(pattern.findall(text)) + len(pattern.findall(headline))
            if hits:
                scores[category] = hits
        ranked = sorted(scores, key=lambda category: scores[category], reverse=True)
        return ranked[:3] or ["Geopolitics"]

    @staticmethod
    def _normalize_http_url(value: str | None, fallback_base_url: str | None = None) -> str | None:
        if not value:
            return None

        clean = value.strip()
        if not clean:
            return None

        if clean.startswith("//"):
            clean = f"https:{clean}"
        elif clean.startswith("/") and fallback_base_url:
            clean = urljoin(fallback_base_url, clean)

        if clean.startswith("http://") or clean.startswith("https://"):
            parsed = urlparse(clean)
            normalized = parsed._replace(fragment="").geturl()
            return ArticleRepository.normalize_url(normalized)
        return None

    @staticmethod
    def _extract_link(entry, fallback_url: str | None = None) -> str | None:
        candidates: list[str] = []

        for tag in ["link", "guid"]:
            value = entry.findtext(tag)
            if value:
                candidates.append(value)

        for elem in entry.iter():
            if elem.tag.endswith("link") and elem.attrib.get("href"):
                candidates.append(elem.attrib.get("href"))

        for candidate in candidates:
            normalized = SourceCollectorService._normalize_http_url(candidate, fallback_base_url=fallback_url)
            if normalized:
                return normalized

        if not candidates and fallback_url:
            return SourceCollectorService._normalize_http_url(fallback_url)
        return None

    @staticmethod
    def _extract_image_url(entry, fallback_base_url: str | None = None) -> str | None:
        candidates: list[str] = []

        enclosure = entry.find("enclosure")
        if enclosure is not None and enclosure.attrib.get("url"):
            candidates.append(enclosure.attrib["url"])

        for tag in ["media:content", "media:thumbnail", "thumbnail", "image", "image_url"]:
            for elem in entry.iter():
                if elem.tag.rsplit("}", 1)[-1] == tag:
                    value = elem.attrib.get("url") or elem.attrib.get("href") or elem.text
                    if value:
                        candidates.append(value)

        for elem in entry.iter():
            if elem.tag.endswith("content") and elem.attrib.get("url"):
                candidates.append(elem.attrib["url"])
            if elem.tag.endswith("thumbnail") and elem.attrib.get("url"):
                candidates.append(elem.attrib["url"])

        combined_html = "".join([
            entry.findtext('description') or '',
            entry.findtext('summary') or '',
            entry.findtext('content') or '',
        ])
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)', combined_html, flags=re.IGNORECASE)
        if img_match:
            candidates.append(img_match.group(1))

        for candidate in candidates:
            usable = SourceCollectorService._usable_image_url(candidate, fallback_base_url)
            if usable:
                return usable
        return None

    @staticmethod
    def _usable_image_url(candidate: str | None, fallback_base_url: str | None = None) -> str | None:
        """Normalize a candidate image URL, or return None if it is not worth storing."""
        if not candidate:
            return None
        cleaned = candidate.strip()
        if not cleaned:
            return None

        if cleaned.startswith("//"):
            cleaned = f"https:{cleaned}"
        elif cleaned.startswith("/") and fallback_base_url:
            cleaned = urljoin(fallback_base_url, cleaned)
        # Browsers block plain http images on the https site, which previously showed up
        # as a mysteriously missing picture rather than as a collection failure.
        if cleaned.startswith("http://"):
            cleaned = "https://" + cleaned[len("http://"):]
        if not cleaned.startswith("https://"):
            return None

        if JUNK_IMAGE_PATTERN.search(cleaned):
            return None

        match = _URL_DIMENSIONS.search(cleaned)
        if match:
            dimensions = [int(group) for group in match.groups() if group]
            if dimensions and min(dimensions) < IMAGE_MIN_EDGE:
                return None
        return cleaned

    @staticmethod
    def _extract_image_from_html(
        html: str | None,
        fallback_base_url: str | None = None,
        include_inline: bool = True,
    ) -> str | None:
        """Return the article's own lead image from its page.

        Metadata (og/twitter/JSON-LD) describes the article itself. The bare <img> scan
        only guesses at it, so callers that have a feed image can skip it with
        include_inline=False and fall back to it only when nothing else exists.
        """
        if not html:
            return None

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
                usable = SourceCollectorService._usable_image_url(match.group(1), fallback_base_url)
                if usable:
                    return usable

        for image in _json_ld_article_images(html):
            usable = SourceCollectorService._usable_image_url(image, fallback_base_url)
            if usable:
                return usable

        if not include_inline:
            return None

        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE | re.DOTALL):
            # The bare <img> scan matches site furniture as readily as article art, so
            # every candidate goes through the junk screen.
            usable = SourceCollectorService._usable_image_url(match.group(1), fallback_base_url)
            if usable:
                return usable
        return None

    def _fetch_article_html(self, article_url: str | None) -> str | None:
        if not article_url:
            return None

        # Google News links are redirect pages whose og:image is Google's own logo, so
        # fetch the publisher's article they point to instead.
        if urlparse(article_url).netloc.endswith("news.google.com"):
            article_url = _decode_google_news_url_logged(article_url)
            if not article_url:
                return None

        try:
            req = request.Request(
                article_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; MilitaryDefenseNewsBot/1.0)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                method="GET",
            )
            with request.urlopen(req, timeout=15) as response:
                content_type = response.headers.get_content_type()
                if content_type != "text/html" and "xml" not in content_type:
                    logger.info("Article page %s returned %s; no page image checked", article_url, content_type)
                    return None
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            # Non-fatal: the story is still stored, just without the page's own image.
            logger.warning("Could not fetch article page %s: %s", article_url, exc)
            return None

    def _best_article_image(self, article_url: str, item: dict, source: Source) -> str | None:
        """Pick the image shown for a story: the article's own lead image first.

        Feed thumbnails are often a section or category graphic shared across many
        stories, so they only win when the article page offers nothing usable.
        """
        html = self._fetch_article_html(article_url)
        base = source.website_url
        return (
            self._extract_image_from_html(html, fallback_base_url=base or article_url, include_inline=False)
            or item.get("image_url")
            or self._extract_image_from_html(html, fallback_base_url=base or article_url, include_inline=True)
        )

    def refresh_article_images(self, limit: int = 200) -> int:
        """Re-resolve images for stored articles whose picture came from the feed.

        Articles collected before the article page was preferred keep the feed
        thumbnail. Returns how many rows changed.
        """
        candidates = (
            self.db.query(Article)
            .filter(Article.original_url.isnot(None))
            .order_by(Article.published_at.desc().nullslast())
            .limit(limit)
            .all()
        )
        changed = 0
        for article in candidates:
            source = self.db.query(Source).filter(Source.id == article.source_id).first()
            html = self._fetch_article_html(article.original_url)
            new_image = self._extract_image_from_html(
                html,
                fallback_base_url=(source.website_url if source else None) or article.original_url,
                include_inline=False,
            )
            if new_image and new_image != article.image_url:
                article.image_url = new_image
                changed += 1
        self.db.commit()
        return changed

    @staticmethod
    def _count_feed_entries(root: ElementTree.Element) -> int:
        return sum(1 for item in root.iter() if item.tag.rsplit("}", 1)[-1] in ("item", "entry"))

    def _find_feed_items(self, root: ElementTree.Element, fallback_base_url: str | None = None) -> list[dict]:
        items = []
        item_tags = ["item", "entry"]
        for item in root.iter():
            if item.tag.rsplit("}", 1)[-1] not in item_tags:
                continue

            title = None
            title_tag = item.find("title")
            if title_tag is None:
                title_tag = item.find("{http://www.w3.org/2005/Atom}title")
            if title_tag is None:
                for elem in item.iter():
                    if elem.tag.rsplit("}", 1)[-1] == "title":
                        title_tag = elem
                        break
            if title_tag is not None:
                title = self._safe_text(title_tag)

            link = self._extract_link(item, fallback_url=fallback_base_url)
            image_url = self._extract_image_url(item, fallback_base_url=fallback_base_url)

            summary = None
            for name in ["description", "summary", "content"]:
                node = item.find(name)
                if node is None:
                    node = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
                if node is not None:
                    summary = self._safe_text(node)
                    break

            published = None
            for name in ["pubDate", "published", "updated", "created_at"]:
                node = item.find(name)
                if node is None:
                    node = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
                if node is not None:
                    published = self._safe_text(node)
                    break

            if not title or not link:
                continue

            body_node = item.find(f"{{{CONTENT_NS}}}encoded")
            if body_node is None:
                body_node = item.find(f"{{{ATOM_NS}}}content")
            body = body_text_from_html("".join(body_node.itertext())) if body_node is not None else None
            summary = clean_summary(summary)
            if not summary and body:
                summary = split_paragraphs(body)[0]

            author_node = item.find(f"{{{DC_NS}}}creator")
            if author_node is None:
                author_node = item.find("author")
            if author_node is None:
                author_node = item.find(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name")
            author = clean_author(self._safe_text(author_node))

            items.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "image_url": image_url,
                "body": body,
                "author": author,
            })
        return items

    def _upsert_job_run(self, source_id: int, status: str, articles_found: int = 0, articles_created: int = 0, error: str | None = None) -> None:
        source = self.db.query(Source).filter(Source.id == source_id).first()
        job = self.job_service.get_by_source_id(source_id)
        if job is None:
            job = self.job_service.create(
                source_id,
                SourceCollectionJobCreate(
                    is_enabled=True,
                    interval_minutes=360,
                    next_run_at=None,
                ),
            )

        self.db.add(
            JobRun(
                source_collection_job_id=job.id,
                status=status,
                articles_found=articles_found,
                articles_created=articles_created,
                articles_updated=0,
                error_message=error,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
        )
        self.db.commit()

        # Update collection job timestamps and scheduling
        self.job_service.repository.update(
            job,
            last_run_at=datetime.now(timezone.utc),
            last_success_at=datetime.now(timezone.utc) if status == "SUCCESS" else job.last_success_at,
            last_failure_at=datetime.now(timezone.utc) if status == "FAILED" else job.last_failure_at,
            last_error=error,
            next_run_at=datetime.now(timezone.utc) + timedelta(minutes=job.interval_minutes or 360),
        )

        # Also update the Source model's health timestamps so source-level health is easy to query
        try:
            if source:
                now = datetime.now(timezone.utc)
                if status == "SUCCESS":
                    source.last_success_at = now
                    source.last_failure_at = None
                elif status == "FAILED":
                    source.last_failure_at = now
                # leave other statuses unchanged
                self.db.commit()

            if status == "FAILED" and source is not None:
                alert_source_failure(
                    source.name,
                    error or "Source collection failed without a detailed error.",
                    source_id=source.id,
                    source_url=source.website_url or source.feed_url,
                )
        except Exception:
            # Never let health-update failures block ingestion paths
            self.db.rollback()
            return

    def collect_source(self, source_id: int) -> CollectionRunResponse:
        source = self.db.query(Source).filter(Source.id == source_id).first()
        if source is None:
            raise ValueError("Source not found")

        if not source.is_active:
            raise ValueError("Source is inactive and cannot be collected")

        if not source.feed_url:
            raise ValueError("Source feed URL is not configured")

        req = request.Request(
            source.feed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MilitaryDefenseNewsBot/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*"
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=20) as response:
                payload = response.read()
        except Exception as exc:  # pragma: no cover - network failure path
            error = f"Failed to fetch source feed: {exc}"
            self._upsert_job_run(source_id, "FAILED", error=error)
            raise RuntimeError(error) from exc

        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            self._upsert_job_run(source_id, "FAILED", error=f"Invalid XML feed: {exc}")
            raise RuntimeError(f"Invalid XML feed: {exc}") from exc

        items = self._find_feed_items(root, fallback_base_url=source.website_url)
        entries = self._count_feed_entries(root)
        skipped = entries - len(items)
        created = 0
        for item in items:
            link = item["link"]
            title = item["title"]
            # Every item is stored with a score; the read endpoints decide what to show.
            # Keeping the low scorers means the display threshold can be retuned without
            # re-collecting feeds that have already moved on.
            relevance = score_defense_relevance(title, item.get("summary"), item.get("body"))

            normalized_url = ArticleRepository.normalize_url(link)
            duplicate = self.article_repository.find_duplicate(
                source_id=source_id,
                title=title,
                original_url=normalized_url,
                canonical_url=None,
            )
            if duplicate is not None:
                # Replace a stored logo or tracking pixel, not just a missing picture;
                # older rows were populated before the junk screen existed. Articles that
                # already have a usable picture are left alone so each collection run does
                # not re-download every story page (see refresh_article_images for those).
                if (
                    not duplicate.image_url
                    or JUNK_IMAGE_PATTERN.search(duplicate.image_url)
                    or duplicate.image_url.startswith("http://")
                ):
                    image_url = self._best_article_image(link, item, source)
                    if image_url:
                        duplicate.image_url = image_url
                if not duplicate.summary and item.get("summary"):
                    duplicate.summary = item.get("summary")
                if not duplicate.description and item.get("summary"):
                    duplicate.description = item.get("summary")
                if duplicate.published_at is None and item.get("published"):
                    duplicate.published_at = self._parse_datetime(item.get("published"))
                if not duplicate.content_excerpt and item.get("body"):
                    duplicate.content_excerpt = item.get("body")
                if not duplicate.author and item.get("author"):
                    duplicate.author = item.get("author")
                if duplicate.importance_score is None or duplicate.importance_score == 50:
                    duplicate.importance_score = score_importance(title, item.get("summary"))
                if duplicate.relevance_score is None:
                    duplicate.relevance_score = relevance
                self.db.commit()
                continue

            image_url = self._best_article_image(link, item, source)
            article_data = ArticleCreate(
                source_id=source_id,
                title=title,
                original_url=normalized_url,
                canonical_url=normalized_url,
                description=item.get("summary"),
                summary=item.get("summary"),
                content_excerpt=item.get("body"),
                author=item.get("author"),
                image_url=image_url,
                language=source.language,
                country_id=source.country_id,
                region_id=source.region_id,
                published_at=self._parse_datetime(item.get("published")),
                reliability_score=source.reliability_score,
                importance_score=score_importance(title, item.get("summary")),
                relevance_score=relevance,
                categories=self._infer_categories(title, item.get("summary")),
            )
            self.article_repository.create(article_data)
            # Flush so later items in this same feed (aggregators like Google News
            # often repeat a story across queries) are caught by find_duplicate,
            # which otherwise can't see uncommitted adds on this autoflush=False session.
            self.db.flush()
            created += 1

        # The run still counts as a success (the feed was reachable and parsed), but an
        # empty or mostly-unusable feed is recorded as a warning so admins can see why
        # nothing new arrived instead of a green status with no explanation.
        warning = None
        if not entries:
            warning = "Feed parsed but contained no entries."
        elif not items:
            warning = f"Feed contained {entries} entries but none had a usable title and link."
        elif skipped:
            warning = f"Skipped {skipped} of {entries} feed entries with no usable title or link."
        if warning:
            logger.warning("Source %s (%s): %s", source_id, source.name, warning)
        logger.info(
            "Source %s (%s) collected: entries=%d usable=%d created=%d",
            source_id, source.name, entries, len(items), created,
        )

        self._upsert_job_run(source_id, "SUCCESS", articles_found=len(items), articles_created=created, error=warning)
        source.last_success_at = datetime.now(timezone.utc)
        source.last_failure_at = None
        self.db.commit()

        return CollectionRunResponse(
            source_id=source_id,
            articles_found=len(items),
            articles_created=created,
            status="SUCCESS",
            message=f"Processed {len(items)} feed items and created {created} articles." + (f" Warning: {warning}" if warning else ""),
        )
