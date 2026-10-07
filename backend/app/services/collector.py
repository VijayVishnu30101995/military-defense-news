from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from urllib import request
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from sqlalchemy.orm import Session

from app.core.content_filters import is_off_topic_story
from app.models.article import Article
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.repositories.article import ArticleRepository
from app.schemas.article import ArticleCreate
from app.schemas.collection import CollectionRunResponse
from app.schemas.source_collection_job import SourceCollectionJobCreate
from app.services.alerts import alert_source_failure
from app.services.source_collection_job import SourceCollectionJobService


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
        text = f"{title} {description or ''}".lower()
        keywords = {
            "Air": ["air", "fighter", "jet", "aerospace", "missile", "air defense"],
            "Naval": ["navy", "naval", "ship", "submarine", "maritime", "fleet"],
            "Land": ["army", "ground", "land", "vehicle", "tank", "deployment"],
            "Cyber": ["cyber", "hacking", "network", "data security", "digital"],
            "Space": ["space", "satellite", "orbital", "rocket", "launch"],
            "Drones": ["drone", "uav", "unmanned", "surveillance"],
            "Procurement": ["procurement", "contract", "deal", "acquisition", "order"],
            "Military Exercises": ["exercise", "drill", "training", "maneuver"],
            "Geopolitics": ["geopolitics", "diplomacy", "summit", "policy", "relations"],
        }
        matches = []
        for category, terms in keywords.items():
            if any(term in text for term in terms):
                matches.append(category)
        return matches[:3] or ["Geopolitics"]

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
            cleaned = candidate.strip()
            if not cleaned:
                continue
            if cleaned.startswith("//"):
                cleaned = f"https:{cleaned}"
            if cleaned.startswith("/") and fallback_base_url:
                cleaned = urljoin(fallback_base_url, cleaned)
            if cleaned.startswith("http://") or cleaned.startswith("https://"):
                return cleaned
        return None

    @staticmethod
    def _extract_image_from_html(html: str | None, fallback_base_url: str | None = None) -> str | None:
        if not html:
            return None

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
            r'<img[^>]+src=["\']([^"\']+)["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
            if match:
                image_url = match.group(1).strip()
                if image_url.startswith("//"):
                    image_url = f"https:{image_url}"
                if image_url.startswith("/") and fallback_base_url:
                    image_url = urljoin(fallback_base_url, image_url)
                if image_url.startswith("http://") or image_url.startswith("https://"):
                    return image_url
        return None

    def _resolve_article_image(self, article_url: str | None, fallback_base_url: str | None = None) -> str | None:
        if not article_url:
            return None

        # Google News links are redirect pages whose og:image is Google's own logo.
        if urlparse(article_url).netloc.endswith("news.google.com"):
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
                    return None
                html = response.read().decode("utf-8", errors="ignore")
                return self._extract_image_from_html(html, fallback_base_url=fallback_base_url or article_url)
        except Exception:
            return None

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

            items.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "image_url": image_url,
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
        created = 0
        for item in items:
            link = item["link"]
            title = item["title"]
            if is_off_topic_story(title, item.get("summary")):
                continue

            normalized_url = ArticleRepository.normalize_url(link)
            image_url = item.get("image_url") or self._resolve_article_image(link, fallback_base_url=source.website_url)
            duplicate = self.article_repository.find_duplicate(
                source_id=source_id,
                title=title,
                original_url=normalized_url,
                canonical_url=None,
            )
            if duplicate is not None:
                if image_url and not duplicate.image_url:
                    duplicate.image_url = image_url
                if not duplicate.summary and item.get("summary"):
                    duplicate.summary = item.get("summary")
                if not duplicate.description and item.get("summary"):
                    duplicate.description = item.get("summary")
                if duplicate.published_at is None and item.get("published"):
                    duplicate.published_at = self._parse_datetime(item.get("published"))
                self.db.commit()
                continue

            article_data = ArticleCreate(
                source_id=source_id,
                title=title,
                original_url=normalized_url,
                canonical_url=normalized_url,
                description=item.get("summary"),
                summary=item.get("summary"),
                image_url=image_url,
                language=source.language,
                country_id=source.country_id,
                region_id=source.region_id,
                published_at=self._parse_datetime(item.get("published")),
                reliability_score=source.reliability_score,
                importance_score=50,
                categories=self._infer_categories(title, item.get("summary")),
            )
            self.article_repository.create(article_data)
            created += 1

        self._upsert_job_run(source_id, "SUCCESS", articles_found=len(items), articles_created=created)
        source.last_success_at = datetime.now(timezone.utc)
        source.last_failure_at = None
        self.db.commit()

        return CollectionRunResponse(
            source_id=source_id,
            articles_found=len(items),
            articles_created=created,
            status="SUCCESS",
            message=f"Processed {len(items)} feed items and created {created} articles.",
        )
