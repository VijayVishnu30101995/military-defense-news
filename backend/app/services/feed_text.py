from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

MAX_BODY_CHARS = 20000
MIN_BODY_WORDS = 60

_BLOCK_TAGS = {
    "p", "div", "section", "article", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "ul", "ol", "blockquote", "pre", "table", "tr",
}
# Media, embeds and captions read as noise once flattened to plain text.
_SKIP_TAGS = {"script", "style", "figure", "figcaption", "iframe", "noscript", "svg", "video", "audio", "form", "button"}
_BOILERPLATE = [
    re.compile(r"^the post .+ appeared first on .+\.?$", re.I),
    re.compile(r"^(advertisement|related:?|read more:?|subscribe.*|sign up.*newsletter.*)$", re.I),
    re.compile(r"^continue reading", re.I),
    re.compile(r"^contact the authors?:", re.I),
]
_TRAILING_POST_NOTICE = re.compile(r"\s*The post .+? appeared first on .+?\.?\s*$", re.I | re.S)


def clean_summary(value: str | None) -> str | None:
    if not value:
        return None
    text = _TRAILING_POST_NOTICE.sub("", value).strip()
    return text or None


class _ParagraphCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        self._buffer = []
        if text:
            self.paragraphs.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self._skip_depth:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if not self._skip_depth:
            self._buffer.append(data)

    def close(self):
        super().close()
        self._flush()


def html_to_paragraphs(html: str | None) -> list[str]:
    if not html or not html.strip():
        return []
    parser = _ParagraphCollector()
    try:
        parser.feed(unescape(html) if "&lt;" in html else html)
        parser.close()
    except Exception:
        return []

    paragraphs = []
    for paragraph in parser.paragraphs:
        cleaned = paragraph.replace("\xa0", " ").strip()
        if not cleaned or any(pattern.match(cleaned) for pattern in _BOILERPLATE):
            continue
        if paragraphs and paragraphs[-1] == cleaned:
            continue
        paragraphs.append(cleaned)
    return paragraphs


def body_text_from_html(html: str | None) -> str | None:
    """Full article body as plain paragraphs separated by blank lines, or None if too thin."""
    paragraphs = html_to_paragraphs(html)
    if sum(len(p.split()) for p in paragraphs) < MIN_BODY_WORDS:
        return None

    kept: list[str] = []
    length = 0
    for paragraph in paragraphs:
        if length + len(paragraph) > MAX_BODY_CHARS:
            break
        kept.append(paragraph)
        length += len(paragraph) + 2
    return "\n\n".join(kept) or None


def split_paragraphs(body: str | None) -> list[str]:
    return [p.strip() for p in (body or "").split("\n\n") if p.strip()]


_IMPORTANCE_RULES: list[tuple[re.Pattern, int]] = [
    # Direct combat / casualties — strongest signal
    (re.compile(r'\b(strikes?|attacked?|offensive|invaded?|besieged?|bombardment|combat|assault|kill(?:ed|ing)?|casualties|destroyed?|downed?|shot down)\b', re.I), 25),
    # Nuclear / strategic
    (re.compile(r'\b(nuclear|thermonuclear|icbm|tactical nuke|dirty bomb|warhead|silo)\b', re.I), 22),
    # Ballistic / hypersonic missiles
    (re.compile(r'\b(ballistic|hypersonic|cruise missile|anti-ship missile|surface-to-air)\b', re.I), 18),
    # Diplomatic milestones
    (re.compile(r'\b(ceasefire|armistice|peace deal|treaty signed?|accord)\b', re.I), 18),
    # Major naval platforms
    (re.compile(r'\b(aircraft carrier|carrier strike group|nuclear submarine|ballistic missile submarine|destroyer)\b', re.I), 15),
    # Missiles (general)
    (re.compile(r'\b(missiles?|rocket barrage|rocket attack)\b', re.I), 12),
    # Sanctions / strategic pressure
    (re.compile(r'\b(sanctions?|embargo|export controls?|arms embargo|blacklist(?:ed)?)\b', re.I), 12),
    # Drone strikes (operationally specific)
    (re.compile(r'\b(drone strike|drone attack|uav strike|kamikaze drone|fpv drone)\b', re.I), 14),
    # Generic drone / unmanned
    (re.compile(r'\b(drones?|uavs?|unmanned aerial)\b', re.I), 7),
    # High-value financial signal
    (re.compile(r'\b(billion|trillion)\b', re.I), 8),
    # Geopolitical tension
    (re.compile(r'\b(ultimatum|escalation|brink|standoff|flashpoint)\b', re.I), 10),
    # Deployments / exercises (lower signal)
    (re.compile(r'\b(deployed?|deployment|exercises?|war games?|joint training|drills?)\b', re.I), 5),
    # Procurement / contracts (lowest signal)
    (re.compile(r'\b(contract(?:ed)?|procurement|acquisition|awarded|ordered)\b', re.I), 3),
]

_IMPORTANCE_BASE = 15


def score_importance(title: str, summary: str | None) -> int:
    """Return 0–100 importance score using weighted keyword rules; no external calls."""
    headline = title.lower()
    body = (summary or "").lower()
    score = _IMPORTANCE_BASE
    for pattern, points in _IMPORTANCE_RULES:
        # Headline hits count 2× — the headline is the most signal-dense text.
        score += len(pattern.findall(headline)) * points * 2
        score += len(pattern.findall(body)) * points
    return min(score, 100)


def clean_author(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    # RSS <author> is often "email@example.com (Name)".
    match = re.match(r"^\S+@\S+\s*\((.+)\)$", text)
    if match:
        text = match.group(1).strip()
    if "@" in text and " " not in text:
        return None
    return text[:255] or None
