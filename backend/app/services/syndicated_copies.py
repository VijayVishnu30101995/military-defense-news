"""Photos and text for stories whose own publisher blocks page fetches, from outlets that
republished them.

Reuters licenses its wire stories, usually with the photo, to outlets such as Yahoo News and
The Straits Times. A Google News search for the exact headline finds those copies. The search
also returns unrelated stories, so a copy is only used when its headline is nearly identical:
a photograph or report of the wrong event is worse than none.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib import request
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

from app.services.feed_text import article_text_from_page, looks_english
from app.services.safe_fetch import MAX_FEED_BYTES, open_public_url, read_limited

if TYPE_CHECKING:
    from app.services.collector import SourceCollectorService

logger = logging.getLogger(__name__)

SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
MIN_HEADLINE_SIMILARITY = 0.8
# Short headlines match unrelated stories too easily to trust.
MIN_HEADLINE_WORDS = 4
MAX_COPIES_TRIED = 3
# Outlets whose pages never carry the story's own photo or report: social posts, market-data
# sites that use one stock illustration for every story, and Reuters' watermarked licensing previews.
SKIPPED_OUTLETS = (
    "x.com", "twitter.com", "facebook.com", "instagram.com", "threads.com", "threads.net",
    "youtube.com", "linkedin.com", "reddit.com", "tiktok.com",
    "tradingview.com", "investing.com", "euronext.com", "marketscreener.com",
    "reutersconnect.com",
)


def _is_outlet(host: str, domains) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


@dataclass
class SyndicatedCopy:
    """What other outlets' copies supplied; each part names the outlet it came from."""

    image_url: str | None = None
    image_credit: str | None = None
    text: str | None = None
    text_credit: str | None = None


def find_syndicated_copy(
    collector: SourceCollectorService,
    title: str,
    publisher_host: str | None,
    want_image: bool = True,
    want_text: bool = False,
) -> SyndicatedCopy | None:
    """Look for another outlet's copy of the story and take what was asked for from it.

    Returns None when no copy supplied anything.
    """
    words = collector._headline_words(title)
    if len(words) < MIN_HEADLINE_WORDS or not (want_image or want_text):
        return None

    own_domain = (publisher_host or "").removeprefix("www.")
    query = f'"{title}"' + (f" -site:{own_domain}" if own_domain else "")
    try:
        search = request.Request(
            SEARCH_URL.format(query=quote(query)),
            headers={"User-Agent": "Mozilla/5.0 (compatible; MilitaryDefenseNewsBot/1.0)"},
        )
        with open_public_url(search, timeout=15) as response:
            copies = collector._find_feed_items(ElementTree.fromstring(read_limited(response, MAX_FEED_BYTES)))
    except Exception as exc:
        logger.warning("Searching for copies of %r failed: %s", title, exc)
        return None

    skipped = SKIPPED_OUTLETS + ((own_domain,) if own_domain else ())
    found = SyndicatedCopy()
    tried = 0
    for copy in copies:
        outlet_url = copy.get("publisher_url")
        host = urlparse(outlet_url or "").hostname
        if not host or _is_outlet(host, skipped):
            continue
        other = collector._headline_words(copy["title"])
        if len(words & other) / len(words | other) < MIN_HEADLINE_SIMILARITY:
            continue

        tried += 1
        html = collector._fetch_article_html(copy["link"], outlet_url)
        outlet = copy.get("publisher") or host
        if want_image and not found.image_url:
            image = collector._extract_image_from_html(html, fallback_base_url=outlet_url, include_inline=False)
            if image:
                found.image_url, found.image_credit = image, outlet
        if want_text and not found.text:
            text = article_text_from_page(html)
            # The search is in English, but outlets abroad also republish translations.
            if text and looks_english(text):
                found.text, found.text_credit = text, outlet
        if (found.image_url or not want_image) and (found.text or not want_text):
            break
        if tried == MAX_COPIES_TRIED:
            break
    return found if (found.image_url or found.text) else None
